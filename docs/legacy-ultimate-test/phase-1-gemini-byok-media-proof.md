# Phase 1: Gemini BYOK And Media Proof

Phase 1 proves a narrow capability: Legacy Glasswear can use a backend-owned Google AI credential to execute Gemini text and generate one draft image plus one draft video. This is a test loop, not inventory, Stripe, social publishing, or autonomous production operation.

## Runtime Boundary

- Backend remains the only durable source of truth.
- `GEMINI_LEGACY` is only a bootstrap source for local smoke. It must be imported into the encrypted `APIKey` store before execution.
- Engine and Gemini may execute work, but durable state is stored in backend records: `APIKey`, `MediaGenerationJob`, `Asset`, and `AssetVersion`.
- Generated media starts as `review_status=draft` and is never approved or published automatically.
- Gemini prompts must use sanitized product/content context only. Do not send payment details, addresses, or private customer messages.

## Scope

In scope:

- Google provider routing for text execution.
- Legacy Gemini credential import from `GEMINI_LEGACY`.
- One sanitized text probe using `gemini-2.5-flash`.
- One Imagen image draft using `imagen-4.0-generate-001` unless overridden.
- One Veo video draft using `veo-3.1-generate-preview` unless overridden.
- Evidence under `docs/legacy-ultimate-test/` and raw media under `logs/media-generations/`.

Out of scope:

- Stripe checkout, stock reservations, fulfillment, Instagram/WhatsApp publishing.
- Public 500-agent claims.
- Full in-graph autonomous Gemini media tooling.
- Publishing generated media without human approval.

## Commands

```bash
cd backend
python manage.py import_legacy_gemini_credential --json
python manage.py run_legacy_gemini_phase1_smoke --json
```

The smoke requires Phase 0 to exist and `GEMINI_LEGACY` to be present in the backend process environment or repo `.env`.

## Success Criteria

- Google is accepted by the LLM access policy.
- The Legacy organization has one encrypted Google `APIKey` credential and the graph version references its `credential_id`.
- Image generation creates a succeeded `MediaGenerationJob`, `Asset(asset_type=image)`, and `AssetVersion`.
- Video generation creates a running job with provider operation name, then a succeeded `MediaGenerationJob`, `Asset(asset_type=video)`, and `AssetVersion` after polling.
- Both generated files are downloadable through authenticated archive content API.
- Evidence records provider, model, job IDs, asset IDs, latency/status, and sanitized errors without printing or committing the secret.

## No-Go Conditions

- `GEMINI_LEGACY` is used directly as durable runtime state.
- Any raw secret appears in command output, docs, git, logs, asset metadata, or evidence.
- A media asset is marked approved or published automatically.
- Gemini receives payment details, addresses, or private customer messages.
- The operator needs raw logs or DB inspection to find the generated draft assets.

## Official References

- Gemini image generation: https://ai.google.dev/gemini-api/docs/image-generation
- Imagen: https://ai.google.dev/gemini-api/docs/imagen
- Veo: https://ai.google.dev/gemini-api/docs/video
