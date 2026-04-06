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
ForgeGraph frontend is a Next.js 14 application built with React 18 and TypeScript. It is the main user interface for the platform and includes authentication flows, a visual graph editor, run monitoring pages, prompt management, approvals, credentials, onboarding, memory views, analytics dashboards, and admin pages. It talks to the Django backend over HTTP and shows execution state produced by the backend and Go engine. The most important routes are `/`, `/login`, `/register`, `/graphs`, `/graphs/[graphId]`, `/runs`, `/runs/[runId]`, `/prompts`, `/memory`, `/approvals`, `/credentials`, `/onboarding`, `/admin/*`, `/analytics/llm`, and `/analytics/memory`. The graph editor under `components/graph-editor/` is the most interaction-heavy area. Existing tests use Jest, Testing Library, and Playwright. For realistic E2E coverage, frontend tests may depend on the backend, engine, and a mock LLM service running together.
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
ForgeGraph backend is a Django 5 control-plane service using Django REST Framework and Channels. It owns authentication, organizations, billing, policies, audit logs, graph and prompt management, run orchestration, marketplace runtime data, onboarding, memory governance, retention, analytics, and integration endpoints. It exposes REST APIs under `/api/` and `/api/v1/`, plus `/health` and optional schema/docs endpoints. The most important API groups are `/api/auth/`, `/api/graphs/`, `/api/runs/`, `/api/prompts/`, `/api/templates/`, `/api/memory/`, `/api/analytics/`, `/api/credentials/`, `/api/integrations/`, `/api/approvals/`, `/api/marketplace/`, `/api/orgs/`, `/api/policies/`, `/api/retention/`, `/api/audit-logs/`, and `/api/scim/`. It coordinates workflow execution with the Go engine over gRPC and receives engine callbacks through `/api/runs/engine-events`. Tests should cover authenticated API behavior, validation, data persistence, run lifecycle, event/callback handling, and integration points with Redis, PostgreSQL, and the engine.
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
