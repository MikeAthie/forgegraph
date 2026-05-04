# Event Contracts

> Runtime precedence: [runtime-invariants.md](runtime-invariants.md) is canonical.

Events are transport and observability artifacts. They are never authoritative state until the backend accepts and applies them through a backend-owned write path.

## Engine Callback Decision Envelope

Every backend response to an engine event callback must include a structured decision envelope. The engine must not infer safe discard from raw HTTP status alone.

```json
{
  "decision": "accepted | duplicate | stale_superseded | reject_invalid | retry_required",
  "reason": "human-readable reason",
  "backend_event_id": "backend event or accepted event id",
  "safe_to_discard": true,
  "retry_after_ms": 1000,
  "conflict_code": "409_ORDERING_CONFLICT"
}
```

Rules:

- `accepted`, `duplicate`, and backend-proven `stale_superseded` are ack decisions only when `safe_to_discard=true`.
- `reject_invalid` moves the event out of retry flow and into local/operator-visible failure handling.
- `retry_required` keeps the event in retry/spool flow.
- `404` and `409` are not discard semantics by themselves.
- `401` and `403` stop callback delivery and alert; the engine must not retry-storm authorization failures.

Runbook: [event-spool-growth-runbook.md](../ops/event-spool-growth-runbook.md)

## Canonical Event Direction

Phase 1 introduces a canonical cross-layer event envelope with `event_id`, `idempotency_key`, tenant/org/run identity, source, type, sequence, causation/correlation IDs, timestamp, schema version, payload, and checksum.

Until that migration is complete, legacy engine callback payloads remain compatibility input only. Frontend code must consume backend read models and DTOs, not engine-native event payloads.

## Backend-Owned Memory Intents

Engine summary/fact output must be emitted as memory intent events, not direct durable memory writes:

- `memory_write_requested`
- `memory_fact_extracted`
- `summary_created`

The backend validates these events, stores backend-owned memory observations, records audit metadata, and returns the callback decision envelope. The event itself is still transport; the persisted backend memory record is the durable fact.

## Replayable State Feed

Phase 2 WebSocket recovery uses backend-persisted state-feed events. Each run-scoped broadcast that reaches clients must carry:

- `event_id`
- `state_version`
- `tenant_id`
- `run_id`
- `type`
- `requires_refetch`

Clients reconnect with `last_seen_state_version`. The backend replays retained events after that version, or emits `full_resync_required` when the replay window is missing, exceeded, or cannot be proven tenant-safe.

## Event Dead Letters

Phase 2 event ingestion failures must create backend-owned operator records when the backend receives an event but does not apply it. This includes invalid schemas, unknown runs, tenant mismatches, ordering conflicts, safety violations, invalid memory intents, and unknown event types.

Each event dead letter records source, tenant/run when known, event id, idempotency key, event type, redacted payload, reason, retry count, first seen, and last seen timestamps. Operator replay requests and acknowledgements are RBAC-protected and audited. Event dead letters are diagnostics and reconciliation records; they do not make the event authoritative state.
