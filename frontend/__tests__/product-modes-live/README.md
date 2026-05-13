# Product Modes Live E2E

This suite is opt-in. It is skipped unless `LIVE_LLM_E2E=true` and a real LLM credential is available through the repo's existing environment names.

Run one worker first:

```powershell
LIVE_LLM_E2E=true USE_SQLITE=true npx playwright test __tests__/product-modes-live --project=chromium
```

Run with two workers:

```powershell
LIVE_LLM_E2E=true USE_SQLITE=true PLAYWRIGHT_WORKERS=2 npx playwright test __tests__/product-modes-live --project=chromium --workers=2
```

The LLM operation spec requires the browser UI launch path by default. To diagnose backend/runtime behavior when the UI launch is temporarily blocked, opt in explicitly:

```powershell
LIVE_LLM_E2E=true LIVE_LLM_ALLOW_BACKEND_FALLBACK=true USE_SQLITE=true npx playwright test __tests__/product-modes-live --project=chromium
```

Supported credential/env names include `OPENAI_API_KEY` with a non-mock `OPENAI_BASE_URL`, local OpenAI-compatible LLM config through `LOCAL_LLM_BASE_URL`, `PLAYWRIGHT_LOCAL_LLM_URL`, or `PLAYWRIGHT_DOCKER_LOCAL_LLM_URL`, `GEMINI_LEGACY`, `GEMINI_API_KEY`, `GOOGLE_API_KEY`, `OPENROUTER`, `OPENROUTER_API_KEY`, and `ANTHROPIC_API_KEY`.

The live slice keeps the architecture boundary explicit: `Organization -> Company -> PackInstallation -> generic primitives`. It does not create ATLAS UI, marketing routes, vertical models, or separate function Companies.
