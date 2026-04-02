# ForgeGraph

A visual workflow graph execution platform for building, testing, and running AI-powered automation pipelines.

![Python](https://img.shields.io/badge/Python-3.12+-blue?logo=python&logoColor=white)
![Go](https://img.shields.io/badge/Go-1.23-00ADD8?logo=go&logoColor=white)
![Next.js](https://img.shields.io/badge/Next.js-14-black?logo=next.js&logoColor=white)
![TypeScript](https://img.shields.io/badge/TypeScript-5.0-3178C6?logo=typescript&logoColor=white)
![License](https://img.shields.io/badge/License-MIT-green)

## Features

- **Visual Graph Editor** — Drag-and-drop graph builder with validation, inspector flows, templates, and quick-add runtime packages
- **Agent Node Runtime** — First-class `agent` nodes with bounded tool loops, step traces, and approval-aware tool policies
- **Runtime Marketplace** — Honest package classes for templates vs executable runtime tools, with tenant-scoped manifest delivery
- **Human-in-the-Loop** — Approval pauses, resumable runs, and agent approval states surfaced in the run UI
- **Version Control** — Graph versioning with SHA256 checksums and stable Graph JSON contracts
- **Real-time Monitoring** — WebSocket/SSE run updates, per-node status, agent traces, and streamed chunks
- **Checkpoints, Replay, and Caching** — Resume paused runs, replay from checkpoints, and cache node outputs
- **Cloud-Safe Policies** — Runtime mode enforcement, blocked `exec` tools in Cloud, policy-denied auditability
- **Budgets and Usage Controls** — Token/cost analytics, quotas, budgets, and entitlements already built into the control plane

## Architecture

```
┌─────────────────┐     ┌─────────────────┐     ┌─────────────────┐
│    Frontend     │────▶│     Backend     │────▶│     Engine      │
│   (Next.js)     │ WS  │    (Django)     │gRPC │      (Go)       │
│   Port 3000     │     │   Port 8000     │     │   Port 50051    │
└─────────────────┘     └────────┬────────┘     └─────────────────┘
                                 │
                        ┌────────┴────────┐
                        │   PostgreSQL    │
                        │   + Redis       │
                        └─────────────────┘
```

| Component | Technology | Purpose |
|-----------|------------|---------|
| Frontend | Next.js 14, React 18, TypeScript | Visual graph editor and monitoring UI |
| Backend | Django 5, DRF, Channels | REST API, WebSocket, authentication |
| Engine | Go 1.23, gRPC | High-performance graph execution |
| Database | PostgreSQL 16 | Persistent storage |
| Cache | Redis 7 | Caching and message broker |

## Getting Started

### Prerequisites

- Docker & Docker Compose
- Node.js 20+ (for frontend development)
- Python 3.12+ (for backend development)
- Go 1.23+ (for engine development)

### Quick Start with Docker

```bash
# Clone the repository
git clone https://github.com/your-org/forgegraph.git
cd forgegraph

# Start all services
./dev up

# The application is now running:
# - Frontend: http://localhost:3000
# - Backend API: http://localhost:8000
# - Engine gRPC: localhost:50051
```

### Local Development Setup

#### Frontend
```bash
cd frontend
npm install
npm run dev
```

#### Backend
```bash
cd backend
python -m venv venv
source venv/bin/activate  # or `venv\Scripts\activate` on Windows
pip install -e ".[dev]"
python manage.py migrate
python -m daphne config.asgi:application
```

#### Engine
```bash
cd engine
go build -o engine .
./engine
```

## Development Commands

### Using the `dev` Script

```bash
./dev up          # Start all services with build
./dev down        # Stop all services
./dev logs        # Stream logs from all services
./dev migrate     # Run database migrations
./dev test        # Run backend tests
./dev shell       # Open Django shell
./dev ps          # Show running services
```

### Running Tests

```bash
# Full test suite (PowerShell)
./test-all.ps1

# Quick mode - key tests only
./test-all.ps1 -Fast

# Skip E2E tests
./test-all.ps1 -SkipE2E
```

#### Component-specific tests

```bash
# Backend
cd backend
python -m pytest                      # All tests
python -m pytest tests/unit/          # Unit tests
python -m pytest tests/integration/   # Integration tests
ruff check .                          # Linting
mypy .                                # Type checking

# Engine
cd engine
go test ./...                         # All tests
go test -race -v ./...                # With race detection

# Frontend
cd frontend
npm run format:check                     # Prettier check
npm test                              # Jest unit tests
npm run test:e2e                      # Playwright E2E tests
npm run lint                          # ESLint
```

## Project Structure

```
forgegraph/
├── backend/                 # Django REST API
│   ├── domain/              # Business entities and services
│   ├── application/         # Use cases and DTOs
│   ├── adapters/            # API routes, repositories
│   ├── infrastructure/      # ORM, gRPC client, auth
│   └── tests/               # pytest tests
│
├── engine/                  # Go execution engine
│   ├── domain/              # Core entities (Graph, Node, Run)
│   ├── application/         # Scheduler, RunManager
│   ├── adapter/             # gRPC server, executors
│   └── proto/               # Protobuf definitions
│
├── frontend/                # Next.js application
│   ├── pages/               # Next.js routes
│   ├── components/          # React components
│   ├── lib/                 # Utilities and API client
│   └── __tests__/           # Jest and Playwright tests
│
├── docker-compose.yml       # Service orchestration
├── dev                      # Development utility script
└── test-all.ps1             # Full test runner
```

## API Overview

The Backend exposes a REST API with the following main endpoints:

| Endpoint | Method | Description |
|----------|--------|-------------|
| `/api/graphs` | GET, POST | List and create graphs |
| `/api/graphs/{id}` | GET, PUT, DELETE | Graph operations |
| `/api/graphs/{id}/versions` | POST | Save new graph version |
| `/api/graphs/external-workflows` | POST | Create/update workflows from external systems with idempotency |
| `/api/runs` | POST | Start graph execution |
| `/api/runs/{id}` | GET | Get run status |
| `/api/runs/{id}/events` | GET | Stream run events |
| `/api/approvals` | GET, POST | Human gate approvals |
| `/api/auth/login` | POST | JWT authentication |

External workflow import example (QA-friendly, repeatable):

```bash
curl -X POST "http://localhost:8000/api/graphs/external-workflows" \
  -H "Authorization: Bearer <ACCESS_TOKEN>" \
  -H "Content-Type: application/json" \
  -H "Idempotency-Key: qa-workflow-001:v3" \
  -d '{
    "name": "QA Lead Capture",
    "description": "Imported from QA seed script",
    "external_source": "qa",
    "external_ref": "qa-workflow-001",
    "graph_json": {
      "nodes": [
        {"id": "prompt1", "type": "prompt", "name": "Prompt", "config": {}},
        {"id": "output1", "type": "output", "name": "Done", "config": {}}
      ],
      "edges": [
        {"id": "e1", "from": "START", "to": "prompt1"},
        {"id": "e2", "from": "prompt1", "to": "output1"}
      ]
    }
  }'
```

- `external_ref`: stable key from your external system. Reusing it updates the same graph.
- `Idempotency-Key` (or body `idempotency_key`): safely retries without duplicate versions.

Full API documentation available at `http://localhost:8000/api/docs/` when running.

## Contracts and Ops

- Graph JSON contract: [`SPECS.md`](SPECS.md)
- Run/event contract: [`docs/architecture/run-event-contract.md`](docs/architecture/run-event-contract.md)
- Marketplace/runtime contract: [`docs/architecture/marketplace-runtime-contract.md`](docs/architecture/marketplace-runtime-contract.md)
- Engine runtime delivery ops: [`docs/ops/engine-marketplace-runtime.md`](docs/ops/engine-marketplace-runtime.md)
- P0 beta scope and operator notes: [`docs/ops/p0-beta-launch-notes.md`](docs/ops/p0-beta-launch-notes.md)
- P0 QA and proof commands: [`docs/ops/p0-qa-checklist.md`](docs/ops/p0-qa-checklist.md)

## Environment Variables

| Variable | Default | Description |
|----------|---------|-------------|
| `DEBUG` | `False` | Django debug mode |
| `SECRET_KEY` | — | Django secret key |
| `DB_HOST` | `localhost` | PostgreSQL host |
| `DB_PORT` | `5433` | PostgreSQL port |
| `DB_NAME` | `forgegraph` | Database name |
| `DB_USER` | `postgres` | Database user |
| `DB_PASSWORD` | — | Database password |
| `REDIS_HOST` | `localhost` | Redis host |
| `REDIS_PORT` | `6379` | Redis port |
| `ENGINE_HOST` | `localhost` | gRPC engine host |
| `ENGINE_PORT` | `50051` | gRPC engine port |
| `FORGEGRAPH_RUNTIME_MODE` | `cloud` | Engine runtime mode: `cloud` or `self_hosted` |
| `CONTROL_PLANE_URL` | — | Backend base URL for tenant runtime manifest delivery |
| `ENGINE_CALLBACK_SECRET` | — | Shared secret for engine event callbacks and manifest fetch signatures |
| `MARKETPLACE_MANIFEST_REFRESH_SECONDS` | `0` | Polling interval for tenant runtime manifest refresh (`0` = startup-only) |
| `TOOL_MANIFEST_DIR` | — | Engine path to JSON tool manifests (for `tool` nodes like Gmail/Calendar/Tasks) |
| `ENCRYPTION_KEY` | — | Fernet key used to encrypt stored credentials/tokens |
| `GOOGLE_OAUTH_CLIENT_ID` | — | Service-level Google OAuth client id (shared Gmail/Calendar/Tasks/Drive) |
| `GOOGLE_OAUTH_CLIENT_SECRET` | — | Service-level Google OAuth client secret |
| `GOOGLE_OAUTH_REDIRECT_URI` | `http://localhost:3000/oauth/callback` | OAuth redirect URI for Google providers |

### OAuth Setup (Service-Level)

OAuth app credentials are configured once at service level via environment variables.  
Users only need to click **Connect account** on the Credentials page.

1. Set OAuth env vars in `.env` (see `.env.example`).
2. Restart backend: `docker compose up -d --force-recreate backend`.
3. In Google Cloud OAuth client, set redirect URI to `http://localhost:3000/oauth/callback`.
4. From ForgeGraph Credentials page, connect Gmail/Calendar/Tasks accounts as needed.

### Tool Manifests (Service-Level)

Tool nodes are resolved from engine manifest files (JSON).

1. Define tool manifests under `engine/tool-manifests/`.
2. Set `TOOL_MANIFEST_DIR` for engine (Docker compose uses `/app/tool-manifests`).
3. Restart engine: `docker compose up -d --build engine`.

Included by default:
- `gmail_reader`
- `google_calendar`
- `google_tasks`

## Contributing

1. Fork the repository
2. Create a feature branch (`git checkout -b feature/amazing-feature`)
3. Make your changes
4. Run tests (`./test-all.ps1`)
5. Commit your changes (`git commit -m 'Add amazing feature'`)
6. Push to the branch (`git push origin feature/amazing-feature`)
7. Open a Pull Request

### Code Style

- **Python**: Follow PEP 8, enforced by `ruff` and `mypy`
- **Go**: Follow standard Go conventions, use `go fmt`
- **TypeScript**: ESLint plus Prettier (`npm run lint`, `npm run format:check`)

### Clean Architecture

All components follow Clean Architecture with strict layer separation:
- **Domain** — Business entities and logic (no external dependencies)
- **Application** — Use cases orchestrating domain logic
- **Adapters** — External interfaces (API, repositories, UI)
- **Infrastructure** — Frameworks and external services

## License

This project is licensed under the MIT License - see the [LICENSE](LICENSE) file for details.
