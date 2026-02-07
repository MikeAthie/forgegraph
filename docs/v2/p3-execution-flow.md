# P3 Execution Flow (Task-by-Task)

## Goal
Execute P3 with strict launch hardening discipline: implement one stability/governance slice, validate with automated tests, then mark complete.

## Completion Rules
1. Implement one P3 task slice at a time.
2. Add or extend automated tests for every acceptance behavior touched.
3. Run targeted tests first, then broader regression checks.
4. Mark a task complete only after tests pass (or record explicit blockers).
5. Log implementation notes, validation commands, and residual risks.

## Task Tracker

### P3-T01: Scalability for Long-Running Graphs
Status: `completed`

Sub-checks:
- [x] Profile scheduler bottlenecks for loops and branch-heavy runs.
- [x] Harden worker/queue behavior for sustained throughput.
- [x] Add per-tenant concurrency and run-time guardrails.
- [x] Add stress dashboard for queue depth, latency, and failure rate.

Validation Gate:
- [x] Load test for 100+ sequential workflows.
- [x] Concurrency test for expected parallel run volume.

### P3-T02: Error Handling + `onError` Flow Support
Status: `completed`

Sub-checks:
- [x] Added structured per-node error payloads (retryability, attempt, policy, error type, action).
- [x] Implemented `on_error` flow controls in scheduler with `skip` and `fallback` routing.
- [x] Added `on_error` retry policy override support (`max_attempts`, `backoff_ms`, `backoff_strategy`).
- [x] Propagated final retry attempt metadata in node completion/failure events.
- [x] Persisted structured `node_failed` payloads into backend `NodeRun.error_json`.

Validation Gate:
- [x] Engine unit tests for skip/fallback/routing-failure/retry-override behavior.
- [x] Backend integration test for structured `node_failed` payload persistence.

### P3-T03: Logging, Auditing, and Run Histories
Status: `completed`

Sub-checks:
- [x] Standardize run/node event and log schemas.
- [x] Ensure run history captures author/timestamp/version/node outcomes.
- [x] Add operational audit filters.
- [x] Align log/run-artifact retention policy behavior.

Validation Gate:
- [x] Integration tests for complete run lifecycle history.
- [x] E2E audit inspection for failed workflow diagnosis.

### P3-T04: Credential Safety Hardening
Status: `completed`

Sub-checks:
- [x] Verify encryption-at-rest coverage for keys/tokens.
- [x] Enforce centralized secret redaction in logs/events/responses.
- [x] Add credential rotation/revocation workflows.
- [x] Add security tests for leakage paths.

Validation Gate:
- [x] Security tests for log/response secret absence.
- [x] Integration test for credential rotation invalidation.

### P3-T05: Provider/API Rate Limit Resilience
Status: `completed`

Sub-checks:
- [x] Standardized retry/backoff handling for 429 + transient 5xx across HTTP/tool/LLM gateway paths.
- [x] Added `Retry-After` header handling and retry-delay propagation.
- [x] Surfaced structured rate-limit diagnostics (`retry_code`, `retry_after_ms`, details) in node failure output.
- [x] Enforced quota-exhausted vs transient throttling distinction to avoid noisy over-retries.

Validation Gate:
- [x] Engine unit tests for backoff/retry policy behavior.
- [x] Existing run-event integration coverage confirms structured node-failure payload persistence.

### P3-T06: Launch QA Gate (Functional, UX, Performance, Security)
Status: `completed`

Sub-checks:
- [x] Convert launch checklist into executable matrix.
- [x] Add launch-blocking functional/integration scenarios.
- [x] Add UX validation for canvas/wizard/forms/shortcuts.
- [x] Publish launch pass/fail report with residual risks.

Validation Gate:
- [x] Staging full-suite run with production-like credentials.
- [x] Regression sweep on final release candidate branch.

## Execution Log
- 2026-02-06: P3 tracker initialized; started with P3-T02.
- 2026-02-06: Completed P3-T02.
  - Added scheduler `on_error` policy support:
    - `skip` action to continue run after node failure.
    - `fallback` action to route only configured outgoing fallback nodes.
    - `retry` action to override retry policy directly from node config.
  - Added structured node failure payload schema in engine events and repository updates.
  - Added final attempt propagation on `node_completed` and `node_failed` events.
  - Updated backend engine-event ingestion to persist structured failure payloads in `NodeRun.error_json`.
  - Validation:
    - `go test ./application/usecase -run "OnError|Retry|NonRetryable" -count=1`
    - `go test ./application/usecase -run "Scheduler" -count=1`
    - `pytest backend/tests/integration/adapters/test_run_api.py -k "structured_error_payload" -q`
    - `pytest backend/tests/integration/adapters/test_run_api.py -k "EngineRunEvents" -q`
- 2026-02-06: Completed P3-T05.
  - Added structured retry metadata support in domain retryable errors (`code`, `retry_after_ms`, diagnostics map).
  - Scheduler retry loop now respects retry-after delays from retryable errors and propagates retry diagnostics into node error payloads.
  - Hardened HTTP executor:
    - 429 transient throttling is retryable with retry-after diagnostics.
    - Quota exhaustion is surfaced as non-retryable with clear remediation text.
    - 5xx responses are standardized as retryable transient failures.
  - Hardened Tool HTTP execution path with the same 429/5xx + retry-after + quota distinction behavior.
  - Hardened OpenAI and Anthropic gateway adapters to emit retryable metadata for transient provider failures and preserve quota-exhaustion distinction.
  - Updated prompt executor to preserve retryable diagnostics from provider clients (instead of flattening all errors).
  - Validation:
    - `go test ./adapter/executor -run "HTTPExecutor|ToolExecutor|PromptExecutor" -count=1`
    - `go test ./application/usecase -run "RetryAfter|OnError|Retry|NonRetryable" -count=1`
    - `go test ./...`
    - `pytest backend/tests/integration/adapters/test_run_api.py -q`
- 2026-02-07: Completed P3-T01, P3-T03, P3-T04, and P3-T06.
  - Added tenant active-run and input-size guardrails for run start/invoke/replay.
  - Expanded metrics summary with stress dashboard fields: queue depth, oldest pending age, top tenants, failure rate, active-run counts, and guardrail settings.
  - Expanded run history outputs with owner context, node outcome summary, failed-node filtering, and redacted run/node payloads.
  - Expanded audit filters with `resource_id`, `run_id`, `action_prefix`, date-range filtering, and text search.
  - Enforced centralized redaction utility across audit persistence, run event ingestion, run detail responses, and retention exports.
  - Added credential rotation/revocation endpoints and revocation checks in engine credential resolution + integration credential usage paths.
  - Added launch QA CI stage and report artifact generation:
    - `.github/workflows/ci.yml` jobs: `launch_qa_backend`, `launch_qa_engine`, `launch_qa_frontend`, `launch_qa_report`.
- 2026-02-07: Closed final V2 readiness doc gap.
  - Added launch quickstart guide:
    - `docs/user-guide/v2-launch-quickstart.md`
  - Added template library guide:
    - `docs/user-guide/template-library.md`
  - Updated onboarding docs links to point users directly to template library + credential setup guidance.
  - Marked final V2 readiness checklist item complete in:
    - `docs/v2/forgegraph-v2-implementation-plan.md`
