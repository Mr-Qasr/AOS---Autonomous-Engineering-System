"""Enumerated types for AOS domain contracts and state machines."""

from enum import StrEnum


class TaskStatus(StrEnum):
    """Lifecycle states for an engineering Task."""

    DRAFT = "DRAFT"
    LOCKED = "LOCKED"
    IN_PROGRESS = "IN_PROGRESS"
    BLOCKED = "BLOCKED"
    READY = "READY"
    RELEASED = "RELEASED"
    ABANDONED = "ABANDONED"


class RunStatus(StrEnum):
    """Lifecycle states for an execution Run."""

    QUEUED = "QUEUED"
    RUNNING = "RUNNING"
    PASSED = "PASSED"
    FAILED = "FAILED"
    REPAIRING = "REPAIRING"
    ESCALATED = "ESCALATED"
    CANCELLED = "CANCELLED"


class EventType(StrEnum):
    """Canonical event catalog per AOS Master Specification §5 and Phase 0 packet."""

    RUN_STATE_CHANGED = "run.state.changed"
    TASK_STATE_CHANGED = "task.state.changed"
    AGENT_STARTED = "agent.started"
    TOOL_REQUESTED = "tool.requested"
    TOOL_COMPLETED = "tool.completed"
    TEST_COMPLETED = "test.completed"
    REVIEW_FINDING = "review.finding"
    APPROVAL_REQUESTED = "approval.requested"
    APPROVAL_DECIDED = "approval.decided"
    RUN_FAILED = "run.failed"
    RUN_COMPLETED = "run.completed"
    REPAIR_ATTEMPT = "repair.attempt"


class FailureClass(StrEnum):
    """Classification of failures during verification or execution per Master Spec §6."""

    CODE_DEFECT = "code_defect"
    TEST_DEFECT = "test_defect"
    ENVIRONMENT_DEFECT = "environment_defect"
    FLAKY_TEST = "flaky_test"
    TOOL_FAILURE = "tool_failure"
    MODEL_FAILURE = "model_failure"
    REQUIREMENT_CONFLICT = "requirement_conflict"
    SECURITY_POLICY_FAILURE = "security_policy_failure"


class PolicyEffect(StrEnum):
    """Effect of a policy rule evaluation."""

    ALLOW = "allow"
    DENY = "deny"


class ApprovalDecision(StrEnum):
    """Status or outcome of an approval request."""

    PENDING = "pending"
    APPROVED = "approved"
    REJECTED = "rejected"
    EXPIRED = "expired"


class WorkerHealth(StrEnum):
    """Operational health status of an execution worker."""

    HEALTHY = "healthy"
    DEGRADED = "degraded"
    UNHEALTHY = "unhealthy"
    DRAINING = "draining"

