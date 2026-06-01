# Task Lifecycle, Routing, And Projection Model

Runtime precedence: [runtime-invariants.md](runtime-invariants.md) is canonical.

## Status

Accepted for pre-beta hardening.

## Decision

ForgeGraph has three task-related records with different ownership:

- `TaskLifecycleRecord` is the canonical logical task lifecycle state.
- `TaskRoutingRecord` is the durable handoff, ownership, SLA, department
  routing, and board/card record.
- `TaskRecord` is an operational read model tied to execution and agent context.

Do not add a fourth central task/card model unless one of these responsibilities
cannot be expressed without breaking the ownership contract.

## Approval And Decision Rule

`ApprovalTask` opens a human or policy gate. `DecisionRecord` closes and audits
the decision. They must not compete as current decision state.

## Consequences

- Lifecycle transitions must update `TaskLifecycleRecord` through backend-owned
  services and idempotency keys.
- Department queues, SLA, assignment, and Kanban-like cards belong in
  `TaskRoutingRecord`.
- Execution-facing summaries may project into `TaskRecord`, but projections are
  not authoritative lifecycle state.
- Tests should fail if a serializer or view presents `TaskRecord` or
  `TaskRoutingRecord` as the canonical lifecycle owner.
