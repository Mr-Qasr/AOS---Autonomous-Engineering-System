# AOS — Phase 7 Execution Packet: Independent Review

## Role
Cold start. Read `AOS_Master_Specification.pdf` + `STATE.md`. Confirm Phase 6's
exit condition (self-repair + repair-event log) is evidenced.

## Objective
Add a check that a green test suite cannot satisfy on its own: a second,
independent pass that can catch unnecessary changes, missed edge cases, and
bad assumptions — and can send work back for repair even after PASS-eligible
verification.

## Deliverables

- Review agent invoked after Phase 5's verification gate would otherwise
  allow PASS, before the Run reaches `READY`.
- **Independence matters**: use a different model route than the one that
  wrote the patch (Phase 3 gateway — e.g. implementer on `local`, reviewer on
  `free_api`, or vice versa), or at minimum a fresh context window with only
  the diff + task contract, not the implementer's chain-of-thought. Same
  model, same context = not independent, don't fake this.
- Review scope, concretely: does the diff match the allowed scope in the
  task contract? Are there unrelated file changes? Are there obvious missed
  edge cases given the acceptance criteria? Is anything suppressed rather
  than fixed (e.g. a disabled test, a broadened exception catch)?
- Findings recorded as `review.finding` events (Phase 0 catalog).
- Reject path: a rejection routes the Run back to `REPAIRING` (Phase 6),
  with the review finding as the repair hypothesis input — don't invent a
  new state, reuse the repair machinery.

## Explicitly out of scope
- No UI for findings yet (Phase 8)
- No multi-reviewer / voting scheme — one independent pass is enough for v1

## Exit condition
Reviewer can reject implementation: construct a patch that passes every
Phase 5 check but has a clear issue on inspection (e.g. touches an unrelated
file, or silently narrows a test's assertions instead of fixing the
underlying bug). Confirm the reviewer flags it via `review.finding` and the
Run does **not** reach `READY` — it goes back to `REPAIRING`.

## Validation commands
```bash
python3 -m aos.loop run --task-id <patch-with-planted-issue>
python3 -m aos.events list --run-id <id> --type review.finding
# confirm run.status != READY after this run
```

## Handoff Block
```markdown
## Phase 7 — Independent review
- Status:
- Reviewer independence mechanism used (different model / fresh context):
- Files created:
- Commands run / validated:
- Exit evidence (planted-issue rejection):
- Decisions made:
- Open questions for Phase 8:
```
