# ForgeGraph Specs

This file is a short repo-root orientation document. Product terminology is canonical in [docs/product/canonical-ontology.md](docs/product/canonical-ontology.md). Runtime ownership is canonical in [docs/architecture/runtime-invariants.md](docs/architecture/runtime-invariants.md).

## Public Product Vocabulary

- Company: durable business entity the user creates and operates.
- Department: functional part of a company responsible for a category of work.
- Operation: live or historical unit of company work.
- Task: concrete unit of work inside an operation.
- Approval: human decision that can pause and unblock work.
- Deliverable: user-visible result produced by an operation.
- Advanced operating model: expert surface for direct structural editing.

## Internal Compatibility Vocabulary

These implementation terms still exist in storage, APIs, engine contracts, logs, and advanced tooling:

- `Graph`
- `GraphVersion`
- `Run`
- `NodeRun`
- `RunEvent`
- `ApprovalTask`
- `MemoryObservation`
- `LLMUsage`
- `AuditLog`

Primary user-facing surfaces should translate those terms through the frontend domain layer.

## Runtime Source Of Truth

The backend owns durable state for companies, operations, tasks, approvals, deliverables, memory, cost, snapshots, liveness, and recovery.

The engine executes backend-issued work and reports results. Events, Redis, Kafka, WebSockets, and client state are not authoritative.

## Route Guidance

- Primary product routes: `/companies`, `/companies/[companyId]`, `/runs`, `/runs/[runId]`, `/approvals`.
- Advanced/internal routes: `/workflows`, `/graphs`, admin and analytics surfaces.
- Compatibility aliases may remain, but new product work should not make builder-first routes the primary experience.
