# AOS — Phase 9 Execution Packet: Research → Requirements

## Role
Cold start. Read `AOS_Master_Specification.pdf` + `STATE.md`. Confirm Phase 8's
exit condition (event stream + graph UI working) is evidenced.

Note: this phase's data model is **not** in the master PDF — it's specified
here in full, taken from the original source blueprint. Treat this packet as
authoritative for Phase 9.

## Objective
Build the front end of the pipeline: turn a vague idea into a versioned,
locked requirement spec that later phases' loop can execute against — with
the machine doing evidence-gathering and only escalating genuine product
decisions to you.

## Deliverables

- **Research Packet** artifact (new Artifact type, Phase 0 contract), with
  these fields:

  | Field | Contents |
  |---|---|
  | Problem | what is being built and why |
  | Facts | evidence-backed findings (must cite a source, even if it's "existing codebase, file X") |
  | Unknowns | questions that could change the product if answered differently |
  | Feasibility | technical, cost, privacy, operational constraints |
  | Options | viable approaches |
  | Trade-offs | benefits/drawbacks/consequences per option |
  | Risks | security, maintenance, delivery risks |
  | Questions | **only** the decisions that require your authority — the machine must not ask about things it can decide itself |

- **Requirement Lock** — a versioned, append-only spec object. Locking
  produces version N; a later change produces version N+1, never mutates N in
  place. Store the version chain, not just the latest.
- Re-plan trigger: if a locked requirement changes, any Task referencing the
  old version is flagged for re-planning — it does not silently continue
  against a stale spec.
- Minimal UI/CLI to answer the "Questions" field and trigger the lock.

## Explicitly out of scope
- No automated market research or external data scraping infra — "Facts"
  can cite the existing repo/spec for this phase's proof; broader research
  tooling is not required here
- No memory/retrieval system yet (Phase 10) — the Requirement Lock is stored
  but not yet used for cross-task retrieval

## Exit condition
Evidence → questions → locked spec: run the pipeline on a toy feature idea,
produce a Research Packet with all fields populated, get the "Questions"
answered by you, produce a Requirement Lock v1. Then change your mind on one
point and confirm it produces v2 (not an edited v1) and flags any Task on v1
for re-plan.

## Validation commands
```bash
python3 -m aos.research start --idea "toy feature"
python3 -m aos.research lock --packet-id <id>       # -> Requirement v1
python3 -m aos.research lock --packet-id <id> --amend  # -> Requirement v2
python3 -m aos.tasks list --requirement-version 1   # should show re-plan flag
```

## Handoff Block
```markdown
## Phase 9 — Research + requirements
- Status:
- Files created:
- Commands run / validated:
- Exit evidence (v1 -> v2 + re-plan flag):
- Decisions made:
- Open questions for Phase 10:
```
