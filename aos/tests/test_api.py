"""Tests for API CRUD operations and transition enforcement."""

import pytest


@pytest.mark.asyncio
async def test_create_and_get_task(client):
    """Test task CRUD."""
    resp = await client.post("/tasks", json={
        "title": "Test Task",
        "description": "A test task",
        "acceptance_criteria": ["criterion1"],
        "requirement_version": 1,
    })
    assert resp.status_code == 201
    task = resp.json()
    assert task["title"] == "Test Task"
    assert task["status"] == "DRAFT"

    # Get the task
    resp = await client.get(f"/tasks/{task['id']}")
    assert resp.status_code == 200
    assert resp.json()["id"] == task["id"]


@pytest.mark.asyncio
async def test_create_and_get_run(client):
    """Test run creation."""
    task_resp = await client.post("/tasks", json={
        "title": "Test Task",
        "acceptance_criteria": ["criterion1"],
        "requirement_version": 1,
    })
    task_id = task_resp.json()["id"]

    resp = await client.post("/runs", json={"task_id": task_id})
    assert resp.status_code == 201
    run = resp.json()
    assert run["task_id"] == task_id
    assert run["status"] == "QUEUED"
    assert run["checkpoint"] == "CP_INITIALIZED"

    resp = await client.get(f"/runs/{run['id']}")
    assert resp.status_code == 200
    assert resp.json()["id"] == run["id"]


@pytest.mark.asyncio
async def test_run_lifecycle_queued_to_running(client):
    """Test QUEUED -> RUNNING transition."""
    task_resp = await client.post("/tasks", json={
        "title": "Test Task",
        "acceptance_criteria": ["criterion1"],
        "requirement_version": 1,
    })
    task_id = task_resp.json()["id"]

    run_resp = await client.post("/runs", json={"task_id": task_id})
    run_id = run_resp.json()["id"]

    resp = await client.post(f"/runs/{run_id}/start", json={"worker_id": "worker-1"})
    assert resp.status_code == 200
    run = resp.json()
    assert run["status"] == "RUNNING"
    assert run["checkpoint"] == "CP_STARTED"
    assert run["fencing_token"] > 0


@pytest.mark.asyncio
async def test_run_workflow_progression(client):
    """Test full workflow progression: STARTED -> PREPARED -> COMMITTED -> COMPLETED."""
    task_resp = await client.post("/tasks", json={
        "title": "Test Task",
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

    # Prepare step
    resp = await client.post(f"/runs/{run_id}/prepare-step", json={"held_token": token})
    assert resp.status_code == 200
    assert resp.json()["checkpoint"] == "CP_STEP_PREPARED"
    assert resp.json()["status"] == "RUNNING"

    # Commit step
    resp = await client.post(f"/runs/{run_id}/commit-step", json={"held_token": token})
    assert resp.status_code == 200
    assert resp.json()["checkpoint"] == "CP_STEP_COMMITTED"
    assert resp.json()["status"] == "RUNNING"

    # Pass
    resp = await client.post(f"/runs/{run_id}/pass", json={"held_token": token})
    assert resp.status_code == 200
    assert resp.json()["checkpoint"] == "CP_COMPLETED"
    assert resp.json()["status"] == "PASSED"


@pytest.mark.asyncio
async def test_event_sequence_contiguous(client):
    """Test that event sequence numbers are contiguous."""
    task_resp = await client.post("/tasks", json={
        "title": "Test Task",
        "acceptance_criteria": ["criterion1"],
        "requirement_version": 1,
    })
    task_id = task_resp.json()["id"]

    run_resp = await client.post("/runs", json={"task_id": task_id})
    run_id = run_resp.json()["id"]

    # Start
    resp = await client.post(f"/runs/{run_id}/start", json={})
    token = resp.json()["fencing_token"]

    # Prepare step
    await client.post(f"/runs/{run_id}/prepare-step", json={"held_token": token})

    # Commit step
    await client.post(f"/runs/{run_id}/commit-step", json={"held_token": token})

    # Get events
    resp = await client.get(f"/runs/{run_id}/events")
    assert resp.status_code == 200
    events = resp.json()
    sequences = [e["sequence"] for e in events]

    # Verify contiguous starting from 1
    assert sequences == list(range(1, len(sequences) + 1)), f"Non-contiguous sequences: {sequences}"


@pytest.mark.asyncio
async def test_illegal_transition_returns_422(client):
    """Test that illegal Phase 0 transitions return 422."""
    task_resp = await client.post("/tasks", json={
        "title": "Test Task",
        "acceptance_criteria": ["criterion1"],
        "requirement_version": 1,
    })
    task_id = task_resp.json()["id"]

    run_resp = await client.post("/runs", json={"task_id": task_id})
    run_id = run_resp.json()["id"]

    # Start the run first to get a valid lease and token
    resp = await client.post(f"/runs/{run_id}/start", json={})
    assert resp.status_code == 200
    token = resp.json()["fencing_token"]

    # Progress through the full checkpoint DAG to reach terminal PASSED
    resp = await client.post(f"/runs/{run_id}/prepare-step", json={"held_token": token})
    assert resp.status_code == 200
    resp = await client.post(f"/runs/{run_id}/commit-step", json={"held_token": token})
    assert resp.status_code == 200
    resp = await client.post(f"/runs/{run_id}/pass", json={"held_token": token})
    assert resp.status_code == 200
    assert resp.json()["status"] == "PASSED"

    # Try to start again — PASSED is terminal, transition_run_start will raise 422
    resp = await client.post(f"/runs/{run_id}/start", json={})
    assert resp.status_code == 422


@pytest.mark.asyncio
async def test_approval_crud(client):
    """Test approval CRUD operations."""
    resp = await client.post("/approvals", json={
        "run_id": "test-run-id",
        "action": "deploy.production",
        "requester": "agent:test",
    })
    assert resp.status_code == 201
    approval = resp.json()
    assert approval["decision"] == "pending"

    # Decide
    resp = await client.post(f"/approvals/{approval['id']}/decide", json={
        "decision": "approved",
        "decided_by": "operator",
        "justification": "Looks good",
    })
    assert resp.status_code == 200
    assert resp.json()["decision"] == "approved"


@pytest.mark.asyncio
async def test_worker_registration(client):
    """Test worker registration."""
    resp = await client.post("/workers", json={
        "hostname": "worker-01",
        "capabilities": ["python", "docker"],
    })
    assert resp.status_code == 201
    worker = resp.json()
    assert worker["health"] == "healthy"

    # Heartbeat
    resp = await client.post(f"/workers/{worker['id']}/heartbeat", json={"health": "degraded"})
    assert resp.status_code == 200
    assert resp.json()["health"] == "degraded"
@pytest.mark.asyncio
async def test_start_idempotency_api_level(client):
    """BLOCKER 2: HTTP POST /runs/{id}/start must honor Idempotency-Key.

    - same key + same payload: first request executes once; replay returns the
      cached logical result with NO second run transition and NO duplicate event
    - same key + different payload: deterministic HTTP 409
    """
    task_resp = await client.post("/tasks", json={
        "title": "Idempotent Start",
        "acceptance_criteria": ["criterion1"],
        "requirement_version": 1,
    })
    task_id = task_resp.json()["id"]

    run_resp = await client.post("/runs", json={"task_id": task_id})
    run_id = run_resp.json()["id"]

    body = {"worker_id": "worker-1", "idempotency_key": "start-op-1"}

    # First request executes exactly once.
    resp = await client.post(f"/runs/{run_id}/start", json=body)
    assert resp.status_code == 200, resp.text
    token = resp.json()["fencing_token"]
    assert resp.json()["status"] == "RUNNING"
    events1 = (await client.get(f"/runs/{run_id}/events")).json()
    assert len(events1) == 1

    # Replay with same key + same payload → cached result, no new transition,
    # no new lease acquisition (same token), no duplicate start event.
    resp2 = await client.post(f"/runs/{run_id}/start", json=body)
    assert resp2.status_code == 200, resp2.text
    assert resp2.json()["fencing_token"] == token
    assert resp2.json()["status"] == "RUNNING"
    events2 = (await client.get(f"/runs/{run_id}/events")).json()
    assert len(events2) == 1, f"duplicate start event on replay: {events2}"

    # Same key + different payload → deterministic HTTP 409.
    resp3 = await client.post(
        f"/runs/{run_id}/start",
        json={"worker_id": "worker-2", "idempotency_key": "start-op-1"},
    )
    assert resp3.status_code == 409, resp3.text
