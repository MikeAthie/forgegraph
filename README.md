# ForgeGraph

A visual, high-performance workflow engine for AI agents and automation, built for production.

**Design agent workflows visually. Run them reliably at scale. Debug them like software.**

## What is ForgeGraph?

ForgeGraph lets you build AI agent workflows using a visual graph builder. Connect nodes like Prompt, HTTP, Branch, and Merge to create complex automation pipelines. Execute them with built-in concurrency, retries, and timeouts. Debug runs with full node-level visibility into inputs, outputs, and timings.

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

2. Make the dev script executable:

   ```bash
   chmod +x dev
   ```

3. Start all services:

   ```bash
   ./dev up
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
- “Note” nodes are editor-only annotations (saved in `editor_state`, not executed by the engine).

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

## Node Types

| Node | Description |
|------|-------------|
| **Prompt** | Call LLM providers with template variables |
| **HTTP Tool** | Call external HTTP APIs |
| **Transform** | Transform state with safe expressions |
| **Branch** | Conditional routing based on state |
| **Merge** | Join parallel branches |
| **Human Gate** | Pause for human approval or input |
| **Output** | Finalize run output |

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
- [ ] Phase 3: Go engine basic execution
- [ ] Phase 4: Run viewer + persistence
- [ ] Phase 5: Branch/merge + retry/timeout
- [ ] Phase 6: Human gate
- [ ] Phase 7: Polish + demo workflows + docs

See [SPECS.md](SPECS.md) for the full project specification.

## License

MIT
