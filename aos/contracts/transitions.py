"""Pure functional state transition engine for Task and Run lifecycles."""

from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Generic, Optional, TypeVar

from aos.contracts.enums import RunStatus, TaskStatus
from aos.contracts.event import (
    RepairAttemptPayload,
    RunStateChangedPayload,
    TaskStateChangedPayload,
)
from aos.contracts.run import Run
from aos.contracts.task import Task

EntityT = TypeVar("EntityT")
EventPayloadT = TypeVar("EventPayloadT")


def _utc_now() -> datetime:
    return datetime.now(timezone.utc)


class InvalidStateTransitionError(Exception):
    """Raised when an illegal or invalid state transition is attempted."""


@dataclass(frozen=True)
class TransitionResult(Generic[EntityT, EventPayloadT]):
    """Result of a domain transition: updated immutable entity + typed event payload representation."""

    entity: EntityT
    event_payload: EventPayloadT


# ============================================================================
# Task State Machine Transitions
# ============================================================================

TASK_TERMINAL_STATES = {TaskStatus.RELEASED, TaskStatus.ABANDONED}


def transition_task_lock(task: Task) -> TransitionResult[Task, TaskStateChangedPayload]:
    """Transition Task from DRAFT to LOCKED."""
    if task.status != TaskStatus.DRAFT:
        raise InvalidStateTransitionError(
            f"Cannot lock Task with status '{task.status}'. Task must be in 'DRAFT'."
        )
    if not task.acceptance_criteria:
        raise InvalidStateTransitionError(
            "Cannot lock Task without acceptance criteria."
        )
    if task.requirement_version < 1:
        raise InvalidStateTransitionError(
            "Cannot lock Task with requirement_version < 1."
        )

    now = _utc_now()
    updated = task.model_copy(
        update={"status": TaskStatus.LOCKED, "updated_at": now}
    )
    payload = TaskStateChangedPayload(
        previous_status=task.status,
        new_status=TaskStatus.LOCKED,
        details={"reason": "Task requirements locked"},
    )
    return TransitionResult(entity=updated, event_payload=payload)


def transition_task_start(task: Task) -> TransitionResult[Task, TaskStateChangedPayload]:
    """Transition Task from LOCKED to IN_PROGRESS."""
    if task.status != TaskStatus.LOCKED:
        raise InvalidStateTransitionError(
            f"Cannot start Task with status '{task.status}'. Task must be 'LOCKED'."
        )

    now = _utc_now()
    updated = task.model_copy(
        update={"status": TaskStatus.IN_PROGRESS, "updated_at": now}
    )
    payload = TaskStateChangedPayload(
        previous_status=task.status,
        new_status=TaskStatus.IN_PROGRESS,
        details={"reason": "Engineering execution started"},
    )
    return TransitionResult(entity=updated, event_payload=payload)


def transition_task_block(
    task: Task, reason: str
) -> TransitionResult[Task, TaskStateChangedPayload]:
    """Transition Task from IN_PROGRESS to BLOCKED."""
    if task.status != TaskStatus.IN_PROGRESS:
        raise InvalidStateTransitionError(
            f"Cannot block Task with status '{task.status}'. Task must be 'IN_PROGRESS'."
        )
    if not reason or not reason.strip():
        raise InvalidStateTransitionError("A reason must be provided to block a Task.")

    now = _utc_now()
    updated = task.model_copy(
        update={"status": TaskStatus.BLOCKED, "updated_at": now}
    )
    payload = TaskStateChangedPayload(
        previous_status=task.status,
        new_status=TaskStatus.BLOCKED,
        details={"reason": reason.strip()},
    )
    return TransitionResult(entity=updated, event_payload=payload)


def transition_task_unblock(
    task: Task,
) -> TransitionResult[Task, TaskStateChangedPayload]:
    """Transition Task from BLOCKED to IN_PROGRESS."""
    if task.status != TaskStatus.BLOCKED:
        raise InvalidStateTransitionError(
            f"Cannot unblock Task with status '{task.status}'. Task must be 'BLOCKED'."
        )

    now = _utc_now()
    updated = task.model_copy(
        update={"status": TaskStatus.IN_PROGRESS, "updated_at": now}
    )
    payload = TaskStateChangedPayload(
        previous_status=task.status,
        new_status=TaskStatus.IN_PROGRESS,
        details={"reason": "Task unblocked; resuming work"},
    )
    return TransitionResult(entity=updated, event_payload=payload)


def transition_task_mark_ready(
    task: Task,
) -> TransitionResult[Task, TaskStateChangedPayload]:
    """Transition Task from IN_PROGRESS to READY."""
    if task.status != TaskStatus.IN_PROGRESS:
        raise InvalidStateTransitionError(
            f"Cannot mark Task as READY from status '{task.status}'. Must be 'IN_PROGRESS'."
        )

    now = _utc_now()
    updated = task.model_copy(
        update={"status": TaskStatus.READY, "updated_at": now}
    )
    payload = TaskStateChangedPayload(
        previous_status=task.status,
        new_status=TaskStatus.READY,
        details={"reason": "All required checks passed; awaiting release approval"},
    )
    return TransitionResult(entity=updated, event_payload=payload)


def transition_task_release(
    task: Task, approval_id: str
) -> TransitionResult[Task, TaskStateChangedPayload]:
    """Transition Task from READY to RELEASED.

    BOUNDARY INVARIANT:
    Phase 0 strictly requires a non-empty `approval_id` string and carries this reference
    as part of the domain contract. Phase 0 does NOT validate approval existence, cryptographic
    signatures, expiry, authorization, or policy evaluation. Those enforcement checks remain
    strictly deferred to Phase 12 (Release Gates).
    """
    if task.status != TaskStatus.READY:
        raise InvalidStateTransitionError(
            f"Cannot release Task with status '{task.status}'. Task must be 'READY'."
        )
    if not approval_id or not approval_id.strip():
        raise InvalidStateTransitionError(
            "approval_id must be a non-empty string to release a Task."
        )

    now = _utc_now()
    updated = task.model_copy(
        update={
            "status": TaskStatus.RELEASED,
            "release_approval_id": approval_id.strip(),
            "updated_at": now,
        }
    )
    payload = TaskStateChangedPayload(
        previous_status=task.status,
        new_status=TaskStatus.RELEASED,
        details={"approval_id": approval_id.strip()},
    )
    return TransitionResult(entity=updated, event_payload=payload)


def transition_task_abandon(
    task: Task, reason: str
) -> TransitionResult[Task, TaskStateChangedPayload]:
    """Transition Task from any non-terminal state to ABANDONED."""
    if task.status in TASK_TERMINAL_STATES:
        raise InvalidStateTransitionError(
            f"Cannot abandon Task with terminal status '{task.status}'."
        )
    if not reason or not reason.strip():
        raise InvalidStateTransitionError("A reason must be provided to abandon a Task.")

    now = _utc_now()
    updated = task.model_copy(
        update={"status": TaskStatus.ABANDONED, "updated_at": now}
    )
    payload = TaskStateChangedPayload(
        previous_status=task.status,
        new_status=TaskStatus.ABANDONED,
        details={"reason": reason.strip()},
    )
    return TransitionResult(entity=updated, event_payload=payload)


# ============================================================================
# Run State Machine Transitions
# ============================================================================

RUN_TERMINAL_STATES = {RunStatus.PASSED, RunStatus.CANCELLED, RunStatus.ESCALATED}


def transition_run_start(
    run: Run, worker_id: Optional[str] = None
) -> TransitionResult[Run, RunStateChangedPayload]:
    """Transition Run from QUEUED to RUNNING."""
    if run.status != RunStatus.QUEUED:
        raise InvalidStateTransitionError(
            f"Cannot start Run with status '{run.status}'. Run must be 'QUEUED'."
        )

    now = _utc_now()
    updates = {"status": RunStatus.RUNNING, "updated_at": now}
    if worker_id is not None:
        updates["worker_id"] = worker_id.strip()

    updated = run.model_copy(update=updates)
    payload = RunStateChangedPayload(
        previous_status=run.status,
        new_status=RunStatus.RUNNING,
        repair_attempt_count=run.repair_attempt_count,
        details={"worker_id": updated.worker_id},
    )
    return TransitionResult(entity=updated, event_payload=payload)


def transition_run_pass(run: Run) -> TransitionResult[Run, RunStateChangedPayload]:
    """Transition Run from RUNNING to PASSED."""
    if run.status != RunStatus.RUNNING:
        raise InvalidStateTransitionError(
            f"Cannot pass Run with status '{run.status}'. Run must be 'RUNNING'."
        )

    now = _utc_now()
    updated = run.model_copy(
        update={"status": RunStatus.PASSED, "updated_at": now}
    )
    payload = RunStateChangedPayload(
        previous_status=run.status,
        new_status=RunStatus.PASSED,
        repair_attempt_count=run.repair_attempt_count,
        details={"reason": "Execution and verification passed"},
    )
    return TransitionResult(entity=updated, event_payload=payload)


def transition_run_fail(
    run: Run, reason: Optional[str] = None
) -> TransitionResult[Run, RunStateChangedPayload]:
    """Transition Run from RUNNING to FAILED."""
    if run.status != RunStatus.RUNNING:
        raise InvalidStateTransitionError(
            f"Cannot fail Run with status '{run.status}'. Run must be 'RUNNING'."
        )

    now = _utc_now()
    updated = run.model_copy(
        update={"status": RunStatus.FAILED, "updated_at": now}
    )
    payload = RunStateChangedPayload(
        previous_status=run.status,
        new_status=RunStatus.FAILED,
        repair_attempt_count=run.repair_attempt_count,
        details={"reason": reason or "Verification or execution failed"},
    )
    return TransitionResult(entity=updated, event_payload=payload)


def transition_run_enter_repair(
    run: Run,
) -> TransitionResult[Run, RunStateChangedPayload]:
    """Transition Run from FAILED to REPAIRING.

    REPAIR ATTEMPT ACCOUNTING INVARIANT:
    Entering repair mode indicates diagnosis and failure classification.
    It does NOT consume a repair attempt. `repair_attempt_count` remains UNCHANGED.
    """
    if run.status != RunStatus.FAILED:
        raise InvalidStateTransitionError(
            f"Cannot enter repair mode from status '{run.status}'. Run must be 'FAILED'."
        )

    now = _utc_now()
    updated = run.model_copy(
        update={"status": RunStatus.REPAIRING, "updated_at": now}
    )
    payload = RunStateChangedPayload(
        previous_status=run.status,
        new_status=RunStatus.REPAIRING,
        repair_attempt_count=run.repair_attempt_count,
        details={"reason": "Diagnosing failure and preparing repair"},
    )
    return TransitionResult(entity=updated, event_payload=payload)


def transition_run_dispatch_repair(
    run: Run, payload: RepairAttemptPayload
) -> TransitionResult[Run, RepairAttemptPayload]:
    """Commit and dispatch a repair attempt: transitions REPAIRING to RUNNING.

    REPAIR ATTEMPT ACCOUNTING INVARIANT:
    - This transition commits an actual repair attempt.
    - `repair_attempt_count` is incremented by exactly 1.
    - If `repair_attempt_count >= max_repair_attempts`, transition is blocked and raises InvalidStateTransitionError.
    - The returned `RepairAttemptPayload` representation must exist before downstream repair actions execute.
    - If the run subsequently fails, the incremented counter is NEVER decremented or reset.
    """
    if run.status != RunStatus.REPAIRING:
        raise InvalidStateTransitionError(
            f"Cannot dispatch repair attempt from status '{run.status}'. Run must be 'REPAIRING'."
        )
    if run.repair_attempt_count >= run.max_repair_attempts:
        raise InvalidStateTransitionError(
            f"Repair budget exhausted ({run.repair_attempt_count}/{run.max_repair_attempts}). "
            "Cannot dispatch repair. Run must be escalated."
        )

    now = _utc_now()
    new_count = run.repair_attempt_count + 1
    updated = run.model_copy(
        update={
            "status": RunStatus.RUNNING,
            "repair_attempt_count": new_count,
            "updated_at": now,
        }
    )
    return TransitionResult(entity=updated, event_payload=payload)


def transition_run_escalate(
    run: Run, reason: str
) -> TransitionResult[Run, RunStateChangedPayload]:
    """Transition Run from REPAIRING to ESCALATED when retry budget is exhausted or unrecoverable."""
    if run.status != RunStatus.REPAIRING:
        raise InvalidStateTransitionError(
            f"Cannot escalate Run with status '{run.status}'. Run must be 'REPAIRING'."
        )
    if not reason or not reason.strip():
        raise InvalidStateTransitionError("A reason must be provided to escalate a Run.")

    now = _utc_now()
    updated = run.model_copy(
        update={"status": RunStatus.ESCALATED, "updated_at": now}
    )
    payload = RunStateChangedPayload(
        previous_status=run.status,
        new_status=RunStatus.ESCALATED,
        repair_attempt_count=run.repair_attempt_count,
        details={"reason": reason.strip()},
    )
    return TransitionResult(entity=updated, event_payload=payload)


def transition_run_cancel(
    run: Run, reason: str
) -> TransitionResult[Run, RunStateChangedPayload]:
    """Transition Run to CANCELLED from any non-terminal state."""
    if run.status in RUN_TERMINAL_STATES:
        raise InvalidStateTransitionError(
            f"Cannot cancel Run with terminal status '{run.status}'."
        )
    if not reason or not reason.strip():
        raise InvalidStateTransitionError("A reason must be provided to cancel a Run.")

    now = _utc_now()
    updated = run.model_copy(
        update={"status": RunStatus.CANCELLED, "updated_at": now}
    )
    payload = RunStateChangedPayload(
        previous_status=run.status,
        new_status=RunStatus.CANCELLED,
        repair_attempt_count=run.repair_attempt_count,
        details={"reason": reason.strip()},
    )
    return TransitionResult(entity=updated, event_payload=payload)

