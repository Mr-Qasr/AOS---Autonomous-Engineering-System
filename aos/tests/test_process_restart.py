"""Process-restart recovery — REAL container kill/restart integration test.

Exercises the actual containerised application stack (PostgreSQL + FastAPI
via Docker Compose) exactly as the Phase 1 packet requires:

    start a Run → kill the API process mid-run → restart the API
    → confirm the Run resumes from its last durable checkpoint
    → no data loss, no duplicate side effects.

The test is deterministic on Windows + Docker Desktop:

  * a DEDICATED Compose project ``aos-test`` (fresh volume, DB on 5433,
    API on 8001, 5-second lease TTL) never touches the dev stack.
  * every step goes through the real HTTP API on 127.0.0.1:8001.
  * resumption requires a fresh lease; the recovery endpoint
    ``POST /runs/{id}/lease/acquire`` returns the new fencing token
    (proving the dead controller's token was invalidated).

The test SKIPS when Docker is not available; run it explicitly to capture
the restart evidence (``pytest aos/tests/test_process_restart.py -v``).
"""

import pathlib
import shutil
import subprocess
import time

import httpx
import pytest

REPO_ROOT = None


def _repo_root() -> str:
    """Repo root = directory containing docker-compose.test.yml."""
    here = pathlib.Path(__file__).resolve()
COMPOSE = ["docker", "compose", "-p", "aos-test", "-f", "docker-compose.test.yml"]
API_BASE = "http://127.0.0.1:8001"


def _docker_available() -> bool:
    if shutil.which("docker") is None:
        return False
    try:
        probe = subprocess.run(
            ["docker", "info"], capture_output=True, text=True, timeout=15
        )
        return probe.returncode == 0
    except (subprocess.SubprocessError, OSError):
        return False


pytestmark = pytest.mark.skipif(
    not _docker_available(), reason="Docker daemon not available"
)


def _run(args: list[str], cwd: str, **kw):
    return subprocess.run(
        args, capture_output=True, text=True, cwd=cwd,
        encoding="utf-8", errors="replace", **kw,
    )


def _compose(step: list[str], cwd: str):
    proc = _run(COMPOSE + step, cwd, timeout=360)
    if proc.returncode != 0:
        raise RuntimeError(
            "docker compose "
            + " ".join(step)
            + " failed:\nSTDOUT:\n"
            + proc.stdout
            + "\nSTDERR:\n"
            + proc.stderr
        )
    return proc


def _wait_until(predicate, timeout: float, interval: float = 0.5, label: str = ""):
    deadline = time.monotonic() + timeout
    last = None
    while time.monotonic() < deadline:
        last = predicate()
        if last:
            return last
        time.sleep(interval)
    raise AssertionError("Timed out waiting for " + label + " (last=" + repr(last) + ")")


class _Unavailable:
    """Sentinel response used while the API process is not yet accepting connections."""

    status_code = 503

    def json(self):  # pragma: no cover - never reached in assertions
        return {}

    text = "service unavailable"


def _api_get(path: str, timeout: float = 30.0):
    try:
        with httpx.Client(timeout=timeout) as c:
            return c.get(API_BASE + path)
    except httpx.HTTPError:
        # uvicorn accepts the TCP connection then closes it while starting,
        # which surfaces as ConnectError/RemoteProtocolError — treat as "not ready".
        return _Unavailable()


def _api_post(path: str, body=None, timeout: float = 30.0):
    try:
        with httpx.Client(timeout=timeout) as c:
            return c.post(API_BASE + path, json=body or {})
    except httpx.HTTPError:
        return _Unavailable()
    return str(here.parent.parent.parent)
@pytest.mark.asyncio
async def test_process_restart_recovery():
    root = _repo_root()

    # 0. Fresh stack — destructive only to the dedicated aos-test project.
    _compose(["down", "-v", "--remove-orphans"], root)
    _compose(["up", "-d", "--build", "db", "api"], root)

    try:
        # Wait for API readiness (image build + migrations take time).
        _wait_until(
            lambda: _api_get("/health").status_code == 200,
            timeout=420.0,
            interval=3.0,
            label="API /health",
        )

        # 1. Drive the workflow through the real HTTP API to a durable
        #    non-terminal checkpoint (CP_STEP_PREPARED).
        task = _api_post("/tasks", {
            "title": "Restart Recovery",
            "acceptance_criteria": ["criterion1"],
            "requirement_version": 1,
        })
        assert task.status_code == 201, task.text
        task_id = task.json()["id"]

        run = _api_post("/runs", {"task_id": task_id})
        assert run.status_code == 201, run.text
        run_id = run.json()["id"]

        start = _api_post("/runs/" + run_id + "/start", {"worker_id": "worker-1"})
        assert start.status_code == 200, start.text
        token_before = start.json()["fencing_token"]

        prep = _api_post("/runs/" + run_id + "/prepare-step", {"held_token": token_before})
        assert prep.status_code == 200, prep.text
        checkpoint_before = prep.json()["checkpoint"]
        assert checkpoint_before == "CP_STEP_PREPARED"
        cp_seq_before = prep.json()["checkpoint_seq"]
        repair_count_before = prep.json()["repair_attempt_count"]

        events_before = _api_get("/runs/" + run_id + "/events")
        assert events_before.status_code == 200, events_before.text
        events_before = events_before.json()
        ev_before_ids = [(e["sequence"], e["type"]) for e in events_before]
# 2. Kill the ACTUAL API process (SIGKILL via `docker compose kill`).
        proc = _run(COMPOSE + ["kill", "api"], root, timeout=60)
        assert proc.returncode == 0, proc.stderr

        def _api_container_stopped():
            ps = _run(COMPOSE + ["ps", "-a", "-q", "api"], root, timeout=60)
            cid = ps.stdout.strip()
            if not cid:
                return False
            insp = _run(
                ["docker", "inspect", "-f", "{{.State.Running}}", cid], root, timeout=60
            )
            return insp.stdout.strip().lower() == "false"

        assert _wait_until(_api_container_stopped, timeout=60, label="api container stopped"), (
            "API container did not stop after `docker compose kill api`"
        )

        # 3. Restart the API process.
        _compose(["up", "-d", "api"], root)
        _wait_until(
            lambda: _api_get("/health").status_code == 200,
            timeout=180.0,
            interval=2.0,
            label="API /health after restart",
        )
# 4. Confirm durable state survived the process kill.
        run_after = _api_get("/runs/" + run_id)
        assert run_after.status_code == 200, run_after.text
        after = run_after.json()
        assert after["checkpoint"] == checkpoint_before, (
            "checkpoint did not survive restart: "
            + str(after["checkpoint"])
            + " != "
            + checkpoint_before
        )
        assert after["checkpoint_seq"] == cp_seq_before
        assert after["repair_attempt_count"] == repair_count_before

        events_after_kill = _api_get("/runs/" + run_id + "/events").json()
        assert [
            (e["sequence"], e["type"]) for e in events_after_kill
        ] == ev_before_ids, "Event history changed across the process kill (data loss / replay)."
# 5. Resume through the real API. The dead controller's lease expired
        #    (TTL=5s); acquire a fresh lease → fencing token MUST advance.
        def _try_acquire():
            resp = _api_post("/runs/" + run_id + "/lease/acquire")
            return resp if resp.status_code == 200 else None

        acq = _wait_until(
            _try_acquire, timeout=60.0, interval=1.0, label="lease acquire after restart"
        )
        token_resumed = int(acq.json()["held_token"])
        assert token_resumed == int(token_before) + 1, (
            "fencing token did not advance on takeover: "
            + str(token_resumed)
            + " vs "
            + str(token_before + 1)
        )

        commit = _api_post("/runs/" + run_id + "/commit-step", {"held_token": token_resumed})
        assert commit.status_code == 200, commit.text
        assert commit.json()["checkpoint"] == "CP_STEP_COMMITTED"

        # Repair accounting across a real process restart: fail → enter repair →
        # dispatch repair (attempt #1) → resume → pass.
        fail = _api_post(
            "/runs/" + run_id + "/fail",
            {"held_token": token_resumed, "reason": "flake"},
        )
        assert fail.status_code == 200, fail.text
        assert fail.json()["checkpoint"] == "CP_FAILED"

        enr = _api_post("/runs/" + run_id + "/enter-repair", {"held_token": token_resumed})
        assert enr.status_code == 200, enr.text

        disp = _api_post("/runs/" + run_id + "/dispatch-repair", {
            "held_token": token_resumed,
            "failure_class": "code_defect",
            "hypothesis": "retry once",
            "patch_sha": "restart-demo",
            "result": "resumed-after-restart",
        })
        assert disp.status_code == 200, disp.text
        assert disp.json()["repair_attempt_count"] == 1
        assert disp.json()["checkpoint"] == "CP_REPAIR_DISPATCHED"

        rp = _api_post("/runs/" + run_id + "/prepare-step", {"held_token": token_resumed})
        assert rp.status_code == 200, rp.text
        rc = _api_post("/runs/" + run_id + "/commit-step", {"held_token": token_resumed})
        assert rc.status_code == 200, rc.text
        passed = _api_post("/runs/" + run_id + "/pass", {"held_token": token_resumed})
        assert passed.status_code == 200, passed.text
        assert passed.json()["status"] == "PASSED"
        assert passed.json()["checkpoint"] == "CP_COMPLETED"

        # 6. Final event-sequence verification: contiguous, and the committed
        #    pre-crash milestone (prepare-step) was NOT replayed.
        events_final = _api_get("/runs/" + run_id + "/events").json()
        seqs = [e["sequence"] for e in events_final]
        assert seqs == list(range(1, len(seqs) + 1)), "non-contiguous sequences: " + str(seqs)
        assert [
            (e["sequence"], e["type"]) for e in events_final[: len(events_before)]
        ] == ev_before_ids, "Pre-crash events were replayed/altered during recovery."
        assert len(events_final) == len(events_before) + 7, (
            "expected exactly 7 post-restart events, got "
            + str(len(events_final) - len(events_before))
        )
        # The start event (sequence 1) must appear exactly once - no duplicate side effect.
        assert seqs.count(1) == 1
    finally:
        # Tear down the dedicated test project (test DB volume only).
        _compose(["down", "-v", "--remove-orphans"], root)
