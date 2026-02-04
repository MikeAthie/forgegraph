# P1: Reliability + Replay (Weeks 3-4)

## Objective
Harden real-time delivery and deliver checkpoint replay UX without regressing demo reliability.

## Prerequisites
- P0 event pipeline working end-to-end.
- WS/SSE updates are functional in run detail page.

---

## Task List

### P1-T01: Event Delivery Hardening
Effort: Medium

Why critical:
Retries and intermittent failures can cause missing or duplicate events, undermining trust.

Current code references:
- `backend/adapters/api/runs/views.py:1075` persists RunEvent without idempotency.
- `engine/adapter/gateway/http_event_emitter.go:117` drops events when buffer is full.

Implementation steps:
1. Add `event_id` unique index scoped to run.
2. Add event delivery metrics (success, retry, dropped).
3. Add optional persistence buffer for unsent events (Redis or disk-backed).
4. Add structured logs when drops occur.

Recommended patterns / best practices:
- At-least-once delivery with idempotent storage.
- Exponential backoff with jitter.

Testing strategy:
- Integration: simulate backend 500 errors and verify retries.
- Unit: idempotent insert with duplicate events.

Success criteria / Definition of Done:
- [ ] No duplicate RunEvent rows for repeated event_id.
- [ ] Buffer overflow events are logged with run_id and event type.

Dependencies:
- P0-T02 and P0-T03.

Risks:
- Additional indexes can slow high-volume inserts.

---

### P1-T02: WS/SSE Reconnect + Resume
Effort: Medium

Why critical:
Stable real-time view requires seamless reconnection without losing events.

Current code references:
- `frontend/pages/runs/[runId].tsx:624` polling fallback when WS/SSE is down.
- `backend/adapters/api/runs/views.py:1236` SSE supports `since` parameter.

Implementation steps:
1. Track `last_event_id` or `lastStreamTimestamp` in frontend.
2. On reconnect, resume from last event via WS or SSE.
3. Add backoff for reconnect attempts and clear UI indicator.
4. Prefer WS -> SSE -> (only if needed) polling.

Recommended patterns / best practices:
- Resume from last known event to avoid gaps.
- Avoid aggressive reconnect loops.

Testing strategy:
- E2E: simulate WS drop and verify events resume without gaps.
- Unit: stream state reducer handles out-of-order events.

Success criteria / Definition of Done:
- [ ] WS reconnect resumes within 5 seconds under normal network conditions.
- [ ] Polling fallback not triggered in happy-path runs.

Dependencies:
- P0 event ingestion.

Risks:
- Token expiry for long-lived runs.

---

### P1-T03: Checkpoint Replay UX + API
Effort: Medium

Why critical:
Replay is a differentiator and required in the demo flow.

Current code references:
- `engine/application/usecase/scheduler.go:216` loads checkpoints.
- `backend/infrastructure/orm/models.py:525` RunCheckpoint model.
- `backend/adapters/api/runs/views.py:886` resume endpoint exists.

Implementation steps:
1. Add endpoint to replay from last checkpoint or specific node.
2. Expose replay action in run detail UI.
3. Record replay metadata in RunEvent for auditability.

Recommended patterns / best practices:
- Replay should create a new run or a distinct replay session.
- Explicit user confirmation before replay.

Testing strategy:
- Integration: replay endpoint creates new run state.
- UI: replay button triggers expected call and updates stream.

Success criteria / Definition of Done:
- [ ] Replay produces new events and output without corrupting original run history.
- [ ] Replay action visible in UI with clear confirmation.

Dependencies:
- P1-T02 for stable streaming of replay results.

Risks:
- Side effects from replayed HTTP/tool nodes.

