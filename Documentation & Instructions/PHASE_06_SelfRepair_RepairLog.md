# AOS — Phase 6 Execution Packet: Self-Repair + Repair-Event Log

## Role
Cold start. Read `AOS_Master_Specification.pdf` + `STATE.md`. Confirm Phase 5's
exit condition (verification gate blocks broken patches) is evidenced.

## Objective
Turn a FAILED Run into a bounded, traceable repair attempt instead of a dead
end. This is the "patient machine, not a reckless machine" property — and the
phase with the highest audit risk in the whole build (silent repair loops).

## Deliverables

- Failure classifier consuming verification-gate output (Phase 5) and
  producing one of: `code_defect`, `test_defect`, `environment_defect`,
  `flaky_test`, `tool_failure`, `model_failure`, `requirement_conflict`,
  `security_policy_failure`.
- Response per class (master spec §6 table):

  | Class | Action this phase implements |
  |---|---|
  | code_defect | reproduce → localize → repair → rerun focused test |
  | test_defect | inspect assumptions → repair test, or escalate if contract changed |
  | environment_defect | separate from code_defect explicitly — do not attempt a code repair |
  | flaky_test | rerun within a **named, finite** flake budget constant — never silently mark passed without a real pass |
  | tool_failure | retry once, then fallback route, then escalate |
  | model_failure | reframe/reduce context or switch model route (Phase 3 gateway) if policy allows |
  | requirement_conflict | stop this Run's affected work, raise for human decision — do not guess |
  | security_policy_failure | never bypass — escalate immediately, no retry |

- **Hard requirement**: every single repair attempt — successful or not —
  emits a `repair.attempt` event (Phase 0 catalog) with `failure_class`,
  `hypothesis`, `patch_sha`, `result` populated. A repair with no event is a
  bug in this phase, not an acceptable shortcut.
- Bounded retry budget: a named constant (e.g. `MAX_REPAIR_ATTEMPTS`), Run
  transitions `REPAIRING → ESCALATED` when exceeded, never loops forever.
- Wire into Run state machine from Phase 0/1: `FAILED → REPAIRING → RUNNING`,
  `REPAIRING → ESCALATED`.

## Explicitly out of scope
- No independent review (Phase 7)
- No UI visibility into repair attempts yet (Phase 8) — the event log is
  enough for this phase; don't build a dashboard here

## Exit condition
Seeded failure repaired automatically, fully logged: seed a `code_defect`,
confirm the loop repairs it without human input and every attempt has a
matching `repair.attempt` event. Separately, seed an unrepairable defect,
confirm the Run reaches `ESCALATED` after the budget — not an infinite loop.

## Validation commands
```bash
python3 -m aos.loop run --task-id <seeded-repairable-bug>
python3 -m aos.events list --run-id <id> --type repair.attempt
python3 -m aos.loop run --task-id <seeded-unrepairable-bug>
# confirm status == ESCALATED and attempt count == MAX_REPAIR_ATTEMPTS, not more
```

## Handoff Block
```markdown
## Phase 6 — Self-repair + repair-event log
- Status:
- MAX_REPAIR_ATTEMPTS value chosen and why:
- Files created:
- Commands run / validated:
- Exit evidence (repairable + unrepairable cases):
- Decisions made:
- Open questions for Phase 7:
```
