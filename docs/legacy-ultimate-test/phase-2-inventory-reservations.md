# Legacy Glasswear Phase 2: Inventory And Reservations

## Summary

Phase 2 builds a reusable ForgeGraph inventory module, with Legacy Glasswear as the first seeded company. The backend owns products, physical stock units, reservations, order shells, and the inventory event timeline. Frontend panels and future storefronts only observe or request changes.

The Phase 2 goal is no-oversell evidence before Stripe, storefront checkout, fulfillment, Instagram or WhatsApp automation, and autonomous commerce workflows.

## Scope

In scope:
- Company-scoped products/SKUs, stock units, reservations, order shells, and inventory events.
- Idempotent Legacy CSV import from `docs/legacy-ultimate-test/Análisis costos.csv`.
- Manual operator holds with 30-minute default expiry.
- Backend APIs under `/api/inventory/`.
- A compact company workspace inventory panel.
- Tests for import, idempotency, release/expiry, no-oversell, API roles, and tenant isolation.

Out of scope:
- Stripe payment state.
- Paid, shipped, refunded, or fulfilled order state.
- Storefront checkout.
- Public social or WhatsApp automation.
- Customer PII beyond sanitized buyer alias, channel, and operator note.

## Runtime Contract

The backend is the only durable inventory source of truth. Stock counts are computed from `InventoryStockUnit` rows, not frontend state, events, or engine memory. Reservations are backend-owned holds. Events are an operational timeline, not authoritative stock state.

## Data Model

- `InventoryProduct`: reusable company SKU metadata, price/cost in MXN, photo reference, anchor/scarcity tags, and status.
- `InventoryStockUnit`: one row per physical unit, with status `available`, `reserved`, `sold`, or `removed`.
- `InventoryReservation`: active hold over one product and quantity, with status `active`, `expired`, `released`, or `converted`.
- `InventoryOrderShell`: payment-free shell created from a reservation for Phase 3 checkout work.
- `InventoryEvent`: backend-owned timeline for import, reserve, release, expire, extend, and order-shell actions.

## Commands

```bash
cd backend
python manage.py seed_legacy_glasswear_phase0 --password "$LEGACY_TEST_PASSWORD" --json
python manage.py import_legacy_inventory_phase2 --json
python manage.py import_legacy_inventory_phase2 --csv "../docs/legacy-ultimate-test/Análisis costos.csv" --json
```

## APIs

- `GET /api/inventory/overview?company_id=...`
- `POST /api/inventory/reservations`
- `POST /api/inventory/reservations/<reservation_id>/release`
- `POST /api/inventory/reservations/<reservation_id>/extend`
- `POST /api/inventory/reservations/<reservation_id>/order-shell`
- `POST /api/inventory/reservations/expire-due`

All mutating APIs require `Idempotency-Key`. Same key and same body replays the stored response. Same key with a different body returns `409`.

## Success Criteria

- CSV import creates 21 products and 62 active stock units from the Legacy cost analysis file.
- Re-running the import updates product metadata and does not duplicate stock units.
- Lowering CSV quantity removes only available units and never deletes reserved or sold units.
- Reservation creates one active hold and marks exactly the selected units as reserved.
- Duplicate reservation command replays the same response.
- Conflicting idempotency command returns `409`.
- Release and expiry restore units to `available` exactly once.
- Order-shell conversion keeps units reserved for Phase 3.
- A viewer can list inventory; a member can mutate; a viewer cannot mutate.
- Cross-tenant inventory and reservations are not visible.

## Evidence Packet

Use `phase-2-evidence-template.md` after a local walkthrough. The minimum packet records:
- CSV path and import command output.
- Stock counts before and after one hold.
- Idempotency replay result.
- Conflict result.
- No-oversell attempt against one remaining unit.
- Release or expiry result with zero drift.
- Operator panel screenshots or notes showing that stock risk and active holds are visible without raw logs.
