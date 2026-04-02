# Backend Service

The backend is the ForgeGraph control plane.

## Responsibilities

- Authentication, tenancy, RBAC, governance, marketplace, analytics, memory APIs
- Canonical persistence for workflow definitions, executions, steps, approvals, memory, and usage
- Projection and summary layer for operator-facing system state

## Phase 1 Additions

- `AgentRegistryEntry`
- `TaskRecord`
- `DecisionRecord`
- `CostLedgerEntry`
- `CostAggregate`

## API Surfaces

- Legacy: `/api/graphs`, `/api/runs`, `/api/approvals`
- Current aliases: `/api/workflows`, `/api/executions`, `/api/decisions`
- New OS views: `/api/agents`, `/api/tasks`, `/api/accounting`, `/api/system-state`

## Rule

Do not move organization-state logic into the engine. Keep runtime execution and operator read models separated.
