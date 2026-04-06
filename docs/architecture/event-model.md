# Event Model

Canonical event backbone:

- `Run`
- `RunEvent`
- `NodeRun`
- `MemoryEvent`
- `DecisionEvent`
- `CostEvent`

Rules:

- the backend ingests events idempotently
- projections must be rebuildable from runtime facts
- UI summaries must link back to runtime facts
- event order, event IDs, causality, and timestamps are first-class for inspectability
- event payloads should support replay-safe snapshot resume
- the frontend should consume backend-materialized summaries rather than raw event firehoses by default

Memory rule:

- `memory_event` is append-only history
- `memory_item` is a backend-derived current view

Reference: [system-invariants.md](system-invariants.md)
