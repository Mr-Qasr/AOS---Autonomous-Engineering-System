# AOS — Phase 4 Execution Packet: Single Coding Loop

## Role
Cold start. Read `AOS_Master_Specification.pdf` + `STATE.md`. Confirm Phase 3's
exit condition (gateway + MCP tools working) is evidenced.

## Objective
The first real milestone: one agent, one task contract, one toy bug, fixed
end to end — no repair, no review, no multi-agent anything yet.

## Deliverables

- Task contract ingestion: given a `Task` (Phase 0 contract) with an
  objective + acceptance criteria + repo snapshot + allowed scope, produce a
  `Run`.
- Loop implementation, exactly per master spec §6, truncated (no repair
  branch yet):
  ```
  OBSERVE -> PLAN -> EDIT -> FOCUSED TEST -> PASS? --yes--> done
                                    |no
                              report FAILED, stop (no auto-repair yet)
  ```
- OBSERVE: inspect repo structure/conventions/existing tests before editing
  (use MCP `read_file`, not a raw file dump into context — respect context
  budget).
- PLAN: a short explicit plan artifact (store as an Event payload or
  Artifact), not just an implicit chain-of-thought that disappears.
- EDIT: smallest coherent change satisfying the contract, via MCP
  `write_file` + `git_commit` on a task branch — no unrelated cleanup.
- FOCUSED TEST: run only the tests relevant to the change first (don't run
  the full suite yet — that discipline matters for later phases too).
- Seed one toy bug in a small sample repo (you create this sample repo as
  part of the deliverable) for the end-to-end proof.

## Explicitly out of scope
- No failure classification, no diagnose/repair loop (Phase 6)
- No independent review (Phase 7)
- No event streaming to a UI (Phase 8)
- If the loop fails, it reports FAILED and stops — that's correct behavior
  for this phase, not a bug to fix here

## Exit condition
Toy issue → branch → patch → tests: a seeded bug in the sample repo is fixed
by the loop, on its own branch, with the relevant test passing — verified by
you, not just claimed by the loop.

## Validation commands
```bash
python3 -m aos.loop run --task-id <seeded-task-id>
git -C sample_repo log --oneline task/<id>
git -C sample_repo diff main task/<id>
pytest sample_repo/tests/test_seeded_bug.py -v
```

## Handoff Block
```markdown
## Phase 4 — Single coding loop
- Status:
- Sample repo + seeded bug description:
- Files created:
- Commands run / validated:
- Exit evidence (diff + test output):
- Decisions made:
- Open questions for Phase 5:
```
