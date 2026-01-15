# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

ForgeGraph is a visual, high-performance workflow engine for AI agents and automation. Users design agent workflows visually, run them reliably at scale, and debug them like software.

**Current Phase:** Phase 1 (Django control plane core complete)

See [SPECS.md](SPECS.md) for full project specification.
See [architecture.md](architecture.md) for Clean Architecture structure.

## Build & Development Commands

```bash
# Start all services (postgres, redis, backend, frontend, engine)
./dev up

# Stop all services
./dev down

# View logs
docker-compose logs -f [service_name]

# Run database migrations
./dev migrate

# Open Django shell
./dev shell

# Run backend tests
./dev test

# Run any Django manage.py command
./dev manage <command>
```

### Individual Services

**Backend (Django):**

```bash
cd backend
pip install -r requirements.txt
python manage.py runserver
python manage.py migrate
python manage.py createsuperuser
```

**Frontend (NextJS):**

```bash
cd frontend
npm install
npm run dev
npm run build
```

**Engine (Go gRPC):**

```bash
cd engine
go mod download
go run main.go
go build -o engine .
```

**Regenerate gRPC (when proto changes):**

```bash
cd engine
protoc --go_out=. --go-grpc_out=. proto/engine.proto
```

## Architecture

### Service Boundaries

```text
┌─────────────┐     REST      ┌─────────────────┐     gRPC      ┌──────────┐
│  Frontend   │ ───────────→  │  Control Plane  │ ───────────→  │  Engine  │
│  (NextJS)   │               │  (Django+DRF)   │               │   (Go)   │
└─────────────┘               └─────────────────┘               └──────────┘
       │                              │                               │
       │                              ▼                               │
       │                      ┌─────────────┐                         │
       │                      │  PostgreSQL │ ←───────────────────────┘
       │                      └─────────────┘
       │                              │
       │                      ┌─────────────┐
       └──────────────────→   │    Redis    │ (optional: event bus)
                              └─────────────┘
```

### Why Django + Go Split

- **Django (control-plane):** Fast shipping for auth, admin, CRUD, API surface
- **Go (engine):** High-performance runtime for concurrency, scheduling, timeouts

### Key Directories

- `frontend/` - NextJS app (graph builder, prompt library, run viewer)
- `backend/` - Django REST API (auth, graphs, prompts, runs)
- `engine/` - Go gRPC service (workflow execution, node runners)

### Data Flow

1. Frontend saves graph JSON via REST to control-plane
2. Control-plane stores GraphVersion in Postgres
3. User triggers run → control-plane calls engine via gRPC
4. Engine executes DAG, writes NodeRun traces to Postgres
5. Frontend polls for run status (MVP) or receives SSE updates (v1)

### Node Types (MVP)

- **Prompt** - LLM calls with template variables
- **HTTP Tool** - External API calls
- **Transform** - State transformations (safe expressions only)
- **Branch** - Conditional routing
- **Merge** - Join parallel branches
- **Human Gate** - Pause for approval
- **Output** - Finalize run result

### State Management

Engine maintains `map[string]any` state:

- `state["node.<id>.output"]` - Node outputs
- `state["vars.<name>"]` - Computed variables

## Development Phases

- [x] Phase 0: Monorepo scaffolding + Docker + gRPC ping
- [x] Phase 1: Django models + auth + prompt library
- [ ] Phase 2: NextJS graph builder + save/load JSON
- [ ] Phase 3: Go engine basic execution (prompt/http/output nodes)
- [ ] Phase 4: Run viewer + persistence
- [ ] Phase 5: Branch/merge + retry/timeout
- [ ] Phase 6: Human gate
- [ ] Phase 7: Polish + demo workflows + docs

## Service Ports

| Service    | Port  |
|------------|-------|
| Frontend   | 3000  |
| Backend    | 8000  |
| Engine     | 50051 |
| PostgreSQL | 5433  |
| Redis      | 6379  |

## API Documentation

When running in DEBUG mode, API documentation is available at:

- **Swagger UI:** <http://localhost:8000/api/docs/>
- **ReDoc:** <http://localhost:8000/api/redoc/>
- **OpenAPI Schema:** <http://localhost:8000/api/schema/>

## Default Development Credentials

When running via Docker Compose, a superuser is automatically created:

- **Email:** `admin@forgegraph.local`
- **Password:** admin123456

## Testing

Backend tests use pytest with pytest-django:

```bash
# Run all tests
cd backend
USE_SQLITE=true pytest

# Run specific test file
USE_SQLITE=true pytest tests/integration/adapters/test_auth_api.py

# Run with verbose output
USE_SQLITE=true pytest -v
```
