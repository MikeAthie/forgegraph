# Legacy Glasswear Phase 0 Checklist

Phase 0 exists to make the Legacy Glasswear test repeatable before any Gemini,
Stripe, inventory, or operator-surface implementation begins.

`docs/architecture/runtime-invariants.md` governs this work. ForgeGraph backend
state is authoritative. Storefront pages, Stripe webhooks, social channels,
Gemini, and engine events are inputs or execution paths only.

## Required Data

- [ ] Full 62-piece SKU sheet
- [ ] SKU names and model groups
- [ ] Quantity by SKU
- [ ] Price by SKU
- [ ] Cost by SKU
- [ ] Target margin by SKU or model group
- [ ] Anchor-model tag for TAYLOR, ROBBIE, VICE, HUNT, WATSON, and MAVERICK
- [ ] Scarcity tag for low-stock SKUs
- [ ] Product photos by SKU
- [ ] Product photo usage rights and source attribution
- [ ] Creative constraints for generated media: aspect ratios, style guardrails,
      blocked claims, and brand-safety notes
- [ ] Storefront URL

## Required Secrets

- [ ] Gemini API key
- [ ] Gemini image/video generation access confirmed for the selected account or
      billing tier
- [ ] Stripe test secret key
- [ ] Stripe test webhook secret

## Optional Secrets

- [ ] Instagram credentials or OAuth app details
- [ ] WhatsApp or Twilio credentials

## PII And Prompt Boundary

- [ ] Gemini receives sanitized business context only.
- [ ] Gemini does not receive payment details.
- [ ] Gemini does not receive customer addresses.
- [ ] Gemini does not receive private customer messages unless explicitly
      sanitized.
- [ ] Gemini media prompts use product, styling, and campaign context only.
- [ ] Generated images and videos are draft assets until a human approves them.
- [ ] Generated media must be persisted as backend-owned `Asset` and
      `AssetVersion` records before reuse or publication.
- [ ] Operator surfaces must show enough context to run the company without raw
      logs or ad hoc database inspection.

## Phase 0 Bootstrap

Run the bootstrap command from `backend/`:

```bash
LEGACY_TEST_PASSWORD="<set locally>" \
  python manage.py seed_legacy_glasswear_phase0 --json
```

Expected command output:

- `user_id`
- `organization_id`
- `company_id`
- `graph_version_id`
- `membership_count`
- `company_count`
- `warnings`

## Phase 0 Completion Evidence

Create a dated evidence packet from
`docs/legacy-ultimate-test/phase-0-evidence-template.md` and record:

- command output
- login result for the dedicated user
- `/api/orgs/me` result showing one organization named `Legacy Glasswear`
- `/api/graphs/` result showing one company named `Legacy Glasswear`
- latest graph version metadata showing the six-department operating model
- latest graph version metadata showing Gemini media generation as planned,
  draft-only, and backend-owned
- missing data, missing photos, and missing secrets

## Exit Criteria

- [ ] Dedicated user exists and is active.
- [ ] Dedicated user has exactly one organization membership.
- [ ] Dedicated user's default organization is `Legacy Glasswear`.
- [ ] Dedicated user has exactly one visible company graph.
- [ ] The company graph is named `Legacy Glasswear`.
- [ ] The graph metadata references `legacy-report.md` and the iterative roadmap.
- [ ] The graph profile uses assisted autonomy, BYOK AI mode, provider `google`,
      and model `gemini-2.5-flash`.
- [ ] The graph profile records Gemini image/video generation as planned Phase 1
      capability with backend-owned image/video assets.
- [ ] Phase 0 evidence packet is recorded.
