# Communication Kafka Consumer Failures

`docs/architecture/runtime-invariants.md` is canonical: consumed Kafka events are not durable state. Backend receipts and operator dead letters are backend-owned diagnostics.

## Symptoms

- `communication_kafka_consumer_failures` is nonzero.
- `communication_event_receipts` contains failed receipts for the communication consumer group.
- Operator dead letters exist with `source=communication_kafka_consumer`.
- The `consume_communication_kafka` worker logs `communication_kafka_consumer_handler_failed`, `communication_kafka_transport_error`, or `communication_kafka_commit_failed`.

## Triage

1. Inspect the failed `CommunicationEventReceipt` and matching `EventDeadLetterRecord`.
2. Confirm payloads are metadata-only and use `schema_version=communication_event_v1`.
3. Check for missing required identifiers, invalid UUIDs, missing organizations/companies, or topic/schema drift.
4. If commit failures occur, verify broker connectivity and consumer-group permissions.

## Recovery

- For invalid JSON or unsupported events, acknowledge or resolve the dead letter after confirming no backend state should change.
- For valid failed metadata, fix the source event contract or missing backend object, then reprocess from backend-owned payload records where an operator replay path exists.
- Do not let a client or Kafka consumer directly mutate communication state; all durable changes must use backend-owned APIs or persistence paths.
