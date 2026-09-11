# AOS — Phase 3 Execution Packet: Model Gateway + MCP Tool Layer

## Role
Cold start. Read `AOS_Master_Specification.pdf` + `STATE.md`. Confirm Phase 2's
exit condition (safe sandboxed execution + installer) is evidenced.

## Objective
Give the (still loop-less) system two abstraction layers it will depend on
for the rest of the build:
1. **Model gateway** — one interface over local + free + paid model tiers.
2. **MCP tool layer** — the "connectors/plugins" ask, standardized on the
   open Model Context Protocol instead of a bespoke plugin system.

## Deliverables — Model Gateway

- LiteLLM proxy (self-hosted, OSS) config (`litellm_config.yaml`) with at
  least two routes configured:
  - `local` → Ollama, tag from Phase 2's `.env`
  - `free_api` → one free-tier provider (OpenRouter free models, or
    whichever is currently available — check current free-tier offerings,
    they change)
- Routing rule stub: task difficulty/context-size/privacy flag decides which
  route is used; hardcode a simple rule for now (e.g. "local by default,
  escalate to free_api on N consecutive local failures") — the real
  escalation logic belongs to Phase 6 (self-repair).
- Paid fallback route defined in config but **disabled by default** — enabling
  it requires an explicit policy flag (ties to Phase 0's "paid compute
  requires approval" rule).

## Deliverables — MCP Tool Layer

- Stand up an MCP server (official Python SDK) exposing a minimal toolset,
  each tool scoped to the Phase 2 sandbox — not the host:
  - `read_file(path)`, `write_file(path, content)` — sandbox workspace only
  - `run_command(cmd)` — routes through Phase 2's sandboxed executor, not a
    raw subprocess call
  - `git_diff()`, `git_commit(message)` — scoped to the task branch
- Every tool call must emit `tool.requested` / `tool.completed` events
  (Phase 0 catalog) — the MCP layer does not bypass the event trail.
- No tool may touch anything outside the current task's sandbox/workspace —
  verify this with a test that tries a path traversal (`../../etc/passwd`)
  and confirms it's rejected.

## Explicitly out of scope
- No coding loop yet (Phase 4) — this phase proves the plumbing, not that an
  agent can use it to fix a bug
- No independent review, no repair loop

## Exit condition
Two providers execute the same task contract via MCP tools: send an
identical toy prompt (e.g. "list files in the workspace") through both the
`local` and `free_api` routes, both return a valid completion, and at least
one of them successfully calls an MCP tool round-trip (e.g. reads a file via
`read_file` and reports its contents accurately).

## Validation commands
```bash
litellm --config litellm_config.yaml &
python3 -m aos.mcp_server &
pytest tests/test_gateway.py -v      # both routes respond
pytest tests/test_mcp_tools.py -v    # tool round-trip + path-traversal rejection
```

## Handoff Block
```markdown
## Phase 3 — Model gateway + MCP tool layer
- Status:
- Providers configured:
- Files created:
- Commands run / validated:
- Exit evidence:
- Decisions made:
- Open questions for Phase 4:
```
