# Legacy Glasswear Phase 4: Commerce Control Tower

## Summary

Phase 4 exercises ForgeGraph's reusable commerce operations layer with Legacy Glasswear as the test company. The goal is not a Legacy-only feature; it is to prove that any company workspace can operate sales, stock risk, cash, stuck work, and fulfillment from backend-owned product surfaces.

## Scope

In scope:
- Generic storefront profile, order status token, and buyer-safe status API.
- Backend-owned fulfillment records and fulfillment timeline.
- Company workspace commerce control tower for stock, payments, orders, stuck work, cash, and fulfillment state.
- Stripe completed webhook creating one fulfillment record idempotently.
- Operator actions: block, mark ready, ship, deliver, and add note.

Out of scope:
- Live Stripe mode, refunds, fees, tax automation, and shipping labels.
- Instagram/WhatsApp automation.
- Autonomous commerce workflows.
- Sending buyer PII, addresses, payment details, or private notes to Gemini.

## Runtime Contract

- Backend remains the only durable source of truth for orders, payments, stock, fulfillment, cash ledger, and generated media assets.
- Stripe webhooks are signed transport events.
- Frontend panels and public storefront pages only observe or request backend changes.
- Public order status uses `public_status_token` and exposes only safe status fields.

## Commands

```bash
cd backend
python manage.py seed_legacy_glasswear_phase0 --password "$LEGACY_TEST_PASSWORD" --json
python manage.py import_legacy_inventory_phase2 --json
STRIPE_LEGACY="$STRIPE_LEGACY" python manage.py import_legacy_stripe_credential --json
```

## Success Criteria

- The Legacy storefront profile resolves `legacy-glasswear` through generic `CommerceStorefrontProfile`, not hardcoded service logic.
- Completed checkout creates one paid order, one sold stock mutation, one sale ledger entry, and one pending fulfillment.
- Duplicate completed events do not duplicate fulfillment, stock, ledger, payment, or event state.
- Operator can mark fulfillment ready, blocked, shipped, and delivered through authenticated APIs.
- Public buyer status page exposes safe order/payment/fulfillment status without internal IDs or Stripe IDs.
- Company workspace control tower answers: what sold, what is stuck, what stock is at risk, what cash changed, and what happens next.

## Evidence To Capture

Use [phase-4-evidence-template.md](phase-4-evidence-template.md) for every Phase 4 run.
