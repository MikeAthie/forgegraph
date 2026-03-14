# P2-F04 Implementation Tickets

## Goal
Convert `P2-F04` into reviewable implementation slices with explicit file targets, acceptance criteria, tests, and PR boundaries.

`P2-F04` is the admin-experience coherence epic:
- governance, billing, identity, policy, and memory surfaces must feel like one product area
- terminology must be consistent
- page-level affordances must remove ambiguity for team admins
- the accumulated admin surface must look intentional enough for real-team adoption

## Status
`P2-F04` is complete as of March 13, 2026.

## Dependency
`P2-F01` through `P2-F03` should establish the reporting, governance, and operational contracts first.

This ticket set assumes:
- reporting/export surfaces are stable enough to link from admin UI
- governance IA decisions from `P2-F02` are settled
- policy, retention, and supportability surfaces from `P2-F03` exist or are stable

## Current Repo Reality
The current codebase already has:
- discrete admin pages for organization, billing, audit logs, marketplace, and SSO/SCIM
- analytics pages for LLM and memory
- product memory browser and run/debugger surfaces
- reusable layout and UI primitives

The current gap is specific:
- admin information architecture is fragmented between admin, analytics, and product pages
- terminology varies across pages and APIs
- empty states, status chips, and risky-control guidance are inconsistent
- unsupported or partially configured states are sometimes implicit
- curated memory is product-visible, but not yet fully integrated into the team-admin story

## Ticketing Strategy
The safest split is:
1. admin IA and shell normalization
2. terminology normalization
3. page-level affordances and state clarity
4. final integration polish across governance, billing, identity, policy, and memory
5. walkthrough proof and consistency QA

This keeps the final admin polish grounded in already-shipped product behavior.

---

## PR-1: Admin IA and Navigation Normalization

### Objective
Give the admin surface a coherent information architecture that explicitly includes memory, governance, and operational reporting.

### Scope
- admin navigation
- section grouping
- page discoverability
- shared admin shell patterns

### Expected Files

#### Frontend files
- `frontend/components/DashboardLayout.tsx`
- `frontend/components/Header.tsx`
- `frontend/pages/admin/*.tsx`
- `frontend/pages/analytics/*.tsx`
- `frontend/__tests__/unit/components/*.test.tsx`

#### Optional planning files
- `docs/mvp/mvp-tasks-p2.md`
- `docs/mvp/p2-f04-implementation-tickets.md`

### Acceptance Criteria
- [x] Admin users can find governance, billing, identity, audit, policy, and memory areas from one coherent navigation model.
- [x] Admin IA reflects the governance grouping established in `P2-F02`.
- [x] Memory and analytics surfaces have an intentional place in the admin/operator story.

### Tests
- frontend unit tests for nav, route visibility, and active-state behavior

### PR Boundary Notes
- Do not rewrite every page here.
- This PR should improve findability and structure first.

### Status
`PR-1` is complete. `/admin` is the governance hub, the policy/operations surface now has a dedicated admin route, and billing plus other governance pages share the same admin shell.

---

## PR-2: Terminology Normalization Across Admin and Docs

### Objective
Remove contradictory or internal-only terminology from the admin/operator experience.

### Scope
- page copy
- API label helpers
- glossary alignment across screens
- doc wording updates where needed

### Expected Files

#### Frontend files
- `frontend/pages/admin/*.tsx`
- `frontend/pages/analytics/*.tsx`
- `frontend/pages/memory.tsx`
- `frontend/lib/*`
- `frontend/__tests__/unit/pages/*.test.tsx`

#### Docs
- `docs/mvp/mvp-tasks-p2.md`
- `docs/ops/*`

### Acceptance Criteria
- [x] Product language is consistent across:
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
- [x] Internal implementation phrasing is removed from user-visible admin surfaces.
- [x] Admin docs use the same vocabulary as the product UI.

### Tests
- frontend tests only where label-dependent assertions exist
- doc review consistency in PR

### PR Boundary Notes
- Avoid copy churn without semantic payoff.
- Keep wording changes tied to actual operator understanding.

### Status
`PR-2` is complete. The shipped copy now uses one operator vocabulary across organization, identity, billing, policy, memory, and support docs instead of mixing implementation terms with product language.

---

## PR-3: Empty States, Status Chips, and Risky-Control Guidance

### Objective
Make the admin surface feel intentional by improving page-level affordances and clarifying unsupported or risky states.

### Scope
- empty states
- status chips
- contextual help
- unsupported-state messaging

### Expected Files

#### Frontend files
- `frontend/pages/admin/*.tsx`
- `frontend/pages/analytics/*.tsx`
- `frontend/pages/memory.tsx`
- `frontend/components/*`
- `frontend/__tests__/unit/pages/*.test.tsx`

### Acceptance Criteria
- [x] Empty states exist where the current UX is ambiguous.
- [x] Health/status chips are added where they improve operator understanding.
- [x] Risky or advanced controls include contextual help text.
- [x] Unsupported or partially configured states are explicit instead of ambiguous.

### Tests
- frontend unit tests for state rendering
- optional browser smoke tests if interactions become more conditional

### PR Boundary Notes
- Keep this focused on clarity, not visual overdesign.
- Do not add new backend concepts just to power badges.

### Status
`PR-3` is complete. Identity state, operator risk notices, retention preview language, and health/status badges now make the main admin states explicit instead of implicit.

---

## PR-4: Final Team-Admin Integration Pass

### Objective
Unify the reporting, governance, policy, retention, and memory surfaces into one mature team-facing admin experience.

### Scope
- cross-page links and summaries
- admin landing or section-level overviews
- consistency pass across the major admin flows

### Expected Files

#### Frontend files
- `frontend/pages/admin/*.tsx`
- `frontend/pages/analytics/*.tsx`
- `frontend/pages/memory.tsx`
- `frontend/components/admin/*`
- `frontend/lib/api.ts`

#### Optional backend files if final read-model gaps appear
- `backend/adapters/api/*`

### Acceptance Criteria
- [x] Admin users can move between billing, policy, identity, audit, and memory areas without confusion.
- [x] Cross-page links reinforce one coherent admin story.
- [x] The admin surface feels intentionally designed rather than accumulated.
- [x] Non-admin product surfaces still behave normally.

### Tests
- frontend integration/unit tests for cross-page affordances
- backend tests only if final read-model changes are required

### PR Boundary Notes
- Keep this as a coherence pass, not a new feature explosion.
- If backend gaps appear, keep them narrowly scoped and additive.

### Status
`PR-4` is complete. Cross-page links now tie together billing, policies and operations, audit, memory, and operator help, so the admin story reads like one product area rather than an accumulated set of pages.

---

## PR-5: Walkthrough Proof and Final QA Matrix

### Objective
Prove the end-to-end admin walkthrough and formalize the QA expectations for the full P2 surface.

### Scope
- walkthrough proof
- QA notes
- final roadmap/doc close-out

### Expected Files

#### Tests
- `frontend/__tests__/e2e/*.spec.ts`
- `frontend/__tests__/unit/pages/*.test.tsx`

#### Docs
- `docs/mvp/mvp-tasks-p2.md`
- `docs/mvp/p2-f04-implementation-tickets.md`
- `docs/ops/*`

### Acceptance Criteria
- [x] A walkthrough across billing, policy, identity, audit, and memory admin areas is possible without contradictory terms or hidden assumptions.
- [x] Known limitations are documented explicitly.
- [x] P2 has a usable QA matrix or walkthrough checklist instead of ad hoc demo steps.

### Tests
- focused browser proof for the main admin walkthrough
- supporting unit tests where the admin shell or major pages changed

### PR Boundary Notes
- Keep the walkthrough deterministic and product-facing.
- This PR closes P2; it should not reopen governance or reporting semantics.

### Status
`PR-5` is complete. The operator help page plus the new `docs/ops` walkthrough/checklist close P2 with a deterministic admin path and explicit known limitations instead of ad hoc demo notes.

---

## Recommended Merge Order
1. PR-1
2. PR-2
3. PR-3
4. PR-4
5. PR-5

## Final Ticket-Level Definition of Done
- [x] Admin users can navigate governance, billing, identity, policy, and memory areas without confusion
- [x] The admin surface feels intentionally designed rather than accumulated
- [x] Terminology is consistent across pages and docs
- [x] P2 closes with one coherent team-admin story instead of scattered surfaces
