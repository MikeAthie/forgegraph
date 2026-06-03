# TestSprite Config Inputs

Use this file to fill TestSprite setup forms manually. Do not commit generated TestSprite `tmp` output, generated credentials, tunnel URLs, API keys, cookies, bearer tokens, or raw reports.

## Frontend

Suggested form values:

- Project path: `c:\Users\mathi\projects\forgegraph\frontend`
- Service type: `frontend`
- Local port: `3000`
- Pathname: `/companies`
- Requires login for meaningful tests: `Yes`

Paste-ready description:

```md
ForgeGraph frontend is a Next.js operator console for an AI Company Operating System. It is a backend-state observer and command surface, not a source of truth. Primary product routes are `/companies`, `/companies/[companyId]`, `/runs`, `/runs/[runId]`, and `/approvals`. Supporting routes include `/departments`, `/tasks`, `/memory`, `/accounting`, `/library`, `/credentials`, and `/prompts`. Advanced or compatibility routes include `/workflows`, `/graphs`, `/executions`, `/inbox`, `/agents`, and `/overview`. The frontend talks to the Django backend over HTTP and WebSockets and reflects backend-owned company, operation, approval, memory, accounting, whiteboard, and deliverable state. Tests should prefer company workspace flows, operation detail, approval resolution, and backend-provenance assertions over raw graph-editor coverage.
```

Suggested additional instruction for hosted/browser runs:

```md
Prefer company-first routes and flows. Use configured login credentials from the secure TestSprite environment, not committed files. Log in through the UI for authenticated browser flows unless the test is explicitly about API auth. The local stack runs over HTTP on localhost. Before generating or running tests, seed deterministic fixture data with `cd backend && uv run python manage.py seed_testsprite_frontend_fixture` if that fixture is appropriate for the test plan. Verify that visible state is read from backend APIs and do not treat local UI state as authoritative.
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
ForgeGraph backend is the Django control plane and the only durable source of truth for runtime and product state. It owns authentication, organizations, companies, operations, approvals, whiteboards, communication, commerce, memory, accounting, audit logs, operating-model packs, connector policy, projections, liveness, snapshots, recovery, and durable resume state. It exposes `/health` plus REST APIs under `/api/`. Primary product and operating APIs include `/api/companies/`, `/api/company-operations/`, `/api/approvals/`, `/api/whiteboards/`, `/api/communication/`, `/api/commerce/`, `/api/memory/`, `/api/accounting/`, `/api/credentials/`, `/api/marketplace/`, and `/api/system-state/`. Compatibility and advanced APIs include `/api/graphs/`, `/api/workflows/`, `/api/runs/`, `/api/executions/`, `/api/decisions/`, `/api/agents/`, and `/api/tasks/`. The backend coordinates execution with the Go engine over gRPC and receives signed callbacks through `/api/runs/engine-events`.
```

Suggested additional instruction for API generation:

```md
Use the real local Django API contract. Prefer company, operation, approval, whiteboard, and memory/accounting APIs for product tests. Treat graph/run aliases as compatibility coverage unless explicitly targeting advanced/internal behavior. Register users with `POST /api/auth/register` using a unique email per test. Login with `POST /api/auth/login` and expect an access token in the JSON body plus refresh cookie behavior. Treat `/api/runs/engine-events` as a server-to-server endpoint that requires `X-ForgeGraph-Timestamp` and `X-ForgeGraph-Signature`. Do not write tests that assume the engine, frontend, Redis, Kafka, WebSockets, or event payloads are authoritative durable state.
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
ForgeGraph engine is a Go execution plane that runs backend-issued workflow revision contracts. It exposes gRPC operations for execution and status behavior plus a Prometheus metrics endpoint over HTTP. The engine executes work, emits signed callbacks and observability events, and may hold ephemeral in-memory execution state. It must not own durable run, company, task, approval, memory, cost, snapshot, or recovery state. Tests should focus on gRPC contract correctness, execution behavior, retries, cancellation, callback delivery, statelessness guardrails, and configuration-driven runtime behavior.
```

## Notes

- If TestSprite asks for a repo-wide summary first, use the three descriptions above as the basis for that summary.
- If TestSprite only supports `frontend` and `backend` service types, classify the engine as `backend` and mention explicitly that it is a gRPC service with `/metrics` on HTTP.
- If the frontend form asks whether login is needed, answer `Yes`.
- If a form asks for a starting page or health path, use `/companies` for frontend, `/health` for backend, and `/metrics` for engine.
- When TestSprite asks what to prioritize, steer it toward company workspace, operation, approval, and backend-provenance flows first; advanced graph/editor compatibility routes second.
