# AOS — Phase 12 Execution Packet: Release Gates

## Role
Cold start. Read `AOS_Master_Specification.pdf` + `STATE.md`. Confirm Phase
11's exit condition (remote worker over mesh, zero open ports) is evidenced.

## Objective
Make the Phase 0 policy table's consequential actions actually unbypassable
— not just documented, enforced, with an adversarial test proving it.

## Deliverables

- Approval-gate enforcement wired to the exact actions from Phase 0's policy
  table: protected merge, production deploy, paid compute, destructive
  operation. Each requires a matching `Approval` object (Phase 0 contract)
  with valid, non-expired scope before the action executes.
- The check happens in the policy engine layer, not inside the agent loop —
  per master spec §8's invariant, the agent may request, only policy decides.
- Budget check for paid compute: a numeric budget ceiling that blocks
  execution outright if exceeded, independent of approval (approval can
  raise the ceiling, but a request can't silently exceed it).
- **Adversarial test suite**: for each gated action, have the agent
  deliberately attempt it without a valid Approval object, and confirm it is
  blocked at the policy layer — not merely discouraged by a prompt
  instruction. Prompt-level "please don't" is not a control; this phase
  proves the control exists below the model.

## Explicitly out of scope
- No production deployment tooling itself (CI/CD pipelines, etc.) — this
  phase gates the *decision*, not the mechanics of deploying
- No UI for approvals beyond what's needed to grant/deny in the test

## Exit condition
Consequential action cannot bypass approval: for every gated action, an
attempt without approval is blocked; the same attempt with a valid Approval
object succeeds. Both halves must be demonstrated — a system that blocks
everything isn't proven, only a system that blocks exactly the ungranted
case and allows the granted one.

## Validation commands
```bash
pytest tests/test_release_gates.py -v
# each gated action: one test without approval (expect block),
# one test with approval (expect success)
python3 -m aos.policy attempt --action deploy_production --run-id <id>   # no approval -> blocked
python3 -m aos.approvals grant --action deploy_production --run-id <id>
python3 -m aos.policy attempt --action deploy_production --run-id <id>   # now succeeds
```

## Handoff Block
```markdown
## Phase 12 — Release gates
- Status:
- Gated actions tested:
- Files created:
- Commands run / validated:
- Exit evidence (blocked + granted pairs for each action):
- Decisions made:
- Open questions for Phase 13:
```
