# P0: Demo-Critical Tasks (Weeks 1-2)

## Objective
Deliver a 10-minute investor demo with secure engine callbacks, real-time updates, multi-model runs, cost visibility, and a guided onboarding flow.

## Prerequisites
- Engine gRPC connectivity from Django control plane.
- Redis configured for Channels in docker-compose.
- Next.js app can reach backend API and WS/SSE endpoints.
- ENCRYPTION_KEY configured for APIKey encryption.

---

## Task List

### P0-T01: S2S Auth + Engine Event Contract
Effort: Large

Why critical:
Secure engine callbacks are required to make real-time updates work without user JWTs.

Current code references:
- `backend/adapters/api/runs/views.py:965` RunEventsView requires user auth.
- `backend/adapters/api/runs/serializers.py:137` accepts only `run.updated`, `node_run.updated`.
- `engine/application/port/event_emitter.go:11` emits `run_started`, `node_started`, etc.
- `engine/proto/engine.proto:49` StartRunRequest includes `callback_url` only.

Implementation steps:
1. Define a signed callback protocol:
   - Headers: `X-Forgegraph-Timestamp`, `X-Forgegraph-Signature`.
   - Payload includes `event_id`, `type`, `run_id`, `timestamp_ms`, optional node fields.
2. Add `ENGINE_CALLBACK_SECRET` and `ENGINE_CALLBACK_MAX_SKEW_SECONDS` env config in backend and engine.
3. Implement signing in engine emitter (HMAC SHA-256 over `timestamp.body`).
4. Implement verification helper in backend for later ingestion endpoint.
5. Document the contract in `docs/mvp/forgegraph-mvp-implementation-plan.md`.

Recommended patterns / best practices:
- HMAC SHA-256 signatures with constant-time comparison.
- 5-10 minute clock skew tolerance.
- Explicit event version field for future schema changes.

Testing strategy:
- Unit: signature validation success/failure and skew handling.
- Unit: event payload schema validation.
- Integration: gRPC StartRun includes callback token end-to-end.

Success criteria / Definition of Done:
- [ ] Engine can generate valid signed headers per event.
- [ ] Backend rejects invalid signatures and stale timestamps.
- [ ] Event payload includes stable `event_id` and `timestamp_ms`.

Dependencies:
- None.

Risks:
- Clock skew causing false rejects.
- Backward compatibility with existing local dev flows.

---

### P0-T02: Backend Engine Events Endpoint + Normalization
Effort: Large

Why critical:
Engine cannot post to user-auth endpoints; without normalization, frontend cannot render run state.

Current code references:
- `backend/adapters/api/runs/views.py:965` RunEventsView requires user auth.
- `backend/adapters/api/runs/views.py:1087` expects `node_run.updated` payloads.
- `backend/adapters/ws/runs/broadcast.py:32` broadcasts normalized events.

Implementation steps:
1. Add a new engine-only endpoint, e.g. `/api/engine/runs/{run_id}/events`.
2. Validate S2S signature before any processing.
3. Map engine events to normalized events:
   - `run_started` -> `run.updated` (status=running, started_at)
   - `run_completed` -> `run.updated` (status=succeeded, ended_at, output_json)
   - `run_failed` -> `run.updated` (status=failed, error_message)
   - `node_started` -> `node_run.updated` (status=running, started_at)
   - `node_completed` -> `node_run.updated` (status=succeeded, ended_at, output_json)
   - `node_failed` -> `node_run.updated` (status=failed, error_json)
   - `run_paused` -> `run.updated` (status=paused, pause_payload)
4. Enforce idempotency on `(run_id, event_id)`.
5. Persist `RunEvent` rows and broadcast to WS/SSE groups.

Recommended patterns / best practices:
- Idempotent writes keyed by `event_id`.
- Normalize timestamps to UTC ISO in backend.
- Keep raw engine payload for debugging in `RunEvent.payload`.

Testing strategy:
- Unit: each event mapping into expected model updates.
- Integration: POST engine event -> Run/NodeRun updates + WS broadcast.
- E2E: run detail page shows updates without polling fallback.

Success criteria / Definition of Done:
- [ ] All engine event types map cleanly to normalized events.
- [ ] Duplicate events do not create duplicate records.
- [ ] WS/SSE updates appear within 1 second of event POST.

Dependencies:
- P0-T01.

Risks:
- Mapping mistakes causing incorrect run state transitions.
- Run ownership checks must not block engine callbacks.

---

### P0-T03: Engine HTTP Event Emitter Wiring (Per Run)
Effort: Medium

Why critical:
No events means no real-time UI. Current engine uses NoOp emitter.

Current code references:
- `engine/main.go:320` uses `NoOpEventEmitter`.
- `engine/adapter/gateway/http_event_emitter.go:16` exists but unused.
- `engine/application/usecase/scheduler.go:565` emits events.

Implementation steps:
1. Instantiate HTTP emitter per run using `callback_url` and S2S auth.
2. Include `event_id` and `timestamp_ms` in every event.
3. Call `Flush` on run completion, cancellation, and pause.
4. Add emitter buffer size and retry limits to engine config.

Recommended patterns / best practices:
- Bounded buffer with metrics on dropped events.
- Exponential backoff with jitter for retries.

Testing strategy:
- Integration: local HTTP server validates order + signature of events.
- Engine test: flush ensures last event delivered.

Success criteria / Definition of Done:
- [ ] Engine emits events for run start, node updates, completion.
- [ ] Retry logic works on transient failures.

Dependencies:
- P0-T01.

Risks:
- Event loss under high throughput if buffer is too small.

---

### P0-T04: Credentials API + UI (Multi-Tenant)
Effort: Medium

Why critical:
Secure per-tenant credentials are required for multi-model support and investor trust.

Current code references:
- `backend/infrastructure/orm/models.py:666` APIKey model.
- `backend/infrastructure/crypto/encryption.py:101` encryption helpers.
- No API endpoints exist for credentials.

Implementation steps:
1. Add CRUD endpoints under `/api/credentials/` with masked key output.
2. Enforce per-user ownership checks.
3. Add frontend pages for credential management.
4. Validate provider-specific formats (basic regex validation).

Recommended patterns / best practices:
- Never return decrypted keys to frontend.
- Show key hints only (last 4 chars).

Testing strategy:
- Unit: encryption/decryption error cases.
- Integration: create/list/delete credential.

Success criteria / Definition of Done:
- [ ] User can create and delete provider credentials.
- [ ] Encrypted keys stored in DB, not plaintext.

Dependencies:
- ENCRYPTION_KEY configured in env.

Risks:
- Misconfigured encryption key breaks decrypt.

---

### P0-T05: Engine LLM Gateway (OpenAI + Anthropic)
Effort: Large

Why critical:
Multi-model switching is required in demo and a key investor expectation.

Current code references:
- `engine/adapter/gateway/openai_client.go:61` uses env key only.
- `engine/adapter/executor/prompt_executor.go:166` uses `model` only.

Implementation steps:
1. Add provider interface and registry in engine.
2. Implement Anthropic client alongside OpenAI client.
3. Resolve credentials via backend S2S endpoint per run.
4. Route per node by `provider` + `model` fields.

Recommended patterns / best practices:
- Cache decrypted credentials in-memory for run duration only.
- Provider allowlist in backend.

Testing strategy:
- Unit: routing logic and error mapping.
- Integration: run with OpenAI and Anthropic.

Success criteria / Definition of Done:
- [ ] Prompt node runs with provider switch without config changes.
- [ ] Invalid provider/model returns a clear error.

Dependencies:
- P0-T04 and P0-T01.

Risks:
- Provider API usage metrics differences.

---

### P0-T06: Prompt Node Schema + Editor UI
Effort: Medium

Why critical:
Users need to select provider, model, and credential per node.

Current code references:
- `backend/domain/value_objects/node_schemas.py:17` Prompt node schema.
- `frontend/components/graph-editor/forms/*` prompt node form.

Implementation steps:
1. Add `provider` and `credential_id` to prompt node schema.
2. Update graph editor UI to show provider/model/credential selectors.
3. Add validation in backend for missing credentials.

Recommended patterns / best practices:
- Default provider/model based on available credentials.
- Inline warnings when no credentials exist.

Testing strategy:
- Unit: schema validation for required fields.
- UI: form validation for missing credentials.

Success criteria / Definition of Done:
- [ ] Prompt nodes can be configured with provider + credential.
- [ ] Runs fail fast with clear error if credential missing.

Dependencies:
- P0-T04, P0-T05.

Risks:
- Schema changes require migration for existing graphs.

---

### P0-T07: LLM Usage Ledger + Pricing + Budgets
Effort: Large

Why critical:
Cost transparency and budget alerts are required for investor readiness.

Current code references:
- `engine/adapter/summarizer/cost_tracker.go:20` summarization costs only.
- `backend/adapters/api/analytics/memory_analytics.py:72` memory analytics UI.

Implementation steps:
1. Create `llm_usage` table with tokens, model, provider, cost, run/node IDs.
2. Add pricing table config in backend (per model).
3. Parse usage metrics from engine events and persist.
4. Add `tenant_budget` table and alerts at thresholds.

Recommended patterns / best practices:
- Immutable ledger entries.
- Pricing table versioned and explicit mapping.

Testing strategy:
- Unit: cost calculations by model.
- Integration: run -> usage rows created -> totals aggregated.

Success criteria / Definition of Done:
- [ ] Usage series and totals available via API.
- [ ] Budget alert triggers at configured threshold.

Dependencies:
- P0-T02 event ingestion.

Risks:
- Missing usage data from provider APIs.

---

### P0-T08: Analytics UI for LLM Costs + Alerts
Effort: Medium

Why critical:
Demo needs visible cost dashboard and alert state.

Current code references:
- `frontend/pages/analytics/memory.tsx:110` existing analytics UI.

Implementation steps:
1. Add new API endpoints for LLM usage and budgets.
2. Extend analytics UI to display LLM costs and budgets.
3. Add alert banner when budget threshold crossed.

Recommended patterns / best practices:
- Do not block UI on slow analytics calls.
- Use cached aggregated endpoints.

Testing strategy:
- UI tests for alert banner rendering.
- API integration tests for budget threshold.

Success criteria / Definition of Done:
- [ ] LLM cost chart renders with daily series.
- [ ] Budget alert visible when threshold reached.

Dependencies:
- P0-T07.

Risks:
- Overfetching analytics on every page load.

---

### P0-T09: Templates + Onboarding Wizard
Effort: Medium

Why critical:
Time-to-value is the core demo flow: template -> credential -> run.

Current code references:
- `backend/infrastructure/orm/management/commands/seed_phase7_demos.py:351` demo graphs.
- No template API or UI.

Implementation steps:
1. Create Template model or metadata table.
2. Add `/api/templates/` endpoints and clone-from-template.
3. Build onboarding wizard in frontend.
4. Seed 2-3 demo templates (incl. human gate).

Recommended patterns / best practices:
- Immutable templates; always clone to user space.
- Preflight credential checks before run.

Testing strategy:
- Integration: template clone creates graph + version.
- E2E: onboarding flow completes with a successful run.

Success criteria / Definition of Done:
- [ ] New user can complete onboarding in <3 minutes.
- [ ] Demo template run starts immediately after credential entry.

Dependencies:
- P0-T04.

Risks:
- Template schema drift with engine graph model.

---

### P0-T10: Control Plane vs Execution Plane Contract (Doc)
Effort: Small

Why critical:
Investors and senior engineers will ask who owns run state, how failures are handled, and whether the engine can run headless.

Current code references:
- No existing architecture doc defining this contract.

Implementation steps:
1. Add `docs/architecture/control-plane-vs-execution-plane.md` with:
   - Ownership of run lifecycle and source of truth.
   - Partial failure semantics (backend down, engine down, WS/SSE down).
   - Delivery guarantees and idempotency assumptions.
   - Replay ownership and non-goals for MVP.
2. Ensure the doc references tenant isolation expectations.

Recommended patterns / best practices:
- Explicitly document what happens during outages.
- Keep the contract stable across teams (backend/engine/frontend).

Testing strategy:
- N/A (documentation task).

Success criteria / Definition of Done:
- [ ] Doc exists and answers: "backend down 10 minutes", "headless engine", "source of truth".
- [ ] Doc states delivery guarantees and replay ownership.

Dependencies:
- None.

Risks:
- If omitted, architecture ambiguity undermines investor confidence.

---

### P0-T11: Tenant ID Propagation and Enforcement (End-to-End)
Effort: Medium

Why critical:
Multi-tenancy must be enforced, not assumed. Tenant isolation is a core investor question.

Current code references:
- `backend/adapters/api/runs/views.py:76` derives tenant_id from user.
- `engine/proto/engine.proto:66` includes tenant_id in StartRunRequest but events do not carry it explicitly.
- `backend/adapters/api/analytics/memory_analytics.py:33` uses tenant_id for memory analytics only.

Implementation steps:
1. Include `tenant_id` in every engine event payload.
2. Persist `tenant_id` on LLM usage rows and audit logs.
3. Enforce tenant ownership on event ingestion before writing Run/NodeRun.
4. Add cross-checks: run_id must belong to tenant_id.
5. Add a lightweight tenant_id invariant check in event normalization path.

Recommended patterns / best practices:
- Treat tenant_id as a required field in engine events.
- Validate tenant_id before any writes to prevent leakage.

Testing strategy:
- Unit: event ingestion rejects mismatched tenant_id.
- Integration: tenant A cannot write events for tenant B run_id.

Success criteria / Definition of Done:
- [ ] tenant_id flows through engine events, usage, and audit logs.
- [ ] Ingestion rejects any event with mismatched tenant ownership.

Dependencies:
- P0-T01, P0-T02.

Risks:
- Missing tenant_id in existing event emitters.

---

### P0-T12: Demo Validation (Real-Time, Human Gate, Budget Alert)
Effort: Small

Why critical:
Ensures demo story is reliable and repeatable.

Implementation steps:
1. Run the full demo flow and capture timings.
2. Verify no polling fallback in run detail view.
3. Validate human gate pause/resume works end-to-end.
4. Simulate budget threshold breach to trigger alert.

Testing strategy:
- Manual demo checklist + recorded runs.

Success criteria / Definition of Done:
- [ ] 10-minute demo runs without manual fixes.
- [ ] Live updates show WS/SSE status, not polling.

Dependencies:
- All P0 tasks.

Risks:
- Hidden race conditions in WS/SSE handshake.

