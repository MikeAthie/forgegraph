# ATLAS Legacy Consult Scenario

This live Playwright scenario covers an ATLAS consulting engagement where ATLAS is the operator `Organization` and `Legacy Eyewear` is the customer `Company`.

## What The Test Proves

- Legacy Eyewear remains one customer `Company`.
- Legacy Marketing, Legacy Accounting, Legacy Legal, and Legacy Consulting are not created as separate companies.
- Legacy internal capabilities are represented as `PackInstallation` records under the same company.
- ATLAS can use the real backend/runtime/LLM path from the existing company workspace UI.
- The resulting strategy is materialized through generic primitives: `WorkArtifact`, `ReportRun`, service history, `CompanySignal`, and, when approved by the review board, service deliverable and approval.
- Captured frontend API requests stay on generic routes and never use `/api/marketing/*`.

## What Is Fixture-Backed

- Test users for `atlasOperator`, `legacyOwner`, and `otherClientUser`.
- One ATLAS/operator organization namespace per Playwright run and worker.
- One `Legacy Eyewear` customer company plus one unrelated client company.
- Legacy company context for `Legacy DEPP GOLD`, `599 MXN`, inventory, specs, brand constraints, metrics, current capabilities, and missing execution connectors.
- Generic service catalog item and service engagement via `/api/service-catalog` and `/api/service-engagements`.
- Generic service deliverable linked to the generated artifact/report.
- Generic publication approval checkpoint when the deliverable is ready.

The customer-facing service request UI does not exist yet, so the scenario records `operationCreationMode=backend-fixture`.

## What Is Live/UI-Driven

- Browser login and role switching for the Legacy owner, ATLAS operator, and unrelated client.
- Navigation through `/companies`, `/companies/:companyId`, and `/approvals`.
- Real operation launch from the existing company workspace Command Ops UI.
- Real backend-owned run completion polling.
- Real LLM-backed output generation.
- Real AI quality judging of the generated strategy before customer delivery.

The expected launch result is `launchMode=ui` with `fallbackAllowed=false`.

## Quality Judge

The ATLAS consult spec runs a second backend-owned live LLM pass as a quality judge after the strategy report is generated and before the customer deliverable and approval checkpoint are created.

The judge returns `schema_version=consulting_review_board_v1`, a strict 1-5 review-board scorecard across:

- ATLAS as the consulting/provider `Organization`.
- Legacy Eyewear as the customer/operator `Company`.
- The engagement itself.

The scorecard is persisted through the generic `/api/evaluations/run` path as `EvaluationRun` and `EvaluationScorecard` with profile id `consulting_ops_demo.v1.quality_judge`. Only sanitized review-board fields are persisted: schema version, decision, hard-fail flag, 1-5 averages, public section rationales, public improvements, approval gate, and company improvement plan. Judge prompts, raw reasoning, raw evidence bundles, private config, pack manifests, and internal traces must not appear in the customer UI or evaluation payload.

Default decision gates:

- `client_ready`: `overall_average >= 4.2`, no score below `3`, no hard fail, approval gate `approved_for_review`, and at least one generic next step such as `CompanySignal` or `OperationRecommendation`.
- `revision_required`: `overall_average >= 3.3`, no hard fail, but important areas still need work.
- `fail`: `overall_average < 3.3`, any hard fail, or critical boundary/safety areas scored `1`.

The customer deliverable, service history, missing-capability signal, and approval checkpoint are materialized only when the review board allows `approved_for_review`. If the judge returns `revision_required`, the test creates or verifies a generic `CompanySignal` for required improvements instead of pretending the work is client-ready. `LIVE_LLM_JUDGE=false` can be used for infrastructure diagnosis, but the normal acceptance run leaves the judge enabled.

Revision-loop automation is intentionally deferred. A future pass should create one revision operation from judge findings when the score is below threshold, judge again, and either deliver the improved strategy or block approval with revision required.

## What Remains Blocked

The missing product slice is the ATLAS customer-facing service request UI:

- Legacy customer opens a generic service catalog.
- Legacy selects a growth strategy / launch readiness consult.
- Legacy completes intake and submits the request.
- A generic service engagement and operation are created from the UI.
- ATLAS operator sees the assigned work.

When that exists, this scenario should move from `operationCreationMode=backend-fixture` to `operationCreationMode=customer-ui`.

## Missing Connectors

The test must not fake publishing to social, email, WhatsApp, or a landing page. If those execution connectors are unavailable, the system records missing executable capabilities as a generic `CompanySignal`. That keeps the test honest: it proves strategy, deliverable, approval, and next-step signaling without pretending an external deployment happened.

## How To Run

From `frontend/`:

```powershell
$env:LIVE_LLM_E2E='true'
$env:LIVE_LLM_PROVIDER='google'
Remove-Item Env:\LIVE_LLM_ALLOW_BACKEND_FALLBACK -ErrorAction SilentlyContinue
$env:USE_SQLITE='true'
$env:PLAYWRIGHT_WORKERS='2'
$env:PLAYWRIGHT_RUN_ID="atlas-legacy-$(Get-Date -Format 'yyyyMMdd-HHmmss')"
$env:SQLITE_DB_PATH="$env:TEMP\forgegraph-$env:PLAYWRIGHT_RUN_ID.sqlite3"
npx playwright test __tests__/product-modes-live --project=chromium --workers=2
```

Expected evidence:

- `Running 3 tests using 2 workers`
- `operationCreationMode=backend-fixture`
- `launchMode=ui`
- `fallbackAllowed=false`
- `qualityJudgeAverage` between `1` and `5`
- `schema_version=consulting_review_board_v1`
- `decision=client_ready` or honest `revision_required`
- no `/api/marketing/*` requests

## Video Output

`atlas-legacy-consult.e2e.spec.ts` uses `test.use({ video: "on" })`.

After the live run, Playwright writes the video under:

```text
frontend/test-results/<atlas-legacy-consult-output-dir>/video.webm
```

The judge scorecard and persisted evaluation JSON are attached to the same Playwright test result as:

```text
atlas-legacy-consult-scorecard
atlas-legacy-consult-evaluation
```

The HTML report for that same run can be opened from:

```powershell
cd frontend
npx playwright show-report
```

Important: a later Playwright command can clean `frontend/test-results` and rewrite `frontend/playwright-report`. Open or preserve the video before running another suite if the video is needed as durable evidence.
