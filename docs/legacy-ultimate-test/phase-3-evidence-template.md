# Legacy Glasswear Phase 3 Evidence Packet

Date:
Operator:
Environment:

## Configuration

- Company ID:
- Storefront slug: `legacy-glasswear`
- Stripe mode: test
- Stripe credential ID:
- Webhook secret configured: yes/no

## Checkout Session

- Source: operator/public storefront
- Idempotency-Key:
- Product/SKU:
- Reservation ID:
- Order ID:
- Payment ID:
- Stripe session ID:
- Checkout URL returned: yes/no

## Stock Before

- Total units:
- Available units:
- Reserved units:
- Sold units:

## Paid Webhook Proof

- Stripe event ID:
- Order status after event:
- Payment status after event:
- Sold stock unit count:
- Cash ledger entry ID:
- Sale amount MXN:
- Duplicate event replay result:

## Expired Webhook Proof

- Stripe event ID:
- Order status after event:
- Payment status after event:
- Released stock units:
- Available units after release:
- Duplicate event replay result:

## Review-Required Proof

- Scenario:
- Stripe event ID:
- Order status:
- Payment status:
- Stock mutation blocked: yes/no
- Operator-visible reason:

## Operator Walkthrough

- What sold?
- What is stuck?
- What stock is at risk?
- What cash is available?
- Was any raw log or DB inspection required?

## Decision

- Result: pass/fail
- Bugs found:
- Regression tests added:
- Next iteration:
