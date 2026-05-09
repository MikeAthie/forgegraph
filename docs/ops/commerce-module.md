# ForgeGraph Commerce Module

## Summary

ForgeGraph commerce is a reusable backend-owned capability for company inventory, reservations, checkout, payments, cash ledger, storefront profiles, and fulfillment operations. Legacy Glasswear is only the first seeded test company using these primitives.

## Runtime Contract

- Backend tables own durable commerce truth.
- Storefronts, frontend panels, Stripe Checkout, Stripe webhooks, Gemini, and engine events are not authoritative.
- Stock counts are computed from `InventoryStockUnit`.
- Stripe webhooks are signed transport signals and are applied idempotently through backend services.
- Public buyer status pages expose only safe order references and status, never internal IDs, stock unit IDs, Stripe IDs, cost data, private notes, addresses, or payment details.

## Core State

- `CommerceStorefrontProfile`: company storefront slug, display name, currency, enabled flag, and optional Stripe credential.
- `InventoryProduct` and `InventoryStockUnit`: reusable SKU metadata and physical-unit stock truth.
- `InventoryReservation` and `InventoryOrderShell`: backend-owned holds and order shells.
- `CommercePayment`, `CommerceStripeEvent`, and `CommerceCashLedgerEntry`: payment state, webhook idempotency, and sale ledger.
- `CommerceFulfillment` and `CommerceFulfillmentEvent`: operator-visible fulfillment status and timeline.
- `MediaGenerationJob`, `Asset`, and `AssetVersion`: backend-owned generated media drafts.

## APIs

- Authenticated operator APIs:
  - `GET /api/commerce/overview?company_id=...`
  - `GET /api/commerce/orders?company_id=...`
  - `GET /api/commerce/orders/<order_id>`
  - `POST /api/commerce/checkout-sessions`
  - `POST /api/commerce/orders/<order_id>/fulfillment/block`
  - `POST /api/commerce/orders/<order_id>/fulfillment/mark-ready`
  - `POST /api/commerce/orders/<order_id>/fulfillment/ship`
  - `POST /api/commerce/orders/<order_id>/fulfillment/deliver`
  - `POST /api/commerce/orders/<order_id>/operator-note`
- Public storefront APIs:
  - `GET /api/storefront/<company_slug>/products`
  - `POST /api/storefront/<company_slug>/checkout-sessions`
  - `GET /api/storefront/<company_slug>/orders/<public_status_token>`
  - `POST /api/storefront/stripe/webhook`

## Evidence Rules

- Generic code must not hardcode a test company name, slug, CSV source, or artifact namespace.
- Legacy-specific values are allowed only in Legacy docs, evidence packets, management commands, and tests.
- `scripts/ci/check_commerce_agnosticism.py` enforces this boundary for reusable commerce/media/storefront code.
