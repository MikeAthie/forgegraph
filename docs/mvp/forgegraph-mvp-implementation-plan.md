# ForgeGraph MVP Implementation Plan

## Executive Summary
This implementation plan aligns the MVP to the current repo reality after P0 and reorients post-P0 work around curated memory as the main product differentiator.

The plan is organized into three phases:
- `P0`: make the product truthful and safe
- `P1`: make the product memory-native
- `P2`: make the product governable, exportable, and team-ready

The target outcome is a narrow but credible product promise:

"ForgeGraph lets a team visually build, run, inspect, and safely operate agent workflows with curated memory, approved integrations, and clear execution contracts."

## Guiding Principles
- Reuse what the repo already has.
- Keep P0 closed; do not reopen solved truth/safety work casually.
- Treat curated memory as the first major product differentiator after P0.
- Prefer explicit, inspectable memory behavior over opaque implicit automation.
- Keep Cloud and self-host differences explicit.
- Prefer reviewable PR slices over large, cross-stack dumps.

## What Already Exists
The current repo already includes foundations that this plan treats as inputs, not greenfield scope:
- run history, node runs, replay, resume, and checkpointing
- `thread_id`, WS/SSE streaming, and run detail surfaces
- LLM usage models, budgets, quotas, and entitlement checks
- organization, RBAC, audit log, retention, and tenant policy models
- webhook-triggered runs and OAuth credential flows
- graph-level memory configuration and propagation
- Tier 1 buffer, Tier 2 store/session memory, and Tier 3 semantic retrieval foundations
- cycle support behind `metadata.allow_cycles`

## Phase Structure

### P0: Sellable MVP Remediation
P0 fixes the core product truth gaps.

P0 is complete when:
- a real `agent` node exists
- marketplace/runtime semantics are coherent
- Cloud mode blocks unsafe execution paths
- graph and event contracts are documented

Primary workstreams:
- `P0-F01`: Agent Node as a First-Class Runtime Primitive
- `P0-F02`: Marketplace Runtime Contract and Delivery
- `P0-F03`: Cloud-Safe Execution and Policy Enforcement
- `P0-F04`: Stable Graph and Event Contracts

Reference:
- `docs/mvp/mvp-tasks-p0.md`

### P1: Curated Memory as the Product Differentiator
P1 turns ForgeGraph from a safe workflow runtime into a memory-native agent product.

P1 is complete when:
- ForgeGraph has a first-class curated memory domain centered on observations
- workflows and agents can explicitly save and retrieve curated memory
- memory is visible in product UI and debugger surfaces
- one Jackie-style workflow proves save -> later retrieval -> memory-backed response end to end

Primary workstreams:
- `P1-F01`: Curated Memory Domain and Contracts
- `P1-F02`: Curated Memory Runtime Integration
- `P1-F03`: Memory Browser, Jackie Journey, and UX Packaging

Reference:
- `docs/mvp/mvp-tasks-p1.md`
- `docs/architecture/curated-memory.md`
- `docs/mvp/p1-f01-implementation-tickets.md`
- `docs/mvp/p1-f02-implementation-tickets.md`
- `docs/mvp/p1-f03-implementation-tickets.md`

### P2: Operational Readiness, Governance, and Memory Hardening
P2 turns the memory-native MVP into something a real team can govern and operate over time.

P2 is complete when:
- runtime and memory usage are admin-friendly and exportable
- governance and team controls are coherent
- curated-memory retention and supportability are visible
- admin workflows feel intentionally designed

Primary workstreams:
- `P2-F01`: Usage Reporting, Export, and Commercial Controls
- `P2-F02`: Governance, Auditability, and Team Controls
- `P2-F03`: Operational Guardrails, Retention, and Supportability
- `P2-F04`: Team-Ready Admin Experience

Reference:
- `docs/mvp/mvp-tasks-p2.md`

## Locked Product Decisions
These decisions should be treated as fixed for the MVP unless there is a deliberate roadmap change:
- curated memory is implemented as a native ForgeGraph subdomain
- MVP exposure is internal only: REST + gRPC + graph nodes + product UI
- no public MCP surface in MVP
- memory capture is explicit first; no passive run-derived capture in MVP
- retrieval defaults to hybrid FTS + vector
- primary scope is graph/run/session, with tenant isolation underneath
- vector indexing must be asynchronous and non-blocking on the critical run path

## Recommended Delivery Order

### Track 1: P0
1. `P0-F01` Agent runtime primitive
2. `P0-F02` Marketplace runtime contract
3. `P0-F03` Cloud-safe execution policy
4. `P0-F04` Specs and contracts

### Track 2: P1
1. `P1-F01` Curated memory domain and contracts
2. `P1-F02` Curated memory runtime integration
3. `P1-F03` Memory Browser and Jackie-style UX packaging

### Track 3: P2
1. `P2-F01` Usage and memory-aware reporting
2. `P2-F02` Governance and auditability
3. `P2-F03` Guardrails, retention, and supportability
4. `P2-F04` Team-ready admin experience

## Sequencing Assumptions
- P0 should remain closed while P1 is planned and executed.
- P1 should stay tightly focused on explicit curated memory and one supported Jackie-style workflow.
- P2 should package governance, exportability, and operational support around the memory-native MVP rather than inventing broad new enterprise scope.

## Cross-Phase Constraints
- No phase should re-implement already shipped foundations unless a clear regression or architectural blocker is proven.
- Cloud and self-hosted behavior must remain explicitly documented where they diverge.
- Any feature that changes runtime truth or memory behavior must land with updated docs and tests.
- Existing KV/session/vector memory paths must keep working while curated memory is added.

## Review and PR Strategy
- Start each major workstream with a contract or architecture doc if the implementation spans backend, engine, and frontend.
- Keep PRs sliceable by concern:
  - schema/contract
  - backend model/API
  - gRPC contract
  - engine/runtime
  - frontend authoring/browser UX
  - debugger/trace UX
- Avoid phase-wide mega-PRs.

## Immediate Next Steps
1. Start `P1-F01` from `docs/mvp/p1-f01-implementation-tickets.md`.
2. Continue into `P1-F02` and `P1-F03` using the new ticket docs instead of inventing PR boundaries during implementation.
3. Define the Jackie-style memory-first workflow as the supported MVP proof for P1.

## Linked Planning Docs
- `docs/mvp/mvp-tasks-p0.md`
- `docs/mvp/mvp-tasks-p1.md`
- `docs/mvp/mvp-tasks-p2.md`
- `docs/architecture/curated-memory.md`
- `docs/mvp/mvp-remediation-tasks.md`
- `docs/mvp/p0-f01-implementation-tickets.md`
- `docs/mvp/p0-f02-implementation-tickets.md`
- `docs/mvp/p1-f01-implementation-tickets.md`
- `docs/mvp/p1-f02-implementation-tickets.md`
- `docs/mvp/p1-f03-implementation-tickets.md`
