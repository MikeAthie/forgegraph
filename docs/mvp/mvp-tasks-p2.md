# P2: Productization + Controls (Weeks 5-6)

## Objective
Add monetization readiness, auditability, and guardrails without destabilizing the demo path.

## Prerequisites
- P0 usage ledger and budgets implemented.
- P1 reliability improvements merged.

---

## Task List

### P2-T01: Usage Export + Quotas
Effort: Medium

Why critical:
Investors expect monetization levers and usage transparency for customers.

Current code references:
- `backend/adapters/api/analytics/memory_analytics.py:72` memory costs only.
- No LLM usage export endpoints.

Implementation steps:
1. Add endpoints for LLM usage export (CSV/JSON).
2. Add quota table with per-tenant limits (monthly tokens or USD).
3. Enforce quota at run start with clear error messaging.

Recommended patterns / best practices:
- Export endpoints should be paginated and rate-limited.
- Quota checks should fail fast before engine dispatch.

Testing strategy:
- Integration: quota exceeded blocks run creation.
- API tests for CSV export formatting.

Success criteria / Definition of Done:
- [ ] Admin can export LLM usage by tenant.
- [ ] Over-quota runs are blocked with actionable error.

Dependencies:
- P0-T07 usage ledger.

Risks:
- Large exports can be slow without pagination.

---

### P2-T02: Audit Logs
Effort: Small

Why critical:
Auditability is expected in investor-ready SaaS and enterprise deployments.

Current code references:
- `backend/infrastructure/orm/models.py` has no audit log model.

Implementation steps:
1. Add `audit_log` table with actor, action, resource, tenant_id, timestamp, metadata.
2. Emit audit events for credential changes, run starts, approvals.
3. Enforce tenant_id presence on every audit log write.
4. Add API and simple UI viewer in admin area.

Recommended patterns / best practices:
- Append-only logs; never mutate existing rows.
- Redact sensitive values.

Testing strategy:
- Unit: audit log creation for key events.
- Integration: ensure only admins can access audit logs.

Success criteria / Definition of Done:
- [ ] Audit log entries appear for credential changes and approvals.
- [ ] Access controls enforced for audit log API.
- [ ] Every audit log row includes tenant_id.

Dependencies:
- P0-T11 tenant_id propagation.

Risks:
- Log volume growth without retention policy.

---

### P2-T03: Guardrails + Egress Controls
Effort: Medium

Why critical:
Controls reduce risk for external HTTP calls and model usage.

Current code references:
- `engine/adapter/executor/http_executor.go:19` allows any URL.
- Prompt nodes accept any model in `engine/adapter/executor/prompt_executor.go:166`.

Implementation steps:
1. Add allowlist/denylist policies for HTTP executor.
2. Add model allowlist per tenant in backend.
3. Surface policy violation errors in UI.

Recommended patterns / best practices:
- Default-deny mode for production tenants.
- Policy configuration stored per tenant.

Testing strategy:
- Unit: policy evaluator for URL and model restrictions.
- Integration: blocked HTTP node returns a clear error.

Success criteria / Definition of Done:
- [ ] Disallowed HTTP calls fail with policy error.
- [ ] Disallowed model selection blocked at config time.

Dependencies:
- P0-T05 provider routing and P0-T06 schema updates.

Risks:
- Policy UX confusion if not clearly surfaced.

