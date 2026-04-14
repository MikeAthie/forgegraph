# State Ownership Contract

> Runtime precedence: [runtime-invariants.md](runtime-invariants.md) is canonical.
> This document elaborates state ownership details but does not override the runtime invariants.

ForgeGraph has one enforceable ownership rule for durable runtime state:

- The backend control plane is the only durable source of truth.
- The engine executes work, but it does not own durable state.
- Events are transport and observability data, not truth.

## Backend Owns

- run lifecycle state
- node lifecycle state
- checkpoints and resume snapshots
- pause and approval state
- durable memory persistence
- liveness, heartbeat, and recovery decisions
- validation, monotonicity, and idempotency of runtime writes

## Engine Owns

- command execution in memory
- goroutines, queues, and transient retry counters
- in-flight execution context that can be lost safely
- signal and event emission
- checkpoint payload generation

If the engine crashes, losing its in-memory state must not corrupt or erase authoritative state.

## Required Write Boundary

- Any durable state mutation must go through a backend-controlled write contract.
- The engine must not write durable runtime state directly to Postgres.
- The engine must not persist durable memory directly.
- The engine must not persist checkpoints directly.
- Resume must start from backend-supplied state, not engine-local state.

## Event Semantics

- Events can inform the backend and operators.
- Events can trigger backend persistence.
- Events never mutate durable state directly.
- Persisted backend state is authoritative, not the event itself.

## Allowed Runtime Modes

- `control-plane-http`: default and intended mode
- `in-memory`: explicit test or local fallback mode only

`dual-write` is removed from the supported runtime modes.

Any new runtime feature must answer one question before implementation:

What state is the engine still allowed to own, even temporarily?

The answer must remain:

Only ephemeral execution state that can be lost without corrupting the system.

References:

- [control-plane.md](control-plane.md)
- [execution-plane.md](execution-plane.md)
- [run-event-contract.md](run-event-contract.md)
