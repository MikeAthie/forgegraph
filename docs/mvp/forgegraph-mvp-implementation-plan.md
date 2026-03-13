# ForgeGraph MVP Implementation Plan

## Executive Summary
This implementation plan aligns the MVP to the current repo reality instead of re-planning features that already exist.

The plan is organized into three phases:
- `P0`: make the product truthful and safe
- `P1`: make the product understandable and adoptable
- `P2`: make the product team-ready and commercially defensible

The target outcome is a narrow but credible product promise:

"ForgeGraph lets a team visually build, run, inspect, and safely operate agent workflows with approved integrations and clear execution contracts."

## Guiding Principles
- Reuse what the repo already has.
- Narrow the MVP instead of expanding surface area.
- Fix end-to-end truth gaps before adding more polish.
- Treat Cloud safety and product honesty as first-order requirements.
- Prefer reviewable PR slices over large, cross-stack dumps.

## What Already Exists
The current repo already includes foundations that this plan treats as inputs, not greenfield scope:
- run history, node runs, replay, resume, and checkpointing
- `thread_id`, WS/SSE streaming, and run detail surfaces
- LLM usage models, budgets, quotas, and entitlement checks
- organization, RBAC, audit log, retention, and tenant policy models
- webhook-triggered runs and OAuth credential flows
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

### P1: Product Fit, Debugging, and Official Integrations
P1 narrows the product into a small set of supported journeys and improves run understanding.

P1 is complete when:
- the MVP has 1-2 opinionated journeys
- first value is fast and guided
- the debugger explains agent and workflow behavior clearly
- verified integrations are trustworthy and test-backed

Primary workstreams:
- `P1-F01`: Product Packaging and Onboarding Flow
- `P1-F02`: Debugger and Run Understanding UX
- `P1-F03`: Official Integration Package Hardening

Reference:
- `docs/mvp/mvp-tasks-p1.md`

### P2: Operational Readiness, Team Controls, and Commercial Hardening
P2 turns the MVP into something easier for a real team to adopt and govern.

P2 is complete when:
- usage and cost reporting are admin-friendly
- governance and team controls are coherent
- policy and retention behavior are visible and supportable
- admin workflows feel intentionally designed

Primary workstreams:
- `P2-F01`: Usage Reporting, Export, and Commercial Controls
- `P2-F02`: Governance, Auditability, and Team Controls
- `P2-F03`: Operational Guardrails, Retention, and Supportability
- `P2-F04`: Team-Ready Admin Experience

Reference:
- `docs/mvp/mvp-tasks-p2.md`

## Recommended Delivery Order

### Track 1: P0
1. `P0-F01` Agent runtime primitive
2. `P0-F02` Marketplace runtime contract
3. `P0-F03` Cloud-safe execution policy
4. `P0-F04` Specs and contracts

### Track 2: P1
1. `P1-F01` Product packaging and onboarding
2. `P1-F02` Debugger UX
3. `P1-F03` Verified integration hardening

### Track 3: P2
1. `P2-F01` Usage and commercial reporting
2. `P2-F02` Governance and auditability
3. `P2-F03` Guardrails and supportability
4. `P2-F04` Team-ready admin experience

## Sequencing Assumptions
- P0 should be delivered before broadening the product story.
- P1 should be kept narrow and tied to the supported MVP journeys.
- P2 should package existing controls before inventing new enterprise scope.

## Cross-Phase Constraints
- No phase should re-implement already shipped foundations unless a clear regression or architectural blocker is proven.
- Cloud and self-hosted behavior must remain explicitly documented where they diverge.
- Any feature that changes runtime truth must land with updated docs and tests.

## Review and PR Strategy
- Start each major workstream with a contract or architecture doc if the implementation span crosses backend, engine, and frontend.
- Keep PRs sliceable by concern:
  - schema/contract
  - engine/runtime
  - backend API/state mapping
  - frontend authoring
  - frontend debugger/UX
- Avoid phase-wide mega-PRs.

## Immediate Next Steps
1. Complete `P0-F01` ticketing and PR slicing.
2. Complete `P0-F02` ticketing and review the package-class decision before implementing runtime delivery.
3. Land the missing graph and event contracts before later phases drift.

## Linked Planning Docs
- `docs/mvp/mvp-tasks-p0.md`
- `docs/mvp/mvp-tasks-p1.md`
- `docs/mvp/mvp-tasks-p2.md`
- `docs/mvp/mvp-remediation-tasks.md`
- `docs/mvp/p0-f01-implementation-tickets.md`
- `docs/mvp/p0-f02-implementation-tickets.md`
