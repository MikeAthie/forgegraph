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

- Product: [docs/product/vision.md](docs/product/vision.md)
- Mental model: [docs/product/mental-model.md](docs/product/mental-model.md)
- Backend map: [docs/backend/domain-map.md](docs/backend/domain-map.md)
- Frontend shell: [docs/frontend/app-shell.md](docs/frontend/app-shell.md)
- Migration: [docs/migration/ui-rollout.md](docs/migration/ui-rollout.md)
