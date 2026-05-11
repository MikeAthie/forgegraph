# Legacy Glasswear Iterative Test Roadmap

This document turns the Legacy Glasswear research into an executable ForgeGraph
test program. It is intentionally a measured learning loop, not a one-time
launch plan.

`docs/architecture/runtime-invariants.md` governs this work. The backend remains
the only durable source of truth. Stripe, storefront pages, webhooks, Instagram,
WhatsApp, Gemini, the engine, and runtime events may trigger or execute work, but
they must not become authoritative durable state.

## Goal

Use Legacy Glasswear as ForgeGraph's ultimate real-world test: operate a small
inventory business with limited stock, real checkout events, human approvals,
agent work, operational dashboards, and continuous evidence gathering.

The operating loop is:

```text
add feature or fix bug -> test -> gather data -> decide -> iterate
```

Every shipped feature or bug fix must leave behind evidence: the hypothesis, the
test or walkthrough, the observed data, the failure or learning, and the next
decision.

Every company operation must also carry an objective contract. Iteration should
answer "why did this run miss the objective?" before it turns into "what bug do
we fix next?"

## Methodology

- Start each feature with a hypothesis, expected signal, test command or
  walkthrough, and rollback or fix rule.
- Keep loops short before going live: one capability, one test, one evidence
  packet.
- During live assisted operation, run daily business loops against real
  inventory and real buyer behavior.
- Treat every bug as a missing regression test. The bug is not closed until the
  regression exists and passes.
- Do not add automation that cannot be inspected from product or operator
  surfaces.
- Treat Playwright video capture as an evidence and storytelling layer, not an
  implementation layer. Product behavior must still be driven by backend-owned
  state and product APIs; recordings only document the process.
- Keep customer-sensitive data out of Gemini prompts. Agents should receive
  sanitized order, stock, cash, and demand context, not payment details,
  addresses, or private customer data.

## Architecture Direction

### Clean Legacy Workspace

- Create a dedicated user for the test.
- Create a single organization for that user.
- Create one ForgeGraph company named `Legacy Glasswear`.
- Verify the user has no unrelated organizations or companies in the workspace.

### Backend-Owned Commerce State

ForgeGraph needs durable backend primitives for the business, separate from
ForgeGraph subscription billing:

- products and SKUs
- stock units
- reservations with expiry
- orders
- payments
- shipments
- cash ledger entries
- leads
- publications
- opportunities
- reorder drafts

Stripe customer checkout must not reuse `/api/billing/checkout` or
`TenantSubscription`; that code is for ForgeGraph's own tenant billing. Legacy
Glasswear checkout needs separate storefront/order APIs backed by Legacy
commerce state.

### Storefront And Stripe

The storefront should use backend APIs such as:

- `GET /api/storefront/<company_slug>/products`
- `POST /api/storefront/<company_slug>/checkout-sessions`
- `POST /api/storefront/stripe/webhook`

Required behavior:

- Checkout creation creates or confirms a backend-owned reservation before
  redirecting to Stripe.
- `checkout.session.completed` commits the order and consumes stock exactly
  once.
- `checkout.session.expired` releases the reservation.
- Duplicate, delayed, and out-of-order Stripe events are idempotent.
- Every order/payment state transition is inspectable from operator surfaces.

### Gemini BYOK

The repo already stores `google` credentials, but the engine currently routes LLM
requests only to OpenAI and Anthropic. Gemini BYOK therefore needs end-to-end
support before it can power Legacy operations:

- Add a Gemini client to the engine multi-provider gateway.
- Route `provider=google` to Gemini with a Google AI API key resolved from the
  backend credential store.
- Use a Gemini model in Legacy company graphs instead of hard-coded OpenAI
  models.
- Capture provider, model, latency, usage, errors, and failure mode in normal
  run output and accounting surfaces.

### Gemini Media Generation

Image and video generation are first-class reasons to connect Gemini for Legacy
Glasswear. Google currently exposes image generation through Gemini-native image
models and Imagen, and video generation through Veo long-running operations.

ForgeGraph should support this as backend-owned media generation, not as hidden
engine state:

- Agents may request image drafts, image edits, video briefs, and video draft
  generations for content drops and product storytelling.
- The backend must persist every prompt, provider, model, generation operation
  name, output URI, asset version, review status, error, and retry result.
- `Asset.asset_type=image` stores generated images; `Asset.asset_type=video`
  stores generated video outputs.
- Veo generation is asynchronous, so operation polling and recovery state must
  be backend-owned.
- Generated media starts as draft-only and needs human approval before
  publication while tone, rights, and brand safety are calibrated.
- Gemini must receive sanitized product, styling, and campaign context only. It
  must not receive payment details, addresses, or private customer messages.
- Exact media model IDs should be selected during Phase 1 by API-key access and
  availability, not hard-coded in Phase 0.

Reference docs checked for this capability:

- https://ai.google.dev/gemini-api/docs/image-generation
- https://ai.google.dev/gemini-api/docs/imagen
- https://ai.google.dev/gemini-api/docs/video

### Operator Surfaces

The Legacy operator must be able to answer without raw logs or ad hoc database
inspection:

- What sold?
- What is stuck?
- What stock is at risk?
- What cash is available?
- What did the company learn?
- What did it decide next?

Minimum surfaces:

- inventory and stock risk
- reservations and expiry
- paid, pending, failed, expired, and fulfilled orders
- cash ledger and reorder fund
- content/publication pipeline
- lost demand caused by sold-out products
- agent operations, approvals, and deliverables

### Objective Run Contract

The primary operating objective is sell-through learning: turn limited inventory
into validated demand and next-action evidence while preserving stock, cash,
approval, and customer-data integrity.

Each run records:

- run goal
- hypothesis
- target signal
- routing-plus-operating-departments action plan
- integrity gates
- success score
- miss analysis
- next decision

The first full run is a rehearsal with real inventory. It can pass without a
sale if all integrity gates pass, no buyer-facing external action occurs, and
the operator gets a concrete next action from product surfaces.

### Demo Capture

Each major loop should have an optional Playwright recording path that can
produce a promo-safe walkthrough after the underlying feature has been tested.
The canonical rules live in `docs/ops/demo-capture-evidence.md`.

Standard capture moments:

- Video 1: create the company operating workspace from a clean user.
- Video 2: supervise signals, active work, approvals, drafts, and next actions.
- Video 3: show a bug-fix or duplicate-trigger regression recovering to one
  durable product state.
- Video 4: show checkout, stock, cash, and fulfillment.
- Video 5: show Gemini media drafts becoming backend-owned archive assets.

Raw recordings stay under `logs/demo-captures/` and are not committed. Evidence
packets may reference sanitized capture metadata when it helps project memory.

### Legacy Operating Model

The company should start with a compact operating model:

- Routing Department: request triage, operation recommendation, and department
  routing. It decides what work should happen next; operations execute that
  work.
- Operating System: goals, policies, approvals, priorities, and daily brief.
- Content Studio: product narratives, captions, creative variants, and drop
  plans, including Gemini image drafts and video briefs.
- Social Desk: publication schedule, comments, mentions, DMs, and lead capture.
- Sales Desk: buyer questions, model recommendations, opportunity qualification,
  and checkout follow-up.
- Ops & Inventory: stock, reservations, fulfillment state, and sold-out demand.
- Finance & Procurement: cash ledger, reorder rules, and purchase-order drafts.

Human gates remain only where they reduce real risk:

- account permissions and credential connection
- final publication approval while tone is calibrated
- fulfillment/address exceptions
- reorder authorization

## Iteration Roadmap

### Loop 0: Plan And Clean Workspace

Hypothesis: a clean user/org/company makes the test evidence easier to trust.

Deliverables:

- this roadmap document
- required secrets and data checklist
- dedicated Legacy user
- single Legacy organization
- single Legacy company graph

Required data and secrets:

- full 62-piece SKU sheet
- prices, costs, and target margins
- product photos by SKU
- product photo usage rights and creative constraints
- Gemini media generation access for image and video tests
- Gemini API key
- Stripe test secret key
- Stripe webhook secret
- storefront URL
- optional Instagram or WhatsApp credentials

Evidence:

- screenshot or API response showing the dedicated user sees only Legacy
  Glasswear
- first company workspace snapshot
- notes on missing inventory/media data
- optional Video 1 capture showing the clean workspace and company setup

### Loop 1: Gemini BYOK Execution And Media Readiness

Hypothesis: Legacy operations can run on Gemini BYOK with observable cost,
latency, and failure behavior, and the company can request Gemini media drafts
through backend-owned artifacts.

Implementation:

- add Gemini support to the engine LLM gateway
- support `provider=google` for company graph nodes
- update Legacy company creation to use Gemini by default
- add backend-owned media generation tool contracts for Gemini image and video
  drafts
- persist generated media outputs as versioned company assets before reuse
- persist Veo operation names and polling state in backend-owned records

Tests:

- unit test provider routing and credential mismatch handling
- unit test Gemini request/response parsing
- unit test media generation request validation and PII redaction boundaries
- unit test video generation operation polling state can resume safely
- integration test a Google credential can start a run
- integration test one image draft writes a backend-owned image asset
- integration test one video draft writes a backend-owned video asset after the
  async operation completes
- one live Legacy operation using Gemini BYOK

Evidence:

- run ID
- provider/model used
- latency
- token or usage data if available
- media asset IDs for generated image/video drafts
- media approval status
- failure mode if Gemini errors or quota is exhausted
- optional Video 5 capture showing draft media assets through product surfaces

### Loop 2: Inventory And Reservation Core

Hypothesis: backend-owned reservations can prevent overselling scarce inventory.

Implementation:

- product/SKU model
- stock-unit model
- reservation model with expiry
- order shell model
- operator inventory view

Tests:

- stock reservation creates one active hold
- reservation expiry releases stock
- two concurrent checkout attempts against one remaining unit cannot both win
- no stock drift after duplicate reservation requests
- tenant isolation across inventory and reservations

Evidence:

- reservation timeline
- stock before/after
- failed concurrent checkout result
- no-oversell proof

### Loop 3: Stripe Checkout And Webhook Fulfillment

Hypothesis: Stripe checkout can become a reliable transport signal while the
backend remains the source of truth for paid orders and stock.

Implementation:

- storefront checkout-session endpoint
- Stripe checkout metadata linking session, company, reservation, and order
- Stripe webhook endpoint for Legacy storefront events
- idempotency records for Stripe events and checkout sessions
- order state transitions and cash ledger writes

Tests:

- checkout session creates a reservation
- completed checkout marks exactly one order paid
- expired checkout releases reservation
- duplicate `checkout.session.completed` does not duplicate order, stock, or cash
- out-of-order expired/completed events resolve through explicit backend policy
- invalid Stripe signature is rejected

Evidence:

- Stripe test event IDs
- order timeline
- stock transition
- cash ledger entry
- duplicate-event proof

### Loop 4: Operator Dashboard

Hypothesis: a human can operate Legacy Glasswear from ForgeGraph surfaces without
raw logs or database inspection.

Implementation:

- inventory risk panel
- reservation/order panel
- cash and reorder fund panel
- stuck work panel
- learned demand panel
- recent decisions/deliverables panel

Walkthrough:

- identify what sold today
- identify stuck orders or expired reservations
- explain current stock risk
- explain available cash and reorder fund
- explain what the company learned and decided

Evidence:

- walkthrough notes
- screenshots or screen recording
- missing-surface backlog
- optional Video 2 capture showing the operator supervising the company without
  raw logs

### Loop 5: Legacy Operating Graph

Hypothesis: the company graph can turn commerce events and inventory context into
useful business work with controlled human gates.

Phase artifact: this loop is implemented through the generic ForgeGraph company
operating-loop module documented in `docs/ops/company-operating-loop.md`; the
Legacy-specific walkthrough and evidence template live in
`phase-5-operating-graph.md` and `phase-5-evidence-template.md`.

Implementation:

- daily operating brief operation
- content drop planning operation
- paid-order follow-up operation
- fulfillment exception operation
- sold-out demand capture operation
- reorder approval operation

Tests:

- each workflow can be launched manually
- a paid Stripe order can trigger or update the correct operation
- human gates pause and resume safely
- duplicate event triggers do not create duplicate business decisions
- deliverables are archived and visible from the company workspace

Evidence:

- operation IDs
- objective contract IDs
- success score
- miss analysis
- next decision
- approvals
- deliverables
- archived decisions
- learned policies or rejected policy candidates
- optional Video 3 capture proving duplicate triggers or bug-fix reruns converge
  to one durable product result

### Loop 6: Live Assisted Run

Hypothesis: ForgeGraph can operate Legacy Glasswear as a real microbusiness while
learning what to build next.

Execution:

- run for 7 to 14 days
- use real inventory
- use Stripe live mode only after test-mode no-oversell and duplicate-event
  proofs pass
- keep publishing and fulfillment approvals human-controlled until confidence
  improves
- fix the highest-friction bug or missing surface before adding more automation

Daily evidence:

- sell-through by SKU
- checkout conversion
- DMs or leads
- lead-to-sale rate
- response time
- payment failures
- reservation expiry
- stock drift
- cash and reorder fund
- sold-out demand
- operator notes

Exit criteria:

- no silent stock drift
- no duplicate cash accounting
- no raw-log dependency for operating the company
- operator can explain what sold, what is stuck, what it cost, what it learned,
  and what it decided
- next iteration is selected from observed data, not guesswork

## Regression Test Matrix

| Area             | Required regression                                                                                                                                                                         |
| ---------------- | ------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| Gemini           | Provider routing, credential resolution, response parsing, quota/error handling, media request validation, generated image asset persistence, video operation polling and asset persistence |
| Credentials      | Google credential can be stored, used, revoked, and rejected when mismatched                                                                                                                |
| Storefront       | Product list, unavailable SKU behavior, checkout-session validation                                                                                                                         |
| Reservations     | Expiry, duplicate request handling, concurrent no-oversell                                                                                                                                  |
| Stripe           | Signature verification, completed event, expired event, duplicate events, out-of-order events                                                                                               |
| Orders           | State transitions, payment commit, fulfillment state, cancellation/refund policy                                                                                                            |
| Cash             | One ledger entry per paid order, no duplicate accounting, reorder fund allocation                                                                                                           |
| Tenant isolation | Legacy commerce objects cannot leak across organizations                                                                                                                                    |
| Operator UI      | Order/stock/cash/stuck-work visibility without logs                                                                                                                                         |
| Workflows        | Paid order and reorder workflows are idempotent and human-gated where required                                                                                                              |

## Evidence Packet Template

Each iteration should produce a short evidence packet:

```md
# Legacy Evidence Packet: <date> <loop>

## Change

- What changed?

## Hypothesis

- What did we expect to learn or improve?

## Test

- Command, walkthrough, or live scenario used.

## Observed Data

- Metrics, IDs, screenshots, or notes.

## Result

- Pass, fail, partial, or blocked.

## Bugs Or Gaps

- What broke or remained unclear?

## Decision

- Ship, rollback, fix next, or gather more data.
```

Store durable reports under `docs/legacy-ultimate-test/` when they are useful for
project memory. Store noisy raw artifacts under the existing logs/artifact
locations used by the test harness.

## Current Assumptions

- This is a measured iterative test, not a broad public launch.
- Stripe starts in test mode and moves live only after duplicate, expiry, and
  no-oversell paths pass.
- Gemini should not receive payment details, addresses, or sensitive customer
  data.
- Gemini media generation is allowed only through backend-owned draft assets
  with human approval before publication.
- Instagram and WhatsApp automation come after checkout, inventory, and operator
  visibility are stable.
- Events from Stripe or social channels are transport inputs. Backend-owned
  commerce and run state remains authoritative.
