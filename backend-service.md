# Backend Service

> Runtime precedence: [docs/architecture/runtime-invariants.md](docs/architecture/runtime-invariants.md) is canonical.

The backend is the ForgeGraph control plane and the only durable source of truth.

## Responsibilities

- Own canonical persisted state for organizations, companies, operating models, operations, tasks, approvals, deliverables, memory, accounting, audit logs, and projections.
- Validate user commands, enforce tenancy/RBAC, apply idempotency, and persist authoritative outcomes.
- Dispatch execution contracts to the Go engine and receive signed callbacks through backend-owned APIs.
- Own snapshots, liveness detection, recovery decisions, approval handoff, resume state, and durable operation lifecycle records.
- Govern operating-model packs, connector policy, marketplace metadata, tool receipts, cost controls, and safety boundaries.
- Serve REST APIs and WebSocket updates for frontend consumers without making events or clients authoritative.

## API Surfaces

Primary product and operating APIs include:

- `/api/companies/*`
- `/api/company-operations/*`
- `/api/approvals/*`
- `/api/whiteboards/*`
- `/api/commerce/*`
- `/api/communication/*`
- `/api/memory/*`
- `/api/accounting/*`
- `/api/credentials/*`
- `/api/marketplace/*`
- `/api/system-state/*`

Compatibility and advanced APIs include:

- `/api/graphs/*`
- `/api/workflows/*`
- `/api/runs/*`
- `/api/executions/*`
- `/api/decisions/*`
- `/api/agents/*`
- `/api/tasks/*`

## Auth Contract Notes

- `POST /api/auth/register` creates a user and returns a top-level user payload.
- `POST /api/auth/login` returns an access token in the JSON body and sets refresh state through HttpOnly cookie behavior.
- `POST /api/auth/refresh` accepts the refresh cookie and may accept a JSON `refresh` field.
- `POST /api/auth/logout` requires Bearer auth and invalidates the refresh session.
- `GET /api/auth/me` returns the authenticated user payload.

## Execution Contract Notes

Workflow metadata and runnable versions remain split for compatibility:

- `POST /api/workflows` or `POST /api/graphs` creates workflow metadata.
- `POST /api/workflows/{id}/versions` or `POST /api/graphs/{id}/versions` creates a runnable revision.
- `POST /api/executions/start` or `POST /api/runs/start` starts an operation backed by a workflow revision / graph version id.

Engine callbacks are server-to-server:

- `POST /api/runs/engine-events` is not a browser login flow.
- Requests must be signed with `X-ForgeGraph-Timestamp` and `X-ForgeGraph-Signature`.
- Local development uses the shared HMAC secret configured by environment.

## Test Automation Guidance

- Verify backend-owned durability, liveness, idempotency, recovery decisions, and tenant isolation.
- Prefer company, operation, approval, and whiteboard APIs for product-facing tests.
- Treat legacy graph/run aliases as compatibility coverage unless a test is explicitly targeting advanced/internal behavior.
- Do not generate tests that assume the engine, frontend, Redis, Kafka, or event streams own durable runtime state.
- When testing lifecycle behavior, assert backend-materialized state rather than raw event streams alone.

## Rule

All durable business and runtime state belongs in backend-owned systems. Runtime execution belongs in the engine.
