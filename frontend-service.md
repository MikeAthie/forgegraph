# Frontend Service

The frontend is the ForgeGraph operator console.

It is a state observer and command surface. It is not a source of truth.

## Responsibilities

- Present company work in product language: companies, departments, operations, tasks, approvals, and deliverables.
- Let users create companies, operate existing companies, resolve approvals, inspect operations, and use advanced operating-model tooling when needed.
- Read canonical state from backend APIs and reflect backend-driven updates over HTTP, polling, and WebSockets.
- Translate raw backend and engine terms through frontend domain repositories and ViewModels before they reach primary UX.

## Primary Routes

- `/companies`
- `/companies/[companyId]`
- `/runs`
- `/runs/[runId]`
- `/approvals`

## Secondary And Expert Routes

- `/workflows`: advanced operating models.
- `/graphs`: compatibility/internal graph editor surface.
- `/executions` and `/executions/[id]`: compatibility redirects to operation views.
- `/memory`, `/accounting`, `/library`, `/departments`, `/tasks`: supporting operational views.
- `/admin/*`, `/analytics/*`, `/prompts`, `/credentials`, `/onboarding`: specialist and admin surfaces.
- `/login`, `/register`, `/oauth/callback`, `/sso/callback`: authentication and callback routes.

## IA Rules

- Company-first, not builder-first.
- State first, actions second.
- Summaries before raw logs.
- Company status, approvals, deliverables, and controls before technical traces.
- Do not infer durable truth from local state when backend state is available.
- Keep advanced/internal terminology out of primary company surfaces.

## Test Automation Guidance

- Prefer `/companies`, company workspace flows, `/runs`, and `/approvals` for product-facing browser tests.
- Treat `/graphs`, raw graph editing, and low-level workflow routes as advanced/internal or compatibility coverage.
- Authenticate through the UI for browser coverage unless a test is explicitly verifying token/session plumbing.
- Verify that visible state traces back to backend APIs and backend-owned records.
- Favor flows that move from company summary to operation detail, approval resolution, deliverable inspection, and supporting evidence.

For deterministic hosted browser automation, the backend command `seed_testsprite_frontend_fixture` prepares the shared test user with:

- one editable prompt
- one pending approval
- one visible memory observation
- one visible credential
