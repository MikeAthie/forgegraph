# Run Event Contract

> Runtime precedence: [runtime-invariants.md](runtime-invariants.md) is canonical.

`Run` and `RunEvent` remain canonical runtime facts.

Requirements:

- events must remain append-only and timestamped
- projections must be explainable back to runtime events
- operator summaries must not replace runtime trace access
- events must not become the authoritative durable state without an explicit backend write
- events never mutate durable state directly; backend handlers validate and apply writes

Primary runtime contract: [runtime-invariants.md](runtime-invariants.md)

Implementation plan: [post-stateless-engine-reliability-hardening-v2.md](post-stateless-engine-reliability-hardening-v2.md)
