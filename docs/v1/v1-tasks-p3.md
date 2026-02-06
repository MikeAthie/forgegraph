# P3: Enterprise Readiness + Billing (Weeks 7-9)

## Objective
Enable enterprise adoption with org management, SSO, and monetization controls.

## Prerequisites
- P2 audit logs and guardrails complete.
- Tenant isolation enforced end-to-end.

---

## Task List

### P3-T01: Organizations + RBAC
Effort: Medium

Why critical:
Enterprise buyers require multi-user organizations with explicit permissions.

Implementation steps:
1. Add organization and membership models with roles (owner, admin, member, viewer).
2. Define a permission matrix for reads, writes, approvals, and billing access.
3. Enforce permissions at API boundaries (backend) and hide disallowed UI actions.
4. Add admin UI for org membership management and role changes.

Recommended patterns / best practices:
- Default least-privilege role for new members.
- Centralized permission checks, not ad hoc conditionals.

Testing strategy:
- Unit: permission matrix coverage by role.
- Integration: role-based access to run, credential, and billing endpoints.

Success criteria / Definition of Done:
- [x] A tenant can have multiple users with distinct roles.
- [x] Permission checks block unauthorized API access.
- [x] UI respects permissions and hides restricted actions.

Dependencies:
- P2 tenant_id propagation and audit logs.

Risks:
- Permission sprawl without a single source of truth.

---

### P3-T02: SSO + SCIM Provisioning
Effort: Medium

Why critical:
Enterprise security teams require SSO and automated user lifecycle management.

Implementation steps:
1. Add OIDC (and optionally SAML) provider configuration per tenant.
2. Implement SSO login flow and account linking.
3. Add SCIM endpoints for create, update, deactivate users.
4. Extend audit logs to capture SSO and provisioning actions.

Recommended patterns / best practices:
- Support just-in-time provisioning on first SSO login.
- Keep local password auth available for break-glass access.

Testing strategy:
- Integration: OIDC login creates or links a user.
- Integration: SCIM deactivation disables access within 1 minute.

Success criteria / Definition of Done:
- [x] Tenant admins can configure OIDC provider settings.
- [x] Users can log in via SSO and receive correct roles.
- [x] SCIM updates propagate to local user records reliably.

Dependencies:
- P3-T01 org and role model.

Risks:
- Provider-specific quirks or attribute mapping issues.

---

### P3-T03: Billing Plans + Entitlements
Effort: Medium

Why critical:
V1 requires monetization controls and plan enforcement.

Implementation steps:
1. Add plan and entitlement models (feature flags, usage limits, seat limits).
2. Integrate billing provider (Stripe or equivalent) for subscriptions.
3. Enforce entitlements at run start and premium feature toggles.
4. Add billing admin UI for plan selection, invoices, and usage.

Recommended patterns / best practices:
- Fail closed when entitlement checks cannot be evaluated.
- Keep plan evaluation server-side only.

Testing strategy:
- Integration: downgrade plan blocks premium nodes and large runs.
- Integration: billing webhook updates plan state.

Success criteria / Definition of Done:
- [x] Tenant can subscribe, change plan, and see current status.
- [x] Over-limit usage is blocked with clear error messaging.
- [x] Usage and invoices are visible in the admin UI.

Dependencies:
- P2 usage ledger and quotas.

Risks:
- Billing edge cases around proration and overage.

---

### P3-T04: Data Retention + Export/Deletion
Effort: Small

Why critical:
Enterprises require data retention controls and deletion workflows.

Implementation steps:
1. Add tenant-level retention settings for runs, logs, and audit data.
2. Implement scheduled cleanup jobs with dry-run reporting.
3. Add export endpoint for compliance requests.

Recommended patterns / best practices:
- Retention rules should be append-only; record changes in audit logs.
- Deletion jobs should be idempotent and safe to re-run.

Testing strategy:
- Unit: retention rules evaluate correctly.
- Integration: cleanup job removes data older than policy.

Success criteria / Definition of Done:
- [x] Tenant can set retention windows per data type.
- [x] Old data is purged on schedule with audit trails.
- [x] Exports cover runs, logs, and usage data.

Dependencies:
- P2 audit logs.

Risks:
- Accidental data loss without preview or guardrails.
