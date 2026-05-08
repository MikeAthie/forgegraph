# Legacy Evidence Packet: 2026-05-08 First Local Run

## Change

- Ran the first local Legacy Glasswear rehearsal against backend-owned state.
- Used isolated SQLite state at `logs/legacy-first-run-20260508.sqlite3`.
- Re-ran the same rehearsal against Docker-backed Postgres at
  `localhost:5433/forgegraph` after Docker Desktop started.
- Ran the first live backend API + run queue + engine objective for Strategy
  Baseline v1.
- Avoided live Gemini media/video and Stripe calls.

## Hypothesis

- Phase 0 bootstrap, Phase 2 inventory, and Phase 5 operating-loop primitives can
  create a clean Legacy company, import real inventory, protect scarce stock, and
  create human-gated operating work without making the engine, frontend, events,
  Gemini, or Stripe authoritative for durable state.

## Commands

```powershell
cd backend
$env:USE_SQLITE='true'
$env:SQLITE_DB_PATH='../logs/legacy-first-run-20260508.sqlite3'
$env:USE_IN_MEMORY_CHANNEL_LAYER='true'
uv run python manage.py migrate --noinput
uv run python manage.py seed_legacy_glasswear_phase0 --json
uv run python manage.py import_legacy_inventory_phase2 --json
uv run python manage.py import_legacy_gemini_credential --json
```

Postgres rerun:

```powershell
docker compose up -d postgres redis
cd backend
uv run python manage.py check
uv run python manage.py migrate --check
$env:LEGACY_TEST_PASSWORD='[redacted]'
uv run python manage.py seed_legacy_glasswear_phase0 --json
uv run python manage.py import_legacy_inventory_phase2 --json
uv run python manage.py import_legacy_gemini_credential --json
```

Focused verification:

```powershell
cd backend
uv run pytest tests/unit/management/test_seed_legacy_glasswear_phase0.py `
  tests/unit/management/test_import_legacy_inventory_phase2.py `
  tests/unit/management/test_import_legacy_gemini_credential.py `
  tests/unit/services/test_inventory.py `
  tests/unit/services/test_company_ops.py `
  tests/unit/services/test_gemini_media.py `
  tests/unit/services/test_commerce.py `
  tests/unit/api/test_inventory_api.py `
  tests/unit/api/test_company_ops_api.py `
  tests/unit/api/test_commerce_storefront_api.py

cd ../engine
go test ./adapter/gateway

cd ../frontend
npx tsc --noEmit --pretty false
npm run test:ci:fast -- components/company/CommerceInventoryPanel.tsx `
  "pages/storefront/[companySlug].tsx" lib/api.ts
```

## Observed Data

- Company ID: `b1ad918f-dac2-40de-8cd7-6293417595c1`
- Organization ID: `f5549f0e-99a4-4b25-b282-53afc55c2aa5`
- Phase 0 output: one Legacy user, one organization, one company graph.
- Storefront slug: `legacy-glasswear`
- Phase 2 import: 21 products, 62 active stock units, 0 import warnings.
- Gemini credential import: `provider=google`, `key_present=true`, graph version 2
  created with BYOK credential metadata.

Reservation proof:

- SKU used: `NC-29026`
- Starting inventory: 62 available, 0 held.
- Hold result: 61 available, 1 held.
- Duplicate hold with same idempotency key replayed the same reservation.
- Second hold against the one-unit SKU failed with `insufficient_stock`.
- Release result: 62 available, 0 held, 0 active reservations.

Operating-loop proof:

- Signal ID: `39234818-f4b0-4649-b782-f32583349b3c`
- Opportunity ID: `29920763-bf00-4081-bd4a-d2fc3c48351b`
- Operation ID: `13036f66-fb4d-4709-b9ef-254cfae158f4`
- Objective contract ID: `cef37490-ff09-4916-b186-b5e4f7c7696a`
- Objective status: `evaluated`
- Success score: `68`
- Publication draft status: `approval_requested`
- Procurement draft status: `approval_requested`
- Approval tasks created: 2
- Context privacy probe: blocked email and blocked Stripe ID were absent.

Postgres rerun observed data:

- Company ID: `1b99ce06-d01d-46a4-9dad-bbd14396fb40`
- Organization ID: `a65d7ce2-0b29-4b3b-97f9-49d9ddde5287`
- Phase 0 output: one Legacy user, one organization, one company graph.
- Storefront slug: `legacy-glasswear`
- Phase 2 import: 21 products, 62 active stock units, 0 import warnings.
- Gemini credential import: `provider=google`, `key_present=true`, graph version 2
  created with BYOK credential metadata.
- Reservation proof matched SQLite: 62 available -> 61 available/1 held -> 62
  available after release.
- Duplicate reservation replayed the same reservation.
- Second hold against `NC-29026` failed with `insufficient_stock`.
- Operation ID: `d12ae544-1aff-4861-a3e6-73115e4ec9cf`
- Objective contract ID: `edb69943-5058-4ad3-99c7-e61386366d32`
- Objective status: `evaluated`
- Success score: `74`
- Publication draft status: `approval_requested`
- Procurement draft status: `approval_requested`
- Approval tasks created: 2
- Context privacy probe: blocked email and blocked Stripe ID were absent.

Live Strategy Baseline objective run:

- Objective: produce Strategy Baseline v1 with strategy, visual content needs,
  KPIs, goals, success criteria, out-of-scope boundaries, and next run plan.
- Final graph version ID: `6bd49773-3da2-44fa-a7ff-181c47abc710`
- Final run ID: `e6653f44-d483-4e46-8588-44b07438122a`
- Final objective contract ID: `58513b8b-72d1-45ce-a189-b7741db593b0`
- Final run status: `succeeded`
- Final objective score: `90`
- Prompt node finish reason: `STOP`
- Usage: 886 prompt tokens, 665 completion tokens, 3757 total tokens.
- Required sections present: `strategy`, `visual_content_needed`, `kpis`,
  `goals`, `success_criteria`, `out_of_scope`, `next_run_plan`.
- Output counts: 5 visual assets, 4 KPIs, 3 goals, 4 success criteria,
  5 out-of-scope boundaries, 4 next-run steps.

Strategy Baseline v1 summary:

- First-run focus: backend stock, cash, learning, and reorder discipline.
- Visual priorities: GAGA, HENDRIX, WINEHOUSE, WATSON, MAVERICK product shots.
- KPI owners: Ops & Inventory, Content Studio, Operating System.
- Explicitly out of scope: customer outreach, live sales, media generation,
  checkout processing, procurement actions.
- Next decision: advance to an approval-gated visual asset brief run and
  reconcile the low-stock metric discrepancy.

Task judge feature run:

- Applied backend-owned task judge migration `0077_taskjudge` to the Docker
  Postgres stack.
- Redis had detached from the Compose network after the restart; recreated the
  Redis service with Compose and restarted backend workers before the run.
- New run ID: `fefab505-60c9-4e57-ab68-da53d16fe557`
- Run status: `succeeded`
- Judged task: `Operating System Strategy Baseline task`
- Task ID: `818c4925-3017-4b3d-8ec2-5fe8e52e52a6`
- Judge ID: `424872c7-6dd7-4c58-ad5c-8096cdcc7152`
- Judge status: `passed`
- Judge threshold: `80`
- Judge grade: `93/100`
- Criteria result summary: 8/8 criteria passed. Lowest criterion score was
  `75` for goals and success criteria wording; all other criteria scored
  `82` or higher.

## Verification Result

- Backend focused slice on SQLite fallback: 73 passed.
- Backend focused slice on Docker Postgres: 73 passed.
- Engine Gemini gateway slice: passed.
- Frontend TypeScript check: passed.
- Frontend related Jest slice: 306 passed.
- Live API objective run: achieved after iteration through `/api/runs/start`,
  Docker run queue, and engine dispatch.

## Bugs Or Gaps

- Initial local Postgres was unavailable because Docker Desktop was not running,
  so the first run used SQLite fallback. After Docker Desktop started, the
  Postgres rerun passed.
- A parallel Postgres seed/import attempt failed because inventory import started
  before Phase 0 committed. The serial rerun passed, which means the first-run
  harness should encode command dependencies explicitly.
- The first pytest attempt ignored `USE_SQLITE=true` because `config.test_settings`
  forces `.env.test` with override; the workaround was setting
  `FORGEGRAPH_ENV_FILE` to a non-existent override path for SQLite-only smoke.
- The first ad hoc walkthrough script used interactive `manage.py shell` via stdin
  and partially executed before a syntax error. The rerun used `manage.py shell -c`.
- No browser walkthrough or Playwright demo capture was run.
- No live Gemini text/media call was made; only credential import and mocked/unit
  media paths were verified.
- Follow-up live API objective did make Gemini text calls through BYOK. Gemini
  media/video remains untested.
- No Stripe checkout/webhook call was made because Stripe test secrets were absent.
- The initial walkthrough did not exercise live engine dispatch; the follow-up
  Strategy Baseline objective did.
- Inventory and company-ops summaries disagree on low-stock semantics: inventory
  reported 3 low-stock products while company-ops reported 9 because it appears
  to include zero-stock products as low stock.
- The objective evaluation intentionally marked `raw_log_dependency` as failed
  because this first run still depended on shell/API inspection instead of a full
  operator-surface walkthrough.
- First strict full-section schema run reached Gemini but failed engine schema
  validation: `ea8c30cb-94de-46d9-8c0a-c5c13030ee43`.
- Full-context warning-mode run succeeded but returned incomplete JSON with
  `MAX_TOKENS`: `892d5233-1a4f-4fba-81c4-e2d94db0b77a`.
- Compact strict-object run failed because Gemini returned JSON as a string/fence
  from the engine validator's perspective:
  `67e79309-045d-4a46-a94c-12fea257994e`.
- Compact warning-mode run with `gemini-2.5-flash` and `max_tokens=1800` still
  hit `MAX_TOKENS` after little visible output:
  `9e0f8a15-0491-4e2f-adde-a7a4a4bbf616`.
- `gemini-2.0-flash` was unavailable/rate-limited for this credential and failed
  because no fallback provider is configured:
  `bb5b47ab-2376-4718-896e-94c0e62d31c7`.
- Achieved configuration used a small JSON skeleton, compact context,
  `gemini-2.5-flash`, and `max_tokens=8192`. This suggests Gemini 2.5 hidden
  reasoning can starve visible JSON unless budgeted explicitly.

## Decision

- Result: partial pass for the primitive local walkthrough; achieved for the
  first live Strategy Baseline objective.
- Keep the backend-owned Legacy primitives as the baseline for iteration.
- Next iteration should make the serial first run a repo-owned command or script,
  normalize stock-risk semantics, add an API/browser walkthrough, and then run an
  approval-gated visual asset brief before invoking external Gemini media or
  Stripe checkout.
