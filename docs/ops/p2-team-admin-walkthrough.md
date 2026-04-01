# P2 Team Admin Walkthrough and QA Checklist

## Goal
Prove that the shipped P2 surface is coherent for a team admin without requiring backend code access.

## Walkthrough
1. Open `/admin`.
   Confirm the governance map includes organization, identity, billing, audit, policies and operations, and memory.
2. Open `/admin/organization`.
   Confirm the current role and the memory-governance role matrix are visible.
3. Open `/admin/sso`.
   Confirm SSO and SCIM state is explicit as configured, partial, or unavailable.
4. Open `/admin/billing`.
   Confirm plan entitlements are separate from tenant quota and budget.
5. Open `/admin/audit-logs`.
   Confirm actor, action, resource, and date-range filters work and entries have human-readable descriptions.
6. Open `/admin/operations`.
   Confirm:
   - runtime mode is visible
   - HTTP egress posture is visible
   - provider/model allowlist posture is visible
   - retention lifecycle is explained
   - cleanup preview is available
   - health badges are visible
   - support-safe exports are available
7. Open `/memory`.
   Confirm curated observations are visible as governed tenant assets.
8. Open a degraded or blocked run in `/runs/[runId]`.
   Confirm the run diagnostics point to policy, budget, quota, entitlement, or degraded memory without reading raw payloads first.

## Expected Outcomes
- A team admin can explain who can govern memory.
- A team admin can explain what is blocked and why.
- A team admin can explain what data is retained and what is manual.
- A support operator can export tenant-scoped diagnostics without direct database access.

## Known Limitations
- The support-safe exports are shaped product exports, not a general observability or SIEM integration.
- Curated observation/chunk lifecycle remains manual-governance oriented in P2.
- This closes the MVP admin/operator story; it is not a full enterprise admin platform.

## QA Checklist
- [x] Admin hub is the primary governance entry point.
- [x] Billing, audit, identity, organization, operations, and memory surfaces are cross-linked coherently.
- [x] Policy, retention, and memory-health summaries are visible from `/admin/operations`.
- [x] Cleanup preview is explicit about destructive implications.
- [x] Support-safe exports are discoverable from the product UI.
- [x] Audit and role surfaces explain memory ownership and actionability.
- [x] Run diagnostics expose blocked/degraded causes without raw JSON spelunking.
