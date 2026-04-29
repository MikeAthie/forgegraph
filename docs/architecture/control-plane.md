# Control Plane

> Internal terminology notice: These terms are INTERNAL and not user-facing. Product surfaces must translate them through the canonical ontology and frontend domain ViewModels.

> Runtime precedence: [runtime-invariants.md](runtime-invariants.md) is canonical.

The backend control plane owns:

- canonical persisted business state
- identity, JWT auth, tenancy, and query-boundary isolation
- workflow definition persistence
- execution command APIs and orchestration boundaries
- decisions and human-in-the-loop state
- canonical memory persistence and derivation
- accounting, quotas, limits, and fast-path budget enforcement
- marketplace governance
- projections, summaries, and operator-facing read models
- idempotent event ingestion and snapshot-backed resume state

It ingests engine events, materializes operator-facing system state, and exposes canonical state to the frontend over REST and WebSockets.

Reference: [system-invariants.md](system-invariants.md)

Primary runtime contract: [runtime-invariants.md](runtime-invariants.md)
