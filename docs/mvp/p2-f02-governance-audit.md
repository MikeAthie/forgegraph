# P2-F02 Governance Audit and IA Baseline

## Goal
Create one stable governance entry point before `P2-F02` starts changing audit, role, identity, and memory-governance behavior.

This audit is intentionally narrow:
- inventory the current operator-facing admin surfaces
- group them into a governance IA that matches the roadmap
- avoid a broad shell redesign before the semantics settle

## Current Surface Inventory

### Organization
- Product surface: `frontend/pages/admin/organization.tsx`
- Backend foundation: organization membership APIs
- Current value: tenant identity, member list, role assignment, invite/remove flows
- Current gap: treated as the default admin page even though it only covers one part of governance

### Identity
- Product surface: `frontend/pages/admin/sso.tsx`
- Backend foundation: OIDC / SSO provider config and SCIM token APIs
- Current value: Auth0 configuration and SCIM token rotation
- Current gap: identity state is isolated from the rest of admin and still reads like a raw config page

### Billing
- Product surface: `frontend/pages/admin/billing.tsx`
- Backend foundation: plans, subscriptions, budget, quota, entitlement checks
- Current value: commercial ceiling, quota, budget, and subscription state
- Current gap: accessible only as a separate page with little connection to the broader governance story

### Audit
- Product surface: `frontend/pages/admin/audit-logs.tsx`
- Backend foundation: append-only audit model and filtering API
- Current value: support-oriented raw event stream
- Current gap: discoverability is weak and the page still assumes operators already know what to look for

### Policies
- Current product surface: `frontend/pages/admin/operations.tsx` plus analytics and run diagnostics
- Backend foundation: tenant policies and retention APIs
- Current value: policy, retention, health, and support exports now share one operator-facing admin surface
- Current gap: page-level polish and walkthrough clarity become a final `P2-F04` concern instead of a missing IA concern

### Memory
- Product surface: `frontend/pages/memory.tsx`, `frontend/pages/analytics/memory.tsx`
- Backend foundation: curated observation APIs, memory analytics, GC foundations
- Current value: observation browsing plus memory usage and retention posture reporting
- Current gap: memory is treated as a product feature, but not yet positioned as a governed asset inside admin

### Additional Admin Tooling
- Product surface: `frontend/pages/admin/marketplace.tsx`
- Current role in IA: important, but not part of the core governance grouping for `P2-F02`

## Governance IA Baseline

`/admin` becomes the shared landing page for governance and operator workflows.

Required governance sections for follow-up PRs:
1. Organization
2. Identity
3. Billing
4. Audit
5. Policies
6. Memory

Section-to-surface mapping for the current baseline:

| Section | Current home | Why it belongs here |
| --- | --- | --- |
| Organization | `/admin/organization` | Membership and role state define who can operate the tenant. |
| Identity | `/admin/sso` | SSO and SCIM affect access, provisioning, and admin trust. |
| Billing | `/admin/billing` | Plan, quota, and budget limits directly affect operator behavior. |
| Audit | `/admin/audit-logs` | Governance requires a readable action trail. |
| Policies | `/admin/operations` plus run diagnostics | Guardrails, retention, memory health, and support exports now have one operator-facing home. |
| Memory | `/memory` and `/analytics/memory` | Curated observations are durable tenant assets and must be presented as governed data. |

## Navigation Decision
- Add a lightweight `/admin` hub now.
- Use that hub as the primary account-menu entry point for governance work.
- Keep direct deep links for operator speed, but treat them as shortcuts, not as the IA itself.
- Do not redesign the whole shell during this baseline PR.

## Follow-up Constraints
- `P2-F02` PR-2 should improve audit readability and filtering inside the Audit section defined here.
- `P2-F02` PR-3 should make role and memory-ownership implications explicit inside Organization and Memory.
- `P2-F02` PR-4 should make Identity status truthful without creating a competing admin grouping.
- `P2-F03` gave Policies a dedicated home without changing this section model.

## Done for PR-1
- Current admin surfaces are inventoried.
- Governance sections are named and mapped to current product surfaces.
- `/admin` is the baseline operator entry point for the rest of `P2-F02`.
