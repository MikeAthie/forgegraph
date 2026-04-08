# Execution Plane

The Go engine is the execution plane.

It owns:

- concurrent execution correctness
- scheduling, dependency handling, retries, and bounded failure behavior
- gRPC execution entrypoints from the backend
- lifecycle event emission back to the backend boundary
- trace continuity and runtime observability

It should become stateless.

That means it should not own:

- durable business state
- durable task state
- durable memory state
- long-lived paused processes for human decisions
- product projections, summaries, dashboards, or governance state

It does not own organization dashboards, agent registry semantics, or accounting aggregation.

Human-in-the-loop flows should suspend through backend-owned snapshots, then resume through a fresh engine invocation with explicit context.

Reference: [system-invariants.md](system-invariants.md)

Primary contract: [state-ownership-contract.md](state-ownership-contract.md)
