# P3: Stability, Governance, and Launch QA (Weeks 8-9)

## Objective
Harden V2 for production launch with strong reliability, observability, security controls, and measurable QA gates.

## Prerequisites
- P0-P2 feature scope complete.
- Core integration connectors available in staging.

---

## Task List

### P3-T01: Scalability for Long-Running Graphs
Effort: Medium

Why critical:
Loops and multi-step agent workflows increase runtime and resource pressure.

Implementation steps:
1. Profile scheduler bottlenecks on long loops and multi-agent branches.
2. Optimize worker pool and queue behavior for sustained throughput.
3. Add per-tenant concurrency and run-time guardrails.
4. Add stress dashboard for queue depth, run latency, and failure rate.

Recommended patterns / best practices:
- Backpressure instead of unbounded queue growth.
- Cap loop iterations and payload sizes to avoid runaway runs.

Testing strategy:
- Load test: 100+ sequential workflows with stable memory profile.
- Concurrency test: expected parallel run volume without timeouts.

Success criteria / Definition of Done:
- [ ] No crashes/timeouts on expected long-running workloads.
- [ ] Resource usage remains stable under sustained execution.
- [ ] Queue and worker metrics are visible in dashboards.

Dependencies:
- Queue and worker execution path.

Risks:
- Loop-heavy workloads causing memory pressure.

---

### P3-T02: Error Handling + `onError` Flow Support
Effort: Medium

Why critical:
Failure isolation is required so one node error does not collapse whole workflows.

Implementation steps:
1. Add per-node try/catch behavior and structured error payloads.
2. Implement `onError` routing with retry/skip/fallback options.
3. Expose retry attempts and final failure reason in run UI.
4. Add policy controls for max retries and backoff strategy.

Recommended patterns / best practices:
- Classify retryable vs non-retryable errors explicitly.
- Keep error payload schema stable for UI/analytics consumers.

Testing strategy:
- Unit: retry/skip/fallback decision matrix.
- Integration: failing node routes to onError branch and run continues.

Success criteria / Definition of Done:
- [ ] Failing node can be retried or skipped without crashing whole graph.
- [ ] `onError` branches execute as configured.
- [ ] Error details are inspectable in run history.

Dependencies:
- Branching execution semantics from P0.

Risks:
- Incorrect retry classification causing noisy loops.

---

### P3-T03: Logging, Auditing, and Run Histories
Effort: Small

Why critical:
Debugging and governance require complete execution visibility.

Implementation steps:
1. Standardize event and log schema for runs and node executions.
2. Ensure run history captures author, timestamps, graph version, and node-level outcomes.
3. Add audit views and filtering for operational diagnosis.
4. Add retention policy alignment for logs and run artifacts.

Recommended patterns / best practices:
- Correlate records by run_id and tenant_id consistently.
- Separate user-visible logs from internal debug logs.

Testing strategy:
- Integration: run lifecycle produces complete history records.
- E2E: admin can inspect run and audit trail for a failed workflow.

Success criteria / Definition of Done:
- [ ] Each run is recorded and inspectable for debugging.
- [ ] Audit records include author, timestamp, and version context.
- [ ] Filters can locate failed runs quickly.

Dependencies:
- Existing run event persistence.

Risks:
- High-volume logs increasing storage costs.

---

### P3-T04: Credential Safety Hardening
Effort: Small

Why critical:
Credential leakage is a launch-blocking security issue.

Implementation steps:
1. Verify encryption-at-rest for API keys/tokens and OAuth refresh tokens.
2. Enforce secret redaction in logs, traces, and API responses.
3. Add credential rotation and revocation workflows.
4. Add security tests for common exposure paths.

Recommended patterns / best practices:
- Never expose decrypted secrets outside the execution boundary.
- Centralized redaction utility for all log/event emitters.

Testing strategy:
- Security tests: confirm secrets are absent from logs and responses.
- Integration: rotated credential invalidates prior tokens.

Success criteria / Definition of Done:
- [ ] Credentials are stored securely and never returned in plaintext.
- [ ] Logs and run payloads do not leak sensitive values.
- [ ] Rotation/revocation flows are operational.

Dependencies:
- Credential model and encryption service.

Risks:
- Legacy paths bypassing redaction filters.

---

### P3-T05: Provider/API Rate Limit Resilience
Effort: Small

Why critical:
LLM and integration APIs frequently enforce rate limits.

Implementation steps:
1. Add standardized retry/backoff behavior for 429 and transient 5xx errors.
2. Respect provider `Retry-After` where available.
3. Surface rate-limit diagnostics in node error output.
4. Add tenant-level throttles to reduce provider burst failures.

Recommended patterns / best practices:
- Exponential backoff with jitter and hard retry caps.
- Distinct handling for quota exhausted vs transient throttling.

Testing strategy:
- Unit: backoff and retry policy behavior.
- Integration: simulated 429/5xx recovers with expected policy.

Success criteria / Definition of Done:
- [ ] LLM/API calls handle rate limits and transient errors robustly.
- [ ] User sees clear action when quota is exhausted.
- [ ] Retries are bounded and observable.

Dependencies:
- Unified error handling path from P3-T02.

Risks:
- Over-retrying can worsen provider throttling.

---

### P3-T06: Launch QA Gate (Functional, UX, Performance, Security)
Effort: Medium

Why critical:
Launch requires an explicit go/no-go quality gate.

Implementation steps:
1. Convert QA checklist into executable test matrix (unit, integration, E2E, load, security).
2. Add must-pass launch scenarios:
   - Linear + branched graph execution.
   - Prompt node response with valid credential.
   - Tool + memory GET/SET flow.
   - Telegram end-to-end and Gmail/Calendar smoke tests.
3. Add UX validation:
   - Canvas interactions, wizard completion, node form validation.
   - Keyboard shortcuts and undo/redo checks.
4. Publish launch report with pass/fail status and unresolved risks.

Recommended patterns / best practices:
- Tag launch-blocking tests and run them in dedicated CI stage.
- Record test evidence artifacts for release signoff.

Testing strategy:
- Full QA suite in staging using production-like credentials.
- Regression sweep after final release candidate branch cut.

Success criteria / Definition of Done:
- [ ] Functional tests pass for graph engine, nodes, memory, and integrations.
- [ ] UX checks pass for canvas, wizard, dialogs, and shortcuts.
- [ ] Performance tests show stable resource usage and acceptable latency.
- [ ] Security checks confirm encrypted credentials and no secret leakage.

Dependencies:
- Completion of P0-P3 feature work.

Risks:
- External provider instability during final validation window.
