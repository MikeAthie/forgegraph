# P2-F03 Implementation Tickets

## Goal
Convert `P2-F03` into reviewable implementation slices with explicit file targets, acceptance criteria, tests, and PR boundaries.

`P2-F03` is the operational guardrails and supportability epic:
- policies and retention must be visible to operators
- curated-memory lifecycle and indexing state must be supportable
- exports must be safe for support workflows
- operational docs must explain what the product and infrastructure are doing

## Status
`P2-F03` is complete as of March 13, 2026.

## Dependency
`P2-F01` and `P2-F02` should establish stable reporting and governance vocabulary first, but `P2-F03` can begin in parallel where it focuses on backend/admin visibility.

This ticket set assumes:
- tenant policy and retention models already exist
- memory health counters and GC/indexing signals already exist
- run detail and memory activity surfaces already exist from P1
- retention export endpoints already cover runs, logs, audit logs, and usage

## Current Repo Reality
The current codebase already has:
- tenant policy APIs
- tenant retention policy APIs plus cleanup and export flows
- run policy-denial detection and audit logging
- memory health counters for GC and observation indexing activity
- curated-memory browser and run memory activity surfaces

The current gap is specific:
- policy visibility is mostly backend-only
- retention controls are not yet a product-level operator flow
- support-safe exports are fragmented across different endpoints
- memory indexing backlog and failure state exist in health counters, not in an operator-facing support workflow
- docs do not yet package cloud/self-host and memory-governance operations into one supportable story

## Ticketing Strategy
The safest split is:
1. policy visibility and denied-state summaries
2. retention and lifecycle UX
3. support-safe exports and troubleshooting surfaces
4. operational documentation and product-doc links
5. proof and support-readiness validation

This keeps backend/operator contracts stable before the final admin experience polish in `P2-F04`.

---

## PR-1: Policy Visibility and Guardrail Summaries

### Objective
Expose tenant policy and guardrail state in an operator-friendly way rather than leaving it buried in APIs and run failures.

### Scope
- policy summary API shaping
- operator-facing policy page or panel
- denied-state summaries outside raw run payloads

### Expected Files

#### Backend files
- `backend/adapters/api/policies/views.py`
- `backend/adapters/api/runs/views.py`
- `backend/tests/integration/adapters/test_run_api.py`

#### Frontend files
- `frontend/pages/admin/*`
- `frontend/lib/api.ts`
- `frontend/__tests__/unit/pages/*.test.tsx`

### Acceptance Criteria
- [x] Admin-facing summaries exist for:
  - egress policy
  - provider/model allowlists
  - runtime mode restrictions
  - curated-memory feature flags or limits where applicable
- [x] Policy-denied states are visible outside raw run errors.
- [x] Policy summaries reflect actual backend enforcement behavior.

### Tests
- integration tests for policy summaries and denied-state shaping
- frontend tests for policy UI rendering and empty states

### PR Boundary Notes
- Keep retention and support exports out of this PR.
- Favor summary/read-model work over adding a deep policy engine.

### Status
`PR-1` is complete. The policy API now exposes operator-facing summaries, run diagnostics already surface policy-denied behavior, and the admin operations page packages those guardrails in a readable control surface.

---

## PR-2: Retention and Data-Lifecycle UX

### Objective
Turn the current retention primitives into a clear operator experience that explains what data exists, how long it stays, and what deletion implies.

### Scope
- retention settings UI
- lifecycle summaries
- safer deletion/retention copy
- curated-memory-aware retention messaging

### Expected Files

#### Backend files
- `backend/adapters/api/retention/views.py`
- `backend/adapters/api/retention/serializers.py`
- `backend/tests/integration/adapters/test_retention_api.py`

#### Frontend files
- `frontend/pages/admin/*`
- `frontend/lib/api.ts`
- `frontend/__tests__/unit/pages/*.test.tsx`

### Acceptance Criteria
- [x] The admin surface explains lifecycle expectations for:
  - runs
  - logs
  - audit logs
  - usage data
  - curated memory observations
  - vector-indexed memory chunks
- [x] Retention settings are understandable from the UI without reading models or migrations.
- [x] Copy makes destructive implications explicit before cleanup or deletion actions.
- [x] Retention exports and previews remain tenant-safe.

### Tests
- integration tests for retention settings, previews, and exports
- frontend tests for lifecycle summaries and dangerous-action copy

### PR Boundary Notes
- Do not turn this into a full compliance workflow.
- Keep the focus on operator clarity and supportability.

### Status
`PR-2` is complete. The admin operations page explains lifecycle expectations across runs, logs, audit logs, usage, observations, and indexed chunks, and it exposes a dry-run cleanup preview instead of risky blind deletion.

---

## PR-3: Support-Safe Exports and Memory Troubleshooting Surfaces

### Objective
Package the existing traces, memory state, and indexing signals into support-safe diagnostic flows.

### Scope
- support export endpoints or wrappers
- memory observation/index-state exports
- indexing backlog/failure summaries
- redaction-safe diagnostic payloads

### Expected Files

#### Backend files
- `backend/adapters/api/runs/views.py`
- `backend/adapters/api/memory/observation_views.py`
- `backend/adapters/api/health/memory_health.py`
- `backend/adapters/api/retention/views.py`
- `backend/tests/integration/adapters/test_run_api.py`
- `backend/tests/integration/adapters/test_memory_observation_api.py`
- `backend/tests/integration/adapters/test_metrics_api.py`

#### Frontend files
- `frontend/pages/runs/[runId].tsx`
- `frontend/pages/admin/*`
- `frontend/lib/api.ts`
- `frontend/__tests__/unit/pages/*.test.tsx`

### Acceptance Criteria
- [x] Support-safe exports exist or are improved for:
  - run traces
  - policy-denial summaries
  - package/runtime state
  - curated-memory observation state
  - indexing failures/backlog state
- [x] Exports respect redaction and tenant boundaries.
- [x] Operators can identify degraded memory-backed runs without direct database access.
- [x] Memory support surfaces use observation-aware terminology from P1 and P2-F01.

### Tests
- integration tests for export permissions, redaction, and payload shape
- frontend tests for support-state rendering and export affordances

### PR Boundary Notes
- Avoid dumping raw internal diagnostics without shaping them for safe support use.
- Do not add SIEM or enterprise integrations here.

### Status
`PR-3` is complete. The admin operations page now exposes support-safe exports for runs, node runs, audit logs, usage, memory usage, and memory reporting, and it packages health plus indexing backlog signals into the same support workflow.

---

## PR-4: Operational Documentation and Product Linking

### Objective
Package the operational story in docs and connect relevant product admin surfaces to that documentation.

### Scope
- operator docs
- cloud vs self-host notes
- memory and retention guidance
- links from product surfaces to relevant docs

### Expected Files

#### Docs
- `docs/ops/*`
- `docs/mvp/mvp-tasks-p2.md`
- `docs/architecture/curated-memory.md`

#### Optional frontend files if contextual help lands here
- `frontend/pages/admin/*`
- `frontend/components/*`

### Acceptance Criteria
- [x] Ops docs cover:
  - cloud vs self-host differences
  - curated-memory behavior and limits
  - package/runtime restrictions
  - data retention expectations
  - incident-triage starting points
- [x] Product admin screens link to the relevant docs where that reduces support confusion.
- [x] Docs reflect actual shipped product behavior rather than roadmap intent.

### Tests
- doc-only PR unless help-link UI changes land
- frontend tests only if doc links or contextual help are added

### PR Boundary Notes
- Keep the docs concrete and support-oriented.
- This PR should document the operational reality, not invent new operational scope.

### Status
`PR-4` is complete. The repo now includes a focused P2 operator guide plus walkthrough/QA notes in `docs/ops`, and the product surfaces link to the in-app operator help page that mirrors those docs.

---

## PR-5: Supportability Proof and Readiness Checklist

### Objective
Prove that operators can diagnose degraded memory-backed runs and understand retention/guardrail behavior from the product and docs.

### Scope
- proof path
- support-readiness checklist
- final P2-F03 consistency pass

### Expected Files

#### Docs
- `docs/mvp/mvp-tasks-p2.md`
- `docs/mvp/p2-f03-implementation-tickets.md`
- `docs/ops/*`

#### Tests
- `backend/tests/integration/adapters/test_run_api.py`
- `backend/tests/integration/adapters/test_metrics_api.py`
- `frontend/__tests__/e2e/*.spec.ts`

### Acceptance Criteria
- [x] An operator can take a degraded memory-backed run and identify the governing policy or indexing issue.
- [x] The operator can inspect retention expectations without database access.
- [x] Support-safe trace/export data is available for diagnosis.
- [x] `P2-F04` can polish the admin product without reopening supportability fundamentals.

### Tests
- focused integration or browser proof for policy, retention, and memory-diagnostics flows
- docs consistency check in PR review

### PR Boundary Notes
- Keep the proof deterministic and support-centric.
- Do not expand this into a broad observability platform effort.

### Status
`PR-5` is complete. The operator walkthrough now spans run diagnostics, admin guardrails, retention preview, health/indexing state, and support-safe exports without requiring database access.

---

## Recommended Merge Order
1. PR-1
2. PR-2
3. PR-3
4. PR-4
5. PR-5

## Final Ticket-Level Definition of Done
- [x] Operators can understand active guardrails and memory retention behavior from UI and docs
- [x] Policy denials, indexing failures, and retention behavior are visible and supportable
- [x] Support-safe exports reduce ad hoc debugging
- [x] P2 has a credible supportability story for curated memory
