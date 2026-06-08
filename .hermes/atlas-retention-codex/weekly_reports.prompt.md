Repository: MikeAthie/forgegraph
Base branch: feat/atlas-deliverable-qa-lifecycle (worktree branch made from its committed HEAD)
Context: Atlas is a productized marketing-agency operating system for CDMX SMB retention. Client acquisition is out of scope. Product must keep clients via measurable leads/sales, low client involvement, weekly proof, and success-fee attribution.
Hard constraints:
- Keep ForgeGraph generic. Put Atlas-specific behavior in Atlas-named services/config/docs, not core hardcoded renderer/model behavior.
- Prefer deterministic services and artifact payloads first; avoid migrations unless strictly necessary.
- Do not add secrets or real credentials. Never log raw phone numbers/messages in persisted receipts; hash/redact where existing patterns do.
- No real external sends in tests. Respect existing approval/operator/allowlist gates.
- Follow project style. Add focused pytest coverage. Run focused tests, ruff on changed files, and python manage.py check if practical.
- Commit the slice when complete with a concise message.
Windows/Git Bash verification preference:
  cd backend
  UV_PROJECT_ENVIRONMENT=.venv-test-department-pipeline uv run python -m pytest <focused tests> -q
  UV_PROJECT_ENVIRONMENT=.venv-test-department-pipeline uv run ruff check <changed files>
  UV_PROJECT_ENVIRONMENT=.venv-test-department-pipeline uv run python manage.py check

TASK: Implement Issue 4 — Atlas weekly retention report artifact.

Why: Keeping clients requires a weekly proof loop: what Atlas did, what happened, where the funnel broke, what changes next, and what commission/new business exists.

Implement a deterministic backend service, preferably `backend/application/services/atlas_weekly_reports.py`, with tests in `backend/tests/unit/services/test_atlas_weekly_reports.py`.

Input should be plain dicts so this remains independent from campaign/lead services for now:
- campaign summary
- activity list
- funnel metrics by stage
- lead/revenue/commission summary
- blockers/approvals needed

Required capabilities:
1. Diagnose funnel bottleneck:
   - no replies -> segment/message/channel problem
   - replies but low qualified rate -> offer/targeting problem
   - qualified leads but no quotes/citas -> trust/pricing/sales process problem
   - quotes/citas but no wins -> closing/fulfillment/economics problem
   - wins with acceptable economics -> scale
2. Generate Spanish client report sections:
   - Qué hicimos esta semana
   - Qué resultados vimos
   - Qué aprendimos
   - Dónde se atoró el funnel
   - Qué cambiaremos la próxima semana
   - Leads/ventas/comisión
   - Qué necesitamos aprobar o confirmar
3. Generate operator payload with scale/kill/iterate recommendation.
4. Keep tone concise, non-generic, and owner-friendly.

Tests:
- no reply scenario recommends changing segment/message/channel, not spending more.
- qualified-no-sales scenario diagnoses close/trust/pricing.
- wins scenario recommends scale with guardrails.
- report includes explicit next actions and commission summary.

Out of scope:
- Live analytics ingestion.
- UI.
- Provider sends.
- DB models.

Commit when done.
