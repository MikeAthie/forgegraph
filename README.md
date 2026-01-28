# ForgeGraph

A visual workflow graph execution platform for building, testing, and running AI-powered automation pipelines.

![Python](https://img.shields.io/badge/Python-3.12+-blue?logo=python&logoColor=white)
![Go](https://img.shields.io/badge/Go-1.22-00ADD8?logo=go&logoColor=white)
![Next.js](https://img.shields.io/badge/Next.js-14-black?logo=next.js&logoColor=white)
![TypeScript](https://img.shields.io/badge/TypeScript-5.0-3178C6?logo=typescript&logoColor=white)
![License](https://img.shields.io/badge/License-MIT-green)

## Features

- **Visual Graph Editor** — Drag-and-drop interface for building workflow graphs with real-time validation
- **Multiple Node Types** — Prompt, Tool, Transform, Branch, Merge, Output, Memory, and Subgraph nodes
- **Human-in-the-Loop** — Approval gates that pause execution for human review
- **Version Control** — Graph versioning with SHA256 checksums for reproducibility
- **Real-time Monitoring** — WebSocket-powered run status updates and event streaming
- **Checkpoints & Caching** — Resume failed runs and cache node outputs for efficiency
- **JSON Schema Validation** — Validate node inputs and outputs against schemas

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
| Engine | Go 1.22, gRPC | High-performance graph execution |
| Database | PostgreSQL 16 | Persistent storage |
| Cache | Redis 7 | Caching and message broker |

## Getting Started

### Prerequisites

- Docker & Docker Compose
- Node.js 20+ (for frontend development)
- Python 3.12+ (for backend development)
- Go 1.22+ (for engine development)

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
| `/api/runs` | POST | Start graph execution |
| `/api/runs/{id}` | GET | Get run status |
| `/api/runs/{id}/events` | GET | Stream run events |
| `/api/approvals` | GET, POST | Human gate approvals |
| `/api/auth/login` | POST | JWT authentication |

Full API documentation available at `http://localhost:8000/api/docs/` when running.

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
- **TypeScript**: ESLint configuration in `frontend/.eslintrc.json`

### Clean Architecture

All components follow Clean Architecture with strict layer separation:
- **Domain** — Business entities and logic (no external dependencies)
- **Application** — Use cases orchestrating domain logic
- **Adapters** — External interfaces (API, repositories, UI)
- **Infrastructure** — Frameworks and external services

## License

This project is licensed under the MIT License - see the [LICENSE](LICENSE) file for details.
