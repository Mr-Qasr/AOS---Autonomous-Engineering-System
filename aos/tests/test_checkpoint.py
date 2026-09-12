"""Tests for checkpoint DAG validation."""

import pytest
from aos.workflow.checkpoints import (
    InvalidCheckpointTransitionError,
    WorkflowCheckpoint,
    validate_checkpoint_transition,
)


def test_valid_transitions():
    """Test all valid checkpoint transitions from the approved DAG."""
    valid_transitions = [
        (WorkflowCheckpoint.CP_INITIALIZED, WorkflowCheckpoint.CP_STARTED),
        (WorkflowCheckpoint.CP_INITIALIZED, WorkflowCheckpoint.CP_CANCELLED),
        (WorkflowCheckpoint.CP_STARTED, WorkflowCheckpoint.CP_STEP_PREPARED),
        (WorkflowCheckpoint.CP_STARTED, WorkflowCheckpoint.CP_CANCELLED),
        (WorkflowCheckpoint.CP_STEP_PREPARED, WorkflowCheckpoint.CP_STEP_COMMITTED),
        (WorkflowCheckpoint.CP_STEP_PREPARED, WorkflowCheckpoint.CP_CANCELLED),
        (WorkflowCheckpoint.CP_STEP_COMMITTED, WorkflowCheckpoint.CP_COMPLETED),
        (WorkflowCheckpoint.CP_STEP_COMMITTED, WorkflowCheckpoint.CP_FAILED),
        (WorkflowCheckpoint.CP_STEP_COMMITTED, WorkflowCheckpoint.CP_STEP_PREPARED),
        (WorkflowCheckpoint.CP_STEP_COMMITTED, WorkflowCheckpoint.CP_CANCELLED),
        (WorkflowCheckpoint.CP_FAILED, WorkflowCheckpoint.CP_REPAIR_DIAGNOSED),
        (WorkflowCheckpoint.CP_FAILED, WorkflowCheckpoint.CP_CANCELLED),
        (WorkflowCheckpoint.CP_REPAIR_DIAGNOSED, WorkflowCheckpoint.CP_REPAIR_DISPATCHED),
        (WorkflowCheckpoint.CP_REPAIR_DIAGNOSED, WorkflowCheckpoint.CP_ESCALATED),
        (WorkflowCheckpoint.CP_REPAIR_DIAGNOSED, WorkflowCheckpoint.CP_CANCELLED),
        (WorkflowCheckpoint.CP_REPAIR_DISPATCHED, WorkflowCheckpoint.CP_STEP_PREPARED),
        (WorkflowCheckpoint.CP_REPAIR_DISPATCHED, WorkflowCheckpoint.CP_CANCELLED),
    ]
    for current, target in valid_transitions:
        validate_checkpoint_transition(current, target)  # Should not raise


def test_invalid_transitions():
    """Test that invalid transitions raise InvalidCheckpointTransitionError."""
    invalid_transitions = [
        # Cannot skip steps
        (WorkflowCheckpoint.CP_INITIALIZED, WorkflowCheckpoint.CP_STEP_PREPARED),
        (WorkflowCheckpoint.CP_STARTED, WorkflowCheckpoint.CP_STEP_COMMITTED),
        (WorkflowCheckpoint.CP_STEP_PREPARED, WorkflowCheckpoint.CP_COMPLETED),
        # Cannot go backwards
        (WorkflowCheckpoint.CP_STEP_COMMITTED, WorkflowCheckpoint.CP_STARTED),
        (WorkflowCheckpoint.CP_COMPLETED, WorkflowCheckpoint.CP_STEP_COMMITTED),
        # Cannot transition from terminal states
        (WorkflowCheckpoint.CP_COMPLETED, WorkflowCheckpoint.CP_CANCELLED),
        (WorkflowCheckpoint.CP_ESCALATED, WorkflowCheckpoint.CP_CANCELLED),
        (WorkflowCheckpoint.CP_CANCELLED, WorkflowCheckpoint.CP_STARTED),
    ]
    for current, target in invalid_transitions:
        with pytest.raises(InvalidCheckpointTransitionError):
            validate_checkpoint_transition(current, target)


def test_terminal_states_have_no_outgoing_edges():
    """Test that terminal states cannot transition at all."""
    terminal = [
        WorkflowCheckpoint.CP_COMPLETED,
        WorkflowCheckpoint.CP_ESCALATED,
        WorkflowCheckpoint.CP_CANCELLED,
    ]
    all_states = list(WorkflowCheckpoint)
    for t in terminal:
        for target in all_states:
            with pytest.raises(InvalidCheckpointTransitionError):
                validate_checkpoint_transition(t, target)
