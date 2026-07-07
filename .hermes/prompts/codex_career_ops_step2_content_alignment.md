You are Codex in C:\Users\mathi\projects\forgegraph. Implement the approved CareerOps Step 2 plan using strict TDD. Do not commit. Do not implement live apply or external sends.

Read the plan: .hermes/plans/2026-06-17_162958-career-ops-tailored-cv-cover-letter-ats-plan.md

Scope for this pass:
1. Create deterministic service backend/application/services/career_ops_content_alignment.py.
2. Add tests backend/tests/unit/services/test_career_ops_content_alignment.py.
3. Generate alignment report, tailored ATS resume draft, and cover letter draft from source-backed candidate facts and posting metadata.
4. Integrate into backend/application/services/career_ops_packet_builder.py so application packets include:
   - packet["alignment"]
   - packet["artifacts"]["tailored_resume"] not None when base CV exists
   - packet["artifacts"]["cover_letter"] as real draft, not draft_stub
5. Update tests in backend/tests/unit/services/test_career_ops_packet_builder.py.
6. Persist standalone resume and cover letter deliverables from backend/application/services/career_ops_pipeline.py.
7. Update tests in backend/tests/unit/services/test_career_ops_pipeline.py and/or test_career_ops_artifacts.py as needed.
8. Extend backend/application/services/career_ops_quality_gates.py so readiness checks packet content quality:
   - tailored resume present
   - cover letter present
   - ATS resume sections present
   - claim/source map present
   - no internal leakage in generated document text
   - still blocked without exact-version approval
9. Update backend/tests/unit/services/test_career_ops_quality_gates.py.

Hard rules:
- RED first: add tests and run them to see expected failure before production code.
- No LLM calls.
- No invented candidate facts. Unsupported job keywords go to gaps/missing keywords; do not add them to resume or cover letter as claims.
- External side effects must remain false everywhere.
- Do not create new database models.
- Use existing Asset/AssetVersion/ServiceDeliverable persistence.
- Opportunity isolation must remain intact.
- Keep JSON/plain text drafts; no PDF rendering in this pass.
- Keep code deterministic and small.

Verification commands from backend:
FORGEGRAPH_ENV_FILE= DEBUG=1 SECRET_KEY='***' USE_SQLITE=true USE_IN_MEMORY_CACHE=1 USE_IN_MEMORY_CHANNEL_LAYER=1 SQLITE_DB_PATH=.hermes/career_ops_step2_codex.sqlite3 UV_PROJECT_ENVIRONMENT=.venv-test-career-ops uv run --group dev pytest tests/unit/services/test_career_ops_content_alignment.py tests/unit/services/test_career_ops_packet_builder.py tests/unit/services/test_career_ops_artifacts.py tests/unit/services/test_career_ops_quality_gates.py tests/unit/services/test_career_ops_pipeline.py -q
UV_PROJECT_ENVIRONMENT=.venv-test-career-ops uv run ruff check application/services/career_ops_content_alignment.py application/services/career_ops_packet_builder.py application/services/career_ops_pipeline.py application/services/career_ops_quality_gates.py tests/unit/services/test_career_ops_content_alignment.py tests/unit/services/test_career_ops_packet_builder.py tests/unit/services/test_career_ops_pipeline.py tests/unit/services/test_career_ops_quality_gates.py
FORGEGRAPH_ENV_FILE= DEBUG=1 SECRET_KEY='***' USE_SQLITE=true USE_IN_MEMORY_CACHE=1 USE_IN_MEMORY_CHANNEL_LAYER=1 SQLITE_DB_PATH=.hermes/career_ops_step2_check.sqlite3 UV_PROJECT_ENVIRONMENT=.venv-test-career-ops uv run python manage.py check

Return summary of files changed, tests added, RED/GREEN outputs, and any blockers. No commits.