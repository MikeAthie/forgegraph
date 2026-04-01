# P2 Memory Governance and Support Guide

## Purpose
This is the short operator guide for the shipped P2 surface.

Use it when a tenant asks:
- why a run was blocked
- what data is retained
- whether curated memory is healthy
- what can be exported safely for support

## Primary Product Surfaces
- `/admin` is the governance hub.
- `/admin/operations` is the operator control plane for guardrails, retention, health, and support exports.
- `/admin/billing` explains plan entitlements, quota, and budget limits.
- `/admin/audit-logs` is the searchable governance trail.
- `/admin/organization` explains memory ownership and role implications.
- `/admin/sso` explains SSO and SCIM readiness.
- `/memory` is the observation browser.
- `/runs/[runId]` is the first stop for run-specific diagnostics.

## Cloud vs Self-Hosted
- `cloud` mode can deny exec-tool behavior even when a graph requests it.
- `self_hosted` mode still follows package restrictions and tenant policy.
- The policy API now returns runtime mode and exec-tool policy summaries so operators do not need to infer this from backend settings.

## Retention Expectations
- Runs, run logs, audit logs, and usage rows follow the tenant retention policy.
- Curated observations and indexed memory chunks are still manual-governance surfaces in P2. Operators should explain that clearly instead of implying automated deletion where it does not exist.
- The admin operations screen exposes a dry-run cleanup preview before destructive action.

## Blocked Run Triage
1. Open the run in `/runs/[runId]`.
2. Read the run diagnostics first.
3. If the run is blocked by budget, quota, or entitlement, move to `/admin/billing`.
4. If the run is blocked by policy, move to `/admin/operations`.
5. If the run is degraded because memory retrieval fell back, inspect indexing backlog and memory health in `/admin/operations`, then inspect the observation trail in `/memory`.

## Memory Degradation Triage
When a run shows degraded curated memory:
- check indexing backlog
- check Redis health
- check memory gRPC health
- check recent maintenance markers
- inspect the observation trail for the expected graph/run/session scope

The goal is to determine whether the issue is:
- a policy block
- an infrastructure/health issue
- indexing lag
- missing observation coverage

## Support-Safe Exports
Use `/admin/operations` for tenant-scoped exports:
- run traces
- node runs
- audit logs
- usage rows
- memory usage rows
- memory report

Why this matters:
- exports follow product/API access controls
- exports inherit API redaction behavior
- operators do not need direct database access for normal support work

## Identity and Governance Questions
- `/admin/organization` explains which roles can view observations, delete observations, manage retention, and export memory data.
- `/admin/audit-logs` shows the action trail for observation create/update/delete and retention changes.
- `/admin/sso` shows whether identity state is configured, partial, or unavailable.

## Known Limits
- P2 does not introduce a custom role builder.
- P2 does not add SIEM or enterprise compliance automation.
- Curated observation and chunk lifecycle is still an operator-managed surface; it is not a full automated data-governance product.
