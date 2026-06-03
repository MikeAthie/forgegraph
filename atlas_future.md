# Atlas And ForgeGraph Reliability Roadmap

## Purpose

This file is the agent-facing test charter for Atlas. It should answer three questions before any new implementation or live run:

- What are we trying to prove?
- What evidence would make the result credible enough to charge money for?
- When the test fails or the judges score low, what should be improved next?

After every meaningful live run, update this file with the run status, the weakest evidence area, and the next target. Do not treat this as a generic product brief or docs cleanup bucket.

## Summary

This document is the current implementation roadmap for improving Atlas and the core ForgeGraph system together. It replaces the earlier external inspection snapshot and corrects stale findings against the local repository state.

Atlas is now visible as the `digital_marketing_pro.v1` operating model pack. Its agency workflow is pack-driven through `operating_model_packs/digital_marketing_pro/agency_ops.yml`, not hidden in client code or inferred from screenshots. The backend already owns the first-class primitives required for the loop: `WorkWhiteboard`, `TaskRoutingRecord`, `StateProjection`, `ProductOperation`, `ToolExecution`, `MetricSnapshot`, `ReportRun`, and `EvaluationRun`.

The canonical live acceptance target is `frontend/__tests__/product-modes-live/atlas-agency-full-flow.e2e.spec.ts`, normally run through:

```powershell
cd frontend
npm run test:e2e:atlas:docker:local-llm
```

The goal is no longer to prove that Atlas exists. The goal is to prove Atlas performs useful agency work while ForgeGraph preserves backend-owned durable state under realistic dependencies, approvals, deployment blockers, performance feedback, recovery pressure, tenant isolation, and AI-judged quality review.

The current test target is the first `atlas_agency_full_flow_v5` live evidence bundle with AI judges enabled. The expected outcome is not necessarily "sellable." The expected outcome is honest: pass deterministic system invariants, persist all judge scorecards, and expose exactly what prevents the result from being chargeable.

README and docs references were locally revalidated during the docs-cleanup pass. That cleanup should remain a separate PR from this Atlas/system reliability roadmap. Generated TestSprite temporary artifacts should stay out of tracked docs and source control.

## Current Status

### Implemented And Static-Verified

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
- Docker/local-LLM Atlas acceptance passed for the earlier P1 UI-driven full-flow target before the AI-judge layer.
- The primary Atlas live flow is UI-driven for connector availability, structured whiteboard context editing, workstream completion, phase synthesis, gate evaluation, performance report generation, and performance evaluation.
- Atlas AI judge profiles now live in `digital_marketing_pro.v1` pack metadata for seven departments, five process capabilities, and overall paid-readiness.
- `/api/evaluations/run` accepts the generic submitted `atlas_rubric_scorecard_v1` schema and persists each judge result as backend-owned `EvaluationRun`, `EvaluationScorecard`, `EvaluationFinding`, and actionable `CompanySignal` evidence.
- The live Atlas flow replaces the deterministic fake review-board scorecard with live LLM judge output by default when `LIVE_LLM_JUDGE` is not `false`.
- A backend-owned snapshot recovery drill corrupts cache-only whiteboard snapshots, rebuilds them from DB truth, and exposes generic ops evidence through `/api/ops/snapshot-recovery-drill`.
- Static validation for the AI-judge implementation has passed: frontend typecheck, Prettier, backend Ruff, Python compile, and `git diff --check`.
- The first report-only Docker/local-LLM live Atlas gate with AI judges passed after parser and evidence-packet hardening. It persisted seven department scorecards, five process scorecards, and one overall sellability scorecard while keeping `ATLAS_JUDGES_REQUIRE_SELLABLE=false`.
- Generic backend-owned media generation now supports OpenAI image credentials through `/api/archive/media-generations`, persisting attempted provider calls as `MediaGenerationJob` records and successful images as draft `Asset`/`AssetVersion` records. Video remains Google-only.

### Latest Local LLM Baseline

The latest report-only run passed structurally and achieved the immediate local LLM baseline: every department and process average is at least `3.0/5`. It is still not a release-grade paid-readiness baseline because memory usefulness is exactly `3.0/5` and one process score is below the strict `3.5/5` floor.

- Command: `LIVE_LLM_JUDGE=true ATLAS_JUDGES_REQUIRE_SELLABLE=false npm run test:e2e:atlas:docker:local-llm`
- Result: Playwright passed and persisted 13 backend-owned `atlas_rubric_scorecard_v1` evaluations.
- Overall paid-readiness: `4.2/5`, decision `sellable_with_minor_revisions`.
- Departments: strategy research `4.2`, brand/content `4.2`, channel execution `4.0`, CRM/lifecycle `3.8`, analytics/performance `4.0`, QA/compliance `4.2`, client/approval ops `4.6`.
- Processes: memory usefulness `3.0`, whiteboard usefulness `3.8`, snapshot recovery `4.2`, connector/tool honesty `4.0`, operation/reliability evidence `3.6`.
- The channel-execution evidence patch moved `channel_execution` from `2.8/5` to `4.0/5`.
- The snapshot-recovery invariant patch moved `snapshot_recovery` from a blocked `3.6/5` to a passing `4.2/5`.
- Next test target: improve actual memory usefulness and operation/reliability evidence until every department and process is at least `3.5/5`, then evaluate whether the strict paid-readiness gate is credible.

### Latest Managed OpenAI Baseline

Managed OpenAI runtime is working again. The latest OpenAI-backed Atlas report-only gate passed structurally with `gpt-5.4-mini`, while keeping `ATLAS_JUDGES_REQUIRE_SELLABLE=false`.

- Command: `LIVE_LLM_PROVIDER=openai LIVE_LLM_MODEL=gpt-5.4-mini OPENAI_BASE_URL=https://api.openai.com/v1 LIVE_LLM_JUDGE=true ATLAS_JUDGES_REQUIRE_SELLABLE=false npm run test:e2e:atlas:docker:local-llm`
- Result: Playwright passed in `8.3m` and persisted 13 backend-owned `atlas_rubric_scorecard_v1` evaluations.
- Overall paid-readiness: `4.0/5`, decision `sellable_with_minor_revisions`, strict sellability gate `false` because the overall average is below `4.2`.
- Departments: strategy research `3.8`, brand/content `4.2`, channel execution `4.6`, CRM/lifecycle `3.8`, analytics/performance `3.4`, QA/compliance `4.2`, client/approval ops `4.4`.
- Processes: memory usefulness `4.2`, whiteboard usefulness `4.4`, snapshot recovery `5.0`, connector/tool honesty `4.8`, operation/reliability evidence `4.8`.
- Backend-owned media smoke succeeded through OpenAI image generation: `MediaGenerationJob 34eb67cc-128d-4e5c-ab5f-72694ae921f4`, model `gpt-image-1-mini`, asset `4e47953a-9fc9-4211-8984-22eaaae70357`, version `4c09fd54-f06f-43e4-a315-797aca768787`, `image/png`, `1492178` bytes.
- `gpt-5.4-mini` required generic OpenAI gateway compatibility for `max_completion_tokens`; older `max_tokens` is rejected by GPT-5-family Chat Completions models.
- Strict gate should not be run yet because it is expected to fail on the persisted scorecard: overall `4.0 < 4.2` and analytics/performance `3.4 < 3.5`.
- Next improvement target: raise analytics/performance and overall measurement coverage, especially multi-source metric evidence and full-funnel connector coverage, then rerun report-only before enabling strict paid-readiness.

### Pending Live Verification And Iteration

- Repeat the report-only Docker/local-LLM gate to confirm the `3.0/5` local baseline is stable across more than one run.
- Raise memory usefulness and operation/reliability evidence to at least `3.5/5` before treating the run as a strict paid-readiness candidate.
- Raise managed-OpenAI analytics/performance from `3.4/5` to at least `3.5/5`, and overall paid-readiness from `4.0/5` to at least `4.2/5`, before running the strict gate.
- Reject or flag any judge recommendation that asks for engine durable ownership; backend-owned recovery and absence of engine durable state are positive runtime invariants.
- After the report-only baseline is stable, rerun with `ATLAS_JUDGES_REQUIRE_SELLABLE=true` only when the evidence indicates the output can plausibly pass.

### Partially Mature

- The second-run memory-uplift follow-up is helper-assisted through backend communication and phase APIs until guided follow-up authoring and memory-review UI exist.
- Connector management is availability/config-only. Real credential onboarding and provider verification are still out of scope.
- Structured whiteboard editing uses pragmatic JSON fields and compact controls rather than full guided artifact authoring.
- Performance report and evaluation UI exists, but richer review packets, score explanations, and human-review rubric support are still immature.
- AI judge results are report-and-flag by default. Low quality does not fail the main live command unless `ATLAS_JUDGES_REQUIRE_SELLABLE=true`.

### Missing Release-Grade Evidence

- Controlled engine-restart evidence in a Docker/live flow, beyond the backend liveness regression tests.
- Load, projection-lag, and event-transport evidence under realistic pressure.
- A stronger human-review rubric for final deliverable quality.
- Richer production deployment evidence.
- Real provider connector evidence beyond configured sandbox receipts and honest blockers.
- A stable paid-readiness baseline with repeated judge runs proving the result is good enough to charge for, not merely structurally complete.

## Reliable Test Objective

The primary gate remains:

```powershell
cd frontend
npm run test:e2e:atlas:docker:local-llm
```

Runtime validation unblock checklist:

```powershell
docker info
docker compose up -d postgres redis backend frontend
curl -f http://127.0.0.1:8000/api/health
curl -f http://127.0.0.1:8000/health
cd frontend
$env:LIVE_LLM_JUDGE = "true"
$env:ATLAS_JUDGES_REQUIRE_SELLABLE = "false"
npm run test:e2e:atlas:docker:local-llm
```

If `/api/health` is not registered, `/health` is acceptable. The health check must prove the backend is actually reachable before Playwright starts because the local-LLM script reuses existing Docker services.

Default required CI/local acceptance should remain deterministic plus report-only AI quality:

```powershell
cd frontend
npx tsc --noEmit --pretty false
npx prettier --check __tests__/product-modes-live/atlas-agency-full-flow.e2e.spec.ts ../atlas_future.md

cd ../backend
uv run ruff check
uv run python -m py_compile application/services/evaluations.py application/services/snapshot_recovery_drills.py adapters/api/ops/views.py
uv run pytest tests/unit/api/test_product_mode_architecture_invariants.py tests/unit/api/test_operating_model_packs_api.py tests/unit/api/test_ops_transport_evidence_api.py tests/unit/services/test_snapshot_recovery_drills.py

cd ../frontend
$env:LIVE_LLM_JUDGE = "true"
$env:ATLAS_JUDGES_REQUIRE_SELLABLE = "false"
npm run test:e2e:atlas:docker:local-llm
```

The strict paid-readiness gate is separate and should be manual, nightly, or release-candidate only until the local and large-LLM baselines are stable:

```powershell
cd frontend
$env:LIVE_LLM_JUDGE = "true"
$env:ATLAS_JUDGES_REQUIRE_SELLABLE = "true"
npm run test:e2e:atlas:docker:local-llm
```

The test objective is not "the flow completed." The objective is:

> Atlas performed useful agency work while ForgeGraph preserved backend-owned durable state under realistic dependencies, approvals, deployment blockers, performance feedback, recovery pressure, isolation, and AI-judged paid-readiness review.

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
- Malformed AI judge output, missing department/process/overall scorecards, invalid 1-5 scores, missing evidence refs, missing improvement plans, or non-generic improvement primitives.
- Low AI judge quality only when `ATLAS_JUDGES_REQUIRE_SELLABLE=true`.

The test should not fail the default gate just because Atlas is not yet sellable. In default mode, low judge scores are a product signal. They must create actionable improvement evidence and make the next implementation target obvious.

## Paid-Readiness Target

Atlas becomes plausibly chargeable when the live evidence repeatedly shows:

- Local limited LLM baseline: every department and process average is at least `3.0`.
- Overall paid-readiness average `>= 4.2`.
- No department or process average below `3.5`.
- No critical criterion below `3`.
- No hard-fail scorecard.
- Overall decision is `sellable` or `sellable_with_minor_revisions`.
- The final deliverable is specific enough for a client to act on without hidden operator context.
- Missing connectors are represented as blockers, signals, or recommendations, never fake execution.
- Memory materially improves the follow-up run by reusing approved constraints and avoiding rejected claims/channels.
- Whiteboard state is useful to agents because dependencies, artifacts, approvals, blockers, and next actions are visible from backend-owned state.

The immediate iteration target with the local Docker LLM is modest: get every department/process scorecard to at least `3.0/5` without weakening deterministic assertions or backend schema validation. After that baseline is stable, the large-LLM target is `4.5/5` average quality with OpenAI or another stronger model.

Once those conditions are met in report-only mode, enable the strict gate:

```powershell
$env:ATLAS_JUDGES_REQUIRE_SELLABLE = "true"
cd frontend
npm run test:e2e:atlas:docker:local-llm
```

## Judge Improvement Loop

When an AI judge score is low, improve the system or Atlas output, not the judge prompt, unless the judge output is structurally invalid or contradicts the evidence.

- Any scorecard average below `3.5` becomes a roadmap item tied to the judged subject.
- Any critical criterion below `3` blocks sellability work until fixed.
- Any overall average below `4.2` means the next implementation should improve final deliverable quality, evidence clarity, or process reliability before tightening the gate.
- Every improvement must map to generic ForgeGraph primitives: `CompanySignal`, `OperationRecommendation`, `MetricSnapshot`, `StateProjection`, or `WorkArtifact`.
- If local LLM output is noisy, stabilize the evidence packet and parser first; do not loosen backend schema validation.
- If deterministic system assertions fail, fix those before interpreting judge quality scores.
- If the local LLM cannot reliably emit valid JSON, improve the repair path or split judge calls by subject; keep the persisted scorecard schema strict.

## Runtime Incident Learning Log

This section is a living log for runtime validation incidents. It is not a substitute for machine-readable Playwright evidence. Its purpose is to preserve what each failure taught us about ForgeGraph reliability and Atlas agency quality so the next test iteration improves both scopes.

Incident entries should include:

- Date and run context.
- System symptom and root cause.
- Atlas or marketing-quality implication.
- Fix applied or next action.
- Whether the incident should become a deterministic assertion, an AI judge criterion, or an operational preflight.

Record both kinds of incidents:

- System incidents: failures in Docker readiness, auth setup, backend ownership, operation lifecycle, recovery, isolation, transport, or test harness behavior.
- Atlas/marketing incidents: weak strategy, unclear content, unsafe claims, missing evidence, poor channel readiness, weak measurement logic, unusable whiteboard context, memory that does not improve the next run, or judge outputs that are too noisy to trust.

Resolution rule: deterministic system incidents should become preflights or hard assertions. Marketing-quality incidents should become judge criteria, scorecard improvement evidence, or pack/workstream improvements. Do not turn a weak marketing result into a passing test by loosening the rubric.

### 2026-06-02 Local Docker LLM Validation Pass

| ID                | Scope                 | Symptom                                                                                                                    | Root Cause                                                                                                                                                                    | Action                                                                                                                                                                                                                                                               | Next Learning Target                                                                                                                                            |
| ----------------- | --------------------- | -------------------------------------------------------------------------------------------------------------------------- | ----------------------------------------------------------------------------------------------------------------------------------------------------------------------------- | -------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- | --------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| INC-2026-06-02-01 | System/runtime        | Live Atlas spec timed out waiting for `connector-management-panel`.                                                        | Frontend Docker image was stale and did not include the completed P1 UI.                                                                                                      | Rebuilt the frontend container before continuing runtime validation.                                                                                                                                                                                                 | Add a Docker local-E2E preflight that proves the served frontend bundle contains required P1 UI markers before running the long Atlas flow.                     |
| INC-2026-06-02-02 | System/runtime        | User registration returned HTTP 429 before Atlas setup.                                                                    | Duplicate local attempts exhausted Docker's production-like `auth_register` throttle.                                                                                         | Raised Docker local-E2E auth register/login defaults while leaving production settings unchanged.                                                                                                                                                                    | Add a local validation preflight that detects throttle exhaustion or uses an isolated seeded test user path.                                                    |
| INC-2026-06-02-03 | System/runtime        | AI judge graph runs failed even though the local LLM was reachable.                                                        | Engine LLM request timeout and backend stale-run timeout were tuned for fast hosted providers, not local Docker inference.                                                    | Raised Docker local defaults for engine LLM request timeout and backend stale-run detection.                                                                                                                                                                         | Keep a separate local-LLM runtime profile so slow inference does not look like engine durable-state failure.                                                    |
| INC-2026-06-02-04 | System/test harness   | Playwright failure opened an HTML report server and kept the command alive.                                                | The local runner did not force noninteractive CI behavior.                                                                                                                    | Set `CI=true` by default in the Docker local-LLM runner.                                                                                                                                                                                                             | Ensure all required gates terminate cleanly without human interaction after pass or fail.                                                                       |
| INC-2026-06-02-05 | System/AI judging     | First judge packet was too slow and brittle for the local 8B model.                                                        | Evidence was too large and included more raw payload than the local judge needed.                                                                                             | Compacted the judge evidence packet and reduced default judge max tokens for Docker local LLM.                                                                                                                                                                       | If malformed JSON continues, split judge calls by subject while preserving strict backend scorecard schema.                                                     |
| INC-2026-06-02-06 | System/recovery       | Snapshot recovery route needed review before being trusted in the live evidence.                                           | A new ops route can accidentally become Atlas-specific if naming, payload, or persistence leaks product assumptions.                                                          | Verified `/api/ops/snapshot-recovery-drill` is generic and backend-owned; fixed rebuilt snapshot evidence to report DB source truth.                                                                                                                                 | Keep ops recovery drills generic and add invariant tests whenever recovery evidence expands.                                                                    |
| INC-2026-06-02-07 | Atlas/process quality | Local LLM judges are expected to be noisy and may score below sellability.                                                 | The immediate local target is structural judge persistence and a `3.0/5` baseline, not paid-readiness.                                                                        | Keep `ATLAS_JUDGES_REQUIRE_SELLABLE=false` in the default gate.                                                                                                                                                                                                      | Convert low department/process scores into concrete `CompanySignal` or recommendation evidence instead of weakening the judge.                                  |
| INC-2026-06-02-08 | System/AI judging     | Three live attempts reached the judge but failed on malformed panel JSON.                                                  | The local 8B model could not reliably emit thirteen strict scorecards in one response, even after repair.                                                                     | Split the E2E judge runner into one AI call per judge profile while preserving strict scorecard validation.                                                                                                                                                          | Track whether subject-level judging reaches stable `3.0/5` averages; improve evidence clarity before changing rubric thresholds.                                |
| INC-2026-06-02-09 | System/AI judging     | Subject-level judge output still failed because `overall_average` did not match criterion scores.                          | The local 8B model can provide useful qualitative scoring but is unreliable at exact arithmetic under strict JSON schema pressure.                                            | Kept backend scorecard validation strict and made the harness compute derived averages from AI-scored criteria before submitting the normalized scorecard.                                                                                                           | Preserve AI-driven judgment for quality while keeping schema math deterministic; watch for other derived fields that should be normalized rather than trusted.  |
| INC-2026-06-02-10 | System/AI judging     | Subject-level judge output included usable criteria but omitted top-level `improvement_plan`.                              | The local model treated per-criterion improvements as enough and did not always emit the aggregate improvement-plan array.                                                    | Kept every criterion improvement and evidence ref mandatory; added deterministic fallback that derives one generic `CompanySignal` improvement from the weakest criterion.                                                                                           | Treat aggregate packaging as deterministic when it is directly derived from AI-scored criteria; keep failing on invalid scores or missing criterion evidence.   |
| INC-2026-06-02-11 | System/AI judging     | A subject-level judge response omitted `rationale` or `improvement` for `strategy_research`.                               | The local model may still drift on required per-criterion fields even after subject-level splitting and repair.                                                               | Keep per-criterion rationale, improvement, and evidence refs mandatory; inspect raw output before deciding whether strict synonym normalization is justified.                                                                                                        | If raw output contains equivalent fields, normalize those fields deterministically; if not, keep this as a hard judge-output failure and improve the prompt.    |
| INC-2026-06-02-12 | System/AI judging     | A `channel_execution` aggregate `improvement_plan` used `type` and `description` instead of exact keys.                    | The local model preserved the same generic primitive and recommendation meaning, but drifted on aggregate packaging fields.                                                   | Accept `type` as `primitive` and `description` as aggregate title/rationale while keeping criterion scores, rationales, improvements, and evidence refs strict.                                                                                                      | Continue deriving or normalizing only aggregate packaging that can be read directly from valid AI-scored criteria or equivalent generic primitive output.       |
| INC-2026-06-02-13 | System/AI judging     | A `strategy_research` repair returned empty criterion `evidence_refs` arrays.                                              | The prompt required evidence refs but did not give the local model a compact list of valid backend-owned refs to copy.                                                        | Added `evidence_ref_catalog` to the judge evidence packet and told repair attempts to copy refs from it; kept empty criterion evidence refs as a hard failure.                                                                                                       | Track whether catalog-backed refs make subject-level judging stable without fabricating route, connector, or execution evidence.                                |
| INC-2026-06-02-14 | System/AI judging     | A scorecard returned `improvement_plan.steps` rather than a top-level improvement-plan array.                              | The local model preserved the aggregate plan content but wrapped it in a `steps` object.                                                                                      | Accept `improvement_plan.steps` as aggregate packaging while still validating generic primitives and deriving evidence refs from backend-owned judge subject context.                                                                                                | Keep normalizing aggregate shape only; do not normalize missing criterion evidence into passing evidence.                                                       |
| INC-2026-06-02-15 | System/AI judging     | High-scoring criteria sometimes returned `improvement: null` while retaining rationale and evidence.                       | The local model used null to mean no material gap on criteria scored `4` or `5`.                                                                                              | Convert null high-score improvements into an explicit maintenance improvement; continue failing missing improvements on scores below `4`.                                                                                                                            | Keep required low-score improvement text strict so weak Atlas/marketing output cannot pass without actionable improvement evidence.                             |
| INC-2026-06-02-16 | System/AI judging     | Aggregate improvement-plan items sometimes included `rationale` or `label` without a separate `title`.                     | The local model preserved actionable aggregate text but omitted the title wrapper field.                                                                                      | Use aggregate rationale/label as title fallback while keeping primitive validation and criterion-level evidence strict.                                                                                                                                              | Keep watching for aggregate packaging drift, but do not relax criterion scores, rationales, improvements, or evidence refs.                                     |
| INC-2026-06-02-17 | System/AI judging     | Aggregate plans sometimes used `improvement_plan.items` and `action` instead of `steps` or `description`.                  | The local model continued to preserve the aggregate plan content while varying wrapper names.                                                                                 | Accept `items` as an aggregate plan array and `action` as aggregate plan text; keep all criterion evidence and low-score improvements strict.                                                                                                                        | If aggregate wrapper drift continues, prefer deriving the aggregate plan from validated criteria rather than adding unbounded aliases.                          |
| INC-2026-06-02-18 | System/AI judging     | Aggregate `top_strengths` or `required_improvements` may be empty or object-shaped.                                        | The local model sometimes focuses on criterion details and under-specifies summary arrays.                                                                                    | Derive missing aggregate strengths and required improvements from validated criterion rationales and improvements; parse object labels/titles/descriptions when present.                                                                                             | Treat summary arrays as report packaging only; never derive missing scores, missing evidence refs, or low-score improvements.                                   |
| INC-2026-06-02-19 | Atlas/channel quality | Report-only AI-judge run passed structurally, but `channel_execution` scored `2.8/5`.                                      | The evidence packet did not make sequencing, deployment readiness, channel blockers, approval compliance, and operation IDs compact enough for the local judge.               | Keep the score; do not inflate the rubric. Add a channel-execution evidence slice with dependency transitions, readiness state, executed/blocked channels, approval, and operation lifecycle IDs.                                                                    | Rerun until channel execution reaches at least `3.0/5` locally, then improve the actual channel plan toward `3.5+` and sellability.                             |
| INC-2026-06-02-20 | System/recovery       | `snapshot_recovery` averaged `3.6/5` but was marked blocked because the judge scored "no engine durable ownership" as bad. | The local judge misread the runtime invariant: engine durable ownership is forbidden, and backend-owned recovery is the desired passing condition.                            | Clarify the snapshot recovery judge instructions and evidence packet so absence of engine durable ownership is explicitly positive; reject any improvement plan that recommends engine durable ownership.                                                            | Add a deterministic guard for invariant-hostile judge recommendations, then rerun to verify recovery scoring rewards backend-owned state.                       |
| INC-2026-06-02-21 | System/runtime        | Follow-up local-LLM rerun failed with `ECONNREFUSED 127.0.0.1:8000` after Docker's Linux engine pipe disappeared mid-run.  | `com.docker.service` was stopped and this shell could not start it; restarting Docker Desktop left `/info` returning HTTP 500.                                                | Stop interpreting this attempt as Atlas quality signal. Require Docker service/daemon recovery before rerunning the live gate.                                                                                                                                       | Add a runtime preflight and incident classifier that separates product failures from Docker daemon/backend availability loss during long local-LLM runs.        |
| INC-2026-06-02-22 | System/runtime        | `memory-grpc` exited with code 1 after Docker recovered.                                                                   | The service validates required operating model packs on startup but did not mount `/operating_model_packs` or set pack env vars like the backend services.                    | Updated `docker-compose.yml` so `memory-grpc` mounts backend code, pack files, docs, and shared venv, and sets `OPERATING_MODEL_PACKS_DIR` plus `REQUIRED_OPERATING_MODEL_PACKS`.                                                                                    | Keep all backend-like services that validate runtime packs on the same pack mount/env contract; add this to local-E2E preflight coverage.                       |
| INC-2026-06-02-23 | Atlas/AI baseline     | Report-only local LLM baseline passed with all department/process averages at least `3.0/5`.                               | Channel execution and snapshot recovery judge evidence became compact and unambiguous enough for the local model.                                                             | Treat the `3.0/5` floor as achieved for this run; keep strict sellability disabled because memory usefulness is still `3.0/5` and operation/reliability is `3.6/5`.                                                                                                  | Next quality target is every department/process `>= 3.5/5`, led by memory usefulness and operation/reliability evidence.                                        |
| INC-2026-06-02-24 | System/provider       | Managed OpenAI runtime reached the provider but could not run Atlas or media generation.                                   | The current OpenAI account/key is quota-blocked: image generation returned "Billing hard limit has been reached" and chat completions returned HTTP 429 `insufficient_quota`. | Added generic OpenAI image support to backend-owned media generation and preserved the live image attempt as a failed `MediaGenerationJob` instead of faking success. Recreated backend/engine with the real OpenAI base URL and stopped before the long Atlas flow. | Add a managed-provider preflight that probes text and media quota before the long Atlas flow; rerun OpenAI-backed Atlas only after quota/billing is restored.   |
| INC-2026-06-02-25 | System/provider       | GPT-5-family Chat Completions models rejected the engine request with unsupported `max_tokens`.                            | Newer OpenAI models exposed on the account require `max_completion_tokens` instead of `max_tokens`; `gpt-4.1-mini` worked but was not the desired newer baseline.             | Updated the generic OpenAI gateway to send `max_completion_tokens` for OpenAI GPT-5/o-series models while preserving `max_tokens` for older and OpenRouter-compatible models.                                                                                        | Keep provider compatibility in the gateway layer so graph config can stay generic; add any future OpenAI request-shape drift as gateway tests, not Atlas logic. |
| INC-2026-06-02-26 | Atlas/AI baseline     | First managed OpenAI Atlas run passed but strict sellability would fail.                                                   | `gpt-5.4-mini` judged process reliability high, but overall paid-readiness was `4.0/5` and analytics/performance was `3.4/5`, below the strict release floor.                 | Keep the run as a report-only baseline and do not loosen the rubric. Treat measurement coverage and analytics specificity as the next product improvement target.                                                                                                    | Improve multi-source metric evidence, full-funnel connector coverage, attribution realism, and insight-to-action specificity before rerunning the strict gate.  |

Open incident-follow-up checklist:

- [ ] Add a local-E2E preflight that checks Docker frontend freshness, backend health, auth throttle headroom, and local LLM model availability before the long Atlas flow.
- [ ] Add a local runtime failure classifier for backend `ECONNREFUSED` and Docker daemon loss during long local-LLM runs.
- [ ] Add a local-E2E preflight check that `memory-grpc` is healthy and using the same required pack mount/env contract as backend services.
- [ ] Add a managed-provider preflight that checks OpenAI text quota, OpenAI image-generation quota, and GPT-5-family token-limit compatibility before running the long OpenAI-backed Atlas flow.
- [ ] Add a test-harness summary that distinguishes expected negative isolation probes from unexpected stale-resource polling after retries.
- [x] Decide whether judge calls should be split by department/process/overall for local models while keeping one fixed evidence packet and one persisted evaluation per scorecard.
- [x] Decide whether scorecard arithmetic should be deterministic in the harness while scores, rationales, and improvements remain AI-judged.
- [x] Decide whether missing aggregate improvement plans may be derived from AI-written criterion improvements.
- [x] Normalize aggregate improvement-plan `type`/`description` aliases only after raw backend-owned output showed equivalent generic primitive evidence.
- [x] Add a compact backend-owned `evidence_ref_catalog` to reduce empty criterion evidence refs without weakening validation.
- [x] Normalize aggregate `improvement_plan.steps` packaging after raw output showed valid generic plan items.
- [x] Convert null high-score criterion improvements into explicit maintenance notes while preserving low-score failures.
- [x] Normalize aggregate improvement-plan title from rationale/label when the generic primitive and criterion evidence are valid.
- [x] Normalize aggregate `improvement_plan.items` and `action` aliases after raw output showed valid generic plan content.
- [x] Derive missing aggregate top strengths and required improvements from validated criterion evidence.
- [x] Add a compact `channel_execution` evidence slice covering dependency sequencing, deployment readiness, blocked connectors, approval compliance, and terminal operation IDs.
- [x] Clarify `snapshot_recovery` judge evidence so "no engine durable ownership" is a positive criterion and engine durable ownership recommendations are rejected.
- [x] Repair `memory-grpc` Docker compose config so required pack validation passes in local runtime.
- [ ] Inspect raw judge output for missing per-criterion rationale/improvement and only normalize exact equivalent fields if the evidence supports it.
- [ ] Record local judge score distributions across repeated runs and promote recurring Atlas weaknesses into the roadmap task list.

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

### P1.5 - AI Judges And Paid-Readiness Evidence

- [x] Add generic submitted Atlas rubric schema support to `/api/evaluations/run`.
- [x] Enforce exactly five scored criteria per scorecard with 1-5 scores, rationales, improvements, evidence refs, and generic improvement primitives only.
- [x] Persist each judge result as backend-owned evaluation, scorecard, finding, and improvement signal evidence.
- [x] Add pack-owned department judges for Strategy & Research, Brand & Content, Channel Execution, CRM & Lifecycle, Analytics & Performance, QA & Compliance, and Client/Approval Ops.
- [x] Add pack-owned process judges for memory usefulness, whiteboard usefulness, snapshot recovery, connector/tool honesty, and operation/reliability evidence.
- [x] Add pack-owned overall paid-readiness judge for "could we charge money for this?"
- [x] Replace the deterministic fake review-board scorecard in the live Atlas spec with live LLM judge output.
- [x] Persist seven department evaluations, five process evaluations, and one overall evaluation from the live judge panel.
- [x] Keep AI quality report-only by default, with paid-readiness failure gated by `ATLAS_JUDGES_REQUIRE_SELLABLE=true`.
- [x] Add backend-owned snapshot recovery drill evidence without making Redis, Kafka, WebSocket, engine, or client state authoritative.
- [ ] Establish a repeated local-LLM baseline showing stable scores and concrete improvement plans over multiple Atlas runs.

### P2 - Scale, Transport, And Review Depth

- [ ] Add a Kafka-enabled whiteboard transport variant while preserving backend-owned authority.
- [ ] Add load-generation coverage for workstream fan-out, dependency transitions, operation lifecycle writes, and projection lag.
- [ ] Add richer scorecards and a human-review packet for release decisions.
- [ ] Add optional real connector integrations for approved deployment channels, with sandbox receipts and honest blockers where providers are unavailable.

## Success Criteria

### Atlas Quality

- Strategy, legal/compliance, tech/martech, media, copy, analytics, traffic, content, timing, and deployment-readiness workstreams are visible in evidence with correct dependency transitions.
- The final deliverable is judged or scored against strategy coherence, compliance safety, execution readiness, client clarity, measurement readiness, and tool honesty.
- Department scorecards cover Strategy & Research, Brand & Content, Channel Execution, CRM & Lifecycle, Analytics & Performance, QA & Compliance, and Client/Approval Ops with exactly five evidence-backed criteria each.
- The overall sellability judge reports whether the output is `sellable`, `sellable_with_minor_revisions`, `needs_revision`, or `blocked`.
- A follow-up campaign proves memory usefulness by reusing prior approved constraints/learnings and avoiding at least one previously rejected claim, channel, or assumption.

### System Reliability

- Every phase, deployment, and performance action has a durable `ProductOperation` with terminal status and contract revision evidence.
- Whiteboard, phase, deployment, performance, approval, memory, and routing state can be re-read from backend APIs after frontend reload.
- Missing connectors create blockers or signals, not fake `ToolExecution` success.
- Other-client isolation returns no whiteboard, operation, approval, deployment, performance, artifact, memory, or route leakage.
- No `/api/atlas/*`, `/api/marketing/*`, or `/api/legacy/*` routes are used.
- AI judge improvements create generic backend-owned evidence such as `CompanySignal` or operation recommendation metadata, never Atlas-specific durable models.

### Runtime Integrity

- Backend remains the only durable source of truth.
- Redis, Kafka, and WebSocket state are treated as cache or transport only.
- Engine tests and runtime checks continue to reject durable ownership regressions.
- Recovery tests prove no stale resume acknowledgement or engine-memory dependency can corrupt state.
- Snapshot recovery evidence proves cache snapshots can be corrupted and rebuilt from DB-owned whiteboard state.

### Release Gate

- Existing targeted backend tests pass.
- Architecture invariant tests pass.
- Frontend typecheck passes.
- `npm run test:e2e:atlas:docker:local-llm` passes with `ATLAS_JUDGES_REQUIRE_SELLABLE=false`.
- AI judges run by default unless `LIVE_LLM_JUDGE=false`.
- The default gate persists and reports low AI quality instead of failing on sellability.
- The optional strict gate with `ATLAS_JUDGES_REQUIRE_SELLABLE=true` requires overall average at least 4.2, no department/process average below 3.5, no critical criterion below 3, no hard fail, and overall decision `sellable` or `sellable_with_minor_revisions`.
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
- Snapshot recovery drill evidence, including cache corruption/rebuild result and backend-owned source-of-truth markers.
- AI judge input packet, raw judge output, normalized scorecards, persisted evaluation IDs, score summaries, decisions, findings, and improvement signal IDs.
- Tenant isolation checks for whiteboards, operations, approvals, deployments, performance records, artifacts, memory, and routes.
- Helper-assisted steps with the reason each helper was still required.

## Assumptions

- Keep Atlas on generic ForgeGraph primitives; do not introduce `/api/atlas/*` or marketing-specific core durable models.
- Keep `digital_marketing_pro.v1` as the current Atlas/DMP pack identifier.
- Keep the existing live Atlas spec as the primary acceptance target rather than creating a parallel production spec immediately.
- Treat docs cleanup as a separate PR from Atlas/system reliability work.
- Keep helper-assisted steps allowed only where the product UI does not exist yet, and require every helper-assisted step to be listed in the evidence artifact.
- Keep `/api/ops/snapshot-recovery-drill` generic and ops-scoped: it may accept generic `whiteboard_id` and optional `run_id`, but must not encode Atlas, marketing, or pack-specific durable ownership.
