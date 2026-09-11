# AOS — Phase 0 Execution Packet: Contracts + Threat Model

## Role

You are the execution agent for **Phase 0 of the AOS build**. You are working
cold — you were not part of the design conversation. Everything you need is in
this packet plus the attached `AOS_Master_Specification.pdf`. Read the PDF
first if attached; if it wasn't attached, ask for it before proceeding — do
not guess at the architecture.

Check `STATE.md` (pasted below your instructions). Phase 0 has no
predecessor, so there is nothing to verify — but confirm STATE.md is in fact
empty/new before starting. If it already has a filled Phase 0 section, stop
and tell the user Phase 0 already ran.

## Context recap (condensed — full detail is in the PDF)

AOS is a self-hosted, FOSS-only autonomous software-engineering system. It
researches, plans, codes, tests, debugs, reviews, and hardens work in a
durable loop, and never claims completion without evidence. A policy engine —
not the agent — decides what actions are executable. Nothing in later phases
(FastAPI app, workers, model gateway, UI) can be built correctly until the
contracts below exist and are unambiguous.

## Objective

Produce the **authority and state contracts** for the whole system: the data
schemas, the state machines, the event catalog, and the policy rule format —
plus a threat model showing every dangerous action is covered by a policy
rule. Nothing here executes anything. This is the constitution the rest of
the system is built against.

## Locked decisions for this phase

- Language: Python 3.12+
- Schema library: **Pydantic v2** models, each exporting JSON Schema
- Repo tool: Git (initialize the repo in this phase)
- No web framework, no database, no Docker yet — those are Phase 1–2

## Deliverables (create all of these)

1. **Git repository skeleton**
   ```
   aos/
     contracts/
       __init__.py
       task.py
       run.py
       artifact.py
       event.py
       approval.py
       policy.py
       worker.py
     docs/
       threat_model.md
       state_machines.md
     tests/
       test_contracts.py
   README.md
   .gitignore
   ```

2. **Pydantic models** for these 7 objects (minimum fields — add fields only
   if a field is clearly required to make the object usable, and note why):

   | Object | Minimum fields |
   |---|---|
   | Task | id, objective, requirement_version, acceptance_criteria, policy_id, status |
   | Run | id, task_id, workflow_version, worker_id, model_route, status, started_at, updated_at |
   | Artifact | id, type, producer, uri, sha256, run_id |
   | Event | id, run_id, sequence, type, timestamp, actor, payload |
   | Approval | id, action, evidence_refs, actor, scope, expiry, decision |
   | Policy | id, version, rules (list of {principal, action, resource, effect, conditions}) |
   | Worker | id, capabilities, health, lease_expiry, cost_metadata |

3. **State machines** (`docs/state_machines.md` + enforced via Pydantic
   validators or a small `transitions.py` helper — your call, document which):

   - **Task status**: `DRAFT → LOCKED → IN_PROGRESS → BLOCKED → READY → RELEASED`,
     plus `ABANDONED` reachable from any non-terminal state.
   - **Run status**: `QUEUED → RUNNING → (PASSED | FAILED)`, `FAILED → REPAIRING → RUNNING`,
     `REPAIRING → ESCALATED` after a bounded retry budget (make the budget a
     named constant, not a magic number), `RUNNING → CANCELLED` reachable at
     any point before a terminal state.
   - Every transition must be a named function, not a raw field assignment.
     Illegal transitions must raise, not silently no-op.

4. **Event catalog** (`contracts/event.py` — a `StrEnum` or `Literal` type):
   `run.state.changed`, `agent.started`, `tool.requested`, `tool.completed`,
   `test.completed`, `review.finding`, `approval.requested`,
   `approval.decided`, `run.failed`, `run.completed`, `repair.attempt`.
   `repair.attempt` payload must include `failure_class`, `hypothesis`,
   `patch_sha`, `result` — this is a hard requirement from the master spec's
   self-repair rule (§6): every repair attempt must be traceable.

5. **Policy rule format** — principal / action / resource / effect
   (allow|deny) / conditions. Write 10 concrete policy rules in
   `docs/threat_model.md` covering every row of this table (from master spec
   §8):

   | Action | Default |
   |---|---|
   | Read project repo | Allowed in project scope |
   | Write code | Task branch/workspace only |
   | Terminal | Sandboxed + resource/command policy |
   | Network | Deny by default; allow required domains |
   | Inbound ports | Deny, no exceptions |
   | Secrets access | Just-in-time, narrow scope, redacted |
   | Protected merge | Requires Approval object |
   | Production deploy | Requires Approval object |
   | Paid compute | Requires budget check + Approval object |
   | Destructive operation | Requires Approval object |

6. **Threat model doc** (`docs/threat_model.md`) — for each action above,
   write: what happens if the policy engine is bypassed (attacker model:
   the coding agent itself, not an external attacker — the agent is the
   thing being contained), and which policy rule prevents it. Use a simple
   STRIDE label per row if it fits; don't force it where it doesn't.

7. **Tests** (`tests/test_contracts.py`): every model round-trips through
   JSON Schema, every illegal state transition raises, every action in the
   policy table maps to at least one rule in your sample policy file.

## Explicitly out of scope for this phase

- No FastAPI app, no HTTP endpoints
- No actual database — schemas only, no persistence layer
- No Docker/sandbox implementation
- No model calls of any kind
- Do not start Phase 1 work even if it seems easy to bolt on

## Exit condition (must be true before you write the Handoff Block)

- `git log` shows an initial commit with the skeleton above
- `pytest tests/` passes
- Every action in the Phase 0 policy table has a corresponding rule and a
  threat-model entry — no gaps
- Illegal state transitions demonstrably raise (show the test)

## Validation commands

```bash
cd aos
python3 -m pytest tests/ -v
python3 -c "from contracts.task import Task; print(Task.model_json_schema())"
git log --oneline
```

## Handoff Block — fill this in and give it to the user verbatim

```markdown
## Phase 0 — Contracts + threat model
- Status: <done | blocked>
- Files created: <list>
- Commands run / validated: <paste actual output of the validation commands>
- Exit evidence: <confirm each bullet above is true, with proof>
- Decisions made: <e.g. how state transitions are enforced, any field you added beyond the minimum and why>
- Open questions for Phase 1: <anything Phase 1 needs to know — e.g. exact Policy storage format, any ambiguity you resolved by assumption>
```

If you cannot fully satisfy the exit condition, say so explicitly in the
Handoff Block instead of marking it done. That failure mode — claiming done
without evidence — is the one thing this entire system exists to prevent,
starting with itself.
