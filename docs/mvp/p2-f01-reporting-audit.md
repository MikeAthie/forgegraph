# P2-F01 Reporting Audit

## Purpose
Document the current reporting, export, budget, quota, subscription, and curated-memory reporting surfaces before changing APIs or admin UX.

This closes `P2-F01` task `F01-T01`:
- inventory current reporting surfaces
- identify missing views and weak copy
- normalize the reporting vocabulary for follow-up PRs

Audit date: March 13, 2026.

## Current Surface Inventory

### Backend Reporting and Export Endpoints

#### LLM analytics
- `GET /api/analytics/llm/usage`
- `GET /api/analytics/llm/export`
- `GET /api/analytics/llm/costs`
- `GET /api/analytics/llm/budget`
- `PUT /api/analytics/llm/budget`
- `GET /api/analytics/llm/quota`
- `PUT /api/analytics/llm/quota`

#### Memory and curated-memory reporting
- `GET /api/analytics/memory/usage`
- `GET /api/analytics/memory/costs`
- `GET /api/analytics/memory/performance`
- `GET /api/memory/usage`
- `GET /api/health/memory`
- `GET /api/memory/observations/search`
- `GET /api/memory/observations/timeline`
- `GET /api/memory/observations/{id}`
- `GET /api/memory/observations/context`

#### Billing and entitlements
- `GET /api/billing/plans`
- `GET /api/billing/subscription`
- `POST /api/billing/checkout`
- `POST /api/billing/portal`

#### Governance and export-adjacent operator surfaces
- `GET /api/audit-logs/`
- `GET /api/retention/`
- `PUT /api/retention/`
- `POST /api/retention/cleanup`
- `GET /api/retention/export`
- `GET /api/policies/guardrails`
- `PUT /api/policies/guardrails`

### Frontend Pages

#### Reporting pages
- `/analytics/llm`
- `/analytics/memory`

#### Admin/operator pages
- `/admin/billing`
- `/admin/audit-logs`
- `/admin/organization`
- `/admin/sso`

#### Product memory surface that operators will still use
- `/memory`

### Frontend API Client Coverage

Implemented in `frontend/lib/api.ts`:
- LLM usage
- LLM costs
- LLM budget
- memory usage
- memory costs
- memory performance
- billing plans/subscription
- audit logs
- organizations
- memory observation search/timeline/context/detail

Missing or not exposed in the frontend API client:
- LLM export
- LLM quota
- retention policy/export
- policy/guardrail admin API
- memory health / indexing health
- any unified reporting export wrapper

## What Already Works

### Reporting
- LLM usage, costs, budget, and quota already exist at the backend layer.
- Memory usage, costs, and performance already exist at the backend layer.
- The LLM analytics page already gives a buyer-grade starting point for spend visibility.
- The memory analytics page already has exportable JSON, period controls, and a decent operator baseline.

### Commercial controls
- Billing plans and subscriptions already exist.
- Plan entitlements are already visible in billing responses and the billing page.
- Run-start enforcement already blocks on:
  - budget
  - quota
  - inactive subscription
  - plan entitlements

### Supportability foundations
- Audit logs exist and are paginated.
- Retention export already covers runs, node runs, audit logs, usage, and memory usage.
- Memory health already exposes GC, gRPC, and observation-indexing counters.

## Gaps That Matter for P2-F01

### Fragmented operator story
The current operator experience is split between:
- analytics pages
- billing page
- run failures
- audit logs
- backend-only health/export endpoints

A team admin cannot currently answer "what are we using, what is it costing, what memory footprint do we have, and why was a run blocked?" from one coherent flow.

### Missing frontend coverage for existing backend capabilities
The frontend API client and UI do not yet expose:
- LLM export
- quota status and quota editing
- retention export for operator workflows
- memory health / indexing counters
- policy summaries

### Curated-memory reporting is not observation-native enough yet
Current memory analytics are still oriented around:
- Tier 1 buffer activity
- Tier 2 key/value storage
- Tier 3 chunks

What operators will ask after P1 is more specific:
- how many observations exist
- how many are indexed
- whether indexing is failing or backlogged
- what retention posture applies to observations and chunks
- how often curated-memory retrieval is actually used

### Commercial limits are enforced but not reconciled
The product currently exposes multiple limit types:
- budget
- quota
- plan entitlement
- policy
- memory/indexing configuration state

These are real and useful, but the product does not yet explain their differences cleanly in one place.

### Export coverage is uneven
Current export support is asymmetrical:
- LLM usage has CSV and JSON export
- memory analytics page has frontend-generated JSON export only
- retention export exists but is framed around compliance/data extraction rather than operator reporting
- budget, quota, entitlement, and memory-index health do not have one obvious export path

## Vocabulary Decisions for P2-F01

Use this wording consistently across backend payloads, frontend labels, docs, and PRs.

- `usage`: measured consumption over time, such as runs, tokens, retrievals, or observations processed
- `cost`: currency-denominated spend derived from usage
- `budget`: tenant-configured spending ceiling with warning and over-budget state
- `quota`: tenant-configured hard operational limit, usually tokens or cost
- `entitlement`: plan-derived commercial limit that comes from billing/subscription state
- `policy`: governance rule that allows or denies behavior
- `memory volume`: count and footprint of curated observations plus related indexed chunks
- `indexing health`: success, error, and backlog state for observation-to-chunk indexing
- `retention posture`: the effective data lifecycle configuration currently applied to the tenant

## Recommended Next PR Scope

### P2-F01 PR-2 should do these things
- Add frontend API support for:
  - LLM export
  - LLM quota
  - memory health
- Expand backend reporting/export payloads to include observation-aware memory metrics.
- Define one export path for budget/quota/memory reporting that matches the LLM export quality bar.
- Keep changes additive and tenant-scoped.

### P2-F01 PR-3 should do these things
- Add a unified admin reporting view or overview layer.
- Make budget, quota, entitlement, and memory health visible together.
- Put exports in the UI where operators expect them.

## Explicit Non-Goals for This Audit
- redesigning billing
- creating invoices
- introducing new monetization models
- reopening P1 curated-memory architecture decisions

## Exit Condition for This Audit
`F01-T01` is complete when implementation can proceed without needing another discovery pass to answer:
- what reporting/export surfaces already exist
- what the missing operator gaps are
- which terms the product should standardize on
