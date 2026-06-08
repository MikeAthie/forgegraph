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

TASK: Implement Issue 3 — Atlas lead/revenue/profit/commission tracker artifacts.

Why: Atlas wants to charge by commission/success. Retention depends on dispute-resistant attribution from lead -> sale -> profit -> commission.

Implement a deterministic backend service, preferably `backend/application/services/atlas_lead_tracking.py`, with tests in `backend/tests/unit/services/test_atlas_lead_tracking.py`.

Required capabilities:
1. Define serializable lead records using dataclasses or plain dict functions. Fields:
   - lead_id
   - prospect_name/company (optional)
   - source/channel/campaign_id
   - status: prospect, contacted, replied, qualified, quoted, won, lost
   - attribution: atlas_sourced/manual_referral/client_existing/unknown
   - revenue_collected
   - direct_cost
   - estimated_profit
   - commission_rate
   - commission_due
   - evidence_notes
   - next_action
2. Normalize and validate statuses/attribution. Unknown invalid values should raise a safe ValueError or domain error.
3. Commission calculation:
   - profit = revenue_collected - direct_cost unless estimated_profit explicitly provided.
   - commission_due = max(profit, 0) * commission_rate.
   - default conservative commission_rate 0.20, allow up to 0.50 for Legacy-style dormant project cases.
   - never produce negative commission.
4. Aggregate report payload:
   - total leads, qualified, quoted, won, lost
   - revenue, profit, commission_due
   - open followups
   - attribution breakdown
5. Markdown commission statement in Spanish for the client:
   - separates leads, qualified leads, closed sales, profit assumptions, commission due, disputed/unknown items.
6. CSV export helper string for operator tracker.

Tests:
- Legacy example with one won sale at 50% profit share and one open quote.
- 20% conservative baseline.
- negative/zero profit produces zero commission.
- invalid status rejected.
- markdown does not include raw sensitive phone-like values if metadata includes one; redact or omit raw PII.

Out of scope:
- DB models/migrations.
- Payment collection.
- CRM integration.
- WhatsApp provider integration.

Commit when done.
