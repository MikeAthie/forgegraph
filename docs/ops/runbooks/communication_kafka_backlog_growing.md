# Communication Kafka Backlog Growing

`docs/architecture/runtime-invariants.md` is canonical: Kafka is transport only, and the backend outbox remains the durable source of truth.

## Symptoms

- `communication_kafka_outbox_backlog` exceeds `COMMUNICATION_KAFKA_OUTBOX_BACKLOG_READY_THRESHOLD`.
- The `publish_communication_outbox` worker logs repeated `communication_kafka_publish_failed` events.
- `/ready` reports `communication_kafka.backlog_ready=false` when `READINESS_REQUIRE_COMMUNICATION_KAFKA=true`.

## Triage

1. Confirm the publisher worker is running and emitting `communication_kafka_publisher_heartbeat`.
2. Check managed Kafka broker reachability, credentials, TLS/SASL settings, and topic existence.
3. Inspect `domain_event_outbox` rows for `topic=COMMUNICATION_KAFKA_TOPIC` and statuses `pending`, `failed`, or `deferred`.
4. Review `last_error` and `next_attempt_at`; backend retry state is authoritative.

## Recovery

- Fix broker/configuration issues, then let the backend outbox retry publish due rows.
- Do not manually mark outbox rows `published` unless the event delivery has been independently verified and approved.
- If a payload is too large, reduce safe metadata size or raise `COMMUNICATION_KAFKA_MAX_PAYLOAD_BYTES` only after confirming managed-broker limits.
