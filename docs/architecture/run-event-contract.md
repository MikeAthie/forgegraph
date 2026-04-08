# Run Event Contract

`Run` and `RunEvent` remain canonical runtime facts.

Requirements:

- events must remain append-only and timestamped
- projections must be explainable back to runtime events
- operator summaries must not replace runtime trace access
- events must not become the authoritative durable state without an explicit backend write

Primary contract: [state-ownership-contract.md](state-ownership-contract.md)
