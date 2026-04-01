# P2-F01 Implementation Tickets

## Goal
Convert `P2-F01` into reviewable implementation slices with explicit file targets, acceptance criteria, tests, and PR boundaries.

`P2-F01` is the reporting and commercial-controls epic:
- runtime and memory usage must be understandable to operators
- export workflows must exist for both LLM and curated-memory activity
- budget, quota, and entitlement states must be distinguishable
- commercial and operational limits must be explainable from the product UI

## Status
`P2-F01` is complete as of March 13, 2026.

PR-1 is complete as of March 13, 2026:
- reporting/export inventory captured in `docs/mvp/p2-f01-reporting-audit.md`
- vocabulary and next-slice gaps documented before API/UI changes

PR-2 is complete as of March 13, 2026:
- LLM export workflows cover usage, costs, budget, and quota datasets
- memory analytics export covers curated-memory observation and indexing health
- export flows now use explicit `export_format` semantics to avoid DRF content-negotiation collisions
- memory analytics gained date-range filtering and staff-only tenant scoping consistent with the reporting contract

PR-3 is complete as of March 13, 2026:
- analytics pages expose buyer-readable usage summaries instead of raw payload-only views
- memory reporting now includes observation counts, indexing backlog, retention posture, and search/retrieval volume
- export actions are visible directly from the product UI

PR-4 is complete as of March 13, 2026:
- billing now explains plan entitlements versus tenant quota versus budget
- blocked run responses include structured cause metadata for budget, quota, and plan-entitlement cases
- run detail surfaces policy-denied and degraded-memory diagnostics for operators

## Dependency
`P1` should be complete or stable first.

This ticket set assumes:
- curated memory observations, indexing, and run read models already exist
- LLM usage, budget, quota, and plan-entitlement enforcement already exist
- frontend analytics and billing pages are already in production shape for MVP use

## Current Repo Reality
The current codebase already has:
- backend LLM analytics endpoints for usage, costs, budget, quota, and usage export
- backend memory analytics endpoints for usage, costs, and performance
- billing plans and subscription APIs
- frontend analytics pages for LLM and memory
- frontend billing UI with visible plan entitlements
- blocked-run enforcement for budget, quota, and plan entitlements in run-start paths

The current gap is specific:
- reporting is split across analytics, billing, and run errors instead of one operator flow
- memory analytics are not yet curated-memory-native enough for observation/index health questions
- export coverage is uneven across LLM, budget, quota, and curated-memory datasets
- admins cannot easily reconcile "plan", "budget", "quota", and "memory limit" as separate concepts
- blocked or degraded states are enforced, but not yet explained cleanly in the reporting/admin UX

## Ticketing Strategy
The safest split is:
1. reporting inventory and contract cleanup
2. export and backend reporting expansion
3. admin-facing usage and memory reporting UI
4. blocked-state and entitlement explainability
5. proof and QA coverage

This keeps backend/reporting contracts stable before polishing the commercial/admin UX.

---

## PR-1: Reporting Inventory and Curated-Memory-Aware Contract Pass

### Objective
Audit the current reporting surfaces and lock the product/reporting contract before adding more endpoints and UI.

### Scope
- reporting inventory
- terminology cleanup decisions
- P2-F01 implementation notes
- no major runtime behavior changes yet

### Expected Files

#### Planning / docs files
- `docs/mvp/mvp-tasks-p2.md`
- `docs/mvp/p2-f01-implementation-tickets.md`
- `docs/mvp/p2-f01-reporting-audit.md`
- `docs/architecture/curated-memory.md`

#### Optional docs if the team wants a short operator glossary
- `docs/ops/*`

### Acceptance Criteria
- [x] Existing usage, budget, quota, entitlement, billing, and memory-analytics surfaces are inventoried.
- [x] The product vocabulary is clarified for:
  - usage
  - cost
  - budget
  - quota
  - entitlement
  - memory volume
  - indexing health
- [x] The backend/export contract for the next PRs is defined without reopening P1 memory decisions.

### Tests
- doc-only PR; no new code tests required

### PR Boundary Notes
- Do not add a large analytics UI rewrite here.
- This PR exists to avoid reporting drift and duplicate export invention later.

---

## PR-2: Export Workflows for LLM, Budget, Quota, and Curated Memory

### Objective
Fill the backend export and reporting gaps so operators can extract meaningful usage and memory data without querying the database directly.

### Scope
- export endpoints
- pagination and date-range consistency
- organization/tenant scoping rules
- curated-memory-aware reporting payloads

### Expected Files

#### Backend files
- `backend/adapters/api/analytics/urls.py`
- `backend/adapters/api/analytics/llm_analytics.py`
- `backend/adapters/api/analytics/memory_analytics.py`
- `backend/adapters/api/memory/usage_views.py`
- `backend/adapters/api/health/memory_health.py`
- `backend/tests/integration/adapters/test_llm_analytics_api.py`
- `backend/tests/integration/adapters/test_memory_analytics_api.py`

#### Optional files depending on final export shape
- `backend/adapters/api/billing/views.py`
- `backend/adapters/api/runs/views.py`

### Acceptance Criteria
- [x] Export workflows exist or are improved for:
  - LLM usage
  - cost by provider/model
  - budget status
  - quota status
  - curated memory observation volume
  - observation indexing backlog/failure state
- [x] Date-range filtering, pagination, and tenant/organization scoping behave consistently.
- [x] Export responses respect role requirements and tenant boundaries.
- [x] Curated-memory reporting surfaces include observation-aware metrics instead of only legacy tier summaries where practical.

### Tests
- integration tests for export format, pagination, and permission enforcement
- integration tests for date-range validation and tenant scoping
- regression tests for existing LLM export behavior

### PR Boundary Notes
- Keep the frontend reporting UI out of this PR.
- Prefer additive endpoints or additive fields over breaking payload changes.

---

## PR-3: Unified Admin Reporting UX

### Objective
Create an admin-friendly reporting surface that ties together usage, cost, memory footprint, and operational state.

### Scope
- frontend reporting pages
- shared admin/reporting cards and summaries
- export entry points
- budget/quota interpretation helpers

### Expected Files

#### Frontend files
- `frontend/pages/analytics/llm.tsx`
- `frontend/pages/analytics/memory.tsx`
- `frontend/pages/admin/billing.tsx`
- `frontend/lib/api.ts`
- `frontend/components/admin/*`
- `frontend/__tests__/unit/pages/*.test.tsx`

#### Optional files depending on IA decisions
- `frontend/components/DashboardLayout.tsx`
- `frontend/components/Header.tsx`

### Acceptance Criteria
- [x] Admins have a clear usage summary view that ties runtime and memory reporting together.
- [x] Budget and quota state are easy to interpret without reading raw API payloads.
- [x] Memory reporting exposes:
  - observation counts
  - indexing failures/backlog
  - retention posture summary
  - search or retrieval volume where available
- [x] Export actions are visible from the product UI instead of being hidden backend-only capabilities.

### Tests
- frontend unit tests for loading, empty, error, and export affordances
- backend integration tests only if payload shaping changes

### PR Boundary Notes
- Keep blocked-run messaging and entitlement diagnostics out of this PR if possible.
- Focus on operator readability, not design-system churn.

---

## PR-4: Entitlement, Budget, Quota, and Blocked-State Explainability

### Objective
Make the product explain why a run was blocked or degraded, and show how plans and entitlements relate to actual system behavior.

### Scope
- run error/read-model shaping
- billing/admin copy
- entitlement visibility
- operator guidance for blocked states

### Expected Files

#### Backend files
- `backend/adapters/api/runs/views.py`
- `backend/adapters/api/runs/serializers.py`
- `backend/tests/integration/adapters/test_run_api.py`
- `backend/tests/integration/adapters/test_billing_entitlements.py`

#### Frontend files
- `frontend/pages/admin/billing.tsx`
- `frontend/pages/runs/[runId].tsx`
- `frontend/lib/api.ts`
- `frontend/lib/error-messages.ts`
- `frontend/__tests__/unit/pages/runs.test.tsx`

### Acceptance Criteria
- [x] Blocked or degraded states explain whether the cause is:
  - budget
  - quota
  - plan entitlement
  - policy
  - memory configuration or indexing limits
- [x] Plan entitlements are visible in admin screens in a way operators can relate to usage/billing behavior.
- [x] Run-facing and admin-facing messaging use stable terminology across these limit types.
- [x] Existing enforcement behavior remains intact.

### Tests
- integration tests for blocked-run messaging and cause distinctions
- frontend tests for user-visible state rendering
- regression tests for existing budget/quota enforcement

### PR Boundary Notes
- Do not redesign all run-detail UX here.
- This PR should improve explanation, not expand enforcement scope.

---

## PR-5: Reporting Proof and Export QA

### Objective
Prove that P2-F01 meets the buyer/operator bar through exports, reporting UI, and blocked-state explainability.

### Scope
- integration coverage
- browser-level reporting proof where useful
- docs/status updates

### Expected Files

#### Tests
- `backend/tests/integration/adapters/test_llm_analytics_api.py`
- `backend/tests/integration/adapters/test_memory_analytics_api.py`
- `frontend/__tests__/unit/pages/*.test.tsx`
- `frontend/__tests__/e2e/*.spec.ts`

#### Docs
- `docs/mvp/mvp-tasks-p2.md`
- `docs/mvp/p2-f01-implementation-tickets.md`

### Acceptance Criteria
- [x] A tenant's runtime and curated-memory usage can be viewed and exported for a date range.
- [x] An operator can explain a blocked or degraded run from product UI plus exported data.
- [x] Known reporting limitations are documented explicitly.
- [x] `P2-F02` can start without reopening reporting contract decisions.

### Tests
- backend integration tests for report/export paths
- frontend tests for the reporting journey
- focused browser proof if export/download UX becomes user-critical

### PR Boundary Notes
- Keep the proof deterministic and tenant-scoped.
- Do not broaden this into general finance or invoicing work.

### Status
`PR-5` is complete. Reporting exports, memory-aware analytics, blocked/degraded run explainability, and the supporting docs/tests now give P2 a stable commercial/operator reporting baseline.

---

## Recommended Merge Order
1. PR-1
2. PR-2
3. PR-3
4. PR-4
5. PR-5

## Final Ticket-Level Definition of Done
- [x] Meaningful usage and curated-memory data are exportable without direct database access
- [x] Budget, quota, entitlement, and memory-related states are visible and distinguishable
- [x] Operators can explain blocked or degraded states from the product UI
- [x] Reporting and export terminology is stable enough for the rest of P2 to build on
