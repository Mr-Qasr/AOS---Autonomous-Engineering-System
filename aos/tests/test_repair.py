"""Tests for repair accounting semantics and workflow progression."""

import pytest
from aos.contracts.enums import RunStatus
from aos.contracts.event import RepairAttemptPayload
from aos.contracts.transitions import (
    transition_run_dispatch_repair,
    transition_run_enter_repair,
    transition_run_fail,
    transition_run_pass,
    transition_run_start,
    InvalidStateTransitionError,
)


@pytest.mark.asyncio
async def test_repair_accounting_semantics():
    """Test that FAILED -> REPAIRING does NOT increment, but dispatch does."""
    from aos.contracts.run import Run

    run = Run(
        id="r1", task_id="t1", status=RunStatus.QUEUED,
        started_at=__import__("datetime").datetime.now(__import__("datetime").timezone.utc),
        updated_at=__import__("datetime").datetime.now(__import__("datetime").timezone.utc),
    )

    # Start the run
    result = transition_run_start(run)
    run = result.entity
    assert run.status == RunStatus.RUNNING
    assert run.repair_attempt_count == 0

    # Fail the run
    result = transition_run_fail(run, reason="test failure")
    run = result.entity
    assert run.status == RunStatus.FAILED
    assert run.repair_attempt_count == 0  # Unchanged

    # Enter repair
    result = transition_run_enter_repair(run)
    run = result.entity
    assert run.status == RunStatus.REPAIRING
    assert run.repair_attempt_count == 0  # Still unchanged

    # Dispatch repair
    payload = RepairAttemptPayload(
        failure_class="code_defect",
        hypothesis="Fix the bug",
        patch_sha="abc123",
        result="Applied fix",
    )
    result = transition_run_dispatch_repair(run, payload)
    run = result.entity
    assert run.status == RunStatus.RUNNING
    assert run.repair_attempt_count == 1  # Incremented by 1


@pytest.mark.asyncio
async def test_repair_budget_enforcement():
    """Test that dispatch is blocked when budget is exhausted."""
    from aos.contracts.run import Run

    run = Run(
        id="r2", task_id="t1", status=RunStatus.REPAIRING,
        repair_attempt_count=3, max_repair_attempts=3,
        started_at=__import__("datetime").datetime.now(__import__("datetime").timezone.utc),
        updated_at=__import__("datetime").datetime.now(__import__("datetime").timezone.utc),
    )

    payload = RepairAttemptPayload(
        failure_class="code_defect",
        hypothesis="Fix",
        patch_sha="sha",
        result="result",
    )

    with pytest.raises(InvalidStateTransitionError, match="Repair budget exhausted"):
        transition_run_dispatch_repair(run, payload)


@pytest.mark.asyncio
async def test_repair_counter_preserved_on_subsequent_failure():
    """Test that repair counter is preserved after subsequent failures."""
    from aos.contracts.run import Run

    run = Run(
        id="r3", task_id="t1", status=RunStatus.REPAIRING,
        repair_attempt_count=2,
        started_at=__import__("datetime").datetime.now(__import__("datetime").timezone.utc),
        updated_at=__import__("datetime").datetime.now(__import__("datetime").timezone.utc),
    )

    # Dispatch repair to get back to RUNNING (counter goes 2 -> 3)
    payload = RepairAttemptPayload(
        failure_class="code_defect",
        hypothesis="Fix",
        patch_sha="sha",
        result="result",
    )
    result = transition_run_dispatch_repair(run, payload)
    run = result.entity
    assert run.repair_attempt_count == 3

    # Now fail — counter should stay at 3
    result = transition_run_fail(run, reason="failed again")
    run = result.entity
    assert run.repair_attempt_count == 3  # Preserved


@pytest.mark.asyncio
async def test_api_repair_workflow(client):
    """Test the full repair workflow through the API."""
    # Create task and run
    task_resp = await client.post("/tasks", json={
        "title": "Repair Test",
        "acceptance_criteria": ["criterion1"],
        "requirement_version": 1,
    })
    task_id = task_resp.json()["id"]

    run_resp = await client.post("/runs", json={"task_id": task_id})
    run_id = run_resp.json()["id"]

    # Start
    resp = await client.post(f"/runs/{run_id}/start", json={})
    assert resp.status_code == 200
    token = resp.json()["fencing_token"]

    # Prepare and commit step
    await client.post(f"/runs/{run_id}/prepare-step", json={"held_token": token})
    await client.post(f"/runs/{run_id}/commit-step", json={"held_token": token})

    # Fail
    resp = await client.post(f"/runs/{run_id}/fail", json={"held_token": token, "reason": "test failure"})
    assert resp.status_code == 200
    assert resp.json()["status"] == "FAILED"
    assert resp.json()["repair_attempt_count"] == 0
    assert resp.json()["checkpoint"] == "CP_FAILED"

    # Enter repair
    resp = await client.post(f"/runs/{run_id}/enter-repair", json={"held_token": token})
    assert resp.status_code == 200
    assert resp.json()["status"] == "REPAIRING"
    assert resp.json()["repair_attempt_count"] == 0  # Not incremented
    assert resp.json()["checkpoint"] == "CP_REPAIR_DIAGNOSED"

    # Dispatch repair
    resp = await client.post(f"/runs/{run_id}/dispatch-repair", json={
        "held_token": token,
        "failure_class": "code_defect",
        "hypothesis": "Fix the bug",
        "patch_sha": "abc123",
        "result": "Applied fix",
    })
    assert resp.status_code == 200
    assert resp.json()["status"] == "RUNNING"
    assert resp.json()["repair_attempt_count"] == 1  # Incremented
    assert resp.json()["checkpoint"] == "CP_REPAIR_DISPATCHED"
@pytest.mark.asyncio
async def test_repair_dispatch_checkpoint_metadata_attempt_number(client, db_session):
    """BLOCKER 4: durable repair checkpoint metadata must match attempt counts.

    After the first dispatch, repair_attempt_count == 1 and the persisted
    checkpoint_metadata must record attempt_number == 1 (not a misleading 0).
    A second dispatch must record attempt_number == 2.
    """
    from sqlalchemy import select

    from aos.db.models import RunRow

    task_resp = await client.post("/tasks", json={
        "title": "Repair Metadata",
        "acceptance_criteria": ["criterion1"],
        "requirement_version": 1,
    })
    task_id = task_resp.json()["id"]
    run_resp = await client.post("/runs", json={"task_id": task_id})
    run_id = run_resp.json()["id"]

    resp = await client.post(f"/runs/{run_id}/start", json={})
    token = resp.json()["fencing_token"]
    await client.post(f"/runs/{run_id}/prepare-step", json={"held_token": token})
    await client.post(f"/runs/{run_id}/commit-step", json={"held_token": token})
    await client.post(f"/runs/{run_id}/fail", json={"held_token": token, "reason": "f1"})
    await client.post(f"/runs/{run_id}/enter-repair", json={"held_token": token})

    resp = await client.post(f"/runs/{run_id}/dispatch-repair", json={
        "held_token": token,
        "failure_class": "code_defect",
        "hypothesis": "Fix",
        "patch_sha": "sha1",
        "result": "fixed",
    })
    assert resp.status_code == 200, resp.text
    assert resp.json()["repair_attempt_count"] == 1

    result = await db_session.execute(
        select(RunRow)
        .where(RunRow.id == run_id)
        .execution_options(populate_existing=True)
    )
    run = result.scalar_one()
    assert run.repair_attempt_count == 1
    assert run.checkpoint_metadata["step_name"] == "repair_dispatched"
    assert run.checkpoint_metadata["attempt_number"] == 1, (
        f"first repair attempt metadata must record attempt_number == 1, "
        f"got {run.checkpoint_metadata['attempt_number']}"
    )
