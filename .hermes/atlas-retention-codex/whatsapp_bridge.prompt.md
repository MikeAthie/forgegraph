Repository: MikeAthie/forgegraph
Base branch: feat/atlas-deliverable-qa-lifecycle (worktree branch made from its committed HEAD)
Context: Atlas is a productized marketing-agency operating system for CDMX SMB retention. Client acquisition is out of scope. Product must keep clients via measurable leads/sales, low client involvement, weekly proof, and success-fee attribution.
Hard constraints:
- Keep ForgeGraph generic. Put Atlas-specific behavior in Atlas-named services/config/docs, not core hardcoded renderer/model behavior.
- Prefer deterministic services and artifact payloads first; avoid migrations unless strictly necessary.
- Do not add secrets or real credentials. Never log raw phone numbers/messages in persisted receipts; hash/redact where existing patterns do.
- No real external sends in tests. Respect existing approval/operator/allowlist gates.
- Follow project style. Add focused pytest coverage. Run focused tests, ruff on changed files, and python manage.py check if practical.
- Commit the slice when complete with a concise message.
Windows/Git Bash verification preference:
  cd backend
  UV_PROJECT_ENVIRONMENT=.venv-test-department-pipeline uv run python -m pytest <focused tests> -q
  UV_PROJECT_ENVIRONMENT=.venv-test-department-pipeline uv run ruff check <changed files>
  UV_PROJECT_ENVIRONMENT=.venv-test-department-pipeline uv run python manage.py check

TASK: Implement Issue 1 — WhatsApp Hermes-style bridge provider for Atlas conversational acquisition.

Why: Atlas's low-cost acquisition system relies on WhatsApp. ForgeGraph already has `backend/application/services/whatsapp_connectors.py` with fake/open_wa_web/cloud_api adapters and guardrails, plus `backend/application/services/gateway_connectors.py` with generic Hermes-style gateway patterns. Hermes Agent (MIT) uses a Node/Baileys WhatsApp bridge. Do NOT vendor a huge copy unless necessary; implement a compatible adapter boundary that can talk to a bridge over HTTP.

Implement:
1. Add a new provider constant in `backend/application/services/whatsapp_connectors.py`, e.g. `WHATSAPP_PROVIDER_HERMES_BRIDGE = "hermes_bridge"` (or similarly clear), wired through `get_whatsapp_provider_adapter`.
2. Add adapter class that talks to an HTTP bridge:
   - settings/env names in `backend/config/settings.py`, e.g. `WHATSAPP_HERMES_BRIDGE_URL`, `WHATSAPP_HERMES_BRIDGE_SESSION_REF`, maybe reusing existing timeout.
   - `credentials_configured()` requires enabled/configured bridge URL and session ref or explicit config; preserve safe defaults disabled.
   - `session_status()` calls `/health` or `/status` and returns a safe status string.
   - `send()` posts a sanitized request to `/send-message` or `/send`; include idempotency_key and session_ref, normalize one or multiple recipients according to existing caps.
   - Sanitize provider response using existing receipt shape. Do not persist raw phone/text/session secret.
3. Preserve all existing real-send gates: environment allow flag, approval, operator confirmation, recipient allowlist, recipient cap. Do not bypass `validate_real_send_allowed`.
4. Add tests in `backend/tests/unit/services/test_whatsapp_connectors.py` or a focused new file:
   - provider selection returns Hermes bridge adapter.
   - disabled/missing URL/session blocks before provider call.
   - health/status maps ready/authenticated/connected to usable statuses and redacts unsafe data.
   - send returns accepted receipt with evidence_mode `web_automation` or `provider_send` and no raw recipient/text/session material.
   - request failure is retryable and sanitized.
5. Update connector docs if an existing connector docs file is relevant, with MIT/Hermes bridge note and safety caveats.

Out of scope:
- Running Node bridge process from Django.
- QR pairing UX.
- Real WhatsApp integration tests.
- Bulk/spam messaging.

Before coding, inspect existing connector code/tests. Then implement TDD and commit.
