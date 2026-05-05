# State Ownership ADR

> Runtime precedence: [runtime-invariants.md](runtime-invariants.md) is canonical.
> If this document conflicts with it, `runtime-invariants.md` wins.

## Decision

ForgeGraph has one durable runtime source of truth: the backend control plane.

| Layer | Allowed | Forbidden |
| --- | --- | --- |
| Engine | Execute tasks, emit events, request decisions, keep ephemeral execution context | Durable memory, long-lived summaries or facts, business projections, final state ownership |
| Backend | Durable source of truth, idempotency, memory, cost, audit, HITL, projections, tenant isolation | Runtime execution loops |
| Frontend | Read backend state, submit user decisions and commands, render observability | Business metric invention, optimistic final state, durable workflow truth |

## Enforcement

- Durable state mutations must go through backend-owned APIs, services, workers, or persistence paths.
- Engine durable product-memory writes are forbidden with no temporary exception manifest.
- Engine Redis usage is allowed only for runtime transport, retry, health, or other backend-owned queues that do not make the engine authoritative for product memory.
- Product and UI state must be traceable to backend DTOs with source and freshness metadata.

## Current Temporary Exceptions

None. The legacy engine Redis product-memory adapter and exception manifest have been removed. Ownership CI fails if engine runtime code reintroduces `RedisMemoryStore`, summary/fact persistence, or product-memory Redis writes.

## Signoff

This ADR is a launch gate. PR CI requires this checklist to remain present.
Release and production evidence gates require every role to be approved.

- [ ] Product Lead
- [ ] Backend Lead
- [ ] Engine Lead
- [ ] Frontend Lead
- [ ] Platform/SRE Lead
