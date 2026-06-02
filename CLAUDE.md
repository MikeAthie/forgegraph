# CLAUDE.md

This file provides guidance to Claude Code and other coding agents working in this repository.

## Project Overview

ForgeGraph is an AI Company Operating System.

The product centers companies, departments, operations, approvals, deliverables, and operating-model packs. Advanced workflow and graph editing remains available for expert/internal use, but primary product work should use company language from [docs/product/canonical-ontology.md](docs/product/canonical-ontology.md).

## Runtime Rule

Follow [docs/architecture/runtime-invariants.md](docs/architecture/runtime-invariants.md) strictly.

If any repo document, test, or implementation note conflicts with that file, `runtime-invariants.md` wins.

Non-negotiable summary:

- Backend is the only durable source of truth.
- Engine executes work and may hold ephemeral execution state only.
- Frontend observes backend-owned state and submits user commands; it is not authoritative.
- Events, Redis, Kafka, WebSocket messages, and client state are transport or observability artifacts, not durable truth.
- Snapshots, liveness, recovery, approvals, and resume state are backend-owned.

## Components

- `backend/`: Django control plane, APIs, persistence, projections, governance, memory, accounting, marketplace, and runtime recovery.
- `engine/`: Go gRPC execution plane for running backend-issued workflow revision contracts.
- `frontend/`: Next.js operator console for companies, operations, approvals, advanced operating models, and admin surfaces.
- `operating_model_packs/`: pack-owned operating-model configuration, including Digital Marketing Pro / Atlas.

## Build And Test Commands

Backend:

```powershell
cd backend
uv sync
uv run python manage.py migrate
uv run pytest
uv run pytest tests/unit/
uv run ruff check .
uv run mypy .
```

Engine:

```powershell
cd engine
go test ./...
go test -race ./...
go build -o engine .
```

Frontend:

```powershell
cd frontend
npm ci
npm run dev
npm run build
npm test
npm run test:e2e
npm run terminology:check
```

Repo gates:

```powershell
.\checks-fast.ps1
.\checks.ps1
```

Docker:

```powershell
docker compose up --build -d
docker compose exec backend python manage.py migrate
docker compose logs -f
docker compose down
```

Atlas live acceptance:

```powershell
cd frontend
npm run test:e2e:atlas:docker:local-llm
```

## Architecture

```text
frontend command
  -> backend validates and persists intent
  -> backend dispatches execution contract over gRPC
  -> engine executes work
  -> engine emits signed callbacks/events
  -> backend ingests idempotently and materializes state
  -> backend notifies frontend
```

The backend is the control plane. The engine is the execution plane. The frontend is an observer and command surface.

## Product Language

Use product terms in user-facing code and docs:

- Company
- Department
- Operation
- Task
- Approval
- Deliverable
- Advanced operating model

Keep raw internal terms such as graph, node, run, node run, workflow, execution, checkpoint, and projection out of primary UX unless the surface is explicitly advanced/internal.

## Testing Notes

- Backend tests should verify durable state correctness, idempotency, liveness, recovery, access control, and projection behavior.
- Engine tests should verify execution behavior and callback/write-intent boundaries, not durable ownership.
- Frontend tests should verify product surfaces reflect backend-owned state.
- Runtime-sensitive tests must not treat event streams, WebSocket messages, local state, Redis, Kafka, or engine memory as authoritative.

## Documentation Notes

Before changing runtime code, docs, or tests, answer:

`Does this make any component other than the backend authoritative for durable state?`

If yes, the change violates the repo contract.
