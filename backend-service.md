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

## API Contract Notes

- Authentication lives under `/api/auth/*`.
- `POST /api/auth/register` creates a user and returns a top-level user payload.
- `POST /api/auth/login` returns an access token in the JSON body and sets the refresh token in an HttpOnly cookie.
- `POST /api/auth/refresh` accepts the refresh cookie and may also accept a JSON `refresh` field.
- `POST /api/auth/logout` requires Bearer auth and invalidates the refresh session.
- `GET /api/auth/me` returns the authenticated user payload.

Workflow and execution creation is intentionally split:

- `POST /api/workflows` or `POST /api/graphs` creates workflow metadata only.
- Runnable content is created separately with `POST /api/workflows/{id}/versions` or `POST /api/graphs/{id}/versions`.
- Executions start with `POST /api/executions/start` or `POST /api/runs/start` using a workflow revision / graph version id.

Engine callbacks are server-to-server:

- `POST /api/runs/engine-events` is not a browser login flow.
- Requests must be signed with `X-ForgeGraph-Timestamp` and `X-ForgeGraph-Signature`.
- Local development uses the shared HMAC secret `dev_shared_secret`.

## Test Automation Guidance

- Prefer current alias APIs over legacy routes when generating new tests.
- Treat legacy routes as compatibility coverage, not the primary contract.
- Verify backend-owned durability, liveness, idempotency, recovery decisions, and alias parity.
- Do not generate tests that assume the engine owns durable runtime state.
- When testing run lifecycle behavior, assert backend-materialized state rather than raw event streams alone.

## Rule

The backend is the only durable source of truth. Keep runtime execution in the engine and all durable business state in backend-owned systems.
