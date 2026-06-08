## Goal
Connect Atlas's conversational acquisition product to WhatsApp through a Hermes-style bridge-compatible provider while preserving ForgeGraph's existing connector guardrails.

## Scope
- Add a WhatsApp provider adapter that talks to an HTTP bridge compatible with Hermes/Baileys-style sidecars.
- Add safe settings/env names.
- Keep real-send gates: env allow flag, approval, operator confirmation, allowlist, cap.
- Add unit tests for provider selection, missing config, health/status, send receipt sanitization, and retryable provider failures.

## Out of scope
- QR pairing UX.
- Running the Node bridge process from Django.
- Real external sends.
- Bulk outbound messaging.

## Success criteria
- Focused WhatsApp connector tests pass.
- No raw phone numbers/message bodies/session refs are persisted in receipts.
- Adapter is disabled by default and safe for dry-run/test environments.
