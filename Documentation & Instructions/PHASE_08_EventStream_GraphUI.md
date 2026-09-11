# AOS — Phase 8 Execution Packet: Event Stream + Graph UI

## Role
Cold start. Read `AOS_Master_Specification.pdf` + `STATE.md`. Confirm Phase 7's
exit condition (independent review can reject) is evidenced.

## Objective
Make everything built so far observable in real time, without letting the
frontend become a second source of truth. Master spec §10 is explicit: the
graph is a monitoring surface, the backend event stream is the only truth.

## Deliverables — Backend

- SSE or WebSocket endpoint streaming `Event` objects (Phase 0 contract) in
  strict sequence order.
- Reconnect support: client sends its last-seen sequence number, server
  replays everything after it before resuming live streaming — never skips
  or invents a gap.

## Deliverables — Frontend

- Next.js + TypeScript app, graph via `@xyflow/react` per master spec §4.
- Node types map to: workflow / agent / tool / artifact / decision / model /
  error (master spec §12 node-shape table).
- Node states: queued / running / blocked / waiting / passed / failed /
  retrying — driven only by consumed events, never a client-side guess.
- Timeline view: ordered event list, independent of the graph, same data
  source.
- Inspector panel: clicking a node shows the exact event(s)/evidence behind
  its current state — no summarized/invented explanation.
- Reconnect behavior: on WS/SSE drop, reconnect, replay missed events, graph
  catches up — verify it does **not** show fabricated intermediate progress
  during the gap.

## Explicitly out of scope
- No auth, no multi-user, no polish beyond functional correctness
- No new backend logic beyond the streaming endpoint — Phases 1–7 already
  produce every event this phase displays

## Exit condition
UI mirrors backend and reconnects: run a task, watch the graph update live
through queued → running → (repair cycles if triggered) → reviewed →
ready/failed. Kill the frontend's connection mid-run, reconnect, confirm it
catches up to the exact current state with no invented intermediate frames.

## Validation commands
```bash
npm run dev
# trigger a run via API, observe graph
# mid-run: kill network tab / close+reopen the WS connection
# confirm sequence-numbered replay in browser devtools network log
```

## Handoff Block
```markdown
## Phase 8 — Event stream + graph UI
- Status:
- Files created:
- Commands run / validated:
- Exit evidence (reconnect replay proof):
- Decisions made:
- Open questions for Phase 9:
```
