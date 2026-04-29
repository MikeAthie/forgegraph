# Runtime Write Intents

> Internal terminology notice: These terms are INTERNAL and not user-facing. Product surfaces must translate them through the canonical ontology and frontend domain ViewModels.

This document extends [runtime-invariants.md](./runtime-invariants.md). If anything here conflicts with that file, `runtime-invariants.md` wins.

## Purpose

Runtime write intents move engine-originated durable state mutations onto a backend-owned pipeline:

- engine publishes an intent to Redis Streams
- backend consumers validate and apply the write in a DB transaction
- the consumer records the processed intent id for idempotency
- the stream message is acknowledged only after commit

The stream is transport only. The database remains the source of truth.

## Envelope

```json
{
  "intent_id": "uuid",
  "intent_type": "pause_run",
  "run_id": "uuid",
  "attempt_id": "string",
  "trace_id": "trace-id",
  "timestamp": "2026-04-14T12:00:00Z",
  "payload": {}
}
```

Rules:

- `intent_id` is the idempotency key.
- `intent_type` identifies one atomic backend mutation.
- `run_id` routes the write to backend-owned state.
- `attempt_id` is carried for correlation and replay safety.
- `trace_id` links the write to execution telemetry.
- `timestamp` is the engine-side publish time, not authoritative state.

## Intent Types

The runtime writer currently accepts these intent types:

- `pause_run`
- `ack_run_resumed`
- `store_checkpoint`
- `set_run_status`
- `upsert_node_run`

Each intent maps to one atomic backend write transaction.

## `pause_run`

Payload contract:

```json
{
  "node_id": "human_gate_1",
  "node_type": "human_gate",
  "node_name": "Human Review",
  "node_attempt": 1,
  "pause_payload": {
    "prompt_message": "Approve the draft",
    "required_fields": ["feedback"]
  },
  "checkpoint": {
    "node_id": "human_gate_1",
    "step_index": 7,
    "state_snapshot": {},
    "completed_nodes": [],
    "skipped_nodes": [],
    "graph_json": {}
  },
  "pause_state": {
    "state_snapshot": {},
    "completed_nodes": [],
    "skipped_nodes": [],
    "graph_json": "{}",
    "tenant_id": "tenant-id"
  }
}
```

Backend consumer responsibilities:

- reject malformed or stale intents
- upsert the checkpoint
- persist the pause state
- move the run to `paused`
- upsert the waiting `NodeRun`
- create or refresh the approval task
- insert the processed-intent record in the same transaction

## Consumer Process

The consumer is a production worker, not a dev-only utility:

- command: `python manage.py process_runtime_write_intents`
- role: durable backend-owned runtime write applier
- supervision: run it under systemd, Docker, or Kubernetes with automatic restart
- scaling: one replica is sufficient initially; add replicas later as stream lag grows

Operational behavior:

- consumes from Redis Streams via consumer groups
- reclaims stale pending messages
- acknowledges only after successful processing
- discards poison messages after `max-deliveries`
- logs intent metadata for retries and discards
- logs lag and emits warnings once lag crosses the configured threshold

Progress means the durable system state moved forward or the message reached a terminal
handling outcome:

- a backend DB transaction committed
- the stream message was ACKed after commit or terminal handling
- the stream message was dead-lettered and the original was ACKed

Polling, fetching, or reclaiming a message is activity, not progress.

Dead-letter entries must include enough operator context to diagnose one run without
reading raw Redis payloads: `run_id`, `intent_id`, `attempt_id`, `delivery_count`,
`reason`, `error_class`, `stream_message_id`, and `timestamp`.

Stream retention has two layers:

- time-based trimming for acknowledged entries after normal progress
- a conservative hard-cap pressure-relief trim that never cuts across pending or
  undelivered consumer-group safety boundaries

If an ancient pending message is still required for correctness, the hard cap may only
trim entries that are safely behind that boundary; the consumer must eventually ACK or
dead-letter pending messages to fully release stream pressure.

## Engine Mode

Runtime writes are now intent-owned. Engine startup fails closed unless:

- `ENGINE_RUNTIME_WRITE_MODE=pause-intents`
- Redis is configured for the intent publisher
