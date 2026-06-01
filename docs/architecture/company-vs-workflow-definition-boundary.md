# Company Vs Workflow Definition Boundary

Runtime precedence: [runtime-invariants.md](runtime-invariants.md) is canonical.

## Status

Accepted for pre-beta hardening.

## Decision

ForgeGraph has one backend-owned durable control plane. `Company` and
`Workflow Definition` are separate domain concepts even though the current
database storage still uses `Graph` for both in several places.

- Company-like scope is the organization/company/client data boundary.
- Workflow Definition is executable workflow design metadata.
- Workflow Revision is the immutable executable revision, currently `GraphVersion`.
- Run/execution is backend-owned runtime state derived from a workflow revision.

No first hardening PR should perform a database-wide rename. Code at API,
serializer, documentation, and service boundaries must use transitional aliases
that state which concept is meant.

## Current Transitional Map

| Domain concept | Current storage | Rule |
| --- | --- | --- |
| Company-like scope | `Graph` | Treat as client/business isolation boundary. |
| Workflow definition | `Graph` | Treat as executable design identity only at workflow APIs. |
| Workflow revision | `GraphVersion` | Owns `graph_json`, checksum, and version number. |
| Run/execution | `Run`, `NodeRun`, runtime records | Backend-owned durable execution state. |
| Service engagement | `ServiceEngagement` | Company-scoped service lifecycle. |
| Workboard | `WorkWhiteboard` | Company-scoped project/work board. |
| Task lifecycle | `TaskLifecycleRecord` | Canonical logical task state. |
| Routing handoff | `TaskRoutingRecord` | Durable department handoff/work card. |
| Task projection | `TaskRecord` | Operational read model tied to execution/agent context. |

## Consequences

- `Graph` may remain as storage temporarily, but public APIs must expose
  transitional aliases such as `company_scope_id` and
  `workflow_definition_id` where ambiguity would otherwise leak.
- Deleting a `Graph` row is safe only when it is still a pure
  workflow-definition row. If company-scoped related resources exist, deletion
  must fail closed.
- Permission checks must never infer company authorization from workflow
  identity alone; company access helpers remain the access boundary until a
  true Company model exists.

## Migration Path

1. Add aliases and documentation without schema changes.
2. Split workflow-facing DTO names from company-facing DTO names.
3. Add negative tests for wrong organization, wrong company, and ambiguous
   workflow/company identity.
4. Only after API semantics are stable, consider a real database rename or a
   dedicated Company table.
