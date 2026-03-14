# P1 Memory QA Matrix

## Status
P1 QA closed on March 13, 2026.

## Supported Proof
- Memory Browser: search, timeline, detail, scope, recency, and topic inspection.
- Graph editor authoring: `observation_save`, `observation_search`, `observation_context`, and `observation_timeline`.
- Runtime proof: Jackie workflow runs twice, retrieves curated context on the second pass, and shows save/context/influence in the run UI.
- Run debugger proof: memory activity summary, per-node activity cards, and raw payload drill-down.

## Coverage Matrix
| Area | Coverage |
| --- | --- |
| Observation domain model | backend unit tests for normalization, dedupe, topic upsert, soft delete, and ordering |
| REST contracts | backend integration tests for create, update, delete, search, detail, context, and timeline |
| gRPC contracts | backend integration tests for save, search, get, context, timeline, and backward-compatible retrieval |
| Engine executors | Go tests for save, search, context, and timeline nodes plus scheduler/runtime behavior |
| Prompt and agent composition | Go tests for curated context injection and trace payloads |
| Run/debug shaping | backend run API tests plus frontend run page tests |
| Memory Browser UI | frontend unit tests and Playwright browser proof |
| Editor authoring | frontend component tests plus Jackie Playwright authoring proof |
| End-to-end Jackie journey | Playwright Chromium proof with local LLM mock and runtime tool fixture |

## Known Limitations
- The supported browser proof is Chromium-based. Firefox and WebKit are not part of the P1 release gate.
- The Jackie proof uses the local OpenAI mock and the deterministic runtime health-check package to keep the journey repeatable.
- Curated retrieval may legitimately report degraded fallback (`fts`, `timeline`) when vector indexing is not yet available.
- MVP memory capture is explicit only. Passive extraction from arbitrary runs remains out of scope.
- The supported story is graph/run/session scoped curated memory, not an organization-wide knowledge workspace.

## Recommended Validation Commands
- `uv run pytest backend/tests/integration/adapters/test_memory_observation_api.py backend/tests/integration/adapters/test_memory_grpc_service.py backend/tests/integration/adapters/test_run_api.py -q`
- `go test ./...`
- `npm run lint`
- `npm run build`
- `npx playwright test __tests__/e2e/memory-browser.spec.ts __tests__/e2e/jackie-workflow.spec.ts --project=chromium`
