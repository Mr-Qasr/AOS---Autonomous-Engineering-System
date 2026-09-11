# AOS Build Index

This file is the manifest for the whole build. Keep it and `STATE.md` open in
every new chat window alongside the current Phase Packet.

## How this works (read this once)

1. Each phase = one Phase Packet file (`PHASE_NN_*.md`).
2. Open a **new** Claude chat. Paste, in this order:
   - `AOS_Master_Specification.pdf` (attach it)
   - `STATE.md` (paste its current contents — empty on Phase 0)
   - `PHASE_NN_*.md` for the phase you're starting
3. Tell the new chat: *"Execute this phase packet. Read STATE.md first and confirm the prior phase's exit condition before doing anything else."*
4. When that chat finishes, it will give you a filled-in **Handoff Block**. Append it to your local `STATE.md`.
5. Download whatever code/files that chat produced, drop them into your local repo in VS Code, commit.
6. Come back here, request the next Phase Packet, repeat.

Never skip the STATE.md read-back step. A fresh chat has zero memory of anything
above — if it doesn't reconfirm the prior exit condition itself, it's guessing.

## Phase manifest

| # | Phase | Exit condition | File | Status |
|---|---|---|---|---|
| 0 | Contracts + threat model | Authority/state rules explicit | `PHASE_00_Contracts_and_Threat_Model.md` | **delivered** |
| 1 | FastAPI + PostgreSQL + workflow decision | State survives restart | `PHASE_01_*.md` | pending — ask for it next |
| 2 | Installer + Worker + sandbox | Code runs safely in isolation on detected hardware | `PHASE_02_*.md` | pending |
| 3 | Model gateway + MCP tool layer | Two providers execute same task contract via MCP | `PHASE_03_*.md` | pending |
| 4 | Single coding loop | Toy issue → branch → patch → tests | `PHASE_04_*.md` | pending |
| 5 | Verification | Broken patch cannot become PASS | `PHASE_05_*.md` | pending |
| 6 | Self-repair + repair-event log | Seeded failure repaired automatically, fully logged | `PHASE_06_*.md` | pending |
| 7 | Independent review | Reviewer can reject implementation | `PHASE_07_*.md` | pending |
| 8 | Event stream + graph UI | UI mirrors backend and reconnects | `PHASE_08_*.md` | pending |
| 9 | Research + requirements | Evidence → questions → locked spec | `PHASE_09_*.md` | pending |
| 10 | Memory | Validated knowledge retrieval | `PHASE_10_*.md` | pending |
| 11 | Remote worker + Headscale/WireGuard mesh | Same worker contract works remotely, zero open ports | `PHASE_11_*.md` | pending |
| 12 | Release gates | Consequential action cannot bypass approval | `PHASE_12_*.md` | pending |
| 13 | Hardening | Fault/security/regression suites block bad versions | `PHASE_13_*.md` | pending |

Say **"next phase"** or **"phase N"** in this conversation whenever you want the
next packet generated.

## `STATE.md` — create this file now, empty header below, append after every phase

```markdown
# AOS STATE

## Phase 0 — Contracts + threat model
- Status:
- Files created:
- Commands run / validated:
- Exit evidence:
- Decisions made:
- Open questions for Phase 1:

## Phase 1 — FastAPI + PostgreSQL + workflow decision
- Status:
...
```

Each Phase Packet ends with a "Handoff Block" template shaped like the section
above — copy its filled-in output straight into `STATE.md`.

## Non-negotiables that apply to every phase (don't let a fresh chat forget these)

- No inbound open ports, ever. Remote access = Headscale/WireGuard mesh only (Phase 11).
- No phase may claim done without the exit condition's evidence in STATE.md.
- No unrelated cleanup / scope creep inside a phase's patch.
- Self-repair (from Phase 6 onward) must emit `repair.attempt` events — no silent retries.
- If a phase's prerequisites aren't met, the executing agent stops and says so.
