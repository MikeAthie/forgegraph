# Demo Capture Evidence

Demo capture is an evidence layer, not a product architecture layer. ForgeGraph
features must still be implemented through backend-owned state, APIs, engine
execution, and product surfaces. Playwright recordings exist to show those
surfaces working and to preserve a promo-safe walkthrough of the process.

`docs/architecture/runtime-invariants.md` still governs this work: recordings,
browser state, traces, and screenshots are artifacts only. They are never the
durable source of truth.

## Capture Rules

- Use real product surfaces for any recording that may be used externally.
- Keep scripted or mocked captures clearly labeled as internal previews.
- Do not record API keys, private customer messages, addresses, payment details,
  Stripe object secrets, admin dashboards, raw logs, or ad hoc database views.
- Record only seeded/demo accounts or sanitized test companies unless a real
  operator explicitly approves live capture.
- Store raw videos, traces, and screenshots under `logs/demo-captures/`.
- Commit only scripts, docs, and sanitized evidence summaries.
- Do not make video capture a required CI gate. It is slower and more fragile
  than correctness tests.

## Standard Videos

| Video | Purpose | Product path |
| --- | --- | --- |
| 1. Create the company | Show a clean user turning an objective into a company operating graph. | Login, create company, review suggested departments, launch the first operation. |
| 2. Supervise work | Show the operator watching active work, signals, drafts, approvals, and next actions. | Company workspace, Commerce tab, Operating Loop, approvals, archive/deliverables. |
| 3. Test after a fix | Show the loop of bug or duplicate trigger, regression proof, and recovered product state. | Trigger safe duplicate/retry case, inspect one durable result, show evidence packet. |
| 4. Commerce checkout | Show stock, reservation, Stripe test checkout, webhook result, cash ledger, fulfillment. | Storefront and Commerce control tower. |
| 5. Media proof | Show Gemini draft generation becoming backend-owned archive assets. | Media generation API/product surface, archive asset review, draft-only status. |

## Running Captures

Use the frontend demo Playwright config:

```bash
cd frontend
PLAYWRIGHT_DEMO_CAPTURE=true npm run demo:capture
```

Useful optional environment variables:

```bash
PLAYWRIGHT_DEMO_CAPTURE_DIR=../logs/demo-captures
PLAYWRIGHT_DEMO_COMPANY_NAME="Legacy Glasswear Demo"
PLAYWRIGHT_DEMO_COMPANY_OBJECTIVE="Operate a limited inventory commerce test with stock, cash, learning, and reorder discipline."
PLAYWRIGHT_REUSE_EXISTING_SERVER=true
```

The capture specs write sanitized JSON evidence next to the raw videos. Raw
videos are gitignored; copy only reviewed excerpts into external promo material.

## Acceptance

A capture is acceptable when:

- The visible product surface answers the intended operator question.
- The backing evidence references backend IDs or sanitized API evidence.
- No secret or sensitive customer data appears on screen or in committed docs.
- The same scenario has a separate correctness test or manual evidence packet.
