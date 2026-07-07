You are Codex working in the ForgeGraph repo at C:\Users\mathi\projects\forgegraph. Implement the user's requested CareerOps live search "skill" slice. Do not commit.

User request: "we can add career_ops_live_search.py as a tool. Actually, if you make it work more like a skill, it'll do everything you need it to do, so let's implement as skill and rerun. Make sure you use codex for the task"

Current relevant files:
- backend/application/services/career_ops_first_prompt.py already has run_career_ops_first_prompt(..., live_postings=...) and build_live_possible_postings filtering/scoring/persistence.
- backend/infrastructure/orm/management/commands/run_career_ops_first_prompt.py accepts --live-postings-json-file/--live-postings-json and calls run_career_ops_first_prompt.
- tests exist in backend/tests/unit/services/test_career_ops_live_discovery.py and backend/tests/unit/management/test_run_career_ops_first_prompt.py.

Goal:
Add backend/application/services/career_ops_live_search.py as a reusable skill-like service/tool. It should turn a CV + constraints + prompt into live posting records that the first prompt command can pass to run_career_ops_first_prompt. The module should be deterministic and testable without network, but also have an optional stdlib-only live web search provider for Docker/manual reruns.

TDD requirements:
1. FIRST write failing tests, then run them and capture the expected failure.
2. Implement minimal code.
3. Run focused tests and ruff.

Acceptance criteria:
A. New service module: backend/application/services/career_ops_live_search.py
   - Include dataclasses or clear structures for search intents/results if useful.
   - Function/class should behave like a skill: generate targeted search queries from extracted CV facts + constraints, call a provider, normalize result hits into live posting dictionaries with at least: title, company, location, url, description, salary_range_usd, provider.
   - It should dedupe by URL.
   - It should attach provenance fields such as source_query, source_rank, provider, and source_mode="live_search_skill" or similar.
   - It should be safe: external_side_effects_allowed=False and no apply/send/browser submission.
   - It should not require external packages. Optional web search provider must use Python stdlib only and degrade gracefully if network/search HTML parsing fails.
   - It should not invent specific salary; unknown salary should be [0, 0].

B. Management command wiring: backend/infrastructure/orm/management/commands/run_career_ops_first_prompt.py
   - Add an option such as --live-search-skill to collect live postings using career_ops_live_search.py, unless --live-postings-json/--live-postings-json-file already supplied.
   - Add optional --live-search-query (repeatable/action append if desired) and --live-search-max-results.
   - Add a test-only/fixture option is acceptable if needed, e.g. --live-search-results-json-file, but the core path should route through the skill service.
   - Payload source_mode should reflect live_search_skill when that path is used, or at least indicate live_url_discovery while postings have provider/source_mode metadata.

C. Tests:
   - Add backend/tests/unit/services/test_career_ops_live_search.py proving query generation, provider hit normalization, dedupe, provenance, and no side effects.
   - Extend backend/tests/unit/management/test_run_career_ops_first_prompt.py with a test proving --live-search-skill plus fixture/provider results routes through the skill and persists only eligible, relevant postings.
   - Keep existing tests passing.

D. Verification commands to run from backend directory on Windows/Git Bash:
   FORGEGRAPH_ENV_FILE= DEBUG=1 SECRET_KEY='***' USE_SQLITE=true USE_IN_MEMORY_CACHE=1 USE_IN_MEMORY_CHANNEL_LAYER=1 SQLITE_DB_PATH=.hermes/career_ops_live_search_skill.sqlite3 UV_PROJECT_ENVIRONMENT=.venv-test-career-ops uv run --group dev pytest tests/unit/services/test_career_ops_live_search.py tests/unit/services/test_career_ops_live_discovery.py tests/unit/management/test_run_career_ops_first_prompt.py -q
   UV_PROJECT_ENVIRONMENT=.venv-test-career-ops uv run ruff check application/services/career_ops_live_search.py application/services/career_ops_first_prompt.py infrastructure/orm/management/commands/run_career_ops_first_prompt.py tests/unit/services/test_career_ops_live_search.py tests/unit/services/test_career_ops_live_discovery.py tests/unit/management/test_run_career_ops_first_prompt.py

Important project constraints:
- Backend-owned state only; no local files as durable truth.
- No employer-facing side effects; no auto-apply.
- Filter/persistence remains handled by run_career_ops_first_prompt/build_live_possible_postings, but live search should produce high-quality candidate records with provenance.
- Use existing ForgeGraph primitives only. No migrations unless truly necessary (should not be necessary).
- Do not edit unrelated files.
- Preserve user's untracked work; there are many untracked files in this repo.

Return a concise summary with files changed, tests run, and any blockers.