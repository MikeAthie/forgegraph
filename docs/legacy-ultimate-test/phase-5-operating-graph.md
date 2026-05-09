# Phase 5: Generic Company Operating Graph

Phase 5 exercises the generic ForgeGraph company operating-loop module through the Legacy Glasswear test company. Legacy is only the fixture; the feature surface is reusable for any company.

## Goal

Prove that commerce, inventory, media, archive, approvals, decisions, and operating briefs can turn real company signals into human-gated work without raw-log dependency.

## Required Walkthrough

1. Capture or import one sanitized demand/lead/stockout signal.
2. Qualify the signal into an opportunity.
3. Launch a daily operating brief operation from the Company Operating Loop panel.
4. Verify the operation has an objective contract with run goal, hypothesis,
   target signal, six-department action plan, and integrity gates.
5. Launch at least one context-specific operation:
   - paid-order follow-up
   - fulfillment exception review
   - sold-out demand capture
   - content drop planning
   - reorder/procurement approval
6. Record objective evaluation with success score, miss analysis, and next decision.
7. Create or inspect a publication draft and request human approval.
8. Create or inspect a procurement draft and request human approval.
9. Verify the operator can answer from product surfaces:
   - what sold
   - what is stuck
   - what stock is at risk
   - what cash changed
   - what the company learned
   - what it decided
   - what happens next

## No-Go Conditions

- Duplicate source signals create duplicate operations or decisions.
- A run has no objective contract or miss analysis after review.
- Gemini context includes payment details, addresses, private buyer data, private notes, Stripe IDs, or checkout URLs.
- A publication or procurement draft becomes externally actionable without human approval.
- The operator needs raw logs or ad hoc DB inspection to explain the company state.

## Evidence Required

Use `phase-5-evidence-template.md` for the dated packet. Include signal IDs, opportunity IDs, draft IDs, operation IDs, objective contract IDs, success score, miss analysis, approval task IDs, decisions, archive links, duplicate-trigger proof, and walkthrough notes.
