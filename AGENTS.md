# AGENTS

Follow [docs/architecture/runtime-invariants.md](docs/architecture/runtime-invariants.md) strictly.

If any repo document conflicts with it, `runtime-invariants.md` wins.

Non-negotiable runtime rules:

- The backend is the only durable source of truth.
- The engine may execute work and hold ephemeral state, but it must not own durable state.
- Events are transport and observability artifacts, not authoritative state.
- Snapshots, liveness, recovery, and durable resume state are backend-owned.

Before changing runtime code, docs, or tests, verify the change does not make the engine or any client authoritative for durable state.
