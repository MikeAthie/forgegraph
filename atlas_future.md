# Atlas And ForgeGraph Reliability Roadmap

## Summary

This document is the current implementation roadmap for improving Atlas and the core ForgeGraph system together. It replaces the earlier external inspection snapshot and corrects stale findings against the local repository state.

Atlas is now visible as the `digital_marketing_pro.v1` operating model pack. Its agency workflow is pack-driven through `operating_model_packs/digital_marketing_pro/agency_ops.yml`, not hidden in client code or inferred from screenshots. The backend already owns the first-class primitives required for the loop: `WorkWhiteboard`, `TaskRoutingRecord`, `StateProjection`, `ProductOperation`, `ToolExecution`, `MetricSnapshot`, `ReportRun`, and `EvaluationRun`.

The canonical live acceptance target is `frontend/__tests__/product-modes-live/atlas-agency-full-flow.e2e.spec.ts`, normally run through:

```powershell
cd frontend
npm run test:e2e:atlas:docker:local-llm
```

The goal is no longer to prove that Atlas exists. The goal is to prove Atlas performs useful agency work while ForgeGraph preserves backend-owned durable state under realistic dependencies, approvals, deployment blockers, performance feedback, recovery pressure, and tenant isolation.

README and docs references were locally revalidated during the docs-cleanup pass. That cleanup should remain a separate PR from this Atlas/system reliability roadmap. Generated TestSprite temporary artifacts should stay out of tracked docs and source control.

## Current Status

### Implemented And Passing

- `digital_marketing_pro.v1` is the current Atlas/DMP pack identifier.
- `operating_model_packs/digital_marketing_pro/agency_ops.yml` defines the integrated Atlas agency work graph, deployment policy, and performance policy.
- The agency work graph includes strategy, legal/compliance, tech/martech, media, copy, analytics, traffic, content, timing, and deployment-readiness workstreams.
- `WorkWhiteboard` is backend-owned and first-class.
- Phase state and routing state are persisted through backend-owned records, including `TaskRoutingRecord.metadata_json` and `StateProjection`.
- Generic `/api/whiteboards/*` routes are used for Atlas work instead of vertical Atlas or marketing APIs.
- Operation lifecycle readiness is represented with backend-owned `ProductOperation` records.
- The live Atlas flow covers request routing, whiteboard creation, workstream fan-out, dependency blocking/unblocking, approval, deployment preparation, performance review, isolation, and forbidden vertical route checks.
- The live Atlas flow emits a release evidence bundle with route checks, operation IDs, contract revisions, workstream dependency transitions, approval state, deployment receipts/blockers, performance IDs, memory references, helper-assisted steps, and isolation checks.
- The live Atlas flow now includes a second-run memory-uplift follow-up that routes a fresh campaign, reuses prior approved memory, and records avoided rejected claims/channels in backend phase evidence.
- Backend memory attribution/reuse tests cover prior-run memory reuse, and liveness tests cover backend-owned checkpoint recovery when stale resume attempt state exists.
- The full-flow agency test emits a consolidated Atlas quality, system reliability, and runtime integrity score summary.
- Docker/local-LLM Atlas acceptance has passed with the live full-flow target.
- The primary Atlas live flow is UI-driven for connector availability, structured whiteboard context editing, workstream completion, phase synthesis, gate evaluation, performance report generation, and performance evaluation.

### Partially Mature

- The second-run memory-uplift follow-up is helper-assisted through backend communication and phase APIs until guided follow-up authoring and memory-review UI exist.
- Connector management is availability/config-only. Real credential onboarding and provider verification are still out of scope.
- Structured whiteboard editing uses pragmatic JSON fields and compact controls rather than full guided artifact authoring.
- Performance report and evaluation UI exists, but richer review packets, score explanations, and human-review rubric support are still immature.

### Missing Release-Grade Evidence

- Controlled engine-restart evidence in a Docker/live flow, beyond the backend liveness regression tests.
- Load, projection-lag, and event-transport evidence under realistic pressure.
- A stronger human-review rubric for final deliverable quality.
- Richer production deployment evidence.
- Real provider connector evidence beyond configured sandbox receipts and honest blockers.

## Reliable Test Objective

The primary gate remains:

```powershell
cd frontend
npm run test:e2e:atlas:docker:local-llm
```

The test objective is not "the flow completed." The objective is:

> Atlas performed useful agency work while ForgeGraph preserved backend-owned durable state under realistic dependencies, approvals, deployment blockers, performance feedback, and isolation.

The live test must fail on:

- `/api/atlas/*`, `/api/marketing/*`, or `/api/legacy/*` usage.
- Fake connector success when a connector is unavailable.
- Tenant leakage across whiteboards, operations, approvals, deployments, performance records, artifacts, memory, or routes.
- Any backend/client/engine ownership violation of durable state.
- Missing approval gates before deployment preparation.
- Missing or non-terminal `ProductOperation` evidence for phase, deployment, and performance actions.
- Missing contract revision evidence for mutable phase/deployment/performance work.
- Untraceable memory or performance outcomes.
- Helper-assisted steps that are not listed in the evidence artifact.

## Roadmap Task List

### P0 - Release Evidence And Runtime Integrity

- [x] Extend the existing live Atlas spec with a production evidence bundle containing route checks, operation IDs, contract revisions, workstream dependency transitions, approval state, deployment receipts/blockers, performance IDs, memory references, and isolation checks.
- [x] Add operation lifecycle assertions for phase start, synthesis, gate evaluation, deployment preparation, performance review, report generation, and evaluation.
- [x] Add a second-run memory-uplift follow-up to the live Atlas flow. The follow-up campaign must reuse prior approved constraints/learnings and avoid at least one previously rejected claim, channel, or assumption.
- [x] Add backend tests for memory attribution and second-run reuse using the existing memory services.
- [x] Add recovery and liveness test coverage proving backend-owned recovery, no stale resume acknowledgement, and no engine durable ownership.
- [x] Add a score summary combining Atlas quality, system reliability, and runtime integrity.

### P1 - Product UI Maturity

- [x] Add UI for workstream artifact submission and completion.
- [x] Add UI for phase synthesis and gate evaluation.
- [x] Add structured whiteboard editing for onboarding and campaign constraints.
- [x] Add connector-management UI so Playwright no longer patches connector availability.
- [x] Add consolidated release evidence export with routes, operation IDs, revisions, approvals, deployment receipts/blockers, performance IDs, memory references, helper-assisted steps, and isolation checks.
- [x] Make performance report and evaluation reviewable from the product UI.

P1 implementation status: complete for the primary Atlas live flow. The Docker/local-LLM live gate passes with connector setup, onboarding enrichment, primary workstream completion, synthesis, gate evaluation, performance report generation, and performance evaluation driven through UI controls. Follow-up memory uplift remains helper-assisted by design until guided follow-up authoring and memory-review UI exist.

### P1 Implementation Plan

P1 target: the primary Atlas live flow should be UI-driven for connector setup, onboarding enrichment, workstream completion, phase synthesis, gate evaluation, performance report generation, and performance evaluation. Follow-up memory uplift may remain helper-assisted until guided follow-up authoring and memory-review UI exist.

- Implement pragmatic v1 controls, not rich artifact editors: compact forms, JSON inputs where structured authoring is still immature, and backend-owned responses as the source of truth.
- Keep every action on generic ForgeGraph routes: company pack config updates through `/api/companies/{companyId}/packs/{installationId}`, and whiteboard phase/deployment/performance actions through `/api/whiteboards/*`.
- Add connector availability controls from pack metadata and preserve pack-owned configuration by only changing `available_connectors`, with generated policy keys removed from submitted company config.
- Add whiteboard context editing for objective, budget, timeline, constraints, stakeholder/resource/delivery context, and assumptions, then reload backend state after save.
- Add workstream completion controls, phase synthesize/evaluate controls, and performance report/evaluate controls in `WhiteboardPanel`, using existing backend contracts and operation lifecycle evidence.
- Update the live Atlas spec so helper-assisted steps for the primary run are removed; remaining helpers must be limited to follow-up memory uplift, durable-state/isolation verification, and evidence collection.

### P2 - Scale, Transport, And Review Depth

- [ ] Add a Kafka-enabled whiteboard transport variant while preserving backend-owned authority.
- [ ] Add load-generation coverage for workstream fan-out, dependency transitions, operation lifecycle writes, and projection lag.
- [ ] Add richer scorecards and a human-review packet for release decisions.
- [ ] Add optional real connector integrations for approved deployment channels, with sandbox receipts and honest blockers where providers are unavailable.

## Success Criteria

### Atlas Quality

- Strategy, legal/compliance, tech/martech, media, copy, analytics, traffic, content, timing, and deployment-readiness workstreams are visible in evidence with correct dependency transitions.
- The final deliverable is judged or scored against strategy coherence, compliance safety, execution readiness, client clarity, measurement readiness, and tool honesty.
- A follow-up campaign proves memory usefulness by reusing prior approved constraints/learnings and avoiding at least one previously rejected claim, channel, or assumption.

### System Reliability

- Every phase, deployment, and performance action has a durable `ProductOperation` with terminal status and contract revision evidence.
- Whiteboard, phase, deployment, performance, approval, memory, and routing state can be re-read from backend APIs after frontend reload.
- Missing connectors create blockers or signals, not fake `ToolExecution` success.
- Other-client isolation returns no whiteboard, operation, approval, deployment, performance, artifact, memory, or route leakage.
- No `/api/atlas/*`, `/api/marketing/*`, or `/api/legacy/*` routes are used.

### Runtime Integrity

- Backend remains the only durable source of truth.
- Redis, Kafka, and WebSocket state are treated as cache or transport only.
- Engine tests and runtime checks continue to reject durable ownership regressions.
- Recovery tests prove no stale resume acknowledgement or engine-memory dependency can corrupt state.

### Release Gate

- Existing targeted backend tests pass.
- Architecture invariant tests pass.
- Frontend typecheck passes.
- `npm run test:e2e:atlas:docker:local-llm` passes.
- The Atlas evidence attachment includes enough IDs and revisions to debug the run without relying on screenshots alone.

## Evidence Contract

The live Atlas evidence artifact should include at minimum:

- Pack id and namespace.
- Company, customer, campaign, whiteboard, and phase identifiers.
- Route list proving only generic routes were used.
- Workstream batches before and after dependency transitions.
- `ProductOperation` IDs, terminal statuses, and contract revisions for phase, deployment, and performance actions.
- Approval task ID, approval status, reviewer identity, and approval timestamp.
- Deployment readiness result, executed connector receipts, and blocker records for missing connectors.
- Performance metric snapshot ID, report run ID, evaluation run ID, and optimization routing records.
- Memory references used by the run and follow-up memory-uplift proof.
- Recovery or resume identifiers for recovery-focused runs.
- Tenant isolation checks for whiteboards, operations, approvals, deployments, performance records, artifacts, memory, and routes.
- Helper-assisted steps with the reason each helper was still required.

## Assumptions

- Keep Atlas on generic ForgeGraph primitives; do not introduce `/api/atlas/*` or marketing-specific core durable models.
- Keep `digital_marketing_pro.v1` as the current Atlas/DMP pack identifier.
- Keep the existing live Atlas spec as the primary acceptance target rather than creating a parallel production spec immediately.
- Treat docs cleanup as a separate PR from Atlas/system reliability work.
- Keep helper-assisted steps allowed only where the product UI does not exist yet, and require every helper-assisted step to be listed in the evidence artifact.
