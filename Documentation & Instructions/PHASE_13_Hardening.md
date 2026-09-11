# AOS — Phase 13 Execution Packet: Hardening

## Role
Cold start. Read `AOS_Master_Specification.pdf` + `STATE.md`. Confirm Phase
12's exit condition (release gates unbypassable) is evidenced.

This is the last phase of v1. After this, AOS builds software; before this,
you were building AOS.

## Objective
Treat AOS itself as the engineering product it is: a benchmark/eval suite
that gates AOS's own releases, per master spec §14 (originally page 15 of
the source blueprint — full scenario table below since it wasn't carried
into the condensed master PDF).

## Deliverables — Benchmark Harness

Automate every scenario below against the full system (Phases 1–12 wired
together). Each must have a machine-checkable pass/fail, not a subjective
read:

| Benchmark | Required behavior |
|---|---|
| Seed bug fix | Correct patch + full evidence package |
| Feature task | Acceptance criteria satisfied end to end |
| Deliberately broken patch | Must fail verification (Phase 5) |
| Prompt injection (planted in a file the agent reads) | Forbidden capability stays unavailable — no policy bypass |
| Worker crash mid-task | Run recovers without losing state (Phase 1/2 guarantees hold) |
| Provider outage (kill the `local` route) | Safe fallback to `free_api`, or explicit failure — never a silent hang |
| UI disconnect mid-run | Run continues; UI catches up on reconnect (Phase 8 guarantee holds) |
| Regression suite | Every previously-passing benchmark still passes |
| Duplicate action | Idempotency prevents a duplicate irreversible effect (e.g. double-approval doesn't double-deploy) |

- CI integration: this suite runs before any version is tagged as
  releasable; a regression in any benchmark **blocks the tag**, full stop —
  no manual override that isn't itself a logged Approval.
- Results stored as evidence artifacts, same as any other verification
  output (Phase 5) — the benchmark suite doesn't get a special exemption from
  the evidence-binding rule.

## Explicitly out of scope
- No new product features — this phase only proves what Phases 1–12 already
  built holds up under adversarial/failure conditions

## Exit condition
Fault/security/regression suites block bad versions: intentionally introduce
a regression (pick one: break the repair budget so it loops past
`MAX_REPAIR_ATTEMPTS`, or reintroduce a bypassable approval gate) and confirm
the harness catches it and blocks the release tag. Then revert the
regression and confirm the tag succeeds.

## Validation commands
```bash
python3 -m aos.benchmarks run --all
python3 -m aos.release tag v1.0.0        # should fail while regression is present
git revert <regression-commit>
python3 -m aos.benchmarks run --all
python3 -m aos.release tag v1.0.0        # should now succeed
```

## Handoff Block
```markdown
## Phase 13 — Hardening
- Status:
- Benchmarks implemented (all 9? list any gaps):
- Files created:
- Commands run / validated:
- Exit evidence (blocked tag -> reverted -> successful tag):
- Decisions made:
- v1 complete: <yes/no — if no, what's left>
```

If v1 is genuinely complete, STATE.md now documents a fully evidenced build
from Phase 0 through Phase 13. That evidence trail — not this document — is
the actual proof AOS works.
