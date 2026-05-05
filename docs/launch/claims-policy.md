# Launch Claims Policy

> Runtime precedence: [../architecture/runtime-invariants.md](../architecture/runtime-invariants.md) is canonical.

Product claims must reflect durable backend-owned truth and checked-in
production evidence.

## Allowed Today

- controlled private beta
- backend-owned runtime architecture
- live HITL flows
- tenant-isolated operations
- early Command Ops surface

## Forbidden Today

- 500+ concurrent agents
- production-grade company OS
- run entire companies at scale
- complete accounting visibility

## Evidence Rule

Forbidden claims stay blocked in README, product copy, SEO text, and frontend
surfaces until the relevant evidence gate passes and
[launch-claims.md](../architecture/launch-claims.md) is fully signed off.
