# TestSprite Config Inputs

Use this file to fill the TestSprite setup forms manually for each service.

## Frontend

Suggested form values:

- Project path: `c:\Users\mathi\projects\forgegraph\frontend`
- Service type: `frontend`
- Local port: `3000`
- Pathname: `/`
- Requires login for meaningful tests: `Yes`

Paste-ready description:

```md
ForgeGraph frontend is a Next.js operator console built with React and TypeScript. It is a backend-state observer and control surface, not a source of truth. The current primary product routes are `/overview`, `/agents`, `/tasks`, `/inbox`, `/memory`, `/accounting`, `/library`, `/workflows`, and `/settings`. Authentication and secondary routes include `/login`, `/register`, `/prompts`, `/credentials`, `/onboarding`, `/admin/*`, and `/analytics/*`. Legacy compatibility routes such as `/graphs`, `/runs`, and `/approvals` still exist but should be treated as secondary coverage. The frontend talks to the Django backend over HTTP and WebSockets and reflects backend-owned execution, decision, memory, and accounting state. Existing tests use Jest, Testing Library, and Playwright. For realistic E2E coverage, frontend tests may depend on the backend and engine running together.
```

Suggested additional instruction for hosted/browser runs:

```md
Prefer the current OS routes (`/overview`, `/agents`, `/tasks`, `/inbox`, `/memory`, `/accounting`, `/library`, `/workflows`, `/settings`) over legacy compatibility routes. Use the configured frontend login credentials for authenticated flows and log in through the UI instead of injecting tokens. The local stack runs over HTTP on localhost. Before generating or running tests, seed deterministic fixture data with `cd backend && uv run python manage.py seed_testsprite_frontend_fixture`. That fixture prepares `test@example.com` with one editable prompt, one pending approval, one visible memory observation, and one visible credential so browser tests can cover real operator flows instead of empty states.
```

## Backend

Suggested form values:

- Project path: `c:\Users\mathi\projects\forgegraph\backend`
- Service type: `backend`
- Local port: `8000`
- Pathname: `/health`
- Requires auth for many flows: `Yes`

Paste-ready description:

```md
ForgeGraph backend is the Django control plane and the only durable source of truth for runtime state. It owns authentication, organizations, billing, policies, audit logs, workflows, executions, decisions, prompts, memory governance, retention, analytics, and integration endpoints. It exposes `/health` plus REST APIs under `/api/`. The most important auth and workflow groups are `/api/auth/`, `/api/workflows/`, `/api/executions/`, `/api/decisions/`, `/api/agents/`, `/api/tasks/`, `/api/accounting/`, `/api/system-state/`, `/api/prompts/`, `/api/memory/`, `/api/analytics/`, `/api/credentials/`, `/api/integrations/`, `/api/marketplace/`, `/api/orgs/`, `/api/policies/`, `/api/retention/`, `/api/audit-logs/`, and `/api/scim/`. Legacy compatibility routes such as `/api/graphs/`, `/api/runs/`, and `/api/approvals/` still exist but should be secondary coverage. The backend coordinates workflow execution with the Go engine over gRPC and receives signed engine callbacks through `/api/runs/engine-events`. Tests should cover authenticated API behavior, validation, backend-owned data persistence, execution lifecycle, signed callback handling, alias parity, and integration points with Redis, PostgreSQL, and the engine.
```

Suggested additional instruction for API generation:

```md
Use the real local Django API contract. Prefer current alias APIs over legacy compatibility routes when generating new tests. Register users with `POST /api/auth/register` using a unique email per test and expect `201` with a top-level user payload only. Login with `POST /api/auth/login` and expect `200` with access in the JSON body plus refresh only in an HttpOnly cookie. Create workflow metadata with `POST /api/workflows` or `POST /api/graphs`, then create a runnable revision with `POST /api/workflows/{workflow_id}/versions` or `POST /api/graphs/{graph_id}/versions`, then start an execution with `POST /api/executions/start` or `POST /api/runs/start`. Treat `/api/runs/engine-events` as a server-to-server endpoint that requires `X-ForgeGraph-Timestamp` and `X-ForgeGraph-Signature` computed with HMAC-SHA256 using the local shared secret `dev_shared_secret`.
```

## Engine

Suggested form values:

- Project path: `c:\Users\mathi\projects\forgegraph\engine`
- Service type: `backend`
- Local port: `50051`
- Pathname: `/metrics`
- Note for form: `This service is a Go gRPC runtime with an HTTP metrics endpoint`

Paste-ready description:

```md
ForgeGraph engine is a Go 1.23 execution service that runs workflow graphs. It exposes a gRPC API for run execution and status operations and a Prometheus metrics endpoint over HTTP. The engine is responsible for graph validation, execution planning, node execution, retries, branching, human-gate behavior, tool execution, memory operations, summarization, and emitting run events back to the Django backend. Important RPCs include `Ping`, `StartRun`, `GetRunStatus`, and `CancelRun`. The default gRPC port is `50051` and the default metrics port is `9090`. Key code areas include `adapter/executor/`, `application/usecase/`, `adapter/store/`, `adapter/gateway/`, `adapter/summarizer/`, and `adapter/tool/`. Tests should focus on gRPC contract correctness, execution behavior, concurrent run handling, retries, storage adapters, callback delivery, and configuration-driven runtime behavior. Integration tests may require the backend callback URL, PostgreSQL, Redis, and mocked LLM/provider dependencies.
```

## Notes

- If TestSprite asks for a repo-wide summary first, use the three descriptions above as the basis for that summary.
- If TestSprite only supports `frontend` and `backend` types, classify the engine as `backend` and mention explicitly that it is a gRPC service with `/metrics` on HTTP.
- If the frontend form asks whether login is needed, answer `Yes`.
- If a form asks for a starting page or health path, use `/` for frontend, `/health` for backend, and `/metrics` for engine.
- When TestSprite asks what to prioritize, steer it toward current OS routes and alias APIs first, then legacy compatibility routes second.
