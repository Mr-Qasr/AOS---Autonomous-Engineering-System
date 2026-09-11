"""Canonical export point for all AOS domain contracts and transitions."""

from aos.contracts.approval import Approval
from aos.contracts.artifact import Artifact
from aos.contracts.base import AOSBaseModel
from aos.contracts.enums import (
    ApprovalDecision,
    EventType,
    FailureClass,
    PolicyEffect,
    RunStatus,
    TaskStatus,
    WorkerHealth,
)
from aos.contracts.event import (
    Event,
    RepairAttemptPayload,
    RunStateChangedPayload,
    TaskStateChangedPayload,
)
from aos.contracts.policy import Policy, PolicyRule
from aos.contracts.run import DEFAULT_MAX_REPAIR_ATTEMPTS, Run
from aos.contracts.task import Task
from aos.contracts.transitions import (
    InvalidStateTransitionError,
    TransitionResult,
    transition_run_cancel,
    transition_run_dispatch_repair,
    transition_run_enter_repair,
    transition_run_escalate,
    transition_run_fail,
    transition_run_pass,
    transition_run_start,
    transition_task_abandon,
    transition_task_block,
    transition_task_lock,
    transition_task_mark_ready,
    transition_task_release,
    transition_task_start,
    transition_task_unblock,
)
from aos.contracts.worker import Worker

__all__ = [
    # Base
    "AOSBaseModel",
    # Enums
    "TaskStatus",
    "RunStatus",
    "EventType",
    "FailureClass",
    "PolicyEffect",
    "ApprovalDecision",
    "WorkerHealth",
    # Core Contracts
    "Task",
    "Run",
    "Artifact",
    "Event",
    "Approval",
    "Policy",
    "PolicyRule",
    "Worker",
    # Payloads
    "RepairAttemptPayload",
    "RunStateChangedPayload",
    "TaskStateChangedPayload",
    # Transitions & Results
    "TransitionResult",
    "InvalidStateTransitionError",
    "DEFAULT_MAX_REPAIR_ATTEMPTS",
    "transition_task_lock",
    "transition_task_start",
    "transition_task_block",
    "transition_task_unblock",
    "transition_task_mark_ready",
    "transition_task_release",
    "transition_task_abandon",
    "transition_run_start",
    "transition_run_pass",
    "transition_run_fail",
    "transition_run_enter_repair",
    "transition_run_dispatch_repair",
    "transition_run_escalate",
    "transition_run_cancel",
]

