You are Codex in C:\Users\mathi\projects\forgegraph. Follow strict TDD. Do not commit.

We already added backend/application/services/career_ops_live_search.py and wired --live-search-skill. Docker run of the real stdlib provider returned 0 postings because provider hits often lack explicit location; downstream CareerOps filtering rejects blank/unknown locations. Patch the live-search skill so normalized hits infer a safe location from the source query when the hit location is missing.

Requirements:
1. Add/extend tests first in backend/tests/unit/services/test_career_ops_live_search.py and run them to see RED.
2. Implement minimal code in backend/application/services/career_ops_live_search.py.
3. Rerun focused tests + ruff.

Expected behavior:
- If hit has no location but source_query includes Spain, set location to "Spain Remote" or "Spain".
- If source_query includes Mexico, set location to "Mexico Remote" or "Mexico".
- If source_query includes Europe/European Union/EU, set location to "Europe Remote" or "European Union Remote".
- If source_query includes Remote only, location may be "Remote".
- Do not infer United States; blank is safer for US-ish queries.
- Preserve explicit hit location if present.
- Keep external_side_effects_allowed=False, source_mode live_search_skill, no salary invention.

Verification commands from backend:
FORGEGRAPH_ENV_FILE= DEBUG=1 SECRET_KEY='***' USE_SQLITE=true USE_IN_MEMORY_CACHE=1 USE_IN_MEMORY_CHANNEL_LAYER=1 SQLITE_DB_PATH=.hermes/career_ops_live_search_skill_location.sqlite3 UV_PROJECT_ENVIRONMENT=.venv-test-career-ops uv run --group dev pytest tests/unit/services/test_career_ops_live_search.py tests/unit/services/test_career_ops_live_discovery.py tests/unit/management/test_run_career_ops_first_prompt.py -q
UV_PROJECT_ENVIRONMENT=.venv-test-career-ops uv run ruff check application/services/career_ops_live_search.py tests/unit/services/test_career_ops_live_search.py

Return summary of changed files and commands.