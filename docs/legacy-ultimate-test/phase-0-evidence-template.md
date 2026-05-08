# Legacy Evidence Packet: <YYYY-MM-DD> Phase 0

## Change

- Seeded or verified the dedicated Legacy Glasswear user, organization, and
  company graph.

## Hypothesis

- A clean user, one organization, and one company graph make later Legacy test
  evidence trustworthy and repeatable.

## Command

```bash
LEGACY_TEST_PASSWORD="<redacted>" \
  python manage.py seed_legacy_glasswear_phase0 --json
```

## Command Output

```json
{
  "user_id": "",
  "organization_id": "",
  "company_id": "",
  "graph_version_id": "",
  "membership_count": 0,
  "company_count": 0,
  "warnings": []
}
```

## Workspace Verification

- `/api/orgs/me` shows exactly one organization named `Legacy Glasswear`.
- `/api/graphs/` shows exactly one company named `Legacy Glasswear`.
- Latest graph version contains the six Legacy departments.
- Latest graph version uses provider `google` and model `gemini-2.5-flash`.
- Latest graph version records Gemini image/video generation as planned,
  draft-only, and backend-owned.
- Backend asset choices support generated images and videos.

## Missing Data Or Secrets

- Inventory/SKU gaps:
- Photo/media gaps:
- Product photo rights:
- Gemini image/video generation access:
- Gemini key:
- Stripe test key:
- Stripe webhook secret:
- Storefront URL:
- Optional Instagram/WhatsApp access:

## Result

- Pass, fail, partial, or blocked:

## Bugs Or Gaps

- What broke or remained unclear?

## Decision

- Ship, rollback, fix next, or gather more data:
