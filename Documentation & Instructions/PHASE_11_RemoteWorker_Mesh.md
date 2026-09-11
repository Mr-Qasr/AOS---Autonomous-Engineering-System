# AOS — Phase 11 Execution Packet: Remote Worker + Headscale/WireGuard Mesh

## Role
Cold start. Read `AOS_Master_Specification.pdf` + `STATE.md`. Confirm Phase
10's exit condition (validated memory retrieval) is evidenced.

This is the phase that answers the original "outsourced GPU" requirement —
correctly, per master spec §8: **zero inbound open ports, no exceptions.**

## Objective
Let a Worker (Phase 2 contract) run on a remote machine — a spare GPU box, a
rented bare-metal/GPU instance, whatever — without opening any port on the
control plane's public side.

## Deliverables

- Self-hosted **Headscale** instance (open-source Tailscale control plane)
  run alongside the control plane, or on a small always-on host you control.
- WireGuard client config generation for a remote worker joining the mesh.
- Remote worker registers against the exact same `Worker` contract from
  Phase 2 — no protocol difference from the worker's point of view beyond
  which network interface it's reached on. If you find yourself changing the
  Worker contract for this phase, stop — that's a sign the abstraction from
  Phase 2 was wrong, fix it there, don't patch around it here.
- Task dispatch to a remote worker over the mesh; results/artifacts flow back
  the same way.
- Verify from **outside** the mesh (a separate machine/network) that no port
  is reachable on the control plane host beyond what existed before this
  phase.

## Explicitly out of scope
- No automatic GPU marketplace/fleet management, no auto-scaling — one
  manually-joined remote worker is the whole scope of v1
- No changes to Phase 6/7's repair or review logic — a remote worker is just
  another worker

## Exit condition
Same worker contract works remotely, zero open ports: run a task on the
remote-mesh worker end to end (through Phase 4–7's full loop), confirm
success, and confirm via `nmap`/`ss` from an external network that the
control plane exposes no new inbound port.

## Validation commands
```bash
headscale nodes list                      # remote worker shows as connected
python3 -m aos.loop run --task-id <id> --worker remote-01
nmap -p- <control-plane-public-ip>        # from an external network — compare to pre-Phase-11 baseline
```

## Handoff Block
```markdown
## Phase 11 — Remote worker + Headscale/WireGuard mesh
- Status:
- Remote host used for the proof:
- Files created:
- Commands run / validated:
- Exit evidence (nmap diff, task success):
- Decisions made:
- Open questions for Phase 12:
```
