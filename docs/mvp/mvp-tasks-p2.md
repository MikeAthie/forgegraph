# P2: Operational Readiness, Team Controls, and Commercial Hardening

## Objective
Take the now-coherent MVP and make it sustainable for real teams to operate, govern, and buy.

If P0 makes ForgeGraph truthful and P1 makes it usable, P2 makes it survivable in production and easier to sell to teams.

## What P2 Must Achieve
At the end of P2, ForgeGraph should be able to make the following promise:

"A team can adopt ForgeGraph with usable controls, clear operational boundaries, exportable usage data, and confidence in how the product behaves over time."

## Assumptions
P2 assumes:
- P0 runtime and contract work is complete
- P1 packaging and debugger work is complete or stable

## What Is Already Done
The repo already includes important foundations that P2 should package, not rebuild:
- audit log model and API surface
- tenant policies and retention policies
- LLM budgets, quotas, analytics endpoints
- organization and role models
- OIDC, SCIM, billing and subscription models

P2 should improve coherence, UX, reporting, and operational quality around those existing capabilities.

## P2 Exit State
P2 is complete only when all of the following are true:
- [ ] Usage and cost data are exportable and understandable for operators.
- [ ] Governance and team controls are surfaced in a usable way.
- [ ] Operational guardrails are visible, documented, and measurable.
- [ ] Admin workflows feel intentional instead of scattered.
- [ ] The product is easier to justify to a paying team, not just a technical evaluator.

## Implementation Readiness
This file is ready to drive implementation once P0 and the core P1 user journeys are stable.

Use these docs as the execution entry point:
- `docs/mvp/forgegraph-mvp-implementation-plan.md`
- `docs/mvp/mvp-tasks-p2.md`

Implementation order for P2:
1. `P2-F01`
2. `P2-F02`
3. `P2-F03`
4. `P2-F04`

Start work immediately with these first PRs:
- `P2-F01`: inventory current reporting/export endpoints and ship the first admin-facing usage export flow
- `P2-F02`: reorganize governance/admin IA and improve audit-log usability before adding more controls
- `P2-F03`: surface active policy and retention state in admin views before adding more ops documentation
- `P2-F04`: normalize admin terminology and page affordances after the prior feature work settles

No extra roadmap decomposition should be required before opening the first P2 implementation PRs.

---

## P2-F01: Usage Reporting, Export, and Commercial Controls

### Feature Description
Turn the existing cost, budget, and quota foundations into buyer-grade reporting and commercial controls.

### Why This Is P2
- The backend already tracks usage, budgets, quotas, and subscriptions.
- The gap is packaging those capabilities into admin-friendly workflows and export paths.
- Teams need reporting and controls before they trust recurring usage-based systems.

### User-Facing Outcome
- Admins can view, export, and explain usage.
- Budget and quota behavior is visible before it surprises users.
- Commercial controls feel deliberate and tied to tenant behavior.

### Non-Goals for P2
- full invoicing engine
- finance-grade revenue recognition
- per-seat billing redesign

### Detailed Tasks

#### F01-T01: Audit current usage and budget surfaces
- [ ] Inventory existing analytics, budget, quota, and subscription endpoints.
- [ ] Identify missing views, weak copy, and places where users cannot reconcile what the system is doing.
- [ ] Consolidate overlapping budget/quota language.

#### F01-T02: Add export workflows
- [ ] Add or improve CSV/JSON exports for:
  - LLM usage
  - cost by provider/model
  - budget status
  - quota status
- [ ] Add pagination and rate limits where needed.
- [ ] Add date-range filtering and organization scoping.

#### F01-T03: Improve admin reporting UX
- [ ] Add an admin-friendly usage summary view.
- [ ] Make budget/quota state easy to interpret:
  - current usage
  - threshold
  - limit
  - projected risk
- [ ] Add clearer over-limit and warning copy.

#### F01-T04: Tie reporting to plan and entitlement behavior
- [ ] Make subscription/plan entitlements visible in admin screens.
- [ ] Show how entitlements relate to budget/quota behavior.
- [ ] Ensure blocked runs explain whether the cause is:
  - budget
  - quota
  - plan entitlement
  - policy

### Success Criteria
- [ ] Admins can export meaningful usage and cost data without querying the database directly.
- [ ] Budget, quota, and entitlement behavior are visible and distinguishable.
- [ ] Over-limit states produce actionable messaging.

### Proof / Demo Feat
Show a tenant’s usage for a date range, export it, then explain exactly why a blocked run was denied using only the product UI and exported data.

---

## P2-F02: Governance, Auditability, and Team Controls

### Feature Description
Turn the existing RBAC, audit, OIDC, SCIM, and org foundations into a clearer team-governance story.

### Why This Is P2
- These primitives already exist in the repo.
- The gap is that they still feel like scattered platform capabilities instead of a coherent team-operating model.
- Paying teams will ask about roles, audit history, identity, and admin boundaries early.

### User-Facing Outcome
- Team admins understand who can do what.
- Audit history is visible and useful.
- Identity and provisioning features have a clear place in the product.

### Non-Goals for P2
- enterprise policy engine
- custom role builder
- deep approval workflow governance

### Detailed Tasks

#### F02-T01: Clarify the admin model
- [ ] Audit current admin pages and org settings flows.
- [ ] Group admin capabilities into clear sections:
  - organization
  - identity
  - billing
  - audit
  - policies
- [ ] Reduce duplication and navigation ambiguity.

#### F02-T02: Improve audit log usability
- [ ] Audit current audit log events for coverage gaps.
- [ ] Add missing audit events for high-value actions if needed.
- [ ] Improve audit log filtering by:
  - actor
  - action
  - resource
  - date range
- [ ] Add human-readable event descriptions.

#### F02-T03: Harden team-role workflows
- [ ] Review org membership and role flows.
- [ ] Add UI affordances to clarify role implications.
- [ ] Add admin-visible warnings for sensitive actions performed by lower-privilege roles if relevant.

#### F02-T04: Clarify identity feature status
- [ ] Review OIDC, SSO, and SCIM UX against actual backend capability.
- [ ] Add docs or UI status indicators for:
  - configured
  - partially configured
  - unavailable
- [ ] Ensure unsupported states are explained instead of silently failing.

### Success Criteria
- [ ] Team admins can understand governance features from the product UI without reading backend code.
- [ ] Audit history is searchable and useful for support/governance workflows.
- [ ] Identity features clearly communicate configuration state and limits.

### Proof / Demo Feat
Invite a user, inspect role implications, review an audit trail for a sensitive action, and explain identity configuration state from the admin UI alone.

---

## P2-F03: Operational Guardrails, Retention, and Supportability

### Feature Description
Package the existing policy and retention foundations into a visible operational control layer that supports cloud operations and support workflows.

### Why This Is P2
- Guardrails and retention models already exist in the repo.
- What is still missing is a strong operator story: visibility, supportability, and clear outcomes when controls trigger.

### User-Facing Outcome
- Operators know what is blocked, why, and where to look next.
- Retention behavior is understandable.
- Support teams have enough tooling to debug tenant issues safely.

### Non-Goals for P2
- enterprise SIEM integrations
- full compliance automation
- per-region data residency orchestration

### Detailed Tasks

#### F03-T01: Consolidate policy visibility
- [ ] Audit how tenant policies are set, surfaced, and enforced.
- [ ] Add admin-facing summaries for:
  - egress policy
  - model/provider allowlists
  - runtime mode restrictions
- [ ] Make policy-denied states visible outside raw run errors.

#### F03-T02: Improve retention UX and operator clarity
- [ ] Review retention settings and current UI.
- [ ] Explain data lifecycle in the admin surface:
  - runs
  - logs
  - audit logs
  - usage data
- [ ] Add safer copy around deletion/retention implications.

#### F03-T03: Supportability features
- [ ] Add or improve support-safe exports for:
  - run traces
  - policy denial summaries
  - package/runtime state
- [ ] Ensure exports and support surfaces respect redaction and tenant boundaries.
- [ ] Add internal troubleshooting notes or docs for common failure classes.

#### F03-T04: Operational documentation
- [ ] Update ops docs with:
  - Cloud vs self-host differences
  - runtime package restrictions
  - data retention expectations
  - incident triage starting points
- [ ] Link product admin screens to the relevant docs where helpful.

### Success Criteria
- [ ] Operators can understand active guardrails and retention behavior without reading models or migrations.
- [ ] Policy denials and retention behavior are visible and supportable.
- [ ] Support-facing exports and docs reduce ad hoc debugging.

### Proof / Demo Feat
Take a blocked run, identify the governing policy, inspect retention expectations, and export support-safe trace data for diagnosis without database access.

---

## P2-F04: Team-Ready Admin Experience

### Feature Description
Bring the scattered admin and operational surfaces together into a more coherent team-facing product experience.

### Why This Is P2
- The repo has a surprising amount of admin capability already.
- The value is diluted because the experience still feels incremental and feature-by-feature rather than system-level.

### User-Facing Outcome
- Admins can find what they need quickly.
- Core operational and commercial settings feel like one product area.
- The system appears mature enough for a team environment.

### Non-Goals for P2
- full design-system rewrite
- net-new enterprise feature explosion

### Detailed Tasks

#### F04-T01: Audit admin IA and page consistency
- [ ] Review all admin pages for:
  - naming consistency
  - information hierarchy
  - navigation gaps
  - contradictory terminology
- [ ] Define a cleaner admin information architecture.

#### F04-T02: Normalize admin language
- [ ] Standardize product language across:
  - organization
  - tenant
  - policy
  - plan
  - budget
  - quota
  - package
- [ ] Remove internal-only phrasing from user-visible admin surfaces.

#### F04-T03: Improve page-level affordances
- [ ] Add empty states where needed.
- [ ] Add health/status chips where useful.
- [ ] Add contextual help text for risky or advanced controls.
- [ ] Make unsupported states explicit instead of ambiguous.

### Success Criteria
- [ ] Admin users can navigate governance, billing, identity, audit, and policy areas without confusion.
- [ ] The admin surface feels intentionally designed rather than accumulated.
- [ ] Terminology is consistent across pages and docs.

### Proof / Demo Feat
Walk through billing, policy, identity, and audit areas in one pass without needing to explain contradictory terms or hidden assumptions.

---

## Cross-Cutting P2 Tasks

### P2-X01: Commercial and Ops Review
- [ ] Review P2 features with both product and engineering stakeholders.
- [ ] Confirm that buyer-facing claims match real behavior.

### P2-X02: Documentation Sync
- [ ] Ensure admin/product docs reflect the final state of P2 features.
- [ ] Remove outdated implementation-plan statements that conflict with shipped behavior.

### P2-X03: Support Readiness
- [ ] Produce a short internal support guide for:
  - blocked runs
  - over-limit states
  - policy denials
  - package/runtime issues
  - identity configuration issues

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
- [ ] P2-F01 complete
- [ ] P2-F02 complete
- [ ] P2-F03 complete
- [ ] P2-F04 complete
- [ ] Operators can explain product behavior from the UI and docs, not just from code
- [ ] Paying teams have a clearer reason to trust adoption and administration workflows
