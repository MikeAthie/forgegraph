# Forgegraph Investor-Ready MVP Implementation Plan (P0-P2)

## Executive Summary
This plan targets an investor-ready MVP in a 4-6 week sprint with 2-3 engineers while retaining the existing stack (Go engine, Django/DRF + Channels, Next.js, gRPC, Docker). The demo flow must complete in 10 minutes:
1. Onboarding -> template selection -> credential entry -> live run.
2. Real-time updates (no polling).
3. Secure engine -> backend callbacks (S2S auth).
4. Multi-model switch.
5. Cost dashboard + budget alert.
6. Human gate pause/resume + checkpoint replay.

## Timeline (Proposed)
- Weeks 1-2: P0 (demo-critical path).
- Weeks 3-4: P1 (reliability + replay UX).
- Weeks 5-6: P2 (productization + controls).

## P0: Demo-Critical Path (Weeks 1-2)

### P0-1. Secure S2S Callbacks + Event Normalization
Why it is critical for MVP/pitch: Real-time observability is the "alive product" moment. Without S2S auth, the engine cannot post events securely, blocking live updates in the demo.

Current relevant code state:
- `backend/adapters/api/runs/views.py:965` `RunEventsView` requires `IsAuthenticated` and owner checks, blocking engine callbacks.
- `backend/adapters/api/runs/serializers.py:137` only accepts `run.updated` and `node_run.updated`.
- `engine/application/port/event_emitter.go:11` emits `run_started`, `node_started`, etc. (mismatch).
- `engine/adapter/gateway/http_event_emitter.go:16` exists but not wired.
- `engine/main.go:320` uses `NoOpEventEmitter`.

Concrete implementation steps (minimum viable with scalable path):
1. Define a S2S auth scheme and event contract (HMAC signed headers + event_id + timestamp). Extend `engine/proto/engine.proto` `StartRunRequest` to carry `callback_auth` or `callback_token` alongside `callback_url`.
2. Add a dedicated engine callback endpoint (e.g. `/api/engine/runs/{run_id}/events`) that validates signatures and bypasses user auth.
3. Implement event mapping: convert engine `ExecutionEvent` into `run.updated` and `node_run.updated` payloads that align with `RunEventSerializer`.
4. Add idempotency by storing `event_id` and skipping duplicates (unique index on `run_id + event_id`).
5. Broadcast mapped events to WS/SSE groups via `broadcast_run_updated` and `broadcast_node_run_updated`.

Recommended patterns/best practices:
- HMAC with `X-Forgegraph-Timestamp` and constant-time comparison.
- Allow 5-10 minute clock skew to avoid false rejections.
- Version event payloads to allow future schema changes.

Definition of Done / success criteria:
- [ ] Engine can POST signed events without user credentials.
- [ ] Backend rejects tampered or expired signatures with 401.
- [ ] Run and node updates appear in real-time with no polling.
- [ ] Duplicate events do not create duplicate RunEvent rows.

Risks & dependencies:
- gRPC proto change requires regenerating stubs in backend and engine.
- Clock skew between services can cause false negatives.

Suggested tests (unit + integration):
- Unit: HMAC verification with valid/invalid signatures.
- Integration: POST engine event -> Run/NodeRun update persists + WS broadcast.
- E2E: run stream updates UI without polling fallback.

### P0-2. Wire Engine HTTP Event Emitter (Per-Run)
Why it is critical for MVP/pitch: Without engine events, the product appears unresponsive and non-operational.

Current relevant code state:
- `engine/main.go:320` initializes `NoOpEventEmitter`.
- `engine/adapter/gateway/http_event_emitter.go:16` provides an HTTP emitter with retries and buffering.
- `engine/application/usecase/scheduler.go:565` emits events through the scheduler.

Concrete implementation steps (minimum viable with scalable path):
1. Replace `NoOpEventEmitter` with an HTTP emitter instantiated per run using the `callback_url` from `StartRunRequest`.
2. Include `event_id` and `timestamp` in all emitted events.
3. Propagate S2S auth headers on every HTTP event.
4. Ensure `Flush` is called on run completion or cancellation to avoid missing tail events.

Recommended patterns/best practices:
- Bounded buffer with backpressure and drop metrics.
- Exponential backoff + jitter for retries.

Definition of Done / success criteria:
- [ ] Engine emits run and node events for a full run.
- [ ] Backend receives all events for a 50-node run without loss.

Risks & dependencies:
- Requires P0-1 event contract and auth scheme.

Suggested tests (unit + integration):
- Integration: local HTTP server captures and validates emitted events.
- Engine test: verify event order and retry behavior.

### P0-3. Multi-Tenant Credentials + Multi-Model Provider Gateway
Why it is critical for MVP/pitch: Investors expect multi-provider LLM support and secure, per-tenant credentials storage.

Current relevant code state:
- `backend/infrastructure/orm/models.py:666` defines `APIKey` model with encrypted storage.
- `backend/infrastructure/crypto/encryption.py:101` provides encryption helpers.
- `engine/adapter/gateway/openai_client.go:61` reads `OPENAI_API_KEY` from env (single-tenant).
- `backend/domain/value_objects/node_schemas.py:17` only has `model` field for prompt nodes.

Concrete implementation steps (minimum viable with scalable path):
1. Create API endpoints for CRUD on `APIKey` (list/create/delete) with masked display.
2. Extend prompt node config schema to include `provider` and `credential_id`.
3. Add engine LLM gateway that resolves credentials on-demand via S2S call to backend.
4. Implement at least OpenAI + Anthropic clients and allow switching per node.
5. Update frontend node forms to select provider, model, and credential.

Recommended patterns/best practices:
- Never return decrypted keys to frontend.
- Cache decrypted keys in engine memory per run with short TTL.
- Allowlist providers/models in backend to prevent unsafe configs.

Definition of Done / success criteria:
- [ ] User can add credentials for OpenAI and Anthropic.
- [ ] Same template can switch providers without code changes.
- [ ] Engine runs with correct provider using per-tenant key.

Risks & dependencies:
- Provider API differences for usage metrics and error handling.
- Requires S2S credential resolution endpoint.

Suggested tests (unit + integration):
- API tests for credential CRUD.
- Engine unit tests for provider routing.
- Integration run with OpenAI + Anthropic.

### P0-4. LLM Cost Tracking + Budgets + Alerts
Why it is critical for MVP/pitch: Unit economics and cost control are core to investor diligence.

Current relevant code state:
- `engine/adapter/summarizer/cost_tracker.go:20` tracks only summarization costs.
- `engine/adapter/executor/prompt_executor.go:226` captures usage in output but does not persist it.
- `backend/adapters/api/analytics/memory_analytics.py:72` and `frontend/pages/analytics/memory.tsx:110` show only memory/summarization costs.

Concrete implementation steps (minimum viable with scalable path):
1. Add `llm_usage` table: run_id, node_id, provider, model, prompt_tokens, completion_tokens, total_tokens, cost_usd, timestamp.
2. Extend engine to attach usage metrics to events for prompt nodes.
3. In backend event ingestion, persist usage rows and compute costs using a provider pricing table.
4. Add `tenant_budget` table with thresholds (warn at 80%, block at 100%).
5. Build budget alert endpoint and UI banner in analytics dashboard.

Recommended patterns/best practices:
- Immutable usage ledger with idempotency guard.
- Pricing table versioning and explicit model mapping.

Definition of Done / success criteria:
- [ ] LLM usage series displayed in dashboard.
- [ ] Budget alert triggers at configured threshold.
- [ ] Over-budget runs return a clear error.

Risks & dependencies:
- Usage metrics vary by provider.
- Pricing updates must be maintained.

Suggested tests (unit + integration):
- Cost calculation tests for each provider/model.
- Integration test: run -> usage row created -> dashboard reflects totals.

### P0-5. Onboarding Templates -> Credential -> Live Run
Why it is critical for MVP/pitch: Investors need a fast, guided "time-to-value" experience.

Current relevant code state:
- Demo graphs exist in `backend/infrastructure/orm/management/commands/seed_phase7_demos.py:351` but not in UI templates.
- Approval UI exists in `frontend/pages/runs/[runId].tsx:892`.

Concrete implementation steps (minimum viable with scalable path):
1. Create `Template` model (or template metadata in DB) with graph JSON + display metadata.
2. Expose templates API and create-from-template endpoint.
3. Add onboarding wizard in frontend: template -> credential prompt -> run.
4. Seed 2-3 templates, including one human-gate flow.

Recommended patterns/best practices:
- Templates are immutable; "create from template" clones into user space.
- Preflight validation for missing credentials before run start.

Definition of Done / success criteria:
- [ ] New user completes onboarding and starts a run within 3 minutes.
- [ ] Template run appears live with streaming updates.

Risks & dependencies:
- Requires credentials UI and multi-provider support.

Suggested tests (unit + integration):
- API tests for template listing and clone.
- E2E onboarding flow.

### P0-6. Control Plane vs Execution Plane Contract (Architecture Doc)
Why it is critical for MVP/pitch: Investors will ask who owns run state, what happens on partial failure, and whether the engine can run headless. This contract builds trust.

Current relevant code state:
- No explicit architecture doc defining control plane vs execution plane responsibilities.

Concrete implementation steps (minimum viable with scalable path):
1. Add `docs/architecture/control-plane-vs-execution-plane.md`.
2. Document ownership of run lifecycle and source of truth.
3. Define failure semantics (backend down, engine down, WS/SSE down).
4. Define delivery guarantees and replay ownership.
5. Call out non-goals for MVP.

Recommended patterns/best practices:
- Keep the contract stable and referenced in onboarding and run docs.
- Prefer explicit, testable statements over vague promises.

Definition of Done / success criteria:
- [ ] Doc answers: "If the backend is down for 10 minutes, what happens?"
- [ ] Doc states whether engine can run headless and with what limitations.
- [ ] Doc states source of truth for run state and replay ownership.

Risks & dependencies:
- None (doc-only).

Suggested tests (unit + integration):
- N/A (documentation).

### P0-7. Tenant Isolation Enforcement (Engine -> Backend -> Analytics)
Why it is critical for MVP/pitch: Multi-tenancy must be enforced end-to-end, not assumed. This is a top investor diligence item.

Current relevant code state:
- Tenant ID is derived in control plane (`backend/adapters/api/runs/views.py:76`).
- StartRun includes tenant_id (`engine/proto/engine.proto:66`), but events and usage do not enforce it explicitly.

Concrete implementation steps (minimum viable with scalable path):
1. Include tenant_id in every engine event payload.
2. Persist tenant_id on LLM usage rows and audit logs.
3. Enforce tenant ownership during event ingestion before any writes.
4. Validate that run_id belongs to tenant_id in control plane.

Recommended patterns/best practices:
- Treat tenant_id as mandatory for all cross-service payloads.
- Reject mismatched tenant_id immediately with 403/401.

Definition of Done / success criteria:
- [ ] tenant_id flows through engine events, LLM usage, and audit logs.
- [ ] Event ingestion rejects mismatched tenant_id.

Risks & dependencies:
- Requires P0-1 event contract and P0-2 ingestion changes.

Suggested tests (unit + integration):
- Unit: ingestion rejects mismatched tenant_id.
- Integration: tenant A cannot post events for tenant B run_id.

## P1: Reliability + Replay UX (Weeks 3-4)

### P1-1. Event Delivery Reliability + Idempotency
Why it is critical for MVP/pitch: Ensures accurate, stable demos under retries and network failures.

Current relevant code state:
- Run events are persisted without idempotency in `backend/adapters/api/runs/views.py:1075`.
- HTTP emitter can drop events when buffer is full in `engine/adapter/gateway/http_event_emitter.go:117`.

Concrete implementation steps (minimum viable with scalable path):
1. Add unique index on `run_id + event_id` and short-circuit duplicates.
2. Add delivery metrics and dead-letter logging on engine emitter failures.
3. Optional Redis buffer for undelivered events if required for stability.

Recommended patterns/best practices:
- At-least-once delivery with idempotent storage.
- Explicit error classification for retry vs drop.

Definition of Done / success criteria:
- [ ] Duplicate events do not create duplicate rows.
- [ ] 1k-event run delivers all events without gaps.

Risks & dependencies:
- Requires event_id from P0.

Suggested tests (unit + integration):
- Unit test idempotent insert.
- Integration test with forced retries.

### P1-2. WS/SSE Stream Resilience
Why it is critical for MVP/pitch: Prevents fallback to polling and maintains a "live" feel.

Current relevant code state:
- Frontend falls back to polling in `frontend/pages/runs/[runId].tsx:624`.
- SSE supports `since` in `backend/adapters/api/runs/views.py:1236`.

Concrete implementation steps (minimum viable with scalable path):
1. Add WS/SSE reconnect with exponential backoff.
2. Track `last_event_id` or `since` timestamp to resume from last event.
3. Add heartbeat + server "connected" event for UI status.

Recommended patterns/best practices:
- Resume from last event on reconnect.
- Keep reconnect limits bounded.

Definition of Done / success criteria:
- [ ] WS/SSE reconnection resumes without missing events.
- [ ] Polling fallback is not triggered in normal runs.

Risks & dependencies:
- Long-running runs require token refresh handling.

Suggested tests (unit + integration):
- E2E test simulating WS drop and recovery.

### P1-3. Checkpoint Replay UX
Why it is critical for MVP/pitch: Demonstrates durable execution and safe replay (LangGraph-style).

Current relevant code state:
- Checkpoints exist in `backend/infrastructure/orm/models.py:525`.
- Engine loads checkpoints in `engine/application/usecase/scheduler.go:216`.
- Pause/resume state is saved on human gate in `engine/application/usecase/scheduler.go:575`.

Concrete implementation steps (minimum viable with scalable path):
1. Expose endpoint to replay from last checkpoint or specific node.
2. Add UI controls on run detail page to trigger replay.
3. Persist replay metadata for auditability.

Recommended patterns/best practices:
- Explicit replay confirmation to avoid unintended side effects.
- Keep original run history immutable; create replay run or append event stream.

Definition of Done / success criteria:
- [ ] User can replay from checkpoint and observe updated output.
- [ ] Replay action is logged and auditable.

Risks & dependencies:
- Side-effect duplication for external calls.

Suggested tests (unit + integration):
- Integration test replay endpoint -> new run state.
- UI e2e for replay action.

## P2: Productization + Controls (Weeks 5-6)

### P2-1. Usage Export + Quotas
Why it is critical for MVP/pitch: Monetization readiness and enterprise readiness.

Current relevant code state:
- Usage analytics currently only covers summarization and memory in `backend/adapters/api/analytics/memory_analytics.py:72`.

Concrete implementation steps (minimum viable with scalable path):
1. Add usage export endpoints (CSV/JSON) for LLM usage.
2. Add per-tenant quota enforcement at run start.
3. Add UI toggle for quota thresholds.

Recommended patterns/best practices:
- Immutable usage ledger.
- Clear over-quota error messaging.

Definition of Done / success criteria:
- [ ] Admin can export usage for any tenant.
- [ ] Runs are blocked when quota exceeded.

Risks & dependencies:
- Business pricing definitions required.

Suggested tests (unit + integration):
- Quota enforcement tests.
- Export validation tests.

### P2-2. Audit Logs
Why it is critical for MVP/pitch: Compliance and security posture for investors.

Current relevant code state:
- No centralized audit log model; approvals exist in `backend/infrastructure/orm/models.py:622`.

Concrete implementation steps (minimum viable with scalable path):
1. Add `audit_log` table with actor, action, resource, timestamp, metadata.
2. Log credential changes, run starts, approval decisions.
3. Add admin API and UI view.

Recommended patterns/best practices:
- Write-once, append-only logs.
- Redact sensitive values.

Definition of Done / success criteria:
- [ ] Key actions appear in audit log within 1 second.

Risks & dependencies:
- Storage growth and retention policy.

Suggested tests (unit + integration):
- Audit log creation tests.
- Access control tests for audit log endpoints.

### P2-3. Guardrails + Egress Controls
Why it is critical for MVP/pitch: Risk management and security.

Current relevant code state:
- HTTP nodes can call any URL (`engine/adapter/executor/http_executor.go:19`).
- No model allowlist or egress policy.

Concrete implementation steps (minimum viable with scalable path):
1. Add domain allowlist/denylist for HTTP executor.
2. Add model allowlist per tenant.
3. Expose policy configuration in admin settings.

Recommended patterns/best practices:
- Default-deny in restricted mode.
- Explicit policy violation errors surfaced in UI.

Definition of Done / success criteria:
- [ ] Disallowed HTTP requests fail with a clear policy error.

Risks & dependencies:
- Customer expectations and policy management UX.

Suggested tests (unit + integration):
- Policy enforcement tests.
- Integration run with blocked HTTP node.

## Final MVP Readiness Checklist

Demo:
- [ ] New user -> template -> credential -> run in <3 minutes.
- [ ] No polling fallback during demo.
- [ ] Human gate pauses and resumes live.
- [ ] Replay creates new run history.
- [ ] Budget alert visibly triggers.

Architecture:
- [ ] Engine callbacks are signed and idempotent.
- [ ] Engine can retry safely.
- [ ] Backend is source of truth for state.
- [ ] tenant_id flows end-to-end.

Product:
- [ ] Provider switch per node works.
- [ ] Credentials never leak.
- [ ] Costs are visible and consistent.
- [ ] One killer template tells the story.

