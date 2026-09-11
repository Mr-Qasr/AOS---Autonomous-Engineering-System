# AOS — Phase 2 Execution Packet: Installer + Worker + Sandbox

## Role
Cold start. Read `AOS_Master_Specification.pdf` + `STATE.md`. Confirm Phase 1's
exit condition (state survives restart) is evidenced. If not, stop.

## Objective
Two things, both required before any model/agent work exists:
1. **Installer** (`aos-init`) — probes the host machine and picks a model tier.
2. **Worker + sandbox** — executes arbitrary commands inside an isolated,
   ephemeral Docker container on behalf of a Run.

## Deliverables — Installer

- Python script, no heavy deps: detect GPU vendor + VRAM (`nvidia-smi
  --query-gpu=memory.total --format=csv` / `rocm-smi` fallback / "none"),
  system RAM (`free -g`), CPU cores (`nproc`).
- Static decision table (put this in code, not a doc — it must be executable):

  | VRAM | CPU-only RAM | Tag |
  |---|---|---|
  | ≥24GB | — | `qwen3-coder-next` (or current best MoE that fits) |
  | 8–24GB | — | quantized 7–14B class |
  | none / <8GB | ≥32GB | smallest quantized coding model, CPU inference, set expectations low |
  | none | <32GB | fail loudly: recommend a free API-tier fallback instead of local, don't silently run something useless |

- Writes `.env` with the chosen `AOS_LOCAL_MODEL_TAG` and pulls it via
  `ollama pull <tag>`.
- `aos-init --dry-run` prints the decision without pulling anything.

## Deliverables — Worker + Sandbox

- Worker registers itself against the Phase 0 `Worker` contract (capabilities,
  health, lease).
- Sandbox: ephemeral Docker container per task — workspace mounted read-write,
  everything else read-only or absent.
- **Network deny-by-default** inside the sandbox — no egress unless the task's
  policy explicitly allow-lists a domain. Enforce via Docker network mode, not
  application-layer trust.
- Resource limits: CPU/memory caps via Docker, wall-clock timeout per command.
- Command execution is logged as `tool.requested` / `tool.completed` events
  (Phase 0 event catalog) — every command run inside the sandbox must be
  traceable.
- Lease renewal / timeout: if a worker dies mid-task, its lease expires and
  the Run becomes eligible for another worker to pick up (ties into Phase 1's
  restart-recovery guarantee).

## Explicitly out of scope
- No model calls yet (Phase 3) — the installer only *selects* a tag, it
  doesn't need to invoke it
- No MCP tool layer yet — raw sandbox exec is enough for this phase
- No remote workers (Phase 11) — local Docker only

## Exit condition
Code runs safely in isolation on the detected hardware tier: run a toy
command through the sandbox, confirm (a) it executes, (b) it cannot reach the
network unless allow-listed, (c) resource limits are enforced (a
memory-bomb test gets killed, not left to hang the host), (d) the installer
picks the correct tag for at least two different simulated hardware profiles.

## Validation commands
```bash
python3 aos_init.py --dry-run --simulate-vram 24
python3 aos_init.py --dry-run --simulate-vram 4
pytest tests/test_sandbox.py -v   # network-deny test, resource-limit test, exec-log test
```

## Handoff Block
```markdown
## Phase 2 — Installer + Worker + sandbox
- Status:
- Files created:
- Hardware tiers tested:
- Commands run / validated:
- Exit evidence:
- Decisions made:
- Open questions for Phase 3:
```
