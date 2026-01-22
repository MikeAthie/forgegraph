# ForgeGraph

A visual, high-performance workflow engine for AI agents and automation, built for production.

**Design agent workflows visually. Run them reliably at scale. Debug them like software.**

## What is ForgeGraph?

ForgeGraph uses a **schema-driven, LangGraph-style runtime** with an **n8n-inspired UX**. Users build workflows as directed graphs of Nodes connected by Edges. The execution engine runs the graph deterministically while supporting conditional branching, parallelism, validation, and final outputs.

### Core Principles

- **Agnostic execution primitives** - A small, stable set of node types that can express most workflows
- **Schema-first reliability** - Outputs can be validated and structured (e.g., JSON Schema) to reduce hallucinations
- **N8n-like UX, LangGraph-like semantics** - Easy graph building with real runtime logic (start nodes, conditional edges, merging, final output)
- **State-driven execution** - Nodes read from and write to a shared run state

### Key Features (MVP)

- **Visual Graph Builder** - Drag-and-drop workflow design with real-time validation
- **Prompt Library** - Built-in prompt templates for research, summarization, extraction, and more
- **High-Performance Engine** - Go-based execution with parallel branches, retries, and timeouts
- **Debug Like Software** - Full run history with per-node traces, timings, and error details
- **Human-in-the-Loop** - Pause workflows for human approval or input

## Architecture

```text
┌─────────────────┐     REST      ┌─────────────────┐     gRPC      ┌─────────────────┐
│    Frontend     │ ───────────▶  │  Control Plane  │ ───────────▶  │     Engine      │
│    (NextJS)     │               │    (Django)     │               │    (Go gRPC)    │
│   Port: 3000    │               │   Port: 8000    │               │   Port: 50051   │
└─────────────────┘               └─────────────────┘               └─────────────────┘
                                         │                                  │
                                         ▼                                  ▼
                                  ┌─────────────────┐               ┌─────────────────┐
                                  │   PostgreSQL    │               │      Redis      │
                                  │   Port: 5432    │               │   Port: 6379    │
                                  └─────────────────┘               └─────────────────┘
```

### Why Django + Go?

- **Django (Control Plane):** Fast shipping for auth, admin, CRUD, API surface
- **Go (Engine):** High-performance runtime for concurrency, scheduling, timeouts

## Prerequisites

- Docker (version 20.10 or higher)
- Docker Compose (version 2.0 or higher)

## Quick Start

1. Clone the repository:

   ```bash
   git clone <repository-url>
   cd forgegraph
   ```

2. Make the dev script executable (macOS/Linux/WSL):

   ```bash
   chmod +x dev
   ```

3. Start all services:

   ```bash
   ./dev up
   # or (PowerShell):
   docker compose up --build -d
   ```

4. Access the services:
   - **Frontend**: http://localhost:3000
   - **Django API**: http://localhost:8000
   - **gRPC Engine**: localhost:50051

## Development Commands

```bash
# Start all services
./dev up

# Stop all services
./dev down

# View logs
./dev logs

# Restart services
./dev restart

# Rebuild services
./dev build

# Check service status
./dev ps
```

## Verifying Services

### Frontend

Open http://localhost:3000 in your browser. You should see "ForgeGraph running" and the backend health status.

## Graph Builder

1. Create a graph in the UI and open it (routes under `/graphs/[graphId]`).
2. Add nodes from the left palette (click to add; if a node is selected, click-to-add will auto-connect).
3. Connect nodes on the canvas and configure them in the right inspector panel.
4. Save a new version with the save button or `Ctrl+S` / `Cmd+S`, then use the version dropdown to load older versions.

**Tips**
- Use `Tidy` to auto-layout, `Ctrl+A` / `Cmd+A` to select all, and `Delete` to remove selected nodes/edges.
- Use the MiniMap + zoom controls for large workflows.
- "Note" nodes are editor-only annotations (saved in `editor_state`, not executed by the engine).

## Observability Demo (Phase 4)

Use the seed commands to validate the run viewer and WebSocket delta updates without the Go engine.

```bash
cd backend

# Seed a demo graph + 3 demo runs (succeeded/failed/running)
uv run python manage.py seed_phase4_demo

# Stream a live execution trace over WebSockets (open /runs first)
uv run python manage.py stream_run_trace <graph_version_id> --run-status succeeded
```

UI flow:
- Open `/runs` to see the run history.
- Open a run to view the node-by-node trace (polling + WebSocket deltas).
- Use **Open in editor** to jump to `/graphs/{graphId}?runId={runId}` and see the execution overlay on the canvas + the execution side panel.

### Backend

```bash
curl http://localhost:8000/health
```

Expected response:

```json
{"status": "ok"}
```

### gRPC Engine

The gRPC engine runs on port 50051 and implements a Ping RPC that returns "pong".

## Execution Model

**Shared Runtime State:** Execution maintains a shared state map. After each node runs, it writes output under a namespaced key (`state["node.<id>.output"]`). Downstream nodes reference previous outputs via state paths.

**Start Nodes:** Any node with no incoming edges (indegree = 0). Multiple start nodes run in parallel.

**Scheduling:** Queue-based execution with worker pool. Nodes become ready when all upstream dependencies are satisfied. Ready nodes execute concurrently.

**Branching:** Branch nodes evaluate boolean conditions and activate exactly one outgoing edge path (true or false). Non-selected branches are skipped.

**Merging:** Merge nodes wait until all incoming branches complete, then continue downstream.

## Node Types

| Node | Description |
|------|-------------|
| **Prompt** | Calls LLM with structured instructions, can target an output schema, writes validated output to state |
| **Tool (HTTP)** | Generic tool executor (HTTP as baseline), UX uses "service pills" as presets, writes response to state |
| **Transform** | Deterministic state transforms (mapping, formatting, extraction), writes derived values to state |
| **Branch** | Evaluates conditions → routes execution to exactly one path |
| **Merge** | Waits for multiple inputs → continues downstream |
| **Human Gate** | Pauses run → resumes on approval/input |
| **Output** | Collects + validates final result → ends run |

## Project Structure

```text
forgegraph/
├── dev                     # Development CLI script
├── docker-compose.yml      # Docker Compose configuration
├── CLAUDE.md               # Claude Code guidance
├── SPECS.md                # Full project specification
├── README.md
├── backend/                # Django REST API (Control Plane)
│   ├── Dockerfile
│   ├── requirements.txt
│   ├── manage.py
│   └── app/
├── frontend/               # NextJS application
│   ├── Dockerfile
│   ├── package.json
│   ├── next.config.js
│   └── pages/
└── engine/                 # Go gRPC service
    ├── Dockerfile
    ├── go.mod
    ├── main.go
    ├── internal/
    └── proto/
```

## Environment Variables

### Backend

| Variable | Description | Default |
|----------|-------------|---------|
| DB_HOST | PostgreSQL host | postgres |
| DB_PORT | PostgreSQL port | 5432 |
| DB_NAME | Database name | forgegraph |
| DB_USER | Database user | forgegraph |
| DB_PASSWORD | Database password | forgegraph_secret |
| REDIS_HOST | Redis host | redis |
| REDIS_PORT | Redis port | 6379 |
| DEBUG | Django debug mode | true |

### Engine

| Variable | Description | Default |
|----------|-------------|---------|
| GRPC_PORT | gRPC server port | 50051 |

### Frontend

| Variable | Description | Default |
|----------|-------------|---------|
| NEXT_PUBLIC_API_URL | Backend API URL | http://localhost:8000 |

## Development Roadmap

- [x] Phase 0: Monorepo scaffolding + Docker + gRPC ping
- [x] Phase 1: Django models + auth + prompt library
- [x] Phase 2: NextJS graph builder + save/load JSON
- [x] Phase 3: Go engine basic execution
- [x] Phase 4: Run viewer + persistence
- [x] Phase 5: Branch/merge + retry/timeout
- [ ] Phase 6: Human gate
- [ ] Phase 7: Polish + demo workflows + docs

See [SPECS.md](SPECS.md) for the full project specification.

## License

MIT
