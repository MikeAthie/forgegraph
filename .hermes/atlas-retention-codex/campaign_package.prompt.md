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

TASK: Implement Issue 2 — Atlas Conversión Local IA campaign package artifacts.

Why: After the free Growth Audit, Atlas needs an internal execution product that can keep clients: one narrow segment, one offer, one CTA, one channel, scripts, follow-up, readiness score, and scale/kill criteria.

Implement a deterministic backend service, preferably new file `backend/application/services/atlas_conversational_campaigns.py`, with tests in `backend/tests/unit/services/test_atlas_conversational_campaigns.py`.

Service should expose functions/classes that accept plain dictionaries/dataclasses and return serializable artifact payloads and markdown in Spanish. Keep no DB/migrations.

Required capabilities:
1. Build a `campaign_brief` payload from business context:
   - business_name, city/neighborhood, business_type
   - target_segment
   - offer
   - primary_cta
   - primary_channel
   - budget_mode (default low/no spend)
   - success_metric
   - commission_model
2. Build an `offer_sheet` with:
   - para_quien, que_incluye, rango_precio_optional, por_que_convierte, objeciones, respuestas, CTA.
3. Build a `funnel_map` with standard stages:
   - descubrimiento -> WhatsApp/landing -> calificación -> cita/cotización -> cierre -> postventa/reseña/referido.
4. Build `scripts_and_followups` for WhatsApp/outreach:
   - initial message
   - 24h follow-up
   - 72h follow-up
   - cold-lead recovery
   - safe placeholders, no fake phone numbers.
5. Build `launch_readiness_scorecard` across 10 dimensions from the roadmap:
   - segment clarity, offer strength, economics, channel fit, attribution, client effort, speed to signal, trust assets, follow-up, scale path.
   - Minimum average >=4 and no score below 3 to mark ready.
6. Render a Markdown client/operator package in Spanish.

Legacy sample must be covered in tests:
- Legacy glassware, CDMX, B2B bars/restaurants/boutique hotels, quote CTA, direct outreach/WhatsApp, commission 20-50% profit.
- Assert the output names the exact segment/offer/CTA and readiness gates.

Out of scope:
- LLM calls.
- New database models.
- WhatsApp sending.
- UI.

Commit when done.
