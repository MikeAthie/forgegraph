# P2 Execution Flow (Task-by-Task)

## Goal
Run P2 with the same discipline as P0/P1: implement one task slice, validate with tests, then mark complete.

## Completion Rules
1. Implement one P2 task slice at a time.
2. Add or extend automated tests for each acceptance criterion touched.
3. Run targeted tests first, then wider regression checks.
4. Mark a task complete only after tests pass (or record explicit environment blockers).
5. Record changes, validation commands, and residual risks.

## Task Tracker

### P2-T01: Credential UX (API Keys + OAuth Assignment)
Status: `completed`

Sub-checks:
- [x] Credentials hub supports API-key create/list/delete and OAuth config/connect/reconnect.
- [x] Node-level credential assignment in node dialogs and wizard paths is complete.
- [x] Credential health states are surfaced where assignment happens.
- [x] OAuth failure/recovery messaging is actionable.

Validation Gate:
- [x] Frontend unit tests for credential assignment controls.
- [x] Backend integration tests for credential and OAuth paths.

### P2-T02: Telegram Trigger + Send + Voice Support
Status: `completed`

Sub-checks:
- [x] Telegram webhook trigger endpoint with secret-token verification and run dispatch.
- [x] Normalized payload mapping for text + voice updates with transcription status.
- [x] Deterministic thread-id derivation for chat resume continuity.
- [x] Credential-backed Telegram send runtime hardening for HTTP executor path.
- [x] Wizard/quick-setup guidance and preset coverage for BotFather + webhook secret.

Validation Gate:
- [x] Frontend unit tests for Telegram wizard/preset hints.
- [x] Engine tests for credential token substitution + auth behavior.
- [x] Backend integration tests pass.

### P2-T03: WhatsApp (Twilio) Trigger + Send + Voice Support
Status: `completed`

Sub-checks:
- [x] Twilio webhook trigger endpoint with signature verification.
- [x] Normalized inbound payload for text/voice including transcription status fields.
- [x] Deterministic sender thread-id mapping for resume continuity.
- [x] Twilio credential support in runtime and quick presets.
- [x] Wizard preset and setup guidance for SID/token/phone wiring.

Validation Gate:
- [x] Backend integration tests added for Twilio webhook auth + voice path.
- [x] Frontend preset coverage includes WhatsApp quick preset + wizard preset.
- [x] Backend integration tests pass.

### P2-T04: Gmail Nodes (Unread Fetch + Send)
Status: `completed`

Sub-checks:
- [x] Added Gmail unread + send quick presets and wizard flow defaults.
- [x] OAuth provider support and scopes wired through credentials hub.
- [x] Credential-aware runtime auth path covers Gmail bearer token execution.
- [x] Reauth health messaging visible in node-level credential assignment UI.

Validation Gate:
- [x] OAuth provider integration tests extended for Gmail-related provider matrix.
- [x] Frontend unit tests validate Gmail quick presets.

### P2-T05: Google Calendar + Tasks Nodes
Status: `completed`

Sub-checks:
- [x] Added Calendar list/create quick presets and marketplace package defaults.
- [x] Added Tasks list/create quick presets and marketplace package defaults.
- [x] OAuth providers (`google_calendar`, `google_tasks`) configured end-to-end.
- [x] Node config UX supports provider-specific hints for date/time and task list inputs.

Validation Gate:
- [x] OAuth start tests added for Calendar and Tasks providers.
- [x] Frontend quick preset tests include Calendar/Tasks defaults.

### P2-T06: HTTP + Webhook Nodes (Fallback Integrations)
Status: `completed`

Sub-checks:
- [x] HTTP executor auth path finalized with provider-aware credential injection.
- [x] Generic webhook trigger endpoint implemented with secret verification.
- [x] HTTP node config dialog includes **Run test** action with response/error rendering.
- [x] Added reusable webhook fallback quick preset and provider hints.

Validation Gate:
- [x] Backend integration tests for generic webhook trigger added.
- [x] Backend integration tests for HTTP run-test endpoint added.
- [x] Frontend unit tests cover HTTP run-test behavior and body-validation modes.
- [x] Backend integration tests pass.

### P2-T07: Quick-Setup Shortcuts Library
Status: `completed`

Sub-checks:
- [x] Quick-add presets include Telegram, WhatsApp (Twilio), Gmail, Calendar, Tasks, and HTTP/Webhook.
- [x] Integration shortcut selection auto-opens node credential configuration dialog with provider prefilled.
- [x] Shortcut defaults include minimal viable config + setup hints.
- [x] Shortcut validation badges/hints are surfaced in Quick Node Palette cards.

Validation Gate:
- [x] Unit tests verify preset coverage and setup-hint metadata.
- [x] Graph editor path updated for marketplace/wizard shortcut credential-first setup flow.

## Execution Log
- 2026-02-06: P2 tracker initialized; started P2-T01 with node-level credential assignment hardening for HTTP/Tool node dialogs.
- 2026-02-06: Completed P2-T01.
  - Added credential provider + credential assignment controls to HTTP and Tool node dialogs.
  - Added credential health and reauth guidance in assignment UI.
  - Updated graph/node schemas and type hints for optional `provider` + `credential_id` on HTTP/Tool nodes.
  - Validation:
    - `npm test -- __tests__/components/graph-editor/forms/HttpNodeForm.test.tsx __tests__/components/graph-editor/forms/ToolNodeForm.test.tsx`
    - `npm run lint`
    - `pytest backend/tests/unit/domain/test_node_schemas.py`
    - `pytest backend/tests/integration/adapters/test_credentials_oauth_api.py`
- 2026-02-06: Completed P2-T02/P2-T03/P2-T04/P2-T05 core integration slices.
  - Added Telegram/WhatsApp webhook adapters with auth verification, normalized payload mapping, and voice transcription support.
  - Added Gmail/Calendar/Tasks provider expansion in OAuth service, model choices, and presets/marketplace defaults.
  - Added credential-aware HTTP executor resolution for provider token substitution and auth header injection.
  - Validation:
    - `go test ./engine/adapter/executor -run TestHTTPExecutor -count=1`
    - `go test ./engine/...`
    - `npm test -- __tests__/unit/lib/agent-wizard-presets.test.ts __tests__/unit/lib/quick-node-presets.test.ts __tests__/unit/lib/template-quick-starts.test.ts`
    - `npm run lint`
    - `ruff check backend/adapters/api/integrations/*.py backend/application/services/oauth.py backend/infrastructure/orm/migrations/0038_p2_integrations_expansion.py backend/tests/integration/adapters/test_integrations_telegram_api.py backend/tests/integration/adapters/test_integrations_whatsapp_api.py backend/tests/integration/adapters/test_integrations_webhook_api.py`
    - `python -m compileall backend/adapters/api/integrations/telegram_views.py backend/adapters/api/integrations/whatsapp_views.py backend/adapters/api/integrations/webhook_views.py`
    - `pytest backend/tests/integration/adapters/test_integrations_telegram_api.py backend/tests/integration/adapters/test_integrations_whatsapp_api.py backend/tests/integration/adapters/test_integrations_webhook_api.py`
- 2026-02-06: Completed P2-T06 + P2-T07 hardening pass.
  - Wired backend `POST /api/integrations/http/test` run-test endpoint and added integration tests.
  - Added HTTP node run-test UI (result/error panel, Twilio SID support, provider hints/docs links).
  - Updated quick shortcut flow to open credential configuration dialog immediately for integration shortcuts.
  - Added setup hints/validation badges for integration presets and provider-scoped credential deep links.
  - Validation:
    - `npm test -- __tests__/components/graph-editor/forms/HttpNodeForm.test.tsx __tests__/unit/lib/quick-node-presets.test.ts`
    - `npm run lint`
    - `ruff check backend/adapters/api/integrations/http_test_views.py backend/adapters/api/integrations/urls.py backend/tests/integration/adapters/test_integrations_http_test_api.py`
    - `python -m compileall backend/adapters/api/integrations/http_test_views.py`
    - `pytest backend/tests/integration/adapters/test_integrations_http_test_api.py -q`
- 2026-02-06: Postgres-enabled rerun and final backend verification.
  - Fixed WhatsApp webhook parser handling for Twilio payloads by enabling `FormParser`/`MultiPartParser`.
  - Validation:
    - `pytest backend/tests/integration/adapters/test_integrations_whatsapp_api.py -q`
    - `pytest backend/tests/integration/adapters/test_integrations_telegram_api.py backend/tests/integration/adapters/test_integrations_whatsapp_api.py backend/tests/integration/adapters/test_integrations_webhook_api.py backend/tests/integration/adapters/test_integrations_http_test_api.py -q`
    - `pytest backend/tests/integration/adapters/test_credentials_oauth_api.py -q`
    - `pytest backend/tests/integration/adapters/test_marketplace_api.py -q`
