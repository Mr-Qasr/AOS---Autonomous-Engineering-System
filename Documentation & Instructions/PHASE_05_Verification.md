# AOS — Phase 5 Execution Packet: Verification Gate

## Role
Cold start. Read `AOS_Master_Specification.pdf` + `STATE.md`. Confirm Phase 4's
exit condition (one toy bug fixed end-to-end) is evidenced.

## Objective
Replace "the loop says it passed" with a real, multi-check verification gate.
Per master spec §7 — this is the core quality mechanism of the entire system.

## Deliverables

Implement each check as an independent, pluggable verifier, all bound to the
exact commit SHA under test:

| Check | Minimum implementation this phase |
|---|---|
| Requirement coverage | Map each acceptance-criterion line to at least one test or explicit manual-check artifact |
| Unit/integration tests | Run project test suite, capture pass/fail per test |
| Build/type/lint | Run the project's actual linter/type-checker if present; if the sample repo has none, add a minimal one (e.g. ruff + mypy) so this check has something real to do |
| Behavioral/E2E | Stub acceptable for now — a single smoke-test script counts, don't over-build this early |
| Security | Run a dependency/secret scan (e.g. `pip-audit`, `gitleaks` or equivalent OSS tool) |
| Regression | Re-run the full existing suite, not just the focused subset from Phase 4 |
| Independent review | **Not this phase** — Phase 7. Leave a clear stub/TODO, don't half-build it here |
| Environment binding | Every check result stores the exact git SHA it ran against; a check run against a different SHA than the current HEAD is invalid, not just stale |

- PASS transition (Phase 0's Run state machine) is gated on **every**
  required check passing with evidence bound to the current SHA — wire this
  into the actual state-transition function, not a comment/convention.

## Explicitly out of scope
- No auto-repair when a check fails (Phase 6) — a failing check just blocks
  PASS and reports which check failed
- No independent review implementation (Phase 7) — stub only

## Exit condition
Broken patch cannot become PASS: deliberately introduce a broken patch (a
failing test, then separately a lint violation, then separately a stale-SHA
evidence record) and confirm the system refuses PASS each time, naming the
specific failing check — not a generic failure.

## Validation commands
```bash
pytest tests/test_verification_gate.py -v
# three deliberate-failure fixtures: failing test, lint error, stale SHA
python3 -m aos.verify run --run-id <id>   # should print which check(s) blocked PASS
```

## Handoff Block
```markdown
## Phase 5 — Verification
- Status:
- Checks implemented:
- Files created:
- Commands run / validated:
- Exit evidence (three deliberate-failure results):
- Decisions made:
- Open questions for Phase 6:
```
