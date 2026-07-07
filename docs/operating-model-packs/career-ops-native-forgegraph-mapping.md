# CareerOps Native ForgeGraph Mapping

This document captures the native platform contract for porting Career-Ops into ForgeGraph.

Detailed contract:

```text
.hermes/plans/2026-06-16_190000-career-ops-native-forgegraph-contract.md
```

## Summary

Career-Ops validates the career-search product pattern. ForgeGraph should implement that pattern using backend-owned native surfaces:

- `Run` / execution
- `TaskRecord`
- `DecisionRecord`
- `MemoryObservation`
- `CostAggregate`
- `AssetVersion`
- `ServiceDeliverable`
- `CompanySignal`
- `CompanyOpportunity`
- `StateProjection`

The backend remains the durable source of truth. Engine, cron, UI, local files, and external events are execution or transport surfaces only.

## Daily discovery

CareerOps should support a 10:00 AM daily discovery automation once ForgeGraph automations are available. The schedule belongs to ForgeGraph; external cron is only a wake-up adapter.

The automation may discover, evaluate, draft, and queue approval-ready options. It must never submit applications.

## Cooldown

Default application cooldown is 30 days for the same employer/role. Cooldown blocks packet readiness and external side effects, but may still create skip/cooldown signals for observability.

## Base CV

A canonical `cv_source` asset version is required before tailoring resumes or producing live-ready packets.
