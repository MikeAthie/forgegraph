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
