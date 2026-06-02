# ForgeGraph

ForgeGraph is an AI Company Operating System.

It lets a user create a company, equip it with departments, skills, tools, policies, and operating-model packs, then launch and supervise real work through operations, approvals, deliverables, and backend-owned evidence.

The product is company-first. Advanced workflow and graph editing still exists, but it is an expert surface under the company operating model, not the primary mental model.

## Runtime Contract

`docs/architecture/runtime-invariants.md` is the canonical runtime contract. If any other document or implementation note conflicts with it, the invariant file wins.

Non-negotiable rules:

- The backend control plane is the only durable source of truth.
- The engine executes work and may hold ephemeral state, but it does not own durable runtime state.
- Events, Redis, Kafka, WebSockets, and client state are transport or observability layers, not authoritative state.
- Snapshots, liveness, recovery, approval handoff, and durable resume state are backend-owned.

## Product Model

ForgeGraph presents a business operating system:

- `Organization`: account, tenant, and permission boundary.
- `Company`: durable business entity the user creates and operates.
- `Department`: functional part of a company responsible for a class of work.
- `Operation`: live or historical unit of company work.
- `Task`: concrete unit of work inside an operation.
- `Approval`: human decision that can pause and unblock work.
- `Deliverable`: result the user can read, approve, use, or act on.
- `Advanced operating model`: expert surface for direct structure editing.

Primary product routes are `/companies`, `/companies/[companyId]`, `/runs`, and `/approvals`. Compatibility and expert routes remain for graph/workflow editing, execution inspection, admin, analytics, and testing.

## Architecture

```text
Browser / operator UI
        |
        | REST + WebSocket
        v
Backend control plane ---------------> PostgreSQL + pgvector
        |                                   Redis
        | gRPC dispatch                     optional Kafka transport
        v
Go execution engine
```

The backend validates commands, persists authoritative state, dispatches execution contracts, ingests signed engine callbacks, materializes projections, and notifies the UI. The engine runs workflow revisions and emits execution results back to backend-owned APIs.

## Repository Map

| Path | Purpose |
| --- | --- |
| `backend/` | Django control plane, REST APIs, projections, governance, memory, accounting, marketplace, migrations, and backend tests. |
| `engine/` | Go gRPC execution plane for running workflow revisions from backend-issued contracts. |
| `frontend/` | Next.js operator console, company workspace, advanced operating-model UI, and Playwright/Jest tests. |
| `operating_model_packs/` | Pack-owned operating-model configuration, including Digital Marketing Pro / Atlas. |
| `docs/architecture/` | Runtime, ownership, event, projection, and control-plane contracts. |
| `docs/product/` | Product ontology, company workspace model, navigation, and UX vocabulary. |
| `docs/ops/` | Release, rollback, reliability, observability, capacity, and incident runbooks. |
| `scripts/` | CI, runtime guardrails, ops utilities, release scripts, and validation helpers. |
| `tools/` | Load generation and supporting developer tooling. |

## Stack

- Backend: Python 3.12+, Django 6, Django REST Framework, Channels, PostgreSQL, pgvector, Redis, optional Kafka.
- Engine: Go 1.25, gRPC, Prometheus metrics, OpenTelemetry.
- Frontend: Next.js 15, React 19, TypeScript, Tailwind, Radix UI, Jest, Playwright.
- Local orchestration: Docker Compose.

## Quick Start

Prerequisites:

- Docker Desktop or Docker Engine with Compose.
- Node.js 20+ for frontend development.
- Python 3.12+ and `uv` for backend development.
- Go 1.25+ for engine development.

Create local environment values, then start the stack:

```powershell
Copy-Item .env.example .env
docker compose up --build -d
docker compose exec backend python manage.py migrate
```

Useful endpoints:

- Frontend: `http://localhost:3000`
- Backend API: `http://localhost:8000`
- Engine gRPC: `localhost:50051`
- Engine metrics: `http://localhost:9090/metrics`

The Docker frontend is built into an image. Rebuild it after frontend source changes:

```powershell
docker compose build frontend
docker compose up -d frontend
```

## Local Development

Backend:

```powershell
cd backend
uv sync
uv run python manage.py migrate
uv run python manage.py runserver 0.0.0.0:8000
uv run pytest
uv run ruff check .
```

Engine:

```powershell
cd engine
go test ./...
go build -o engine .
```

Frontend:

```powershell
cd frontend
npm ci
npm run dev
npm test
npm run test:e2e
npm run terminology:check
```

Repo-level checks:

```powershell
.\checks-fast.ps1
.\checks.ps1
```

On macOS/Linux or Git Bash, the `./dev` helper wraps the common Docker Compose commands:

```bash
./dev up
./dev migrate
./dev logs
./dev down
```

## Atlas / Operating-Model Pack Acceptance

Atlas lives as pack configuration and generic whiteboard/orchestration behavior, not as a vertical backend route family.

Primary live acceptance command:

```powershell
cd frontend
npm run test:e2e:atlas:docker:local-llm
```

That command expects the Docker stack and a local OpenAI-compatible LLM endpoint as configured by the repo scripts. The acceptance target must stay on generic `/api/whiteboards/*` and pack-owned configuration, with no `/api/atlas/*` or marketing-specific durable core model ownership.

## Documentation Index

Start here when changing product, runtime, or release behavior:

- Runtime invariants: [docs/architecture/runtime-invariants.md](docs/architecture/runtime-invariants.md)
- Product definition: [docs/product/forgegraph-product-definition.md](docs/product/forgegraph-product-definition.md)
- Canonical terminology: [docs/product/canonical-ontology.md](docs/product/canonical-ontology.md)
- Company workspace model: [docs/product/company-workspace-model.md](docs/product/company-workspace-model.md)
- Control plane vs execution plane: [docs/architecture/control-plane-vs-execution-plane.md](docs/architecture/control-plane-vs-execution-plane.md)
- Backend domain map: [docs/backend/domain-map.md](docs/backend/domain-map.md)
- Frontend page hierarchy: [docs/frontend/page-hierarchy.md](docs/frontend/page-hierarchy.md)
- Contributing guide: [docs/contributing.md](docs/contributing.md)
- Release runbook: [docs/ops/release-runbook.md](docs/ops/release-runbook.md)
- Rollback runbook: [docs/ops/rollback-runbook.md](docs/ops/rollback-runbook.md)
- Deployment environment contract: [docs/ops/deploy-env-contract.md](docs/ops/deploy-env-contract.md)

## Security And Generated Artifacts

Do not commit `.env`, local database files, Playwright reports, generated TestSprite temp output, local logs, or provider credentials. Runtime credentials and connector secrets belong in environment-managed configuration, not in docs or fixtures.

If a generated artifact contains test credentials, API keys, tunnel URLs, provider keys, cookies, or bearer tokens, treat it as sensitive and rotate the credential after removal.

## License

See [LICENSE](LICENSE).
