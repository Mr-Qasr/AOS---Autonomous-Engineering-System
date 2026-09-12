# AOS STATE

## Project Status
- Current phase: 1
- Phase 0 status: COMPLETED
- Phase 1 status: COMPLETED (this commit)
- Last verified commit: 37512c9 (Phase 0 completion base); Phase 1 verified against this Phase 1 commit's exact tree (69/69 tests + fresh-DB migration validation)
- Build status: PHASE 1 COMPLETE

## Build Rules
- Phases are strictly sequential.
- Never claim completion without evidence.
- Never proceed past an unmet phase exit condition.
- The human operator retains release authority.
- Agents may request consequential actions; the policy engine decides whether they execute.
- Every self-repair attempt must emit a `repair.attempt` event before the next action.
- Evidence must be bound to the exact code state and environment.

## Phase Handoffs

### Phase 0 — Contracts + Threat Model
- Status: COMPLETED
- Verified commit: e45138cb397f5db1973984071582b80fb6c23371
- Implementation summary:
  - Created root packaging (`pyproject.toml`, `README.md`, updated `.gitignore`).
  - Implemented 7 core immutable Pydantic v2 domain contracts in `aos/contracts/`: `Task`, `Run`, `Artifact`, `Event`, `Approval`, `Policy`, `Worker`.
  - Implemented pure functional transition engine in `aos/contracts/transitions.py` producing `TransitionResult[EntityT, EventPayloadT]`.
  - Enforced exact repair attempt accounting semantics: `FAILED -> REPAIRING` does not consume an attempt; `REPAIRING -> RUNNING` commits an attempt, increments `repair_attempt_count`, generates `RepairAttemptPayload`, and enforces `MAX_REPAIR_ATTEMPTS=3`.
  - Enforced approval reference carriage boundary in `transition_task_release(task, approval_id)` without Phase 0 authorization/validity checks.
  - Authored comprehensive documentation in `aos/docs/threat_model.md` (agent containment, STRIDE categorization, Master Spec §8 mapping) and `aos/docs/state_machines.md`.
  - Created reference `aos/docs/sample_policy.json` covering all 10 consequential actions.
  - Implemented comprehensive 24-test suite in `aos/tests/test_contracts.py`.
- Validation commands & results:
  - `.\.venv\Scripts\python.exe -m pytest aos/tests/ -v`: 24 passed in 0.19s (100% pass rate).
  - `.\.venv\Scripts\python.exe -c "from aos.contracts.task import Task; ... Task.model_json_schema()"`: Clean JSON schema exported.
  - Canonical imports verified: `from aos.contracts.<module> import <Class>`.
- Exit evidence:
  - Immutability enforced: Direct mutation raises Pydantic `ValidationError`.
  - Illegal state transitions demonstrably raise `InvalidStateTransitionError`.
  - Repair accounting semantics verified: counter increments only on dispatch, persists on subsequent failures, and blocks dispatch at budget ceiling.
  - Sample policy covers all 10 Master Spec §8 actions with zero gaps.
- Known limitations & boundary discipline:
  - No database or persistence layer built (deferred to Phase 1).
  - No FastAPI or HTTP endpoints built (deferred to Phase 1).
  - No workflow orchestration (Temporal/asyncio) built (deferred to Phase 1).
  - No policy evaluation or approval authorization engine built (deferred to Phase 12).
  - No model invocation, sandbox execution, or repair loop runners built (Phases 2-6).
- Phase 1 confirmation:
  - Phase 1 is completed in the commit that carries this handoff (see Phase 1 handoff below).

### Phase 1 — FastAPI + PostgreSQL + workflow controller
- Status: COMPLETED
- Workflow controller chosen: **custom asyncio + PostgreSQL** — reasoning: minimal
  moving parts for a solo-operated, FOSS-only system; no extra coordination service
  to run. Durability primitives were therefore built and proven rather than assumed:
  SELECT FOR UPDATE row locking, fencing tokens, a frozen checkpoint DAG, and a
  DB-enforced append-only event log.
- Files created:
  - `aos/api/` — FastAPI app, deps, routers (tasks, runs, events, approvals, workers).
  - `aos/db/` — async engine, ORM models, Alembic `env.py` + `0001_initial_schema.py`
    (6 tables, constraints, indexes, `trg_events_no_update_delete` append-only trigger).
  - `aos/services/` — `RunService`, `TaskService` (application command boundary).
  - `aos/workflow/` — `RunRepository` (authoritative transaction boundary),
    `LeaseManager`, `IdempotencyStore`, checkpoint DAG, `CheckpointMetadata`.
  - `aos/tests/` — 45 Phase 1 tests incl. `test_process_restart.py` (container
    kill/restart) and a schema-drift check.
  - `Dockerfile`, `docker-compose.yml`, `docker-compose.test.yml`, `alembic.ini`,
    `.env.example`; `pyproject.toml` server/dev dependency groups.
- Commands run / validated:
  - `alembic upgrade head` from a fresh database: creates all tables, constraints,
    indexes, append-only trigger; `alembic_version` at head.
  - `python -m pytest aos/tests/ -v`: **69 passed** (24 Phase 0 regression + 45
    Phase 1), 0 failed, 0 skipped, against live PostgreSQL 16.
  - `docker compose up -d --build` (dev stack) and the dedicated test stack
    (`aos-test`, ports 5433/8001, fresh volume): DB healthy, API starts, migrations
    run, `/health` responds.
- Exit evidence (restart test output) — **container-level process termination/recovery**:
  - `aos/tests/test_process_restart.py::test_process_restart_recovery` drives the real
    HTTP API: create Task/Run → start → prepare-step (durable `CP_STEP_PREPARED`,
    checkpoint_seq and events recorded) → `docker compose kill api` (container
    confirmed stopped via `docker inspect`) → `docker compose up -d api` → `/health`
    ready → same Run read back from PostgreSQL with checkpoint, checkpoint_seq,
    repair_attempt_count, and event history unchanged → new lease acquired
    (fencing token +1, dead controller's token invalidated) → Run resumes (not
    replays): commit-step → fail → enter-repair → dispatch-repair (counter 0→1) →
    prepare → commit → pass → `PASSED`/`CP_COMPLETED`, event sequence contiguous,
    pre-crash events byte-identical, start event appears exactly once.
  - Scope of this evidence: the API **container** is terminated and restarted while
    PostgreSQL (separate container) keeps running. Bare-metal OS-level crash testing
    was not exercised.
  - Session-level tests additionally prove PostgreSQL transaction rollback
    (crash-before-commit) and recovery-from-checkpoint across controller identity
    change (`test_restart_recovery.py`).
- Decisions made:
  - PostgreSQL is authoritative; the controller is disposable. No correctness
    depends on in-memory state.
  - API transport schemas (`RunCreateRequest`, `RunTransitionRequest`, `RunResponse`,
    etc.) are intentionally separate from the immutable Phase 0 domain contracts.
    Domain objects remain authoritative for state semantics; no business rules are
    duplicated in the transport layer — all Run mutations resolve through named
    Phase 0 transition functions inside the repository transaction boundary.
  - Idempotency scope `(resource_type, idempotency_key)` + persisted request hash.
    Same key + same hash after completion → cached result; same key + different
    hash → HTTP 409; concurrent identical first-use → exactly one executes, the
    other receives a deterministic conflict (wait-and-cached-result is deferred).
    Wired end-to-end on `POST /runs/{id}/start`; idempotent completion is recorded
    in the same transaction as the Run transition. This is NOT an exactly-once
    external-side-effect guarantee — external actions are not exercised in Phase 1.
  - Terminal invariant: every terminal Run has no active lease (`cancel` releases
    it in-transaction, consistent with `pass`/`escalate`).
  - Repair checkpoint metadata `attempt_number` is resolved against the
    post-transition Run, so durable metadata always matches `repair_attempt_count`
    (FAILED→REPAIRING: no increment; REPAIRING→RUNNING via dispatch: +1 exactly once).
- Open questions for Phase 2:
  - Durable external-action persistence/reconciliation (action-token boundary only
    in Phase 1; `CheckpointMetadata.action_token` is never populated yet).
  - Wait-and-cached-result semantics for concurrent identical idempotent requests.
  - Optionally bare-metal process-crash testing beyond container restart.
