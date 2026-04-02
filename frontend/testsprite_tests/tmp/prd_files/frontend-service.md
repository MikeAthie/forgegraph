# Frontend Service

## Overview

The frontend service is the ForgeGraph user interface. It is a Next.js 14 application using React 18 and TypeScript. It provides the visual graph editor, authentication flows, prompt and run management pages, analytics dashboards, memory views, admin pages, approvals, onboarding, and runtime marketplace UI. It communicates with the Django backend over HTTP and relies on backend-managed execution state from the engine.

Default local port: `3000`

Primary entrypoints:
- `frontend/pages/_app.tsx`
- `frontend/pages/index.tsx`
- `frontend/components/`
- `frontend/lib/api.ts`

## Stack

- Next.js 14
- React 18
- TypeScript
- Jest + Testing Library
- Playwright
- Radix UI primitives

## Responsibilities

- Render the landing page and authentication entry points
- Provide the graph authoring experience and node configuration UI
- Show runs, run traces, approvals, prompts, credentials, memory views, analytics, onboarding, and admin workflows
- Call backend APIs for CRUD actions and execution workflows
- Present backend and engine state to users in a usable form

## Main Pages

Core routes:
- `/`
- `/login`
- `/register`
- `/graphs`
- `/graphs/[graphId]`
- `/runs`
- `/runs/[runId]`
- `/prompts`
- `/memory`
- `/approvals`
- `/credentials`
- `/onboarding`

Admin and analytics routes:
- `/admin`
- `/admin/audit-logs`
- `/admin/billing`
- `/admin/help`
- `/admin/marketplace`
- `/admin/operations`
- `/admin/organization`
- `/admin/sso`
- `/analytics/llm`
- `/analytics/memory`

Callback routes:
- `/oauth/callback`
- `/sso/callback`

## Key UI Areas

- Graph editor components under `frontend/components/graph-editor/`
- Shared UI primitives under `frontend/components/ui/`
- Auth state in `frontend/contexts/AuthContext.tsx`
- Wizard/onboarding state in `frontend/contexts/WizardContext.tsx`
- API helpers and graph utilities under `frontend/lib/`

## External Dependencies

- Django backend API for data, auth, and run orchestration
- Engine behavior is surfaced indirectly through backend APIs and run-event streams
- Playwright E2E setup can start backend, engine, and a mock LLM service together

## Existing Test Surface

- Unit and component tests under `frontend/__tests__/unit/` and `frontend/__tests__/components/`
- Integration tests under `frontend/__tests__/integration/`
- End-to-end Playwright tests under `frontend/__tests__/e2e/`

Representative areas already covered:
- Landing and admin pages
- Graph editor components, forms, dialogs, validation, and wizard flows
- Auth context and protected routes
- Graph utilities and type inference helpers
- E2E flows for auth, graph editing, runs, prompts, onboarding, marketplace runtime, and memory browser

## Test Notes

- Many authenticated pages depend on backend auth/session behavior
- E2E runs can orchestrate frontend, backend, engine, and a mock LLM together
- Frontend behavior includes both page-level rendering and graph-editor interaction complexity
- Tests should cover loading states, error handling, route protection, form validation, and API-driven UI updates

## Useful Commands

From `frontend/`:

```bash
npm run dev
npm test
npm run test:e2e
npm run lint
```

## Playwright Environment Notes

The existing Playwright setup can launch:
- the frontend on a dev port, default `3001`
- the backend on `8002`
- the engine on `50071`
- an LLM mock server on `8011`

This makes the frontend test environment suitable for realistic multi-service E2E coverage.
