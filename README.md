# ForgeGraph

ForgeGraph is an operating system for AI-native organizations.

It supervises a system of agents, tasks, decisions, memory, and cost over time. Workflow authoring still exists, but it is now a secondary workspace under `Workflows`, not the primary product surface.

## Product Direction

- Primary surface: organizational system state
- Secondary surface: workflow definitions and revisions
- Canonical runtime facts stay unchanged: `Run`, `NodeRun`, `RunEvent`, `ApprovalTask`, `MemoryObservation`, `LLMUsage`, `AuditLog`
- New OS read models layer on top: `AgentRegistryEntry`, `TaskRecord`, `DecisionRecord`, `CostLedgerEntry`, `CostAggregate`

## Architecture

- `frontend/`: Next.js operator console and workflow workspace
- `backend/`: Django control plane, APIs, projections, governance, marketplace, memory, accounting
- `engine/`: Go execution plane focused on runtime execution only

## Phase 1 in this repo

- New OS shell with `Overview`, `Agents`, `Tasks`, `Inbox`, `Memory`, `Accounting`, `Library`, `Workflows`, `Settings`
- Public terminology shift:
  - `Graph -> Workflow Definition`
  - `GraphVersion -> Workflow Revision`
  - `Run -> Execution`
  - `NodeRun -> Execution Step`
  - `ApprovalTask -> Decision`
- Alias APIs under `/api/workflows`, `/api/executions`, `/api/decisions`
- Projection-backed APIs under `/api/agents`, `/api/tasks`, `/api/accounting`, `/api/system-state`

## Docs

- Canonical runtime contract: [docs/architecture/runtime-invariants.md](docs/architecture/runtime-invariants.md)
- Product: [docs/product/vision.md](docs/product/vision.md)
- Mental model: [docs/product/mental-model.md](docs/product/mental-model.md)
- State ownership: [docs/architecture/state-ownership-contract.md](docs/architecture/state-ownership-contract.md)
- Backend map: [docs/backend/domain-map.md](docs/backend/domain-map.md)
- Frontend shell: [docs/frontend/app-shell.md](docs/frontend/app-shell.md)
- Migration: [docs/migration/ui-rollout.md](docs/migration/ui-rollout.md)

## Test Automation Notes

Generated tests should target the current OS surfaces first and treat legacy routes as compatibility coverage:

- Frontend primary routes: `/overview`, `/agents`, `/tasks`, `/inbox`, `/memory`, `/accounting`, `/library`, `/workflows`, `/settings`
- Frontend compatibility routes: `/graphs`, `/runs`, `/approvals`
- Backend current aliases: `/api/workflows`, `/api/executions`, `/api/decisions`, `/api/agents`, `/api/tasks`, `/api/accounting`, `/api/system-state`
- Backend compatibility routes: `/api/graphs`, `/api/runs`, `/api/approvals`

Runtime-sensitive coverage must preserve the control-plane contract from [docs/architecture/runtime-invariants.md](docs/architecture/runtime-invariants.md):

- The backend owns durable state, snapshots, resume state, and recovery decisions.
- The engine executes work but is not authoritative for durable runtime state.
- The frontend observes backend-owned state and issues user actions; it is not authoritative.

For deterministic browser coverage in local and hosted automation, seed the shared frontend fixture user before generating or running UI-heavy suites:

```bash
cd backend
uv run python manage.py seed_testsprite_frontend_fixture
```

That fixture prepares `test@example.com` with a default organization plus an editable prompt, a pending approval, a visible memory observation, and a visible credential so generated tests can cover real operator flows instead of empty states.

For backend API coverage, prefer these contracts:

- Auth flows under `/api/auth/*`
- Workflow metadata creation followed by workflow revision creation before execution start
- Execution lifecycle through `/api/executions/*` or `/api/runs/*`
- Signed engine callback delivery through `/api/runs/engine-events`

## Local CI Hook

Install the shared Git hook once per clone:

- macOS/Linux: `bash scripts/install-git-hooks.sh`
- PowerShell: `powershell -ExecutionPolicy Bypass -File scripts/install-git-hooks.ps1`

Run the same gate manually without pushing:

- macOS/Linux: `bash scripts/ci/run_required_checks.sh`
- PowerShell: `powershell -ExecutionPolicy Bypass -File scripts/run-required-checks.ps1`
- Shortcut from repo root on Windows: `.\checks.cmd` or `.\checks.ps1`

The PowerShell wrappers intentionally delegate to `scripts/ci/run_required_checks.sh`, so local Windows runs and GitHub Actions use the same repo-owned check scripts.

Run the fast selective gate locally:

- macOS/Linux: `bash scripts/ci/run_required_checks_fast.sh`
- PowerShell: `powershell -ExecutionPolicy Bypass -File scripts/run-required-checks-fast.ps1`
- Shortcut from repo root on Windows: `.\checks-fast.cmd` or `.\checks-fast.ps1`

PR CI uses the fast selective scripts. Pushes to `main` and nightly runs use the full authoritative gate.

The `pre-push` hook runs the same repo-owned check scripts used by GitHub Actions. Backend checks expect local Postgres and Redis to be reachable on the repo defaults from `docker-compose.yml`:

- Postgres: `localhost:5433`
- Redis: `localhost:6379`

Start them with `docker compose up -d postgres redis` before pushing.

`backend/pytest.ini` points pytest at `config.test_settings`, which loads the repo-owned `.env.test` overrides. With the local dependencies up, the authoritative backend full-suite command is:

- `cd backend && uv run pytest`

## Production Ops

- Release contract: `scripts/release/run_backend_migrate.sh` and `.github/workflows/release.yml`
- Native Postgres backup/restore: `scripts/ops/backup_postgres.sh` and `scripts/ops/restore_postgres.sh`
- Deploy env contract: `docs/ops/deploy-env-contract.md`
- Release/rollback runbooks: `docs/ops/release-runbook.md`, `docs/ops/rollback-runbook.md`
