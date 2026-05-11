# Phase 7: Autonomy Strategy And Media Loop

Phase 7 tests Legacy Glasswear as a small company system rather than a single prompt-response agent.

One operator request is routed by Routing Department to Strategy Department, converted into a channel strategy, transformed into approval-gated Instagram/Facebook media packages, materialized as backend-owned media assets and publication drafts, then judged by an AI evaluator whose result is stored as backend-owned task evidence.

## Runtime Boundary

- Backend remains the only durable source of truth.
- Engine and providers may execute text/media generation, but they do not own durable strategy, media, approval, snapshot, resume, or judge state.
- Events are observability/transport artifacts only.
- Media outputs are draft assets and require approval before any external publication.

## Providers

- Primary text/media provider: `GEMINI_LEGACY`, imported into backend `APIKey` storage as Google.
- Required fallback provider: `OPENROUTER`, imported into backend `APIKey` storage as OpenRouter.
- Optional judge transport: local/OpenAI-compatible endpoint, or Groq when `GROQ`/`GROQ_API_KEY` and a compatible model are configured.

Fallback is intentionally scoped to this Legacy autonomy test:

- Gemini is attempted first.
- OpenRouter is retried once only when Gemini shows a quota/token-limit class signal such as HTTP 429, `RESOURCE_EXHAUSTED`, quota exhaustion, rate limit, token limit, context limit, or `MAX_TOKENS`.
- Invalid credentials, malformed prompts, privacy violations, graph authoring bugs, approval failures, and missing backend state are not fallback-eligible.

## Run Command

```bash
PLAYWRIGHT_LEGACY_AUTONOMY_TEST=true npx playwright test frontend/__tests__/legacy-ultimate-test/specs/legacy_autonomy_strategy_media.spec.ts
```

Useful optional flags:

- `PLAYWRIGHT_LEGACY_FORCE_GEMINI_TEXT_LIMIT=true` forces the text path to exercise OpenRouter fallback by constraining the Gemini primary attempt.
- `PLAYWRIGHT_LEGACY_OPENROUTER_TEXT_MODEL` overrides the OpenRouter text model.
- `PLAYWRIGHT_LEGACY_GEMINI_IMAGE_MODEL` and `PLAYWRIGHT_LEGACY_OPENROUTER_IMAGE_MODEL` override media models.
- `PLAYWRIGHT_LEGACY_JUDGE_LLM_URL`, `PLAYWRIGHT_LEGACY_JUDGE_MODEL`, and `PLAYWRIGHT_LEGACY_JUDGE_API_KEY` configure the AI judge.

## Evidence

The spec writes:

- `logs/legacy-autonomy-YYYY-MM-DD.json`
- `docs/legacy-ultimate-test/legacy-autonomy-YYYY-MM-DD.md`

The evidence must include provider attempts, fallback usage, strategy output, media job and asset IDs, publication approval IDs, AI judge score, and backend task judge score.
