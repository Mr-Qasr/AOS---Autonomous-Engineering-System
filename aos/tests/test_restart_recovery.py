"""Tests for synthetic restart/recovery workflow."""

import pytest
from sqlalchemy import select, text

from aos.contracts.enums import EventType
from aos.db.models import RunRow
from aos.services.run_service import RunService
from aos.workflow.lease import LeaseManager

from aos.tests.conftest import TestSessionFactory


async def _expire_lease_and_acquire(session, run_id: str, controller_id: str) -> int:
    """Helper: expire old lease and acquire new one."""
    await session.execute(
        text("UPDATE runs SET lease_expiry = NOW() - INTERVAL '1 second' WHERE id = :rid"),
        {"rid": run_id},
    )
    await session.commit()
    lease_mgr = LeaseManager(session, controller_id=controller_id)
    return await lease_mgr.acquire(run_id)


@pytest.mark.asyncio
async def test_restart_recovery_from_checkpoint(client):
    """Test that a run recovers from its last committed checkpoint after crash."""
    task_resp = await client.post("/tasks", json={
        "title": "Restart Test",
        "acceptance_criteria": ["criterion1"],
        "requirement_version": 1,
    })
    task_id = task_resp.json()["id"]

    run_resp = await client.post("/runs", json={"task_id": task_id})
    run_id = run_resp.json()["id"]

    # Progress the workflow
    resp = await client.post(f"/runs/{run_id}/start", json={})
    token = resp.json()["fencing_token"]
    assert resp.json()["checkpoint"] == "CP_STARTED"

    resp = await client.post(f"/runs/{run_id}/prepare-step", json={"held_token": token})
    checkpoint_before_crash = resp.json()["checkpoint"]
    assert checkpoint_before_crash == "CP_STEP_PREPARED"
    events_before = len((await client.get(f"/runs/{run_id}/events")).json())

    # Simulated crash: new session = new controller
    async with TestSessionFactory() as new_session:
        new_service = RunService(new_session, controller_id="restarted-controller")

        # Verify checkpoint survived
        run_row = await new_service.get(run_id)
        assert run_row.checkpoint == checkpoint_before_crash

        # Resume from checkpoint
        new_token = await _expire_lease_and_acquire(new_session, run_id, "restarted-controller")
        run_row = await new_service.commit_step(run_id, new_token)
        assert run_row.checkpoint == "CP_STEP_COMMITTED"
        await new_session.commit()

        # Complete
        run_row = await new_service.mark_passed(run_id, new_token)
        assert run_row.checkpoint == "CP_COMPLETED"
        assert run_row.status == "PASSED"
        await new_session.commit()

    # Verify contiguous event sequence
    resp = await client.get(f"/runs/{run_id}/events")
    events = resp.json()
    sequences = [e["sequence"] for e in events]
    assert sequences == list(range(1, len(sequences) + 1))
    assert len(events) == events_before + 2


@pytest.mark.asyncio
async def test_crash_before_commit_rollback(client):
    """Test that a crash before transaction commit rolls back state changes."""
    task_resp = await client.post("/tasks", json={
        "title": "Crash Before Commit",
        "acceptance_criteria": ["criterion1"],
        "requirement_version": 1,
    })
    task_id = task_resp.json()["id"]

    run_resp = await client.post("/runs", json={"task_id": task_id})
    run_id = run_resp.json()["id"]

    resp = await client.post(f"/runs/{run_id}/start", json={})
    token = resp.json()["fencing_token"]

            # Simulate a crash during prepare_step by calling the repository directly
    # and NOT committing the session — simulating a process crash mid-transaction.
    async with TestSessionFactory() as crash_session:
        crash_service = RunService(crash_session)  # same default controller as /start
        # Call repository.advance_checkpoint directly — same path, but no commit
        from aos.workflow.checkpoints import WorkflowCheckpoint
        from aos.workflow.metadata import CheckpointMetadata
        row = await crash_service._repo.advance_checkpoint(
            run_id=run_id,
            held_token=token,
            target_checkpoint=WorkflowCheckpoint.CP_STEP_PREPARED,
            event_type=EventType.AGENT_STARTED,
            actor="controller",
            checkpoint_metadata=CheckpointMetadata(step_name="step_prepared"),
        )
        assert row.checkpoint == "CP_STEP_PREPARED"
        # Do NOT commit — simulate process crash

    # Verify rollback
    async with TestSessionFactory() as verify_session:
        result = await verify_session.execute(select(RunRow).where(RunRow.id == run_id))
        run = result.scalar_one()
        assert run.checkpoint == "CP_STARTED"


@pytest.mark.asyncio
async def test_repair_counter_survives_restart(client):
    """Test that repair_attempt_count survives a controller restart."""
    task_resp = await client.post("/tasks", json={
        "title": "Repair Counter Restart",
        "acceptance_criteria": ["criterion1"],
        "requirement_version": 1,
    })
    task_id = task_resp.json()["id"]

    run_resp = await client.post("/runs", json={"task_id": task_id})
    run_id = run_resp.json()["id"]

    # Start -> Prepare -> Commit -> Fail -> Enter Repair -> Dispatch
    resp = await client.post(f"/runs/{run_id}/start", json={})
    token = resp.json()["fencing_token"]

    await client.post(f"/runs/{run_id}/prepare-step", json={"held_token": token})
    await client.post(f"/runs/{run_id}/commit-step", json={"held_token": token})
    await client.post(f"/runs/{run_id}/fail", json={"held_token": token, "reason": "fail1"})
    await client.post(f"/runs/{run_id}/enter-repair", json={"held_token": token})
    resp = await client.post(f"/runs/{run_id}/dispatch-repair", json={
        "held_token": token,
        "failure_class": "code_defect",
        "hypothesis": "Fix",
        "patch_sha": "sha",
        "result": "result",
    })
    assert resp.json()["repair_attempt_count"] == 1

    # Crash + restart
    async with TestSessionFactory() as new_session:
        result = await new_session.execute(select(RunRow).where(RunRow.id == run_id))
        run = result.scalar_one()
        assert run.repair_attempt_count == 1

        new_token = await _expire_lease_and_acquire(new_session, run_id, "restarted")
        new_service = RunService(new_session, controller_id="restarted")

                # After dispatch_repair, the run is back at RUNNING / CP_REPAIR_DISPATCHED.
        # To complete the repair loop and fail again, we must:
        #   CP_REPAIR_DISPATCHED → CP_STEP_PREPARED (prepare_step)
        #   CP_STEP_PREPARED → CP_STEP_COMMITTED (commit_step)
        #   CP_STEP_COMMITTED → CP_FAILED (mark_failed)
        run_row = await new_service.prepare_step(run_id, new_token)
        run_row = await new_service.commit_step(run_id, new_token)
        await new_service.mark_failed(run_id, new_token, reason="fail2")
        # Enter repair (FAILED → REPAIRING, counter unchanged)
        await new_service.enter_repair(run_id, new_token)
        # Dispatch repair (REPAIRING → RUNNING, counter +1)
        from aos.contracts.event import RepairAttemptPayload
        run_row = await new_service.dispatch_repair(
            run_id, new_token,
            RepairAttemptPayload(
                failure_class="code_defect",
                hypothesis="Fix2",
                patch_sha="sha2",
                result="result2",
            ),
        )
        assert run_row.repair_attempt_count == 2
        await new_session.commit()
