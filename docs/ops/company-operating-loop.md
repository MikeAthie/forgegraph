# ForgeGraph Company Operating Loop

ForgeGraph company operations are backend-owned business loops that turn durable company state into inspectable work. The engine may execute a graph operation, but the backend remains authoritative for signals, opportunities, drafts, approvals, archive assets, decisions, policies, commerce, and inventory.

## Generic Objects

- `CompanySignal`: sanitized business input such as demand, lead, stockout, content response, fulfillment issue, paid order, or manual operator signal.
- `CompanyOpportunity`: qualified demand that may become follow-up, reservation, order, or lost opportunity.
- `PublicationDraft`: human-gated content or publication draft linked to assets, media jobs, signals, or opportunities.
- `CommerceProcurementDraft`: human-gated procurement/reorder proposal with line items.
- `CompanyOperationObjective`: measurable run contract linked one-to-one to an operation, including goal, hypothesis, target signal, six-department action plan, integrity gates, success score, miss analysis, and next decision.
- `ContextPack`: backend-prepared, sanitized operation context built from inventory, commerce, archive, decisions, policies, signals, and opportunities.

## Operating Templates

The first generic templates are:

- daily operating brief
- content drop planning
- paid-order follow-up
- fulfillment exception review
- sold-out demand capture
- reorder/procurement approval

Each template creates inspectable backend state and a run record. Duplicate source signals must replay existing work instead of creating duplicate decisions, drafts, or operations.

Every operation starts with an objective contract. The default objective is sell-through learning: turn limited inventory into validated demand and next-action evidence while preserving stock, cash, approval, and customer-data integrity. Rehearsal operations may pass without a sale when integrity gates pass and the operator receives a concrete next action from real company context.

Objective evaluation records `success_score`, `miss_analysis`, and `next_decision`. Miss analysis must answer why the operation did not achieve the objective, not only what broke technically.

## Privacy And Authority Rules

- Buyer payment details, addresses, private notes, Stripe object IDs, checkout URLs, and status tokens are excluded from company-ops context packs.
- Publication and procurement drafts start as `draft` and require human approval before external action.
- No social publishing, buyer outreach, or procurement commitment is automatic in this module.
- Frontend panels observe and request changes; they are not durable truth.
