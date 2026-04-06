# Read Models And Projections

Phase 1 read models:

- `AgentRegistryEntry`
- `TaskRecord`
- `DecisionRecord`
- `CostLedgerEntry`
- `CostAggregate`

Rules:

- build from canonical facts
- do not mutate engine contracts
- keep rebuild logic in the backend control plane
- prefer cached summaries over frontend-side aggregation
- expose canonical reads over REST and push live deltas over WebSockets
- keep event ingestion idempotent
- design projections for 500+ agents, high fan-out, and summary-first UI delivery

Snapshot-backed resume state also belongs in backend-owned projections and persistence, not in long-lived engine process state.

Reference: [system-invariants.md](system-invariants.md)
