# Event Model

> Internal terminology notice: These terms are INTERNAL and not user-facing. Product surfaces must translate them through the canonical ontology and frontend domain ViewModels.

> Runtime precedence: [runtime-invariants.md](runtime-invariants.md) is canonical.

Canonical event backbone:

- `Run`
- `RunEvent`
- `NodeRun`
- `MemoryEvent`
- `DecisionEvent`
- `CostEvent`

Rules:

- the backend ingests events idempotently
- every runtime event is categorized as `state` or `observability`
- only `state` events may trigger backend-controlled runtime state writes
- `observability` events may be persisted for inspection, but must remain read-only with respect to authoritative runtime state
- projections must be rebuildable from runtime facts
- UI summaries must link back to runtime facts
- event order, event IDs, causality, and timestamps are first-class for inspectability
- event payloads should support replay-safe snapshot resume
- the frontend should consume backend-materialized summaries rather than raw event firehoses by default

Memory rule:

- `memory_event` is append-only history
- `memory_item` is a backend-derived current view

Reference: [runtime-invariants.md](runtime-invariants.md)
