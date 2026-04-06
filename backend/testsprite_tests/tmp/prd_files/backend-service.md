# Backend Service

## Overview

The backend service is the ForgeGraph control plane. It is a Django 5 application with Django REST Framework and Channels. It owns authentication, graph and prompt management, run orchestration, tenant policies, billing, analytics, memory governance, audit logs, and integrations. It exposes REST APIs and WebSocket-capable infrastructure for the frontend and coordinates execution with the Go engine over gRPC and callback endpoints.

Default local port: `8000`

Primary entrypoints:
- `backend/manage.py`
- `backend/config/asgi.py`
- `backend/config/urls.py`

## Stack

- Python 3.12+
- Django 5
- Django REST Framework
- Channels + Daphne
- PostgreSQL
- Redis
- Celery
- gRPC client support

## Responsibilities

- Authenticate users with JWT and SSO flows
- Manage organizations, members, policies, billing, and audit logs
- Create, validate, version, and store workflow graphs
- Manage prompts, templates, credentials, and marketplace runtime metadata
- Start, resume, replay, cancel, and track workflow runs
- Receive engine callbacks and expose run-event APIs to the frontend
- Provide memory governance, analytics, and retention APIs
- Expose health and schema/docs endpoints

## Main API Surface

Base prefixes are mounted under `/api/` and `/api/v1/`.

Important route groups:
- `/api/auth/`
- `/api/graphs/`
- `/api/runs/`
- `/api/prompts/`
- `/api/templates/`
- `/api/memory/`
- `/api/analytics/`
- `/api/credentials/`
- `/api/integrations/`
- `/api/approvals/`
- `/api/marketplace/`
- `/api/orgs/`
- `/api/policies/`
- `/api/retention/`
- `/api/audit-logs/`
- `/api/scim/`
- `/health`

Important run-related endpoints:
- `POST /api/runs/start`
- `POST /api/runs/invoke`
- `GET /api/runs/<run_id>`
- `GET /api/runs/<run_id>/events`
- `GET /api/runs/<run_id>/stream`
- `POST /api/runs/<run_id>/resume`
- `POST /api/runs/<run_id>/replay`
- `POST /api/runs/engine-events`

## External Dependencies

- PostgreSQL for persistent application data
- Redis for caching and async/runtime support
- Go engine service for workflow execution
- Optional external providers for OAuth, billing, embeddings, and model access

## Interaction With Other Services

- Serves JSON APIs consumed by the Next.js frontend
- Calls the Go engine to start and manage workflow execution
- Receives engine callback events and surfaces them to clients
- Exposes memory- and analytics-related APIs used by UI pages and tests

## Existing Test Surface

- Unit tests under `backend/tests/unit/`
- Integration tests under `backend/tests/integration/`
- End-to-end backend flows under `backend/tests/e2e/`

Representative areas already covered:
- Auth and registration
- Graph APIs and validation
- Run APIs and run WebSocket/event behavior
- Memory APIs, analytics, and gRPC health/service integration
- Marketplace, billing, SSO, SCIM, onboarding, audit logs, and integrations

## Test Notes

- Many API endpoints require authentication
- Some flows rely on database state, tenant context, or seeded fixtures
- Engine-related tests may need the engine callback path and/or gRPC service available
- Memory and analytics scenarios may depend on Redis/PostgreSQL setup
- The service includes both synchronous API behavior and async/event-driven run behavior

## Useful Commands

From `backend/`:

```bash
python manage.py migrate
python -m daphne config.asgi:application
python -m pytest
python -m pytest tests/unit/
python -m pytest tests/integration/
```
