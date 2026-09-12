"""Run application service — lifecycle management via the repository transaction boundary."""

import hashlib
import json
import uuid
from datetime import datetime, timezone
from typing import Any, Optional

from sqlalchemy.ext.asyncio import AsyncSession

from aos.contracts.enums import EventType, RunStatus
from aos.contracts.event import RepairAttemptPayload
from aos.contracts.run import Run
from aos.contracts.transitions import (
    transition_run_cancel,
    transition_run_dispatch_repair,
    transition_run_enter_repair,
    transition_run_escalate,
    transition_run_fail,
    transition_run_pass,
    transition_run_start,
)
from aos.db.models import EventRow, RunRow
from aos.workflow.checkpoints import WorkflowCheckpoint
from aos.workflow.idempotency import IdempotencyConflictError, IdempotencyStore
from aos.workflow.lease import LeaseManager, StaleControllerFencingError
from aos.workflow.metadata import CheckpointMetadata
from aos.workflow.repository import RunRepository


def _compute_request_hash(body: Any) -> str:
    """Compute a SHA-256 hash of the canonicalised request body."""
    canonical = json.dumps(body, sort_keys=True, separators=(",", ":"), default=str)
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


class RunService:
    """Manages Run lifecycle.

    All state mutations go through RunRepository.apply_transition() which
    enforces fencing, Phase 0 transitions, checkpoint DAG, and atomic
    event append in a single ACID transaction.
    """

    def __init__(
        self,
        session: AsyncSession,
        controller_id: Optional[str] = None,
    ) -> None:
        self._session = session
        self._repo = RunRepository(session, controller_id=controller_id or _default_controller())
        self._lease_mgr = LeaseManager(session, controller_id=controller_id or _default_controller())
        self._idempotency = IdempotencyStore(session)

    # ------------------------------------------------------------------
    # Read
    # ------------------------------------------------------------------

    async def get(self, run_id: str) -> RunRow:
        return await self._repo.get(run_id)

    async def acquire_lease(self, run_id: str) -> int:
        """Acquire the lease for this Run and return the new fencing token.

        Part of the restart-recovery path: after a controller process dies, the
        replacement controller acquires the lease (vacant or expired) and gets a
        fresh fencing token, then resumes the Run through the HTTP API. The old
        controller's token is invalidated by the fencing-token increment.

        The UPDATE is committed here because this service method IS the HTTP
        command boundary (get_db does not auto-commit).
        """
        token = await self._lease_mgr.acquire(run_id)
        await self._session.commit()
        return token

    async def list_by_task(self, task_id: str) -> list[RunRow]:
        return await self._repo.list_by_task(task_id)

    async def list_events(self, run_id: str) -> list[EventRow]:
        return await self._repo.list_events(run_id)

    # ------------------------------------------------------------------
    # Create
    # ------------------------------------------------------------------

    async def create(
        self,
        task_id: str,
        workflow_version: str = "1.0.0",
        worker_id: Optional[str] = None,
        model_route: Optional[str] = None,
    ) -> RunRow:
        """Create a new Run in QUEUED / CP_INITIALIZED state."""
        run = Run(
            id=str(uuid.uuid4()),
            task_id=task_id,
            workflow_version=workflow_version,
            worker_id=worker_id,
            model_route=model_route,
            status=RunStatus.QUEUED,
            started_at=datetime.now(timezone.utc),
            updated_at=datetime.now(timezone.utc),
        )
        row = await self._repo.create(run)
        await self._session.commit()
        return row

    # ------------------------------------------------------------------
    # Transitions (require lease acquisition first)
    # ------------------------------------------------------------------

    async def start(
        self,
        run_id: str,
        worker_id: Optional[str] = None,
        idempotency_key: Optional[str] = None,
    ) -> RunRow:
        """Transition QUEUED → RUNNING, acquiring a lease.

        If idempotency_key is provided, the operation is idempotent:
        - Same key + same request hash → returns cached response
        - Same key + different request hash → raises IdempotencyConflictError
        """
        request_hash = _compute_request_hash({"worker_id": worker_id})

        if idempotency_key:
            # Check for cached response
            cached = await self._idempotency.get_cached(
                "run_start", idempotency_key, request_hash
            )
            if cached is not None:
                # Return the run from the cached response
                return await self.get(run_id)

            # Lock the key
            await self._idempotency.lock("run_start", idempotency_key, request_hash)

        try:
            token = await self._lease_mgr.acquire(run_id)
            await self._session.flush()
            row = await self._repo.apply_transition(
                run_id=run_id,
                held_token=token,
                transition_fn=lambda r: transition_run_start(r, worker_id=worker_id),
                target_checkpoint=WorkflowCheckpoint.CP_STARTED,
                checkpoint_metadata=CheckpointMetadata(step_name="start"),
                event_type=EventType.RUN_STATE_CHANGED,
                actor="controller",
            )
            # Record the idempotent completion in the SAME transaction as the
            # run transition so a replay after a crash cannot re-execute start.
            if idempotency_key:
                await self._idempotency.complete(
                    "run_start", idempotency_key, 200, {"run_id": row.id, "status": row.status}
                )
            await self._session.commit()
            return row
        except Exception:
            if idempotency_key:
                # Release the lock on failure
                await self._session.rollback()
            raise

    async def prepare_step(self, run_id: str, held_token: int) -> RunRow:
        """Advance checkpoint CP_STARTED → CP_STEP_PREPARED (status stays RUNNING)."""
        row = await self._repo.advance_checkpoint(
            run_id=run_id,
            held_token=held_token,
            target_checkpoint=WorkflowCheckpoint.CP_STEP_PREPARED,
            event_type=EventType.AGENT_STARTED,
            actor="controller",
            checkpoint_metadata=CheckpointMetadata(step_name="step_prepared"),
        )
        await self._session.commit()
        return row

    async def commit_step(self, run_id: str, held_token: int) -> RunRow:
        """Advance checkpoint CP_STEP_PREPARED → CP_STEP_COMMITTED (status stays RUNNING)."""
        row = await self._repo.advance_checkpoint(
            run_id=run_id,
            held_token=held_token,
            target_checkpoint=WorkflowCheckpoint.CP_STEP_COMMITTED,
            event_type=EventType.TOOL_COMPLETED,
            actor="controller",
            checkpoint_metadata=CheckpointMetadata(step_name="step_committed"),
        )
        await self._session.commit()
        return row

    async def dispatch_repair(
        self,
        run_id: str,
        held_token: int,
        payload: RepairAttemptPayload,
    ) -> RunRow:
        """Transition REPAIRING → RUNNING via repair dispatch. Increments repair_attempt_count.

        checkpoint_metadata is a callable resolved against the post-transition
        Run so the durable attempt_number matches the updated repair_attempt_count
        (1 for the first dispatch, 2 for the second, ...).
        """
        row = await self._repo.apply_transition(
            run_id=run_id,
            held_token=held_token,
            transition_fn=lambda r: transition_run_dispatch_repair(r, payload=payload),
            target_checkpoint=WorkflowCheckpoint.CP_REPAIR_DISPATCHED,
            checkpoint_metadata=lambda r: CheckpointMetadata(
                step_name="repair_dispatched",
                attempt_number=r.repair_attempt_count,
            ),
            event_type=EventType.REPAIR_ATTEMPT,
            actor="controller",
        )
        await self._session.commit()
        return row

    async def mark_passed(self, run_id: str, held_token: int) -> RunRow:
        """Transition RUNNING → PASSED."""
        row = await self._repo.apply_transition(
            run_id=run_id,
            held_token=held_token,
            transition_fn=transition_run_pass,
            target_checkpoint=WorkflowCheckpoint.CP_COMPLETED,
            checkpoint_metadata=CheckpointMetadata(step_name="passed"),
            event_type=EventType.RUN_COMPLETED,
            actor="controller",
        )
        await self._lease_mgr.release(run_id, held_token)
        await self._session.commit()
        return row

    async def mark_failed(
        self, run_id: str, held_token: int, reason: Optional[str] = None
    ) -> RunRow:
        """Transition RUNNING → FAILED."""
        row = await self._repo.apply_transition(
            run_id=run_id,
            held_token=held_token,
            transition_fn=lambda r: transition_run_fail(r, reason=reason),
            target_checkpoint=WorkflowCheckpoint.CP_FAILED,
            checkpoint_metadata=CheckpointMetadata(step_name="failed"),
            event_type=EventType.RUN_FAILED,
            actor="controller",
        )
        await self._session.commit()
        return row

    async def enter_repair(self, run_id: str, held_token: int) -> RunRow:
        """Transition FAILED → REPAIRING. Does NOT consume a repair attempt."""
        row = await self._repo.apply_transition(
            run_id=run_id,
            held_token=held_token,
            transition_fn=transition_run_enter_repair,
            target_checkpoint=WorkflowCheckpoint.CP_REPAIR_DIAGNOSED,
            checkpoint_metadata=CheckpointMetadata(step_name="repair_diagnosis"),
            event_type=EventType.RUN_STATE_CHANGED,
            actor="controller",
        )
        await self._session.commit()
        return row

    async def escalate(self, run_id: str, held_token: int, reason: str) -> RunRow:
        """Transition REPAIRING → ESCALATED."""
        row = await self._repo.apply_transition(
            run_id=run_id,
            held_token=held_token,
            transition_fn=lambda r: transition_run_escalate(r, reason),
            target_checkpoint=WorkflowCheckpoint.CP_ESCALATED,
            checkpoint_metadata=CheckpointMetadata(step_name="escalated"),
            event_type=EventType.RUN_STATE_CHANGED,
            actor="controller",
        )
        await self._lease_mgr.release(run_id, held_token)
        await self._session.commit()
        return row

    async def cancel(
        self, run_id: str, reason: str, held_token: Optional[int] = None
    ) -> RunRow:
        """Cancel a Run from any non-terminal state.

        If ``held_token`` is supplied, the caller is the current lease holder
        (e.g. the controller that started the Run) and that lease is used for the
        fenced transition, then released. If no token is supplied, a fresh lease
        is acquired (operator-initiated cancel on a vacant/expired slot).

        Invariant: every terminal Run has no active lease. The lease is
        released in the same transaction, before commit, so the committed
        row has lease_owner IS NULL / lease_expiry IS NULL.
        """
        if held_token is None:
            token = await self._lease_mgr.acquire(run_id)
            await self._session.flush()
        else:
            token = held_token
        row = await self._repo.apply_transition(
            run_id=run_id,
            held_token=token,
            transition_fn=lambda r: transition_run_cancel(r, reason),
            target_checkpoint=WorkflowCheckpoint.CP_CANCELLED,
            checkpoint_metadata=CheckpointMetadata(step_name="cancelled"),
            event_type=EventType.RUN_STATE_CHANGED,
            actor="controller",
        )
        await self._lease_mgr.release(run_id, token)
        await self._session.commit()
        await self._session.refresh(row)
        return row


def _default_controller() -> str:
    import os
    return os.environ.get("AOS_CONTROLLER_ID", "default-controller")
