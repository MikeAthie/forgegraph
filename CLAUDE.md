# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

ForgeGraph is a workflow graph execution platform with three components:
- **Backend**: Django REST API control plane (Python 3.12+)
- **Engine**: Go gRPC execution engine (Go 1.22)
- **Frontend**: Next.js React UI for graph editing (Node 20, TypeScript)

## Build & Test Commands

### Backend (Django)
```bash
cd backend
python -m pytest                                    # All tests
python -m pytest tests/unit/                        # Unit tests only
python -m pytest tests/integration/                 # Integration tests only
python -m pytest -q tests/integration/adapters/test_run_api.py  # Single file
ruff check .                                        # Lint
mypy .                                              # Type check
python manage.py migrate                            # Run migrations
python -m daphne config.asgi:application            # Dev server
```

### Engine (Go)
```bash
cd engine
go build -o engine .                                # Build
go test ./...                                       # All tests
go test -race -v ./...                              # Tests with race detection
go test -v ./application/usecase/scheduler_test.go # Single test file
```

### Frontend (Next.js)
```bash
cd frontend
npm run dev                                         # Dev server (:3000)
npm run build                                       # Production build
npm test                                            # Jest unit tests
npm run test:watch                                  # Watch mode
npm run test:e2e                                    # Playwright E2E tests
npm run lint                                        # ESLint
```

### Full Stack
```powershell
./test-all.ps1           # Full test suite
./test-all.ps1 -Fast     # Quick mode (key tests only)
./test-all.ps1 -SkipE2E  # Skip Playwright tests
```

### Docker Development
```bash
./dev up          # Start all services with build
./dev down        # Stop services
./dev logs        # Stream logs
./dev migrate     # Run migrations
./dev test        # Run backend tests
./dev shell       # Django shell
```

## Architecture

```
Frontend (Next.js)  ──HTTP/WebSocket──>  Backend (Django)  ──gRPC──>  Engine (Go)
                                               │
                                          PostgreSQL + Redis
```

**Communication Flow:**
1. Frontend calls Backend REST API (axios) and WebSocket for real-time updates
2. Backend delegates graph execution to Engine via gRPC (proto in `engine/proto/`)
3. Engine executes nodes, reports status back through gRPC
4. Backend broadcasts updates to Frontend via Django Channels WebSocket

**Clean Architecture** across all components:
- `domain/` - Entities and business logic
- `application/` - Use cases and DTOs
- `adapters/` (backend) or `adapter/` (engine) - External interfaces (API, repositories)
- `infrastructure/` - Database, external services

## Key Domain Concepts

**Graph**: Workflow definition with versioned snapshots (SHA256 checksum)
- Node types: Prompt, Tool, Transform, Branch, Merge, Output, Memory, Subgraph

**Run**: Execution instance of a graph version
- Statuses: PENDING → RUNNING → PAUSED/SUCCEEDED/FAILED/CANCELED
- Supports checkpoints, events, and node-level caching

**Human Gates**: Approval nodes that pause execution for human review

## Services (docker-compose.yml)

| Service   | Port  | Purpose                    |
|-----------|-------|----------------------------|
| postgres  | 5433  | PostgreSQL 16 database     |
| redis     | 6379  | Cache & message broker     |
| backend   | 8000  | Django API                 |
| engine    | 50051 | gRPC execution server      |
| frontend  | 3000  | Next.js app                |

## Testing Notes

- Backend uses SQLite in-memory for test isolation
- Frontend E2E tests use temporary SQLite DB, not dev database
- Run `./test-all.ps1 -Fast` for quick validation during development
