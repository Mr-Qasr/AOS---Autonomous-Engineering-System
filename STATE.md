# AOS STATE

## Project Status
- Current phase: 0
- Phase 0 status: COMPLETED
- Last verified commit: e45138cb397f5db1973984071582b80fb6c23371
- Build status: PHASE 0 COMPLETE

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
  - Phase 1 has NOT been started.
  - Next phase: Phase 1 (FastAPI + PostgreSQL + workflow controller).
