# AOS — Phase 10 Execution Packet: Memory

## Role
Cold start. Read `AOS_Master_Specification.pdf` + `STATE.md`. Confirm Phase 9's
exit condition (research → locked requirement) is evidenced.

## Objective
Give the loop (Phase 4/6) access to validated knowledge across tasks —
without adding a vector database on faith. Master spec §4/11: Postgres
first, vector only if proven.

## Deliverables

- Memory schema (Postgres tables): versioned requirements (from Phase 9),
  decisions, validated postmortems (a structured record of a resolved
  repair — failure class, root cause, fix, from Phase 6's repair.attempt
  history), repository facts (conventions, key file locations — derived,
  not guessed).
- Retrieval API used by the Phase 4 loop's OBSERVE step: given a new task,
  return relevant prior decisions/postmortems/facts.
- **Evidence gate before adding anything beyond Postgres retrieval**: run an
  evaluation — same toy task run twice, once with memory retrieval enabled,
  once without. If retrieval doesn't measurably change the plan or reduce
  repair attempts, do not add a vector component. Document the result either
  way in STATE.md. This is the system's own "no false completion" rule
  applied to its own build: don't add a component on the assumption it helps.
- If (and only if) the evaluation shows Postgres full-text/structured
  retrieval is insufficient, add a minimal vector store (pgvector extension,
  not a separate custom vector DB — master spec explicitly cuts that) and
  re-run the same evaluation to prove it helps.

## Explicitly out of scope
- No large memory platform, no automatic summarization pipeline beyond what's
  needed to store a postmortem
- Unverified model opinions, secrets, and temporary debug output never enter
  memory — enforce this at the write path, not by convention

## Exit condition
Validated knowledge retrieval: demonstrate a task where a previously stored
decision or postmortem actually changes the loop's plan step (visible in the
PLAN artifact from Phase 4) — not just stored-and-ignored.

## Validation commands
```bash
python3 -m aos.memory eval --task-id <toy-task> --with-memory
python3 -m aos.memory eval --task-id <toy-task> --without-memory
diff <(cat plan_with.json) <(cat plan_without.json)   # must differ meaningfully
```

## Handoff Block
```markdown
## Phase 10 — Memory
- Status:
- Vector store added? (yes/no + evaluation evidence):
- Files created:
- Commands run / validated:
- Exit evidence (plan diff with vs without memory):
- Decisions made:
- Open questions for Phase 11:
```
