"""Comprehensive test suite for AOS Phase 0 contracts, state machines, and threat model policy."""

from datetime import datetime, timezone, timedelta
import json
from pathlib import Path
import pytest
from pydantic import ValidationError

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


# ============================================================================
# 1. Canonical Imports & Base Model Tests
# ============================================================================

def test_canonical_imports():
    """Verify that all public contracts are directly importable from canonical paths."""
    from aos.contracts.task import Task as TaskDirect
    from aos.contracts.run import Run as RunDirect
    from aos.contracts.artifact import Artifact as ArtifactDirect
    from aos.contracts.event import Event as EventDirect
    from aos.contracts.approval import Approval as ApprovalDirect
    from aos.contracts.policy import Policy as PolicyDirect, PolicyRule as PolicyRuleDirect
    from aos.contracts.worker import Worker as WorkerDirect

    assert TaskDirect is Task
    assert RunDirect is Run
    assert ArtifactDirect is Artifact
    assert EventDirect is Event
    assert ApprovalDirect is Approval
    assert PolicyDirect is Policy
    assert PolicyRuleDirect is PolicyRule
    assert WorkerDirect is Worker


def test_base_model_immutability():
    """Verify that AOSBaseModel enforces immutability and forbids extra fields."""
    class SampleModel(AOSBaseModel):
        name: str
        count: int = 0

    m = SampleModel(name="test", count=1)
    assert m.name == "test"
    assert m.count == 1

    # Immutability check
    with pytest.raises(ValidationError):
        m.name = "modified"  # type: ignore

    # Forbid extra check
    with pytest.raises(ValidationError):
        SampleModel(name="test", extra_field="forbidden")  # type: ignore


# ============================================================================
# 2. Domain Contract Validation & Immutability Tests
# ============================================================================

def test_task_contract_valid_and_immutable():
    task = Task(
        objective="Implement feature X",
        requirement_version=1,
        acceptance_criteria=["Tests pass", "Docs updated"],
        policy_id="policy-default-v1",
        allowed_scope=["src/feature_x/**"],
    )
    assert task.status == TaskStatus.DRAFT
    assert len(task.acceptance_criteria) == 2
    assert task.release_approval_id is None

    # Verify immutability
    with pytest.raises(ValidationError):
        task.status = TaskStatus.LOCKED  # type: ignore

    # Verify extra forbidden
    with pytest.raises(ValidationError):
        Task(
            objective="Obj",
            requirement_version=1,
            acceptance_criteria=["A"],
            policy_id="pol-1",
            unknown_extra_field=True,  # type: ignore
        )


def test_task_contract_field_validations():
    # Empty objective
    with pytest.raises(ValidationError):
        Task(
            objective="",
            requirement_version=1,
            acceptance_criteria=["A"],
            policy_id="pol-1",
        )

    # Invalid requirement version (< 1)
    with pytest.raises(ValidationError):
        Task(
            objective="Valid",
            requirement_version=0,
            acceptance_criteria=["A"],
            policy_id="pol-1",
        )

    # Empty acceptance criteria list
    with pytest.raises(ValidationError):
        Task(
            objective="Valid",
            requirement_version=1,
            acceptance_criteria=[],
            policy_id="pol-1",
        )


def test_run_contract_valid_and_immutable():
    run = Run(task_id="task-123")
    assert run.status == RunStatus.QUEUED
    assert run.repair_attempt_count == 0
    assert run.max_repair_attempts == DEFAULT_MAX_REPAIR_ATTEMPTS
    assert run.workflow_version == "1.0.0"

    with pytest.raises(ValidationError):
        run.status = RunStatus.RUNNING  # type: ignore


def test_artifact_contract_sha256_validation():
    valid_sha = "a" * 64
    art = Artifact(
        type="git_patch",
        producer="agent:coder",
        uri="file:///tmp/patch.diff",
        sha256=valid_sha,
        run_id="run-1",
    )
    assert art.sha256 == valid_sha

    # Invalid length sha256
    with pytest.raises(ValidationError):
        Artifact(
            type="git_patch",
            producer="agent:coder",
            uri="file:///tmp/patch.diff",
            sha256="short_sha",
            run_id="run-1",
        )

    # Invalid characters in sha256
    with pytest.raises(ValidationError):
        Artifact(
            type="git_patch",
            producer="agent:coder",
            uri="file:///tmp/patch.diff",
            sha256="z" * 64,
            run_id="run-1",
        )


def test_approval_contract_validations():
    exp = datetime.now(timezone.utc) + timedelta(hours=1)
    app = Approval(
        action="deploy.production",
        evidence_refs=["art-1", "art-2"],
        actor="operator:alice",
        scope={"env": "prod"},
        expiry=exp,
    )
    assert app.decision == ApprovalDecision.PENDING
    assert len(app.evidence_refs) == 2


def test_worker_contract_validations():
    worker = Worker(
        id="worker-01",
        capabilities=["docker", "gpu"],
        cost_metadata={"tier": "standard"},
    )
    assert worker.health == WorkerHealth.HEALTHY
    assert "docker" in worker.capabilities


def test_all_models_export_json_schema():
    """Verify that all 7 primary contracts and payloads export valid JSON Schema."""
    models = [
        Task,
        Run,
        Artifact,
        Event,
        Approval,
        Policy,
        PolicyRule,
        Worker,
        RepairAttemptPayload,
        RunStateChangedPayload,
        TaskStateChangedPayload,
    ]
    for model in models:
        schema = model.model_json_schema()
        assert isinstance(schema, dict)
        assert "properties" in schema
        assert schema.get("type") == "object"


def test_models_json_round_trip():
    """Verify serialization to JSON string and round-trip deserialization preserves fidelity."""
    task = Task(
        objective="Round trip test",
        requirement_version=2,
        acceptance_criteria=["Valid JSON serialization"],
        policy_id="pol-default",
    )
    json_str = task.model_dump_json()
    reloaded = Task.model_validate_json(json_str)
    assert task == reloaded


# ============================================================================
# 3. Task State Machine Tests
# ============================================================================

def test_task_lifecycle_legal_progression():
    task = Task(
        objective="Test lifecycle",
        requirement_version=1,
        acceptance_criteria=["Must pass"],
        policy_id="pol-1",
    )
    assert task.status == TaskStatus.DRAFT

    # 1. Lock
    res_lock = transition_task_lock(task)
    task_locked = res_lock.entity
    assert task_locked.status == TaskStatus.LOCKED
    assert res_lock.event_payload.new_status == TaskStatus.LOCKED

    # 2. Start
    res_start = transition_task_start(task_locked)
    task_running = res_start.entity
    assert task_running.status == TaskStatus.IN_PROGRESS

    # 3. Block & Unblock
    res_block = transition_task_block(task_running, reason="Waiting for clarification")
    task_blocked = res_block.entity
    assert task_blocked.status == TaskStatus.BLOCKED

    res_unblock = transition_task_unblock(task_blocked)
    task_resumed = res_unblock.entity
    assert task_resumed.status == TaskStatus.IN_PROGRESS

    # 4. Ready
    res_ready = transition_task_mark_ready(task_resumed)
    task_ready = res_ready.entity
    assert task_ready.status == TaskStatus.READY

    # 5. Release (requires approval_id)
    res_release = transition_task_release(task_ready, approval_id="app-12345")
    task_released = res_release.entity
    assert task_released.status == TaskStatus.RELEASED
    assert task_released.release_approval_id == "app-12345"


def test_task_release_approval_reference_boundary():
    """Verify that release requires approval_id, records it, and does not evaluate validity."""
    task = Task(
        objective="Release boundary check",
        requirement_version=1,
        acceptance_criteria=["Check"],
        policy_id="pol-1",
    )
    locked = transition_task_lock(task).entity
    started = transition_task_start(locked).entity
    ready = transition_task_mark_ready(started).entity

    # Rejection on empty approval_id
    with pytest.raises(InvalidStateTransitionError, match="approval_id must be a non-empty string"):
        transition_task_release(ready, approval_id="")

    with pytest.raises(InvalidStateTransitionError, match="approval_id must be a non-empty string"):
        transition_task_release(ready, approval_id="   ")

    # Success: approval reference is carried without external DB lookup in Phase 0
    res = transition_task_release(ready, approval_id="external-approval-token-xyz")
    assert res.entity.status == TaskStatus.RELEASED
    assert res.entity.release_approval_id == "external-approval-token-xyz"


def test_task_abandonment_from_all_non_terminal_states():
    base_task = Task(
        objective="Abandon test",
        requirement_version=1,
        acceptance_criteria=["Criteria"],
        policy_id="pol-1",
    )
    locked = transition_task_lock(base_task).entity
    started = transition_task_start(locked).entity
    blocked = transition_task_block(started, reason="Block").entity
    ready = transition_task_mark_ready(transition_task_unblock(blocked).entity).entity

    # Can abandon from DRAFT, LOCKED, IN_PROGRESS, BLOCKED, READY
    for state_task in [base_task, locked, started, blocked, ready]:
        res = transition_task_abandon(state_task, reason="Operator cancelled")
        assert res.entity.status == TaskStatus.ABANDONED


def test_task_terminal_states_cannot_transition():
    task = Task(
        objective="Terminal check",
        requirement_version=1,
        acceptance_criteria=["Crit"],
        policy_id="pol-1",
    )
    locked = transition_task_lock(task).entity
    started = transition_task_start(locked).entity
    ready = transition_task_mark_ready(started).entity
    released = transition_task_release(ready, approval_id="app-1").entity
    abandoned = transition_task_abandon(task, reason="Cancelled").entity

    # Released is terminal
    with pytest.raises(InvalidStateTransitionError):
        transition_task_abandon(released, reason="Cannot abandon released")
    with pytest.raises(InvalidStateTransitionError):
        transition_task_start(released)

    # Abandoned is terminal
    with pytest.raises(InvalidStateTransitionError):
        transition_task_lock(abandoned)
    with pytest.raises(InvalidStateTransitionError):
        transition_task_abandon(abandoned, reason="Already abandoned")


def test_task_illegal_transitions():
    task = Task(
        objective="Illegal transitions",
        requirement_version=1,
        acceptance_criteria=["Crit"],
        policy_id="pol-1",
    )
    # Direct DRAFT -> IN_PROGRESS illegal
    with pytest.raises(InvalidStateTransitionError):
        transition_task_start(task)

    # Direct DRAFT -> READY illegal
    with pytest.raises(InvalidStateTransitionError):
        transition_task_mark_ready(task)

    # Direct DRAFT -> RELEASED illegal
    with pytest.raises(InvalidStateTransitionError):
        transition_task_release(task, approval_id="app-1")


# ============================================================================
# 4. Run State Machine & Exact Repair Accounting Tests
# ============================================================================

def test_run_lifecycle_legal_pass():
    run = Run(task_id="task-1")
    assert run.status == RunStatus.QUEUED

    started = transition_run_start(run, worker_id="worker-01").entity
    assert started.status == RunStatus.RUNNING
    assert started.worker_id == "worker-01"

    passed = transition_run_pass(started).entity
    assert passed.status == RunStatus.PASSED


def test_repair_accounting_exact_semantics():
    """Verify that:
    1. FAILED -> REPAIRING does NOT consume a repair attempt.
    2. REPAIRING -> RUNNING commits an attempt and increments repair_attempt_count by 1.
    3. repair_attempt_count is never decremented on subsequent failures.
    4. At max_repair_attempts, further repair dispatch is blocked.
    5. Escalation transitions REPAIRING -> ESCALATED.
    """
    run = Run(task_id="task-1", max_repair_attempts=3)
    running = transition_run_start(run).entity
    assert running.repair_attempt_count == 0

    # First Failure
    failed_1 = transition_run_fail(running, reason="Unit test failed").entity
    assert failed_1.status == RunStatus.FAILED
    assert failed_1.repair_attempt_count == 0

    # 1. Entering repair mode does NOT consume an attempt
    repairing_1 = transition_run_enter_repair(failed_1).entity
    assert repairing_1.status == RunStatus.REPAIRING
    assert repairing_1.repair_attempt_count == 0  # CRITICAL INVARIANT

    # 2. Dispatching a repair commits attempt #1
    payload_1 = RepairAttemptPayload(
        failure_class=FailureClass.CODE_DEFECT,
        hypothesis="Off by one error in index loop",
        patch_sha="sha256-patch-001",
        result="Applied fix to loop boundary",
    )
    res_dispatch_1 = transition_run_dispatch_repair(repairing_1, payload_1)
    attempt_1_run = res_dispatch_1.entity
    assert attempt_1_run.status == RunStatus.RUNNING
    assert attempt_1_run.repair_attempt_count == 1  # INCREMENTED
    assert res_dispatch_1.event_payload == payload_1

    # 3. Subsequent failure does NOT decrement counter
    failed_2 = transition_run_fail(attempt_1_run, reason="Test still failed").entity
    assert failed_2.repair_attempt_count == 1

    repairing_2 = transition_run_enter_repair(failed_2).entity
    assert repairing_2.repair_attempt_count == 1  # NOT DECREMENTED

    # Dispatch attempt #2
    payload_2 = RepairAttemptPayload(
        failure_class=FailureClass.CODE_DEFECT,
        hypothesis="Try alternative regex parser",
        patch_sha="sha256-patch-002",
        result="Replaced custom tokenizer",
    )
    attempt_2_run = transition_run_dispatch_repair(repairing_2, payload_2).entity
    assert attempt_2_run.repair_attempt_count == 2

    # Fail attempt #2, enter repairing #3
    failed_3 = transition_run_fail(attempt_2_run, reason="Parsing syntax error").entity
    repairing_3 = transition_run_enter_repair(failed_3).entity
    assert repairing_3.repair_attempt_count == 2

    # Dispatch attempt #3 (reaches max_repair_attempts=3)
    payload_3 = RepairAttemptPayload(
        failure_class=FailureClass.CODE_DEFECT,
        hypothesis="Ensure strict grammar parsing",
        patch_sha="sha256-patch-003",
        result="Fixed grammar rules",
    )
    attempt_3_run = transition_run_dispatch_repair(repairing_3, payload_3).entity
    assert attempt_3_run.repair_attempt_count == 3

    # Fail attempt #3, enter repairing
    failed_4 = transition_run_fail(attempt_3_run, reason="Still fails").entity
    repairing_4 = transition_run_enter_repair(failed_4).entity
    assert repairing_4.repair_attempt_count == 3

    # 4. Attempting dispatch when count >= max_repair_attempts is BLOCKED
    payload_4 = RepairAttemptPayload(
        failure_class=FailureClass.CODE_DEFECT,
        hypothesis="Should not execute",
        patch_sha="sha256-patch-004",
        result="N/A",
    )
    with pytest.raises(InvalidStateTransitionError, match="Repair budget exhausted"):
        transition_run_dispatch_repair(repairing_4, payload_4)

    # 5. Must escalate instead
    res_escalate = transition_run_escalate(repairing_4, reason="Retry budget exhausted after 3 attempts")
    escalated_run = res_escalate.entity
    assert escalated_run.status == RunStatus.ESCALATED
    assert escalated_run.repair_attempt_count == 3


def test_run_cancellation():
    # Cancel from QUEUED
    run_q = Run(task_id="t1")
    assert transition_run_cancel(run_q, reason="User cancelled").entity.status == RunStatus.CANCELLED

    # Cancel from RUNNING
    run_r = transition_run_start(run_q).entity
    assert transition_run_cancel(run_r, reason="Timeout").entity.status == RunStatus.CANCELLED

    # Cancel from REPAIRING
    run_f = transition_run_fail(run_r).entity
    run_rep = transition_run_enter_repair(run_f).entity
    assert transition_run_cancel(run_rep, reason="Stop repair").entity.status == RunStatus.CANCELLED


def test_run_terminal_states_cannot_transition():
    run = Run(task_id="t1")
    running = transition_run_start(run).entity
    passed = transition_run_pass(running).entity
    cancelled = transition_run_cancel(run, reason="Cancel").entity

    for terminal in [passed, cancelled]:
        with pytest.raises(InvalidStateTransitionError):
            transition_run_start(terminal)
        with pytest.raises(InvalidStateTransitionError):
            transition_run_pass(terminal)
        with pytest.raises(InvalidStateTransitionError):
            transition_run_fail(terminal)
        with pytest.raises(InvalidStateTransitionError):
            transition_run_cancel(terminal, reason="Cancel again")


# ============================================================================
# 5. Events & Strict RepairAttemptPayload Tests
# ============================================================================

def test_canonical_event_catalog():
    expected_events = {
        "run.state.changed",
        "task.state.changed",
        "agent.started",
        "tool.requested",
        "tool.completed",
        "test.completed",
        "review.finding",
        "approval.requested",
        "approval.decided",
        "run.failed",
        "run.completed",
        "repair.attempt",
    }
    actual_events = {e.value for e in EventType}
    assert expected_events.issubset(actual_events)


def test_repair_attempt_payload_strict_validation():
    # Valid payload
    payload = RepairAttemptPayload(
        failure_class=FailureClass.TEST_DEFECT,
        hypothesis="Assumption in test was outdated after spec bump",
        patch_sha="abc12345",
        result="Updated test fixtures",
    )
    assert payload.failure_class == FailureClass.TEST_DEFECT

    # Missing field
    with pytest.raises(ValidationError):
        RepairAttemptPayload(
            failure_class=FailureClass.CODE_DEFECT,
            hypothesis="Hypo",
            patch_sha="sha",
            # missing result
        )  # type: ignore

    # Empty string field
    with pytest.raises(ValidationError):
        RepairAttemptPayload(
            failure_class=FailureClass.CODE_DEFECT,
            hypothesis="",
            patch_sha="sha",
            result="result",
        )


def test_event_model_validates_repair_attempt_type():
    # Event with REPAIR_ATTEMPT type and valid payload succeeds
    event_valid = Event(
        run_id="run-1",
        sequence=1,
        type=EventType.REPAIR_ATTEMPT,
        actor="agent:repair",
        payload={
            "failure_class": "code_defect",
            "hypothesis": "Null pointer check missing",
            "patch_sha": "def456",
            "result": "Added guard clause",
        },
    )
    assert event_valid.type == EventType.REPAIR_ATTEMPT

    # Event with REPAIR_ATTEMPT type and invalid payload fails
    with pytest.raises(ValidationError):
        Event(
            run_id="run-1",
            sequence=2,
            type=EventType.REPAIR_ATTEMPT,
            actor="agent:repair",
            payload={"invalid": "payload"},
        )


# ============================================================================
# 6. Policy Contracts & Sample Policy Coverage Tests (Spec §8)
# ============================================================================

def test_sample_policy_file_exists_and_validates():
    policy_file = Path(__file__).parent.parent / "docs" / "sample_policy.json"
    assert policy_file.exists(), f"sample_policy.json not found at {policy_file}"

    with open(policy_file, "r", encoding="utf-8") as f:
        data = json.load(f)

    policy = Policy.model_validate(data)
    assert policy.id == "policy-default-v1"
    assert policy.version == 1
    assert len(policy.rules) >= 10


def test_sample_policy_covers_all_master_spec_actions():
    """Verify that all 10 consequential actions from Master Specification §8 are represented in sample_policy.json."""
    required_actions = {
        "repo.read",
        "repo.write",
        "terminal.execute",
        "network.egress",
        "network.bind_inbound",
        "secrets.access",
        "git.protected_merge",
        "deploy.production",
        "compute.paid",
        "system.destructive_op",
    }

    policy_file = Path(__file__).parent.parent / "docs" / "sample_policy.json"
    with open(policy_file, "r", encoding="utf-8") as f:
        data = json.load(f)

    policy = Policy.model_validate(data)
    policy_actions = {rule.action for rule in policy.rules}

    missing_actions = required_actions - policy_actions
    assert not missing_actions, f"Sample policy is missing rules for required actions: {missing_actions}"

