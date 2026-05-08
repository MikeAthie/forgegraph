# Legacy Glasswear Phase 3: Stripe Checkout And Webhook Fulfillment

## Scope

Phase 3 proves ForgeGraph's reusable one-time checkout and webhook fulfillment primitives, with Legacy Glasswear as the first seeded test company. ForgeGraph backend remains the durable source of truth.

In scope:
- Operator checkout links from active holds or order shells.
- Public storefront product listing and checkout-session creation through a backend-owned storefront profile.
- Stripe-hosted Checkout Sessions in `payment` mode.
- Backend-owned order, payment, stock, Stripe event, and sale cash ledger state.
- Duplicate webhook and expired-session behavior.

Out of scope:
- Refunds, Stripe fees, tax automation, live mode, fulfillment labels, and Instagram/WhatsApp automation.
- Any claim that Stripe state is authoritative.
- Sending payment details, addresses, or private customer data to Gemini.

## Runtime Contract

- Backend stock units, order shells, payments, cash ledger entries, and processed Stripe event IDs are authoritative.
- Stripe Checkout Sessions and webhooks are external transport signals.
- `checkout.session.completed` can mark backend state paid only through the commerce service.
- `checkout.session.expired` can release backend reservations only when the order is not already paid.
- Duplicate Stripe event IDs are recorded once and replayed as no-ops.

## Commands

```bash
cd backend

STRIPE_LEGACY="$STRIPE_LEGACY" \
  uv run python manage.py import_legacy_stripe_credential --json
```

Local API smoke after Phase 2 inventory exists:

```bash
# Operator path, requires a member JWT and an active reservation.
curl -X POST http://127.0.0.1:8000/api/commerce/checkout-sessions \
  -H "Authorization: Bearer $ACCESS_TOKEN" \
  -H "Content-Type: application/json" \
  -H "Idempotency-Key: legacy-operator-checkout-001" \
  -d '{"company_id":"<company_id>","reservation_id":"<reservation_id>"}'

# Public storefront listing.
curl http://127.0.0.1:8000/api/storefront/legacy-glasswear/products
```

Webhook endpoint:

```text
POST /api/storefront/stripe/webhook
```

The webhook is `AllowAny` and relies on Stripe signature verification with `COMMERCE_STRIPE_WEBHOOK_SECRET`. `LEGACY_STRIPE_WEBHOOK_SECRET` remains a local compatibility alias for the Legacy test wrapper.

## Success Criteria

- Checkout creation reserves stock before calling Stripe on public checkout.
- Operator checkout returns a Stripe-hosted `checkout_url`.
- Completed webhook marks exactly one order paid, exactly one set of reserved units sold, and exactly one sale ledger entry.
- Duplicate completed webhook does not duplicate order, payment, stock, ledger, or event state.
- Expired webhook releases an unpaid reservation and marks order/payment expired.
- Expired webhook after completed payment does not release sold stock.
- Completed webhook after an expired/released reservation becomes `payment_review_required` instead of overselling.
- Operator panel shows checkout link, payment status, paid/expired/review states, and the sale timeline without raw logs.

## Evidence To Capture

- Stripe test session ID.
- Stripe event IDs.
- Order ID and reservation ID.
- Stock counts before and after checkout.
- Payment status and order status.
- Cash ledger entry ID and amount.
- Duplicate-event proof.
- Expired-session proof.

Use [phase-3-evidence-template.md](phase-3-evidence-template.md) for each run.
