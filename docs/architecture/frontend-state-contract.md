# Frontend State Contract

> Runtime precedence: [runtime-invariants.md](runtime-invariants.md) is canonical.

The frontend observes and controls backend-owned state. It does not invent durable workflow truth, terminal state, financial metrics, operational metrics, memory facts, or accounting results.

## Metric Provenance

Financial and operational metrics may be displayed only when backed by a backend DTO that identifies provenance.

Required metadata for displayed financial and operational metrics:

- `source`: backend service, table, projection, or read model
- `computed_at`: backend computation timestamp
- `freshness_ms`: freshness or lag when available
- `status`: `available`, `not_instrumented`, `stale`, or `error`
- `value`: present only when the backend provides a real value

If a real metric is not available, the frontend displays `Not yet instrumented`.

## Forbidden UI Behavior

- Do not compute revenue, profit, or accounting values from constants, offsets, or client-only projections.
- Do not show optimistic terminal run/approval state before backend confirmation.
- Do not derive business state from engine event payloads.
- Do not treat WebSocket messages as authoritative when backend read state disagrees.

## Allowed UI Behavior

- Format backend-provided values.
- Compute purely presentational metadata such as relative freshness text from backend timestamps.
- Submit user commands and decisions through backend APIs with idempotency keys when available.

## Signoff

This frontend state contract is a release gate. PR CI requires this checklist to
remain present. Release and production evidence gates require every role to be
approved.

- [ ] Product Lead
- [ ] Backend Lead
- [ ] Engine Lead
- [ ] Frontend Lead
- [ ] Platform/SRE Lead
