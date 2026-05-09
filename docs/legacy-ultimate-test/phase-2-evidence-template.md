# Legacy Glasswear Phase 2 Evidence Packet

Date:
Operator:
Branch/commit:

## Commands

```bash
cd backend
python manage.py seed_legacy_glasswear_phase0 --password "$LEGACY_TEST_PASSWORD" --json
python manage.py import_legacy_inventory_phase2 --json
pytest tests/unit/services/test_inventory.py tests/unit/api/test_inventory_api.py tests/unit/management/test_import_legacy_inventory_phase2.py
```

## CSV Import Result

- CSV path:
- Products seen:
- Active stock units:
- Warnings:

Paste sanitized JSON output:

```json
{}
```

## Reservation Walkthrough

- Company ID:
- Product/SKU:
- Starting available units:
- Reservation ID:
- Idempotency key:
- Available units after hold:
- Held units after hold:

## No-Oversell Proof

- SKU with one remaining unit:
- First hold result:
- Second hold result:
- Final available units:
- Final reserved units:
- Drift observed:

## Expiry Or Release Proof

- Reservation ID:
- Action:
- Available units before:
- Available units after:
- Inventory event ID:
- Drift observed:

## Operator Surface Check

Answer from product/API surfaces, not raw logs:
- What stock is at risk?
- What is currently held?
- Which holds are expiring?
- What changed in the inventory timeline?

## Decision

- Phase 2 accepted:
- Blocking bugs:
- Next iteration:
