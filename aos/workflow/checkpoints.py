"""Workflow checkpoint DAG — constrained cursor for durable workflow execution.

Design invariants:
- ``WorkflowCheckpoint`` values are the only legal checkpoint states.
  ``RunStatus`` enum values from Phase 0 are NEVER used as checkpoints.
- Checkpoint transitions follow the frozen DAG below; no arbitrary
  assignment is permitted. Any illegal transition raises
  ``InvalidCheckpointTransitionError``.
- Every checkpoint transition increments ``checkpoint_seq`` by exactly 1,
  in the same ACID transaction as the domain mutation and event append.
- Completed checkpoints are never logically re-executed; recovery reads
  the last committed checkpoint and resumes at the next legal step.

Checkpoint DAG
--------------
CP_INITIALIZED
    └─► CP_STARTED
            └─► CP_STEP_PREPARED
                    └─► CP_STEP_COMMITTED
                            ├─► CP_COMPLETED  (terminal — run passed)
                            ├─► CP_FAILED
                            │       └─► CP_REPAIR_DIAGNOSED
                            │               ├─► CP_REPAIR_DISPATCHED
                            │               │       └─► CP_STEP_PREPARED  (repair loop)
                            │               └─► CP_ESCALATED  (terminal)
                            └─► CP_STEP_PREPARED  (next step loop)

Any non-terminal checkpoint → CP_CANCELLED  (terminal)
"""

from enum import StrEnum
from typing import FrozenSet


class WorkflowCheckpoint(StrEnum):
    """Legal checkpoint cursor values for a Run's workflow execution position."""

    CP_INITIALIZED = "CP_INITIALIZED"
    CP_STARTED = "CP_STARTED"
    CP_STEP_PREPARED = "CP_STEP_PREPARED"
    CP_STEP_COMMITTED = "CP_STEP_COMMITTED"
    CP_COMPLETED = "CP_COMPLETED"
    CP_FAILED = "CP_FAILED"
    CP_REPAIR_DIAGNOSED = "CP_REPAIR_DIAGNOSED"
    CP_REPAIR_DISPATCHED = "CP_REPAIR_DISPATCHED"
    CP_ESCALATED = "CP_ESCALATED"
    CP_CANCELLED = "CP_CANCELLED"


# Terminal checkpoints cannot be transitioned further.
TERMINAL_CHECKPOINTS: FrozenSet[WorkflowCheckpoint] = frozenset(
    {
        WorkflowCheckpoint.CP_COMPLETED,
        WorkflowCheckpoint.CP_ESCALATED,
        WorkflowCheckpoint.CP_CANCELLED,
    }
)

# Frozen DAG: maps each source checkpoint to the set of legal target checkpoints.
_CHECKPOINT_DAG: dict[WorkflowCheckpoint, FrozenSet[WorkflowCheckpoint]] = {
    WorkflowCheckpoint.CP_INITIALIZED: frozenset({WorkflowCheckpoint.CP_STARTED, WorkflowCheckpoint.CP_CANCELLED}),
    WorkflowCheckpoint.CP_STARTED: frozenset({WorkflowCheckpoint.CP_STEP_PREPARED, WorkflowCheckpoint.CP_CANCELLED}),
    WorkflowCheckpoint.CP_STEP_PREPARED: frozenset({WorkflowCheckpoint.CP_STEP_COMMITTED, WorkflowCheckpoint.CP_CANCELLED}),
    WorkflowCheckpoint.CP_STEP_COMMITTED: frozenset(
        {
            WorkflowCheckpoint.CP_COMPLETED,
            WorkflowCheckpoint.CP_FAILED,
            WorkflowCheckpoint.CP_STEP_PREPARED,  # next step loop
            WorkflowCheckpoint.CP_CANCELLED,
        }
    ),
    WorkflowCheckpoint.CP_FAILED: frozenset({WorkflowCheckpoint.CP_REPAIR_DIAGNOSED, WorkflowCheckpoint.CP_CANCELLED}),
    WorkflowCheckpoint.CP_REPAIR_DIAGNOSED: frozenset(
        {
            WorkflowCheckpoint.CP_REPAIR_DISPATCHED,
            WorkflowCheckpoint.CP_ESCALATED,
            WorkflowCheckpoint.CP_CANCELLED,
        }
    ),
    WorkflowCheckpoint.CP_REPAIR_DISPATCHED: frozenset(
        {WorkflowCheckpoint.CP_STEP_PREPARED, WorkflowCheckpoint.CP_CANCELLED}
    ),
    # Terminal states — no outgoing edges.
    WorkflowCheckpoint.CP_COMPLETED: frozenset(),
    WorkflowCheckpoint.CP_ESCALATED: frozenset(),
    WorkflowCheckpoint.CP_CANCELLED: frozenset(),
}


class InvalidCheckpointTransitionError(Exception):
    """Raised when a checkpoint transition violates the frozen DAG."""


def validate_checkpoint_transition(
    current: WorkflowCheckpoint,
    target: WorkflowCheckpoint,
) -> None:
    """Assert that transitioning ``current`` → ``target`` is a legal DAG edge.

    Raises:
        InvalidCheckpointTransitionError: if the transition is not in the DAG.
    """
    allowed = _CHECKPOINT_DAG.get(current, frozenset())
    if target not in allowed:
        raise InvalidCheckpointTransitionError(
            f"Illegal checkpoint transition: {current!r} → {target!r}. "
            f"Allowed targets from {current!r}: {sorted(str(t) for t in allowed) or 'none (terminal)'}."
        )
