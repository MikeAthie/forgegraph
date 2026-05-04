# Event Spool Growth Runbook

> Runtime precedence: [../architecture/runtime-invariants.md](../architecture/runtime-invariants.md) is canonical.

Engine callback spools are a delivery backlog, not source-of-truth state. The backend remains authoritative for all durable runtime state.

## Signals

Investigate when any of these move above normal baseline:

- `events_spooled_total`
- `events_replayed_total`
- `events_discarded_total`
- `events_conflict_total`
- engine event spool file size or age
- backend engine callback `retry_required` or `409_ORDERING_CONFLICT` responses

## Triage

1. Check whether backend callback health is degraded.
2. Separate auth failures from retryable delivery failures:
   - `401` or `403`: stop engine callback retry storm, rotate/check callback secret, and alert platform.
   - `retry_required`: keep events spooled and inspect backend conflict or availability reason.
   - `reject_invalid`: inspect the local dead-letter file and backend validation reason.
3. Confirm whether the backend is returning structured callback decision envelopes.
4. Check projection lag and dead-letter queues for the same tenant/run.
5. Verify the affected tenant/run still exists and is not explicitly tombstoned.

## Recovery

- Do not delete spool files to make metrics quiet.
- Restore backend callback availability first.
- Let the engine replay retryable spooled events.
- For invalid events, preserve the dead-letter file and attach the event payload, reason, tenant/run, and timestamps to the incident.
- If ordering conflicts persist, reconcile backend run/task state before replaying.

## Escalation

Escalate to Backend and Platform when:

- spool age continues increasing after backend recovery,
- conflicts are dominated by `404_UNKNOWN_ENTITY` or `409_ORDERING_CONFLICT`,
- dead-letter volume increases after a deployment,
- auth failures affect more than one engine instance.
