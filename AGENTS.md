# AOS Agent Operating Rules

## Mission

Build AOS according to `Documentation & Instructions/AOS_Master_Specification.pdf`
and the current phase packet.

AOS is a controlled, self-hosted, FOSS-only autonomous software-engineering system.
It must not claim completion without verified evidence.

## Mandatory Operating Rules

1. Read `STATE.md` before doing any implementation work.
2. Read the Master Specification before beginning a new phase.
3. Read the current Phase Packet completely before implementation.
4. Confirm the previous phase exit condition is evidenced in `STATE.md`.
5. If the previous exit condition is not evidenced, STOP. Do not guess or proceed.
6. Work only within the current phase's explicit scope.
7. Do not perform unrelated cleanup or scope expansion.
8. Preserve existing working behavior unless the current phase requires a change.
9. Validate changes with the phase's specified tests and commands.
10. Never report a phase as complete without actual evidence.
11. Record important implementation decisions and unresolved questions in the phase handoff.
12. Keep code truth in Git.
13. Use task branches for implementation work once the project structure requires them.
14. Do not bypass security, policy, approval, budget, or sandbox boundaries.
15. Never treat an agent's own claim of success as verification.

## Authority Boundary

The human operator is the final release authority.

An agent may propose or request an action, but it must never assume authority over:

- protected merges
- production deployment
- paid compute
- destructive operations
- unrestricted secrets
- policy overrides
- inbound network exposure

## Verification Rule

A task is not READY merely because an implementation appears correct.

Required checks must produce evidence tied to the exact code state and environment.

## Self-Repair Rule

Every self-repair attempt must produce a `repair.attempt` event before the next repair action executes.

Silent repair cycles are prohibited.

## Phase Discipline

The phases are sequential:

0. Contracts + threat model
1. FastAPI + PostgreSQL + workflow
2. Installer + worker + sandbox
3. Model gateway + MCP
4. Single coding loop
5. Verification
6. Self-repair
7. Independent review
8. Event stream + graph UI
9. Research + requirements
10. Memory
11. Remote worker mesh
12. Release gates
13. Hardening

Do not start a later phase because its implementation appears convenient.

## Communication

When blocked:

- state exactly what is blocking progress
- provide the evidence
- do not silently work around the constraint

When completing a phase:

- report files created or changed
- report commands executed
- report actual validation results
- report exit-condition evidence
- report decisions made
- report open questions for the next phase
