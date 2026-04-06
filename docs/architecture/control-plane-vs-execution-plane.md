# Control Plane Vs Execution Plane

Control plane:

- owns canonical durable state
- owns product APIs
- owns tenancy, auth, governance, and idempotency boundaries
- owns projections, summaries, memory persistence, and decision state
- owns marketplace governance, accounting, limits, and snapshot-backed HITL flows

Execution plane:

- receives execution contracts over gRPC
- runs workflow revisions concurrently
- emits execution events and results
- handles runtime retries and failure signaling
- does not remain durably paused for approvals

Rule: product-level system state belongs in the control plane, not in the engine.

Transport boundaries:

- `frontend <-> backend`: REST and WebSockets
- `backend <-> engine`: gRPC
- `backend <-> storage`: Postgres, pgvector, Redis

System flow:

`frontend command -> backend validate and persist intent -> backend dispatch via gRPC -> engine execute -> engine emit events -> backend ingest idempotently -> backend materialize state -> backend notify UI`

Reference: [system-invariants.md](system-invariants.md)
