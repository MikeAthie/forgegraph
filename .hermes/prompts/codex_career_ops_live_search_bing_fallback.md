You are Codex in C:\Users\mathi\projects\forgegraph. Follow strict TDD. Do not commit.

Issue: Docker live run with --live-search-skill returns 0 postings because StdlibCareerOpsLiveSearchProvider uses DuckDuckGo HTML only, and inside Docker DuckDuckGo returns a 202/interstitial with no result links. Direct test shows Bing returns HTML 200 for the same query. Add a stdlib-only Bing fallback parser/provider behavior to career_ops_live_search.py.

Requirements:
1. Add failing tests first in backend/tests/unit/services/test_career_ops_live_search.py for parsing representative Bing HTML into hits.
2. Implement minimal stdlib-only code in backend/application/services/career_ops_live_search.py.
3. Keep existing DuckDuckGo parser, but if DDG returns no results, fallback to Bing search.
4. Parser should extract URL, title, and snippet/description from typical Bing result HTML (`li.b_algo`, `<h2><a href=...>Title</a></h2>`, snippet in `p`), using html.parser or conservative regex, no external packages.
5. Must degrade gracefully to [] on failures.
6. Preserve normalization behavior, no side effects.

Suggested test HTML can be small, e.g. `<li class="b_algo"><h2><a href="https://example.test/job">Backend AI Engineer</a></h2><p>Python FastAPI backend role in Spain.</p></li>` and assert parser/search helper returns one dict.

Verification from backend:
FORGEGRAPH_ENV_FILE= DEBUG=1 SECRET_KEY='***' USE_SQLITE=true USE_IN_MEMORY_CACHE=1 USE_IN_MEMORY_CHANNEL_LAYER=1 SQLITE_DB_PATH=.hermes/career_ops_live_search_skill_bing.sqlite3 UV_PROJECT_ENVIRONMENT=.venv-test-career-ops uv run --group dev pytest tests/unit/services/test_career_ops_live_search.py tests/unit/services/test_career_ops_live_discovery.py tests/unit/management/test_run_career_ops_first_prompt.py -q
UV_PROJECT_ENVIRONMENT=.venv-test-career-ops uv run ruff check application/services/career_ops_live_search.py tests/unit/services/test_career_ops_live_search.py

Return summary and test output.