# Connector Testing Contract

ForgeGraph connector tests prove that deployment channels remain generic, policy-driven, approval-gated, and safe by default. The backend remains the durable source of truth, and `ToolExecution` is the durable connector receipt.

## Evidence Modes

- `sandbox`: local dry-run evidence. It can unlock performance review only when deployment/performance policy explicitly allows sandbox evidence.
- `web_automation`: manual/experimental WhatsApp web automation evidence. It is not official provider delivery.
- `manual_publish`: operator-recorded social publish evidence. It is not provider success.
- `provider_send` / `provider_publish`: accepted provider execution after approval, policy, env permission, credentials, allowlist, and caps pass.

Blocked-before-provider-call outcomes such as missing credentials, missing sender/session/account, allowlist failure, cap failure, or missing approval create `CompanySignal` and `TaskRoutingRecord` through deployment orchestration. They must not be recorded as provider failures.

## Sanitization Rules

Connector `result_json`, `error_json`, state projections, report/evaluation payloads, logs, and frontend responses must not persist:

- API keys, tokens, auth headers, app secrets, provider config, `private_config_ref`
- raw recipient email addresses, raw phone numbers, raw HTML, raw captions, raw media URLs, raw provider responses
- raw external post URLs when policy requires hashing
- pack manifests, raw prompts, debug traces, or raw evidence bundles

Receipts may store sanitized evidence such as counts, domains, hashes, safe internal asset IDs, provider message/post IDs when safe, status, timestamps, and idempotency keys.

## Safe Defaults

- Email: `EMAIL_CONNECTOR_PROVIDER=fake`, dry-run enabled, `EMAIL_CONNECTOR_ALLOW_REAL_SEND=false`.
- WhatsApp: `WHATSAPP_CONNECTOR_PROVIDER=fake`, web automation and Hermes bridge providers disabled, real send disabled.
- Social: `SOCIAL_CONNECTOR_PROVIDER=fake`, provider publish disabled, manual evidence allowed only when policy permits it.

All real sends/publishes require explicit env permission and allowlists.

## Test Layout

- Shared helpers: `backend/tests/helpers/connector_contracts.py`
- Connector units: `backend/tests/unit/services/test_email_connectors.py`, `test_whatsapp_connectors.py`, `test_social_connectors.py`
- Contract coverage: `backend/tests/unit/services/test_connector_contracts.py`
- Pack dispatch: `backend/tests/unit/services/test_pack_tool_executions_connectors.py`
- Deployment/performance evidence: `backend/tests/unit/services/test_deployment_orchestration_connectors.py`, `test_performance_connector_evidence.py`
- Pending suites: `test_landing_connectors.py`, `test_analytics_connectors.py`
- Optional integrations: `backend/tests/integration/connectors/`
- Product-mode regression: `frontend/__tests__/product-modes/connectors.regression.spec.ts`

## Optional Provider Flags

Provider integration tests skip unless explicitly enabled:

- Resend: `RUN_EMAIL_CONNECTOR_INTEGRATION=true`, `EMAIL_CONNECTOR_PROVIDER=resend`, `RESEND_API_KEY`, `EMAIL_CONNECTOR_RECIPIENT_ALLOWLIST`
- WhatsApp web automation: `RUN_WHATSAPP_WEB_AUTOMATION_INTEGRATION=true`, session/sidecar config, `WHATSAPP_RECIPIENT_ALLOWLIST`
- WhatsApp Hermes bridge: `WHATSAPP_CONNECTOR_PROVIDER=hermes_bridge`, `WHATSAPP_HERMES_BRIDGE_ENABLED=true`, `WHATSAPP_HERMES_BRIDGE_URL`, `WHATSAPP_HERMES_BRIDGE_SESSION_REF`, `WHATSAPP_RECIPIENT_ALLOWLIST`
- Meta social: `RUN_SOCIAL_CONNECTOR_INTEGRATION=true`, `SOCIAL_CONNECTOR_PROVIDER=meta_graph`, `META_GRAPH_ACCESS_TOKEN`, account/page allowlist

Default integration checks perform dry-run/config validation only. Real external sends/publishes are not part of the default suite.

The Hermes bridge provider is a generic HTTP adapter boundary for an operator-run WhatsApp bridge with a Hermes Agent-style Node/Baileys shape. Hermes Agent is MIT-licensed; ForgeGraph does not vendor or launch the bridge process. Treat the bridge like experimental web automation: it must stay opt-in, approval-gated, operator-confirmed, allowlisted, recipient-capped, and isolated from persisted receipts that contain raw phone numbers, message text, session refs, QR tokens, or provider response bodies.

## Useful Commands

```bash
python -m ruff check backend/application/services backend/tests
python -m pytest backend/tests/unit/services/test_connector_contracts.py backend/tests/unit/services/test_pack_tool_executions_connectors.py backend/tests/unit/services/test_deployment_orchestration_connectors.py backend/tests/unit/services/test_performance_connector_evidence.py
```

```bash
cd frontend
npx tsc --noEmit
npx eslint __tests__/product-modes/connectors.regression.spec.ts __tests__/product-modes-live/atlas-agency-full-flow.e2e.spec.ts
USE_SQLITE=true npx playwright test __tests__/product-modes/connectors.regression.spec.ts --project=chromium
```
