# AOS — Phase 1 Execution Packet: FastAPI + PostgreSQL + Workflow Controller

## Role
Cold start. Read `AOS_Master_Specification.pdf` + current `STATE.md` first.
Confirm Phase 0's exit condition is evidenced in STATE.md (contracts committed,
tests passing, threat model complete). If not, stop and say so.

## Objective
Give the Phase 0 contracts a real backend: FastAPI app + PostgreSQL
persistence, and resolve the one decision the master spec left open — the
workflow controller.

## Decision gate — resolve this FIRST, before writing app code

| Option | Pro | Con |
|---|---|---|
| Temporal (self-hosted OSS) | Durable execution is proven/battle-tested; retries, timers, signals built in | Extra service to run/operate solo; steeper learning curve |
| Custom asyncio + Postgres controller | Minimal moving parts, full control, easy to debug solo | You are building durability primitives yourself — must be proven, not assumed |

Pick one. Write the reasoning into STATE.md under Phase 1 "Decisions made"
before writing any workflow code. Either choice must satisfy: **a Run's state
survives a process kill and resumes correctly on restart** — that's the exit
condition, not the choice of tool.

## Deliverables

1. FastAPI app (`aos/api/`) with CRUD endpoints for Task, Run, Event,
   Approval, Worker (from Phase 0 contracts) — Pydantic request/response
   models reused directly from `contracts/`.
2. PostgreSQL schema + migrations (Alembic). Tables mirror the Phase 0
   contract objects; Event table is append-only (no UPDATE/DELETE — enforce
   at the DB layer, not just app layer).
3. Workflow controller implementation per your Phase 1 decision above,
   wired to advance Run/Task state machines from Phase 0 (only through the
   named transition functions — no raw status writes).
4. `docker-compose.yml` for local Postgres (+ Temporal if chosen).
5. Restart-recovery test: start a Run, kill the API process (and workflow
   worker if Temporal) mid-run, restart, confirm the Run resumes from its
   last durable state rather than restarting or vanishing.

## Explicitly out of scope
- No agent loop, no model calls, no sandbox/worker execution yet (Phase 2–4)
- No auth/multi-user
- No frontend

## Exit condition
State survives restart: kill and restart the stack, a Run in progress
continues from its last known state, no data loss, no duplicate side effects.

## Validation commands
```bash
docker compose up -d
alembic upgrade head
pytest tests/ -v
# create a task, start a run, then:
docker compose kill api        # or the workflow worker
docker compose up -d api
# confirm run status + event history intact via GET /runs/{id}
```

## Handoff Block
```markdown
## Phase 1 — FastAPI + PostgreSQL + workflow controller
- Status:
- Workflow controller chosen: <Temporal | custom> — reasoning:
- Files created:
- Commands run / validated:
- Exit evidence (restart test output):
- Decisions made:
- Open questions for Phase 2:
```
If the restart test doesn't hold cleanly, say so — don't mark this done on a
partial pass.
