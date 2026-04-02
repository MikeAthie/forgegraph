# Accounting Aggregation

Raw source records remain unchanged.

Aggregation rules:

- `LLMUsage` and `MemoryUsage` become `CostLedgerEntry`
- `CostLedgerEntry` becomes `CostAggregate`
- aggregates are grouped by time, provider, model, and agent when available

This keeps cost inspectable without pushing aggregation work into the frontend.
