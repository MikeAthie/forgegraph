# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

ForgeGraph is a visual, high-performance workflow engine for AI agents and automation. Users design agent workflows visually, run them reliably at scale, and debug them like software.

**Core Principles:**

- **Agnostic execution primitives** - A small, stable set of node types that can express most workflows
- **Schema-first reliability** - Outputs can be validated and structured to reduce hallucinations
- **N8n-like UX, LangGraph-like semantics** - Easy graph building with real runtime logic
- **State-driven execution** - Nodes read from and write to a shared run state

**Current Phase:** Phase 6 (Human gate)

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

# Seed a sample run trace for the Runs UI (Phase 4)
./dev manage seed_run_trace <graph_version_uuid>
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

### Execution Model

**Start Nodes (Triggers):**

- Any node with no incoming edges (indegree = 0) is a start node
- Multiple start nodes run in parallel on run start

**Scheduling & Parallelism:**

- Queue-based execution with worker pool (goroutines)
- Node becomes ready when all upstream dependencies are satisfied
- Ready nodes execute concurrently

**Conditional Branching:**

- Branch node evaluates boolean condition against state
- Exactly one outgoing edge path is activated (true or false)
- Non-selected branches are skipped for that run

**Merging:**

- Merge node waits until all incoming branches complete
- Supports "namespaced" (default) and "last_write_wins" merge strategies

### Node Types (MVP)

| Node           | Status             | Description                                               |
| -------------- | ------------------ | --------------------------------------------------------- |
| **Prompt**     | ⚠️ Interface ready | Calls LLM with structured instructions, validates output  |
| **Tool (HTTP)**| ✅ Complete        | Generic tool executor (HTTP baseline, service presets)    |
| **Transform**  | ✅ Complete        | Deterministic state transforms (mapping, formatting)      |
| **Branch**     | ✅ Complete        | Evaluates conditions → routes execution                   |
| **Merge**      | ✅ Complete        | Waits for multiple inputs → continues downstream          |
| **Human Gate** | ❌ Phase 6         | Pauses run → resumes on approval/input                    |
| **Output**     | ✅ Complete        | Collects + validates final result → ends run              |

### Branch Node Conditions

The branch executor supports these condition expressions:

```text
vars.score > 80                    # Numeric comparison
node.http_1.output.status == 200   # Node output check
vars.approved == true              # Boolean comparison
input.mode != "test"               # String inequality
vars.count                         # Truthy check (non-zero)
```

Supported operators: `==`, `!=`, `>`, `<`, `>=`, `<=`

### State Management

Engine maintains a shared state map during execution:

```text
state["node.<id>.output"]  # Node outputs (written after each node runs)
state["vars.<name>"]       # User/computed variables
state["input.<name>"]      # Run input values
```

Downstream nodes reference previous outputs via state paths. This makes wiring simple and deterministic.

## Development Phases

- [x] Phase 0: Monorepo scaffolding + Docker + gRPC ping
- [x] Phase 1: Django models + auth + prompt library
- [x] Phase 2: NextJS graph builder + save/load JSON
- [x] Phase 3: Go engine basic execution (prompt/http/output nodes)
- [x] Phase 4: Run viewer + persistence
- [x] Phase 5: Branch/merge + retry/timeout
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
USE_SQLITE=true USE_IN_MEMORY_CHANNEL_LAYER=true pytest

# Run specific test file
USE_SQLITE=true USE_IN_MEMORY_CHANNEL_LAYER=true pytest tests/integration/adapters/test_auth_api.py

# Run with verbose output
USE_SQLITE=true USE_IN_MEMORY_CHANNEL_LAYER=true pytest -v
```

Engine tests use Go's built-in testing:

```bash
cd engine
go test ./...

# Run with verbose output
go test -v ./...
```
