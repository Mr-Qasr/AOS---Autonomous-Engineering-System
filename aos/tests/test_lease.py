"""Tests for lease acquisition, renewal, release, and fencing."""

from datetime import datetime, timezone

import pytest
import pytest_asyncio
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from aos.workflow.lease import LeaseManager, StaleControllerFencingError


@pytest_asyncio.fixture
async def lease_mgr(db_session: AsyncSession) -> LeaseManager:
    return LeaseManager(db_session, controller_id="test-controller")


@pytest_asyncio.fixture
async def other_lease_mgr(db_session: AsyncSession) -> LeaseManager:
    return LeaseManager(db_session, controller_id="other-controller")


def _insert_run(run_id: str):
    """Return SQL to insert a run with all required columns."""
    return text(
        "INSERT INTO runs (id, task_id, started_at, updated_at) VALUES (:rid, 'task-1', :now, :now)"
    ), {"rid": run_id, "now": datetime.now(timezone.utc)}


@pytest.mark.asyncio
async def test_lease_acquire_success(db_session, lease_mgr):
    """Test successful lease acquisition."""
    run_id = "test-run-1"
    sql, params = _insert_run(run_id)
    await db_session.execute(sql, params)
    await db_session.commit()

    token = await lease_mgr.acquire(run_id)
    assert token == 1


@pytest.mark.asyncio
async def test_lease_acquire_increments_fencing_token(db_session, lease_mgr):
    """Test that acquire increments fencing_token."""
    run_id = "test-run-2"
    sql, params = _insert_run(run_id)
    await db_session.execute(sql, params)
    await db_session.commit()

    token1 = await lease_mgr.acquire(run_id)
    await lease_mgr.release(run_id, token1)
    token2 = await lease_mgr.acquire(run_id)
    assert token2 == token1 + 1


@pytest.mark.asyncio
async def test_lease_acquire_fails_when_held(db_session, lease_mgr, other_lease_mgr):
    """Test that acquire fails when another controller holds the lease."""
    run_id = "test-run-3"
    sql, params = _insert_run(run_id)
    await db_session.execute(sql, params)
    await db_session.commit()

    await lease_mgr.acquire(run_id)
    with pytest.raises(StaleControllerFencingError):
        await other_lease_mgr.acquire(run_id)


@pytest.mark.asyncio
async def test_lease_renew_success(db_session, lease_mgr):
    """Test successful lease renewal."""
    run_id = "test-run-4"
    sql, params = _insert_run(run_id)
    await db_session.execute(sql, params)
    await db_session.commit()

    token = await lease_mgr.acquire(run_id)
    await lease_mgr.renew(run_id, token)


@pytest.mark.asyncio
async def test_renew_fails_with_wrong_token(db_session, lease_mgr):
    """Test that renew fails with wrong token."""
    run_id = "test-run-5"
    sql, params = _insert_run(run_id)
    await db_session.execute(sql, params)
    await db_session.commit()

    await lease_mgr.acquire(run_id)
    with pytest.raises(StaleControllerFencingError):
        await lease_mgr.renew(run_id, 999)


@pytest.mark.asyncio
async def test_lease_release_success(db_session, lease_mgr):
    """Test successful lease release."""
    run_id = "test-run-6"
    sql, params = _insert_run(run_id)
    await db_session.execute(sql, params)
    await db_session.commit()

    token = await lease_mgr.acquire(run_id)
    await lease_mgr.release(run_id, token)

    token2 = await lease_mgr.acquire(run_id)
    assert token2 == token + 1


@pytest.mark.asyncio
async def test_release_fails_with_wrong_token(db_session, lease_mgr):
    """Test that release fails with wrong token."""
    run_id = "test-run-7"
    sql, params = _insert_run(run_id)
    await db_session.execute(sql, params)
    await db_session.commit()

    await lease_mgr.acquire(run_id)
    with pytest.raises(StaleControllerFencingError):
        await lease_mgr.release(run_id, 999)


@pytest.mark.asyncio
async def test_stale_controller_cannot_mutate(db_session, lease_mgr, other_lease_mgr):
    """Test that a stale controller cannot acquire when another holds the lease."""
    run_id = "test-run-8"
    sql, params = _insert_run(run_id)
    await db_session.execute(sql, params)
    await db_session.commit()

    await lease_mgr.acquire(run_id)
    with pytest.raises(StaleControllerFencingError):
        await other_lease_mgr.acquire(run_id)
@pytest.mark.asyncio
async def test_cancel_releases_lease(client, db_session):
    """BLOCKER 3: a terminal Run must have no active lease.

    cancel → status CANCELLED, checkpoint CP_CANCELLED,
    lease_owner IS NULL, lease_expiry IS NULL.
    """
    from sqlalchemy import select

    from aos.db.models import RunRow

    task_resp = await client.post("/tasks", json={
        "title": "Cancel Lease Cleanup",
        "acceptance_criteria": ["criterion1"],
        "requirement_version": 1,
    })
    task_id = task_resp.json()["id"]
    run_resp = await client.post("/runs", json={"task_id": task_id})
    run_id = run_resp.json()["id"]

    # Start the run first so a lease is actually held.
    resp = await client.post(f"/runs/{run_id}/start", json={})
    assert resp.status_code == 200, resp.text
    assert resp.json()["fencing_token"] == 1

    # Verify a lease is held before cancel.
    result = await db_session.execute(select(RunRow).where(RunRow.id == run_id))
    run = result.scalar_one()
    assert run.lease_owner is not None
    assert run.lease_expiry is not None

    # Cancel with the held token — the terminal transition must release the
    # lease in the same txn.
    resp = await client.post(f"/runs/{run_id}/cancel", json={
        "reason": "demo-complete",
        "held_token": 1,
    })
    assert resp.status_code == 200, resp.text
    assert resp.json()["status"] == "CANCELLED"
    assert resp.json()["checkpoint"] == "CP_CANCELLED"

    result = await db_session.execute(
        select(RunRow)
        .where(RunRow.id == run_id)
        .execution_options(populate_existing=True)
    )
    run = result.scalar_one()
    assert run.status == "CANCELLED"
    assert run.checkpoint == "CP_CANCELLED"
    assert run.lease_owner is None
    assert run.lease_expiry is None
