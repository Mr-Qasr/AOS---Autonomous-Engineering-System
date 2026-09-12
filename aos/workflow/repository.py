"""Run repository — enforces the mandatory transaction boundary.

Every authoritative mutation of a Run must go through
``RunRepository.apply_transition()``.  The transaction boundary is:

    1.  BEGIN TRANSACTION
    2.  SELECT * FROM runs WHERE id = :run_id FOR UPDATE
    3.  VERIFY: lease_owner == controller_id
                AND fencing_token == held_token
                AND lease_expiry >= NOW()
        → if any fails: ROLLBACK, raise StaleControllerFencingError
    4.  INVOKE Phase 0 transition function → TransitionResult
    5.  VALIDATE checkpoint DAG transition
    6.  next_seq  = run.current_event_sequence + 1
    7.  next_cp_seq = run.checkpoint_seq + 1
    8.  UPDATE runs SET status, checkpoint, checkpoint_seq,
                        current_event_sequence, checkpoint_metadata, updated_at
        WHERE id = :run_id AND fencing_token = :held_token   ← second fencing guard
        → if rows_affected == 0: ROLLBACK, raise StaleControllerFencingError
    9.  INSERT INTO events (sequence = next_seq, ...)
    10. COMMIT

No code outside this module may issue a raw ``UPDATE runs SET status = …``.
"""

import os
import uuid
import json
from datetime import datetime, timezone
from typing import Any, Callable, Optional

from sqlalchemy import select, text, update
from sqlalchemy.ext.asyncio import AsyncSession

from aos.contracts.enums import EventType
from aos.contracts.run import Run
from aos.contracts.transitions import TransitionResult
from aos.db.models import EventRow, RunRow
from aos.workflow.checkpoints import (
    WorkflowCheckpoint,
    validate_checkpoint_transition,
)
from aos.workflow.lease import StaleControllerFencingError
from aos.workflow.metadata import CheckpointMetadata

_CONTROLLER_ID: str = os.environ.get("AOS_CONTROLLER_ID", "default-controller")


class RunNotFoundError(Exception):
    """Raised when a Run does not exist in the database."""


class RunRepository:
    """Provides the authoritative RunRow ↔ Run domain object bridge.

    All state mutations go through ``apply_transition()``.
    Read operations (``get``, ``list``) are plain SELECTs with no locking.
    """

    def __init__(
        self,
        session: AsyncSession,
        controller_id: str = _CONTROLLER_ID,
    ) -> None:
        self._session = session
        self._controller_id = controller_id

    # ------------------------------------------------------------------
    # Read operations
    # ------------------------------------------------------------------

    async def get(self, run_id: str) -> RunRow:
        """Fetch a RunRow by ID (no lock).

        Raises:
            RunNotFoundError: if the run does not exist.
        """
        result = await self._session.execute(
            select(RunRow).where(RunRow.id == run_id)
        )
        row = result.scalar_one_or_none()
        if row is None:
            raise RunNotFoundError(f"Run {run_id!r} not found.")
        return row

    async def list_by_task(self, task_id: str) -> list[RunRow]:
        """Return all RunRows for a given task_id, ordered by started_at desc."""
        result = await self._session.execute(
            select(RunRow)
            .where(RunRow.task_id == task_id)
            .order_by(RunRow.started_at.desc())
        )
        return list(result.scalars().all())

    async def list_events(self, run_id: str) -> list[EventRow]:
        """Return all EventRows for a run ordered by sequence ascending."""
        result = await self._session.execute(
            select(EventRow)
            .where(EventRow.run_id == run_id)
            .order_by(EventRow.sequence.asc())
        )
        return list(result.scalars().all())

    # ------------------------------------------------------------------
    # Write operations — always through apply_transition
    # ------------------------------------------------------------------

    async def create(self, run: Run) -> RunRow:
        """Persist a new Run (QUEUED) with CP_INITIALIZED checkpoint.

        This is the only path that inserts a RunRow; it does not go through
        apply_transition() because no Phase 0 transition function is invoked
        (the run is already in its initial state).
        """
        row = RunRow(
            id=run.id,
            task_id=run.task_id,
            workflow_version=run.workflow_version,
            worker_id=run.worker_id,
            model_route=run.model_route,
            status=str(run.status),
            repair_attempt_count=run.repair_attempt_count,
            max_repair_attempts=run.max_repair_attempts,
            checkpoint=str(WorkflowCheckpoint.CP_INITIALIZED),
            checkpoint_seq=0,
            checkpoint_metadata={},
            current_event_sequence=0,
            lease_owner=None,
            lease_expiry=None,
            fencing_token=0,
            started_at=run.started_at,
            updated_at=run.updated_at,
        )
        self._session.add(row)
        await self._session.flush()
        return row

    async def apply_transition(
        self,
        run_id: str,
        held_token: int,
        transition_fn: Callable[[Run], TransitionResult],
        target_checkpoint: WorkflowCheckpoint,
        checkpoint_metadata: "CheckpointMetadata | Callable[[Run], CheckpointMetadata]",
        event_type: EventType,
        actor: str,
    ) -> RunRow:
        """Execute the mandatory transaction boundary for a single Run mutation.

        Steps:
          1. SELECT … FOR UPDATE (row-level exclusive lock)
          2. Verify fencing (controller, token, expiry)
          3. Invoke Phase 0 transition_fn → TransitionResult
          4. Validate checkpoint DAG
          5. Allocate next event sequence under lock
          6. UPDATE runs (with fencing WHERE condition)
          7. INSERT event
          8. COMMIT (caller's session.commit())

        Args:
            run_id:              The Run to mutate.
            held_token:          The fencing token this controller holds.
            transition_fn:       A Phase 0 transition function (takes Run → TransitionResult).
            target_checkpoint:   Target WorkflowCheckpoint after this transition.
            checkpoint_metadata: Typed metadata to persist alongside the checkpoint.
            event_type:          EventType for the generated event row.
            actor:               Actor string recorded on the event.

        Returns:
            The updated RunRow after the committed transaction.

        Raises:
            RunNotFoundError:            Run does not exist.
            StaleControllerFencingError: Fencing verification failed.
            InvalidStateTransitionError: Phase 0 transition rejected.
            InvalidCheckpointTransitionError: Checkpoint DAG violated.
        """
        # ----------------------------------------------------------------
        # Step 2: Lock row
        # ----------------------------------------------------------------
        result = await self._session.execute(
            text(
                "SELECT id, task_id, workflow_version, worker_id, model_route, "
                "status, repair_attempt_count, max_repair_attempts, "
                "checkpoint, checkpoint_seq, checkpoint_metadata, "
                "current_event_sequence, lease_owner, lease_expiry, "
                "fencing_token, started_at, updated_at "
                "FROM runs WHERE id = :run_id FOR UPDATE"
            ),
            {"run_id": run_id},
        )
        row_data = result.fetchone()
        if row_data is None:
            raise RunNotFoundError(f"Run {run_id!r} not found.")

        # ----------------------------------------------------------------
        # Step 3: Verify fencing
        # ----------------------------------------------------------------
        (
            _id, task_id, workflow_version, worker_id, model_route,
            db_status, repair_attempt_count, max_repair_attempts,
            db_checkpoint, checkpoint_seq, db_checkpoint_metadata,
            current_event_sequence, lease_owner, lease_expiry,
            db_fencing_token, started_at, updated_at,
        ) = row_data

        now = datetime.now(timezone.utc)
        fencing_ok = (
            lease_owner == self._controller_id
            and db_fencing_token == held_token
            and lease_expiry is not None
            and lease_expiry >= now
        )
        if not fencing_ok:
            raise StaleControllerFencingError(
                f"Fencing check failed for run {run_id!r}. "
                f"Controller: {self._controller_id!r}, held_token: {held_token}, "
                f"db_token: {db_fencing_token}, lease_owner: {lease_owner!r}, "
                f"lease_expiry: {lease_expiry}."
            )

        # ----------------------------------------------------------------
        # Step 4: Reconstruct Run domain object and invoke Phase 0 transition
        # ----------------------------------------------------------------
        from aos.contracts.enums import RunStatus
        from aos.contracts.run import Run

        domain_run = Run(
            id=_id,
            task_id=task_id,
            workflow_version=workflow_version,
            worker_id=worker_id,
            model_route=model_route,
            status=RunStatus(db_status),
            repair_attempt_count=repair_attempt_count,
            max_repair_attempts=max_repair_attempts,
            started_at=started_at,
            updated_at=updated_at,
        )
        transition_result: TransitionResult = transition_fn(domain_run)
        updated_run: Run = transition_result.entity

        # Resolve checkpoint metadata. A callable receives the post-transition
        # domain Run so durable metadata can reflect the true new state
        # (e.g. repair attempt ordinal == updated repair_attempt_count).
        if callable(checkpoint_metadata):
            resolved_metadata = checkpoint_metadata(updated_run)
        else:
            resolved_metadata = checkpoint_metadata

        # ----------------------------------------------------------------
        # Step 5: Validate checkpoint DAG transition
        # ----------------------------------------------------------------
        current_cp = WorkflowCheckpoint(db_checkpoint)
        validate_checkpoint_transition(current_cp, target_checkpoint)

        # ----------------------------------------------------------------
        # Steps 6-7: Allocate sequence numbers
        # ----------------------------------------------------------------
        next_seq = current_event_sequence + 1
        next_cp_seq = checkpoint_seq + 1

        # ----------------------------------------------------------------
        # Step 8: UPDATE runs with mandatory fencing WHERE condition
        # ----------------------------------------------------------------
        update_result = await self._session.execute(
            text(
                """
                UPDATE runs
                SET
                    status               = :status,
                    repair_attempt_count = :repair_attempt_count,
                    checkpoint           = :checkpoint,
                    checkpoint_seq       = :checkpoint_seq,
                    checkpoint_metadata  = :checkpoint_metadata,
                    current_event_sequence = :current_event_sequence,
                    worker_id            = :worker_id,
                    updated_at           = NOW()
                WHERE
                    id            = :run_id
                    AND fencing_token = :held_token
                RETURNING id
                """
            ),
            {
                "status": str(updated_run.status),
                "repair_attempt_count": updated_run.repair_attempt_count,
                "checkpoint": str(target_checkpoint),
                "checkpoint_seq": next_cp_seq,
                "checkpoint_metadata": json.dumps(resolved_metadata.model_dump()),
                "current_event_sequence": next_seq,
                "worker_id": updated_run.worker_id,
                "run_id": run_id,
                "held_token": held_token,
            },
        )
        if update_result.fetchone() is None:
            raise StaleControllerFencingError(
                f"Concurrent fencing violation: UPDATE rows_affected=0 for run {run_id!r}."
            )

        # ----------------------------------------------------------------
        # Step 9: Append event
        # ----------------------------------------------------------------
        payload = _serialize_payload(transition_result.event_payload)
        event_row = EventRow(
            id=str(uuid.uuid4()),
            run_id=run_id,
            sequence=next_seq,
            type=str(event_type),
            timestamp=datetime.now(timezone.utc),
            actor=actor,
            payload=payload,
        )
        self._session.add(event_row)

                # Step 10: COMMIT is the caller's responsibility (session.commit())
        # Flush to detect constraint violations before commit.
        await self._session.flush()

        # Re-fetch the RunRow with populate_existing=True to bypass the
        # identity-map cache. The text() UPDATE above bypassed SQLAlchemy's
        # unit-of-work, so a cached RunRow would have stale field values.
        _stmt = (
            select(RunRow)
            .where(RunRow.id == run_id)
            .execution_options(populate_existing=True)
        )
        _result = await self._session.execute(_stmt)
        return _result.scalar_one()

    # ------------------------------------------------------------------
    # Checkpoint-only advancement (no Phase 0 status change)
    # ------------------------------------------------------------------

    async def advance_checkpoint(
        self,
        run_id: str,
        held_token: int,
        target_checkpoint: "WorkflowCheckpoint",
        event_type: EventType,
        actor: str,
        checkpoint_metadata: "CheckpointMetadata",
        event_payload: Any = None,
    ) -> RunRow:
        """Advance the workflow checkpoint without changing RunStatus.

        This follows the same authoritative mutation boundary as apply_transition:
        SELECT FOR UPDATE → fencing verification → checkpoint DAG validation →
        event sequence allocation → atomic state/event commit.

        Used for CP_STARTED → CP_STEP_PREPARED and CP_STEP_PREPARED → CP_STEP_COMMITTED
        transitions where the RunStatus stays RUNNING but the checkpoint advances.
        """
        now = datetime.now(timezone.utc)

        # Step 1: SELECT FOR UPDATE
        result = await self._session.execute(
            text(
                """
                SELECT id, status, repair_attempt_count, checkpoint, checkpoint_seq,
                       checkpoint_metadata, current_event_sequence, lease_owner,
                       lease_expiry, fencing_token
                FROM runs WHERE id = :run_id FOR UPDATE
                """
            ),
            {"run_id": run_id},
        )
        row = result.fetchone()
        if row is None:
            raise RunNotFoundError(f"Run {run_id!r} not found.")

        (
            db_id,
            db_status,
            db_repair_count,
            db_checkpoint,
            db_checkpoint_seq,
            db_checkpoint_metadata,
            db_event_seq,
            lease_owner,
            lease_expiry,
            db_fencing_token,
        ) = row

        # Step 2: Verify fencing
        fencing_ok = (
            lease_owner == self._controller_id
            and db_fencing_token == held_token
            and lease_expiry is not None
            and lease_expiry >= now
        )
        if not fencing_ok:
            raise StaleControllerFencingError(
                f"Stale controller or invalid lease for run {run_id!r}."
            )

        # Step 3: No Phase 0 transition (status unchanged)
        current_event_sequence = db_event_seq
        checkpoint_seq = db_checkpoint_seq

        # Step 4: Validate checkpoint DAG transition
        current_cp = WorkflowCheckpoint(db_checkpoint)
        validate_checkpoint_transition(current_cp, target_checkpoint)

        # Step 5: Allocate sequence numbers
        next_seq = current_event_sequence + 1
        next_cp_seq = checkpoint_seq + 1

        # Step 6: UPDATE runs with mandatory fencing WHERE condition
        update_result = await self._session.execute(
            text(
                """
                UPDATE runs
                SET
                    checkpoint           = :checkpoint,
                    checkpoint_seq       = :checkpoint_seq,
                    checkpoint_metadata  = :checkpoint_metadata,
                    current_event_sequence = :current_event_sequence,
                    updated_at           = NOW()
                WHERE
                    id            = :run_id
                    AND fencing_token = :held_token
                RETURNING id
                """
            ),
            {
                "checkpoint": str(target_checkpoint),
                "checkpoint_seq": next_cp_seq,
                "checkpoint_metadata": json.dumps(checkpoint_metadata.model_dump()),
                "current_event_sequence": next_seq,
                "run_id": run_id,
                "held_token": held_token,
            },
        )
        if update_result.fetchone() is None:
            raise StaleControllerFencingError(
                f"Concurrent fencing violation: UPDATE rows_affected=0 for run {run_id!r}."
            )

        # Step 7: Append event
        payload = _serialize_payload(event_payload) if event_payload else {}
        event_row = EventRow(
            id=str(uuid.uuid4()),
            run_id=run_id,
            sequence=next_seq,
            type=str(event_type),
            timestamp=datetime.now(timezone.utc),
            actor=actor,
            payload=payload,
        )
        self._session.add(event_row)

                # Step 8: Flush (commit is caller's responsibility)
        await self._session.flush()

        # Re-fetch with populate_existing=True to bypass identity-map cache.
        _stmt = (
            select(RunRow)
            .where(RunRow.id == run_id)
            .execution_options(populate_existing=True)
        )
        _result = await self._session.execute(_stmt)
        return _result.scalar_one()


def _serialize_payload(payload: Any) -> dict:
    """Convert a Pydantic model or dict to a JSON-serialisable dict."""
    if hasattr(payload, "model_dump"):
        return payload.model_dump(mode="json")
    if isinstance(payload, dict):
        return payload
    return {"value": str(payload)}
