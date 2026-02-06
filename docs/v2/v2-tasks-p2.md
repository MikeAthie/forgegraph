# P2: Integrations + Credential UX (Weeks 5-7)

## Objective
Ship the integration surface expected for launch and make credential setup as simple as possible for non-technical users.

## Prerequisites
- P0 prompt/tool/memory runtime paths are complete.
- P1 palette and wizard support node metadata for setup guidance.

---

## Task List

### P2-T01: Credential UX (API Keys + OAuth Assignment)
Effort: Medium

Why critical:
Integration adoption depends on frictionless credential setup.

Implementation steps:
1. Expand credentials hub with provider-specific setup forms.
2. Add OAuth provider config + connect/reconnect flow for supported integrations.
3. Add node-level credential assignment in node dialogs and wizard steps.
4. Add credential health states (valid, expiring, expired, reauth required).

Recommended patterns / best practices:
- Keep secret values write-only after creation.
- Use clear provider-specific scope descriptions.

Testing strategy:
- Integration: create/list/delete API-key credentials.
- Integration: OAuth connect/callback and reauth path.

Success criteria / Definition of Done:
- [ ] Connecting an API requires filling a form, not code.
- [ ] Credentials persist and can be assigned to nodes.
- [ ] OAuth failures surface actionable recovery messages.

Dependencies:
- Existing credential storage + encryption.

Risks:
- Provider-specific OAuth edge cases.

---

### P2-T02: Telegram Trigger + Send + Voice Support
Effort: Medium

Why critical:
Telegram is a top quick-start chatbot channel.

Implementation steps:
1. Add Telegram trigger node for inbound messages and metadata.
2. Add Telegram send/reply action node.
3. Add optional voice-message transcription path.
4. Add wizard quick setup with BotFather token helper text.

Recommended patterns / best practices:
- Verify webhook signatures and bot token ownership.
- Normalize inbound payload shape for downstream nodes.

Testing strategy:
- Integration: inbound message triggers run.
- E2E: receive user message and send response.

Success criteria / Definition of Done:
- [ ] User can build Telegram chat agent end-to-end.
- [ ] Voice messages can be transcribed and processed.
- [ ] Quick setup path configures required fields in minutes.

Dependencies:
- P2-T01 credential UX.

Risks:
- Webhook reliability and retry handling.

---

### P2-T03: WhatsApp (Twilio) Trigger + Send + Voice Support
Effort: Medium

Why critical:
WhatsApp expands deployment channels for business automations.

Implementation steps:
1. Add WhatsApp trigger node using Twilio inbound webhook format.
2. Add WhatsApp send action node.
3. Add voice-note transcription compatibility.
4. Add quick setup form for Twilio SID/token/phone.

Recommended patterns / best practices:
- Strict signature verification for inbound requests.
- Shared message schema with Telegram where possible.

Testing strategy:
- Integration: inbound Twilio webhook triggers run.
- E2E: user message -> agent response round trip.

Success criteria / Definition of Done:
- [ ] User can build WhatsApp chatbot workflow end-to-end.
- [ ] Twilio credential setup is fully UI-driven.
- [ ] Voice message path works with transcription enabled.

Dependencies:
- P2-T01 credential UX.

Risks:
- Twilio sandbox vs production behavior differences.

---

### P2-T04: Gmail Nodes (Unread Fetch + Send)
Effort: Medium

Why critical:
Email automation is a core workflow category.

Implementation steps:
1. Add Gmail "Get unread emails" node with query controls.
2. Add Gmail "Send email" node with templated body and attachments metadata.
3. Wire OAuth scopes and token refresh handling.
4. Add preset defaults for unread query and reply workflow.

Recommended patterns / best practices:
- Request least-privilege scopes.
- Surface token expiry and reconnect prompts.

Testing strategy:
- Integration: fetch at least 5 unread emails in test inbox.
- E2E: summarize unread email and send generated reply.

Success criteria / Definition of Done:
- [ ] Agent can read inbox and send replies with OAuth credential.
- [ ] Expired Gmail credentials trigger reauth UX.
- [ ] Gmail nodes are available in palette and wizard presets.

Dependencies:
- OAuth provider configuration support.

Risks:
- Gmail API quota and rate-limit behavior.

---

### P2-T05: Google Calendar + Tasks Nodes
Effort: Medium

Why critical:
Calendar/task automation is central to assistant use cases.

Implementation steps:
1. Add Calendar nodes: list events, create event.
2. Add Tasks nodes: list tasks, create task.
3. Share Google OAuth credential path where possible.
4. Add date range helpers and validation.

Recommended patterns / best practices:
- Normalize timezone handling at node boundaries.
- Validate required event/task fields before dispatch.

Testing strategy:
- Integration: list today's events and create one new item.
- E2E: run workflow that reads events and schedules a task.

Success criteria / Definition of Done:
- [ ] Agent reads events and schedules tasks successfully.
- [ ] OAuth flow works for both Calendar and Tasks nodes.
- [ ] Node forms validate date/time inputs and required fields.

Dependencies:
- P2-T01 OAuth credential UX.

Risks:
- Timezone mismatch causing incorrect schedules.

---

### P2-T06: HTTP + Webhook Nodes (Fallback Integrations)
Effort: Small

Why critical:
HTTP/Webhook nodes are essential fallback for unlisted services.

Implementation steps:
1. Finalize HTTP node request builder (method, URL, headers, body, auth).
2. Add webhook trigger node with payload mapping and signature options.
3. Add "Run test" action in node config dialog.
4. Add reusable request presets for common API patterns.

Recommended patterns / best practices:
- Per-request timeout and retry policy controls.
- Redact auth headers from logs and UI previews.

Testing strategy:
- Integration: GET/POST against test API endpoint.
- E2E: webhook trigger initiates graph and completes run.

Success criteria / Definition of Done:
- [ ] Any REST API can be integrated with HTTP/Webhook nodes.
- [ ] "Run test" validates node config before full run.
- [ ] HTTP errors are surfaced with response context.

Dependencies:
- Tool/HTTP executor reliability from P0.

Risks:
- SSRF/security concerns without allowlist policy.

---

### P2-T07: Quick-Setup Shortcuts Library
Effort: Small

Why critical:
One-click setup reduces onboarding friction and mimics top workflow tools.

Implementation steps:
1. Add quick-add shortcuts for Telegram, WhatsApp (Twilio), Gmail, Calendar, Tasks, and HTTP.
2. Auto-open matching credential panel when shortcut is used.
3. Prefill minimal viable node config for each shortcut.
4. Add shortcut validation badge and inline setup hints.

Recommended patterns / best practices:
- Keep shortcuts metadata-driven for easy updates.
- Link to official provider setup docs where needed.

Testing strategy:
- E2E: shortcut -> credential -> run test flow per provider.
- Unit: shortcut preset generation and required field checks.

Success criteria / Definition of Done:
- [ ] User can configure common integrations via one-click shortcuts.
- [ ] Shortcut-created nodes pass validation with expected defaults.
- [ ] Setup hints are visible for each shortcut path.

Dependencies:
- P2-T01 credentials and provider nodes.

Risks:
- Preset defaults may become stale as APIs evolve.
