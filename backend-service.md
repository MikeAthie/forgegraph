# Backend Service

> Runtime precedence: [docs/architecture/runtime-invariants.md](docs/architecture/runtime-invariants.md) is canonical.

The backend is the ForgeGraph control plane.

## Responsibilities

- Canonical persisted state for workflows, executions, decisions, memory, accounting, and operator views
- Authentication, JWT validation, tenancy, RBAC, governance, and auditability
- Idempotent command handling, event ingestion, and snapshot-backed resume orchestration
- Canonical memory ownership with Postgres and pgvector persistence
- Real-time and eventual-consistency cost handling, with fast-path limit and overage signaling
- REST APIs plus WebSocket updates for frontend consumers
- Rate limiting, throttling, Redis-backed token revocation, and query-boundary isolation

## Phase 1 Additions

- `AgentRegistryEntry`
- `TaskRecord`
- `DecisionRecord`
- `CostLedgerEntry`
- `CostAggregate`

## API Surfaces

- Legacy: `/api/graphs`, `/api/runs`, `/api/approvals`
- Current aliases: `/api/workflows`, `/api/executions`, `/api/decisions`
- New OS views: `/api/agents`, `/api/tasks`, `/api/accounting`, `/api/system-state`

## Rule

The backend is the only durable source of truth. Keep runtime execution in the engine and all durable business state in backend-owned systems.
