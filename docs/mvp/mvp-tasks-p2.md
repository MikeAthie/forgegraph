# P2: Operational Readiness, Governance, and Memory Hardening

## Objective
Take the now-memory-native MVP and make it sustainable for real teams to operate, govern, and buy.

If P0 made ForgeGraph truthful and P1 made it memory-native, P2 makes curated memory governable, exportable, and supportable in production.

## What P2 Must Achieve
At the end of P2, ForgeGraph should be able to make the following promise:

"A team can adopt ForgeGraph with clear operational boundaries, governable curated memory, exportable usage data, and confidence in how memory and runtime behavior evolve over time."

## Assumptions
P2 assumes:
- P0 runtime and contract work is complete
- P1 curated memory domain, runtime integration, and Jackie-style workflow are complete or stable

## What Is Already Done
The repo already includes important foundations that P2 should package, not rebuild:
- audit log model and API surface
- tenant policies and retention policies
- LLM budgets, quotas, analytics endpoints
- organization and role models
- OIDC, SCIM, billing and subscription models
- memory analytics and GC foundations

P2 should improve coherence, governance, exportability, and operational clarity around those existing capabilities and the new curated memory surfaces.

## P2 Exit State
P2 is complete only when all of the following are true:
- [x] Usage, cost, and memory data are exportable and understandable for operators.
- [x] Governance and team controls are surfaced in a usable way.
- [x] Curated memory retention, supportability, and auditability are visible and measurable.
- [x] Admin workflows feel intentional instead of scattered.
- [x] The product is easier to justify to a paying team, not just a technical evaluator.

## Implementation Readiness
This file now records the shipped P2 scope and the docs that prove the final operator/admin story.

Use these docs as the execution entry point:
- `docs/mvp/forgegraph-mvp-implementation-plan.md`
- `docs/mvp/mvp-tasks-p2.md`
- `docs/architecture/curated-memory.md`
- `docs/mvp/p2-f01-implementation-tickets.md`
- `docs/mvp/p2-f02-implementation-tickets.md`
- `docs/mvp/p2-f03-implementation-tickets.md`
- `docs/mvp/p2-f04-implementation-tickets.md`

Implementation order for P2:
1. `P2-F01`
2. `P2-F02`
3. `P2-F03`
4. `P2-F04`

P2 started from these initial entry points:
- `P2-F01`: inventory current usage/export surfaces and add curated-memory-aware reporting/export requirements
- `P2-F02`: extend governance/admin IA so memory ownership, access, and auditability have a clear home
- `P2-F03`: surface curated-memory retention, redaction, and support exports before broader admin polish
- `P2-F04`: normalize product/admin terminology after memory governance surfaces settle

No extra roadmap decomposition should be required before opening the first P2 implementation PRs.

---

## P2-F01: Usage Reporting, Export, and Commercial Controls

### Feature Description
Turn the existing cost, budget, quota, and analytics foundations into buyer-grade reporting that also explains the operational cost and footprint of curated memory.

### Why This Is P2
- The backend already tracks usage, budgets, quotas, and analytics.
- P1 adds curated memory as a new product-level capability that teams will need to understand and justify.
- Teams need exportable data before they trust recurring usage-based systems with memory retention.

### User-Facing Outcome
- Admins can view, export, and explain runtime and memory usage.
- Budget and quota behavior is visible before it surprises users.
- Commercial controls feel deliberate and tied to actual product behavior.

### Non-Goals for P2
- full invoicing engine
- finance-grade revenue recognition
- per-seat billing redesign

### Detailed Tasks

#### F01-T01: Audit current reporting surfaces
- [x] Inventory current analytics, budget, quota, subscription, and memory-analytics endpoints.
- [x] Identify missing views, weak copy, and places where users cannot reconcile what the system is doing.
- [x] Consolidate overlapping usage language across runtime and memory features.

#### F01-T02: Add export workflows
- [x] Add or improve CSV/JSON exports for:
  - LLM usage
  - cost by provider/model
  - budget status
  - quota status
  - curated memory volume and indexing status
- [x] Add pagination and rate limits where needed.
- [x] Add date-range filtering and organization scoping.

#### F01-T03: Improve admin reporting UX
- [x] Add an admin-friendly usage summary view.
- [x] Make budget/quota state easy to interpret.
- [x] Add curated-memory reporting for:
  - observation counts
  - indexing backlog/failures
  - retention posture
  - search volume

#### F01-T04: Tie reporting to plan and entitlement behavior
- [x] Make subscription/plan entitlements visible in admin screens.
- [x] Show how entitlements relate to budget/quota behavior.
- [x] Ensure blocked runs explain whether the cause is:
  - budget
  - quota
  - plan entitlement
  - policy
  - memory configuration limits

### Success Criteria
- [x] Admins can export meaningful usage and memory data without querying the database directly.
- [x] Budget, quota, entitlement, and memory-related states are visible and distinguishable.
- [x] Over-limit or blocked states produce actionable messaging.

### Proof / Demo Feat
Show a tenant's runtime and curated-memory usage for a date range, export it, and explain a blocked or degraded run using only the product UI and exported data.

---

## P2-F02: Governance, Auditability, and Team Controls

### Feature Description
Turn the existing RBAC, audit, OIDC, SCIM, and org foundations into a clearer team-governance story that now includes curated memory ownership and visibility.

### Why This Is P2
- These primitives already exist in the repo.
- P1 adds a new memory object that teams will ask about immediately: who can see it, who can delete it, and how changes are audited.

### User-Facing Outcome
- Team admins understand who can do what with curated memory.
- Audit history is visible and useful.
- Identity and provisioning features have a clear place in the product.

### Non-Goals for P2
- enterprise policy engine
- custom role builder
- deep approval workflow governance

### Detailed Tasks

#### F02-T01: Clarify the admin model
- [x] Audit current admin pages and org settings flows.
- [x] Group admin capabilities into clear sections:
  - organization
  - identity
  - billing
  - audit
  - policies
  - memory
- [x] Reduce duplication and navigation ambiguity.

#### F02-T02: Improve audit log usability
- [x] Audit current audit events for curated-memory coverage gaps.
- [x] Add missing audit events for high-value memory actions if needed.
- [x] Improve audit log filtering by:
  - actor
  - action
  - resource
  - date range
- [x] Add human-readable event descriptions.

#### F02-T03: Harden team-role workflows
- [x] Review org membership and role flows.
- [x] Clarify who can:
  - view observations
  - delete observations
  - manage memory retention settings
  - export memory-related data
- [x] Add UI affordances that make role implications clear.

#### F02-T04: Clarify identity feature status
- [x] Review OIDC, SSO, and SCIM UX against actual backend capability.
- [x] Add docs or UI status indicators for:
  - configured
  - partially configured
  - unavailable
- [x] Ensure unsupported states are explained instead of silently failing.

### Success Criteria
- [x] Team admins can understand governance features and memory ownership from the product UI without reading backend code.
- [x] Audit history is searchable and useful for support/governance workflows.
- [x] Identity features clearly communicate configuration state and limits.

### Proof / Demo Feat
Inspect a curated-memory action trail, explain who had permission to perform it, and review identity configuration state from the admin UI alone.

---

## P2-F03: Operational Guardrails, Retention, and Supportability

### Feature Description
Package the existing policy and retention foundations into a visible operational control layer that now covers curated memory lifecycle, redaction, indexing, and support workflows.

### Why This Is P2
- Guardrails and retention models already exist in the repo.
- P1 adds a durable curated-memory layer that now needs explicit operator visibility.

### User-Facing Outcome
- Operators know what is blocked, why, and where to look next.
- Curated-memory retention behavior is understandable.
- Support teams have enough tooling to debug tenant issues safely.

### Non-Goals for P2
- enterprise SIEM integrations
- full compliance automation
- per-region data residency orchestration

### Detailed Tasks

#### F03-T01: Consolidate policy visibility
- [x] Audit how tenant policies are set, surfaced, and enforced.
- [x] Add admin-facing summaries for:
  - egress policy
  - model/provider allowlists
  - runtime mode restrictions
  - curated-memory feature flags and limits
- [x] Make policy-denied states visible outside raw run errors.

#### F03-T02: Improve retention UX and operator clarity
- [x] Review retention settings and current UI.
- [x] Explain data lifecycle in the admin surface for:
  - runs
  - logs
  - audit logs
  - usage data
  - curated memory observations
  - vector-indexed memory chunks
- [x] Add safer copy around deletion/retention implications.

#### F03-T03: Supportability features
- [x] Add or improve support-safe exports for:
  - run traces
  - policy denial summaries
  - package/runtime state
  - curated-memory observation state
  - indexing failures and backlog state
- [x] Ensure exports and support surfaces respect redaction and tenant boundaries.
- [x] Add internal troubleshooting notes or docs for memory-related failure classes.

#### F03-T04: Operational documentation
- [x] Update ops docs with:
  - Cloud vs self-host differences
  - curated-memory behavior and limits
  - runtime package restrictions
  - data retention expectations
  - incident triage starting points
- [x] Link product admin screens to the relevant docs where helpful.

### Success Criteria
- [x] Operators can understand active guardrails and curated-memory retention behavior without reading models or migrations.
- [x] Policy denials, indexing failures, and retention behavior are visible and supportable.
- [x] Support-facing exports and docs reduce ad hoc debugging.

### Proof / Demo Feat
Take a degraded memory-backed run, identify the governing policy or indexing issue, inspect retention expectations, and export support-safe trace data for diagnosis without database access.

---

## P2-F04: Team-Ready Admin Experience

### Feature Description
Bring the scattered admin and operational surfaces together into a more coherent team-facing product experience, including curated memory as a first-class admin concern.

### Why This Is P2
- The repo has substantial admin capability already.
- P1 increases surface area further with memory browser and governance needs.
- The value is diluted unless the admin story feels intentional.

### User-Facing Outcome
- Admins can find what they need quickly.
- Core operational, memory, governance, and commercial settings feel like one product area.
- The system appears mature enough for team environments.

### Non-Goals for P2
- full design-system rewrite
- net-new enterprise feature explosion

### Detailed Tasks

#### F04-T01: Audit admin IA and page consistency
- [x] Review all admin pages for:
  - naming consistency
  - information hierarchy
  - navigation gaps
  - contradictory terminology
- [x] Define a cleaner admin information architecture that includes memory surfaces explicitly.

#### F04-T02: Normalize admin language
- [x] Standardize product language across:
  - organization
  - tenant
  - policy
  - plan
  - budget
  - quota
  - package
  - memory
  - observation
  - session
- [x] Remove internal-only phrasing from user-visible admin surfaces.

#### F04-T03: Improve page-level affordances
- [x] Add empty states where needed.
- [x] Add health/status chips where useful.
- [x] Add contextual help text for risky or advanced controls.
- [x] Make unsupported states explicit instead of ambiguous.

### Success Criteria
- [x] Admin users can navigate governance, billing, identity, policy, and memory areas without confusion.
- [x] The admin surface feels intentionally designed rather than accumulated.
- [x] Terminology is consistent across pages and docs.

### Proof / Demo Feat
Walk through billing, policy, identity, audit, and memory admin areas in one pass without needing to explain contradictory terms or hidden assumptions.

---

## Cross-Cutting P2 Tasks

### P2-X01: Commercial and Ops Review
- [x] Review P2 features with both product and engineering stakeholders.
- [x] Confirm that buyer-facing claims about memory, governance, and operations match real behavior.

### P2-X02: Documentation Sync
- [x] Ensure admin/product docs reflect the final state of P2 features.
- [x] Remove outdated implementation-plan statements that conflict with shipped behavior.

### P2-X03: Support Readiness
- [x] Produce a short internal support guide for:
  - blocked runs
  - over-limit states
  - policy denials
  - package/runtime issues
  - identity configuration issues
  - curated-memory indexing and retrieval issues

---

## Suggested Build Order

### Week 1
- F01-T01 to F01-T03
- F02-T01 to F02-T02
- F03-T01

### Week 2
- F01-T04
- F02-T03 to F02-T04
- F03-T02 to F03-T03
- F04-T01

### Week 3
- F04-T02 to F04-T03
- P2-X01 to P2-X03
- final doc and admin UX polish

## Final Definition of Done
- [x] P2-F01 complete
- [x] P2-F02 complete
- [x] P2-F03 complete
- [x] P2-F04 complete
- [x] Operators can explain runtime and curated-memory behavior from the UI and docs, not just from code
- [x] Paying teams have a clearer reason to trust adoption, administration, and memory governance workflows
