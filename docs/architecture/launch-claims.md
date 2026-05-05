# Launch Claims

> Runtime precedence: [runtime-invariants.md](runtime-invariants.md) is canonical.

Launch claims must follow backend-owned durable truth and checked-in evidence.
Architecture goals, stress targets, or frontend affordances are not public
capability claims.

## Decision

ForgeGraph may be described as a controlled private beta with backend-owned
runtime architecture, live HITL flows, tenant-isolated operations, and an early
Command Ops surface.

ForgeGraph must not be described as production-grade company OS infrastructure,
a 500+ concurrent-agent system, a platform that can run entire companies at
scale, or a product with complete accounting visibility until the corresponding
evidence gates pass and this document is signed off.

## Evidence Rules

- Capacity claims must match the latest checked-in capacity gate evidence.
- Accounting claims must match backend-instrumented accounting DTOs.
- Command Ops claims must match backend-owned read models and live-state tests.
- Product copy must link to the evidence that supports any broad launch claim.

## Signoff

This launch-claim contract is a release gate. PR CI requires this checklist to
remain present. Release and production evidence gates require every role to be
approved.

- [ ] Product Lead
- [ ] Backend Lead
- [ ] Engine Lead
- [ ] Frontend Lead
- [ ] Platform/SRE Lead
