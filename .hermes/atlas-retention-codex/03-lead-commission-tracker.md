## Goal
Make the commission/success-fee model operational with deterministic lead, revenue, profit, and commission artifacts.

## Scope
- Lead status normalization.
- Attribution categories.
- Profit and commission calculations.
- Aggregated report payload.
- Spanish commission statement.
- CSV export helper.

## Out of scope
- DB models.
- Payment collection.
- CRM integration.

## Success criteria
- Legacy-style 50% profit share and conservative 20% baseline are both covered.
- Negative profit never creates negative commission.
- Invalid statuses are rejected.
