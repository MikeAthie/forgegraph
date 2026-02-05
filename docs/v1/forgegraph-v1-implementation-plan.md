# ForgeGraph V1 Implementation Plan (P3-P5)

## Executive Summary
This plan targets a V1 release after the MVP (P0-P2). The focus is enterprise readiness, scale, and platform growth while preserving the fast demo path. The stack remains Go engine, Django/DRF + Channels, Next.js, gRPC, Docker.

## Timeline (Proposed)
- Weeks 7-9: P3 (enterprise readiness + billing).
- Weeks 10-12: P4 (scale, reliability, and cost controls).
- Weeks 13-16: P5 (platform ecosystem + growth).

## P3: Enterprise Readiness + Billing (Weeks 7-9)
Goals:
- Organization and role-based access control.
- Single sign-on and user provisioning.
- Monetization with plan entitlements and usage enforcement.

See detailed tasks: `docs/v1/v1-tasks-p3.md`.

## P4: Scale + Reliability (Weeks 10-12)
Goals:
- Queue-based execution and worker scaling.
- Full observability with metrics, traces, and SLOs.
- High availability, backups, and disaster recovery.

See detailed tasks: `docs/v1/v1-tasks-p4.md`.

## P5: Platform Ecosystem + Growth (Weeks 13-16)
Goals:
- Node SDK and marketplace for integrations.
- Template library with versioning and sharing.
- Expansion of core integrations and onboarding templates.

See detailed tasks: `docs/v1/v1-tasks-p5.md`.

## V1 Readiness Checklist
Product:
- [ ] RBAC and org management enforce permissions for all APIs.
- [ ] SSO (OIDC or SAML) supported with just-in-time provisioning.
- [ ] Plans and entitlements block overuse with clear errors.

Reliability:
- [ ] Runs are queued and can scale across workers.
- [ ] Metrics, tracing, and alerts cover engine and API critical paths.
- [ ] Backups and restore drills complete with documented RTO/RPO.

Platform:
- [ ] SDK can ship a new node without editing core engine code.
- [ ] Templates are versioned and can be shared across tenants.
- [ ] Top 10 integrations are available with OAuth setup flows.
