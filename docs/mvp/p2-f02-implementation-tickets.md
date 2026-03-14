# P2-F02 Implementation Tickets

## Goal
Convert `P2-F02` into reviewable implementation slices with explicit file targets, acceptance criteria, tests, and PR boundaries.

`P2-F02` is the governance and team-controls epic:
- admins must understand how curated memory is governed
- audit history must become useful for memory-aware support and governance flows
- organization, identity, and audit controls must have a clear home
- role implications must be visible instead of implied by backend code

## Status
`P2-F02` is complete as of March 13, 2026.

## Dependency
`P2-F01` does not need to be fully complete first, but the reporting vocabulary from `P2-F01` should be stable enough to avoid term drift.

This ticket set assumes:
- org and role models exist
- audit logging exists
- SSO/OIDC and SCIM foundations exist
- curated memory observations and deletion workflows already exist

## Current Repo Reality
The current codebase already has:
- organization and membership APIs plus an organization admin page
- audit log API and a basic audit-log UI
- SSO and SCIM APIs plus a combined admin page
- role-aware admin checks across billing, retention, and organization flows
- curated-memory create/update/delete behavior with audit-ready backend primitives

The current gap is specific:
- governance surfaces are spread across unrelated pages
- audit-log UX is functional but still raw and support-oriented rather than operator-friendly
- curated-memory ownership and action coverage are not yet made explicit in the product story
- role implications for viewing, deleting, exporting, or retaining memory are not surfaced clearly
- identity configuration state is present, but the UI does not clearly distinguish configured, partial, and unavailable states

## Ticketing Strategy
The safest split is:
1. admin IA and governance inventory
2. audit-log usability and curated-memory event coverage
3. role and memory-ownership clarity
4. identity-state clarity and admin grouping
5. proof and documentation

This keeps governance semantics stable before broader admin polish in `P2-F04`.

---

## PR-1: Governance Inventory and Admin IA Baseline

### Objective
Audit the current admin model and define where organization, identity, billing, audit, policies, and memory governance should live.

### Scope
- admin IA review
- governance grouping decisions
- navigation and terminology notes
- no major backend changes yet

### Expected Files

#### Planning / docs files
- `docs/mvp/mvp-tasks-p2.md`
- `docs/mvp/p2-f02-implementation-tickets.md`
- `docs/mvp/p2-f02-governance-audit.md`

#### Optional frontend shell files if lightweight nav cleanup lands here
- `frontend/components/DashboardLayout.tsx`
- `frontend/components/Header.tsx`
- `frontend/pages/admin/index.tsx`

### Acceptance Criteria
- [x] Current admin pages and settings flows are audited.
- [x] Admin capabilities are grouped into clear sections:
  - organization
  - identity
  - billing
  - audit
  - policies
  - memory
- [x] The governance IA for follow-up PRs is defined without reworking the whole product shell yet.

### Tests
- doc-only or light-nav PR; frontend tests only if nav changes land

### PR Boundary Notes
- Do not attempt full admin polish here.
- This PR should prevent F02 and F04 from inventing competing navigation structures.

### Status
`PR-1` is complete. The governance audit doc defines the section model, and `/admin` is now the lightweight hub for the current admin surfaces.

---

## PR-2: Audit Log Usability and Curated-Memory Coverage

### Objective
Make audit history searchable, readable, and useful for curated-memory support and governance workflows.

### Scope
- audit event inventory
- missing curated-memory audit events if needed
- audit filtering improvements
- human-readable audit descriptions

### Expected Files

#### Backend files
- `backend/application/services/audit_log.py`
- `backend/adapters/api/audit_logs/views.py`
- `backend/adapters/api/audit_logs/serializers.py`
- `backend/tests/integration/adapters/test_audit_logs_api.py`

#### Frontend files
- `frontend/pages/admin/audit-logs.tsx`
- `frontend/lib/api.ts`
- `frontend/__tests__/unit/pages/*.test.tsx`

### Acceptance Criteria
- [x] Audit coverage for high-value curated-memory actions is reviewed and filled if necessary.
- [x] Audit log filtering supports:
  - actor
  - action
  - resource
  - date range
- [x] Audit entries use human-readable descriptions instead of requiring raw metadata inspection first.
- [x] Existing audit-log pagination and tenant boundaries remain intact.

### Tests
- integration tests for audit filtering and visibility
- regression tests for existing audit-log access rules
- frontend tests for filter state and event rendering

### PR Boundary Notes
- Keep org-role and identity-state work out of this PR where possible.
- Favor additive event fields over changing existing audit semantics unnecessarily.

### Status
`PR-2` is complete. Curated-memory create/update/delete actions are now audited, the audit API returns human-readable descriptions, and the admin audit page exposes actor/resource/date-range filtering without changing tenant boundaries.

---

## PR-3: Team Roles and Memory Ownership Clarity

### Objective
Make it obvious who can view observations, delete them, manage retention, and export memory-related data.

### Scope
- role implication copy and affordances
- memory-governance summaries
- admin role visibility
- permission-denied UX

### Expected Files

#### Backend files
- `backend/adapters/api/organizations/views.py`
- `backend/adapters/api/memory/observation_views.py`
- `backend/adapters/api/retention/views.py`
- `backend/tests/integration/adapters/test_memory_observation_api.py`
- `backend/tests/integration/adapters/test_organizations_api.py`

#### Frontend files
- `frontend/pages/admin/organization.tsx`
- `frontend/pages/memory.tsx`
- `frontend/lib/api.ts`
- `frontend/__tests__/unit/pages/*.test.tsx`

### Acceptance Criteria
- [x] Admin users can tell who can:
  - view observations
  - delete observations
  - manage memory retention settings
  - export memory-related data
- [x] UI affordances make role implications clear before a user hits a permission error.
- [x] Memory-governance messaging reflects actual backend permission checks.
- [x] Cross-tenant and low-role restrictions remain intact.

### Tests
- integration tests for role-sensitive memory/admin actions
- frontend tests for role-dependent affordances and messaging

### PR Boundary Notes
- Do not build a custom role system here.
- This PR should clarify the existing model, not reopen RBAC scope.

### Status
`PR-3` is complete. The organization contract now exposes a memory-governance capability map, the organization page renders the role matrix explicitly, and the memory browser explains the current role’s practical limits before users run into retention or export restrictions.

---

## PR-4: Identity Status and Provisioning Clarity

### Objective
Make identity features explain their actual configuration state and limits instead of behaving like an opaque admin page.

### Scope
- OIDC/SSO status
- SCIM token and provisioning status
- configured/partial/unavailable state handling
- admin IA alignment with governance sections

### Expected Files

#### Backend files
- `backend/adapters/api/scim/views.py`
- `backend/application/services/oidc.py`
- `backend/application/services/scim.py`
- `backend/tests/integration/adapters/test_scim_api.py`

#### Frontend files
- `frontend/pages/admin/sso.tsx`
- `frontend/lib/api.ts`
- `frontend/__tests__/unit/pages/*.test.tsx`

### Acceptance Criteria
- [x] Identity features clearly indicate whether they are:
  - configured
  - partially configured
  - unavailable
- [x] Unsupported or incomplete states are explained instead of silently failing.
- [x] Identity UI copy matches the actual backend/provider capability.
- [x] Governance/admin grouping remains coherent with the rest of F02.

### Tests
- integration tests for SCIM/OIDC status payloads if they change
- frontend tests for state rendering and failure messaging

### PR Boundary Notes
- Do not broaden provider support or add a new identity platform here.
- Keep this focused on clarity and truthful status communication.

### Status
`PR-4` is complete. The backend now returns explicit identity readiness states for SSO and SCIM, and the admin identity page renders those states inside the same governance shell instead of behaving like a raw configuration screen.

---

## PR-5: Governance Proof and Documentation

### Objective
Prove the governance story end to end from product UI and docs.

### Scope
- browser or integration proof
- doc updates
- final F02 consistency pass

### Expected Files

#### Docs
- `docs/mvp/mvp-tasks-p2.md`
- `docs/mvp/p2-f02-implementation-tickets.md`
- `docs/ops/*`

#### Tests
- `backend/tests/integration/adapters/test_audit_logs_api.py`
- `backend/tests/integration/adapters/test_scim_api.py`
- `frontend/__tests__/e2e/*.spec.ts`

### Acceptance Criteria
- [x] An admin can inspect a curated-memory action trail from the product UI.
- [x] The product makes it clear who had permission to perform the action.
- [x] Identity configuration state can be reviewed without reading backend code.
- [x] `P2-F03` and `P2-F04` can build on one coherent governance IA.

### Tests
- focused browser proof or integration coverage for audit + identity admin flows
- docs consistency checks as part of PR review

### PR Boundary Notes
- Keep this proof narrow and deterministic.
- This PR should validate the governance story, not start a broader admin redesign.

### Status
`PR-5` is complete. The governance proof now lives in the admin hub, audit trail, organization role matrix, identity readiness states, and the P2 operator/help docs, so later admin polish no longer needs to reopen the governance foundation.

---

## Recommended Merge Order
1. PR-1
2. PR-2
3. PR-3
4. PR-4
5. PR-5

## Final Ticket-Level Definition of Done
- [x] Team admins can understand governance features and memory ownership from the product UI
- [x] Audit history is searchable and useful for memory-aware support workflows
- [x] Identity configuration state and limits are communicated clearly
- [x] `P2-F04` can polish the admin experience without inventing new governance structure
