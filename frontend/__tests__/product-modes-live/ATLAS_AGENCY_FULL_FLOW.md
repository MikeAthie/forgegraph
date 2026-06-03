# ATLAS Agency Full Flow Live E2E

`PM-LIVE-ATLAS-AGENCY-001` is the canonical live acceptance test for the full ATLAS agency operating loop on top of generic ForgeGraph primitives.

The test proves that `Legacy Eyewear` can submit a customer request, an ATLAS operator can route it into a durable `WorkWhiteboard`, and the backend-owned workflow can continue through onboarding, the pack-owned agency work graph, approval, deployment preparation, performance review, and optimization routing without introducing vertical ATLAS, Legacy, or marketing APIs.

## Flow Covered

1. Legacy owner opens the Legacy company workspace and creates a customer-visible request through `CommunicationPanel`.
2. The request persists as a `CommunicationMessage`.
3. Before operator routing, no `WorkWhiteboard` exists for that message.
4. ATLAS operator clicks the generic `Route request` action on the communication message.
5. The backend classifies the request as `NEW_REQUEST` and creates exactly one `WorkWhiteboard`.
6. Onboarding context is completed and the operator marks the whiteboard ready.
7. The integrated agency phase starts from the generic whiteboard phase controls.
8. Strategy, Legal/Compliance, Tech/Martech, Media, Copy, Analytics, and Traffic workstreams fan out together.
9. Content/Creative, Timing, and Deployment-readiness workstreams remain blocked until their backend-owned hard dependencies are complete.
10. Dependency transitions unblock from `TaskRoutingRecord` and phase projection state, then the configured agency gate passes.
11. A generic `ApprovalTask` is created and resolved through the approvals UI.
12. Deployment preparation runs from `WhiteboardPanel`.
13. Available sandbox deployment channels create durable `ToolExecution` evidence.
14. Missing deployment connectors create `CompanySignal` and `TaskRoutingRecord` blockers instead of fake success.
15. Performance review starts only after deployment evidence exists.
16. Performance collection creates `MetricSnapshot`, `ReportRun`, and `EvaluationRun` evidence.
17. Optimization routing is created from policy-defined routing rules.
18. Legacy customer visibility, ATLAS operator visibility, and other-client isolation are verified.
19. Captured frontend routes are checked for no `/api/marketing/*`, `/api/atlas/*`, or `/api/legacy/*` requests.

## UI-First Steps

P1 moves the primary operator-facing Atlas run onto real UI surfaces:

- Legacy creates the initial request through `CommunicationPanel`.
- ATLAS routes the request through the communication message `Route request` action.
- ATLAS configures pack connector availability through the company operating-model workspace.
- The test asserts no whiteboard exists before routing and exactly one exists after routing.
- ATLAS enriches onboarding context through the structured `WhiteboardPanel` editor.
- ATLAS marks onboarding ready through `WhiteboardPanel`.
- ATLAS starts the integrated agency phase through generic phase buttons in `WhiteboardPanel`.
- ATLAS completes primary-run workstreams, phase synthesis, and gate evaluation through `WhiteboardPanel`.
- ATLAS resolves the whiteboard/gate approval through the approvals UI.
- ATLAS prepares deployment through `WhiteboardPanel`.
- ATLAS starts the performance review through `WhiteboardPanel`.
- ATLAS generates the performance report and evaluation through `WhiteboardPanel`.

The UI renders phase, deployment, and performance labels from policy/config contracts. The generic components do not hardcode ATLAS phase names, channel names, metric names, or gate criteria.

## Helper-Assisted Steps

The live spec attaches a `helperAssistedSteps` array to the Playwright result so every remaining non-UI step is explicit. These steps remain helper-assisted because the honest product UI does not exist yet or because they are direct verification reads:

- Follow-up memory uplift uses backend communication and phase APIs until guided follow-up campaign authoring and memory-review UI exist.
- Isolation and durable-state checks use backend API to verify DB-owned state directly.
- Evidence collection uses backend API reads to attach durable IDs, revisions, and operation state.

Helper usage is not used to fake customer-facing UI, primary-run work production, approvals, deployment success, or external connector success.

## Evidence Attachment

The spec attaches `atlas-agency-full-flow-evidence` as JSON in the Playwright output. The evidence includes:

- run namespace
- request classification
- whiteboard id, final status, and completion score
- agency phase id, gate result, approval task id, initial concurrent fan-out, and dependency transition snapshots
- approval result
- deployment status, executed channels, and blocked channels
- performance status, metric snapshot id, report run id, evaluation id, and routing record ids
- memory readiness and follow-up memory-uplift evidence
- release score summary
- `helperAssistedSteps`
- captured generic API route list
- whether communication Kafka was enabled
- live LLM provider label

The evidence is structural. It does not assert exact LLM prose.

## Required Services And Settings

- Postgres: required for the normal live backend path.
- Redis: required for live runtime/cache paths; Redis snapshots are cache only.
- Kafka: optional. Kafka remains event transport only and is not required for the default live run.
- Live LLM: required by the current live guard unless the repo's explicit live fallback/debug settings are used.
- Backend fallback: keep `LIVE_LLM_ALLOW_BACKEND_FALLBACK` unset or false for acceptance runs.
- Operating model packs: backend startup requires `digital_marketing_pro` by default and exposes `/api/system/operating-model-packs/health` for pack directory, hashes, and required Atlas policy contents.

Common environment variables:

```powershell
$env:LIVE_LLM_E2E='true'
$env:LIVE_LLM_PROVIDER='google'
$env:OPERATING_MODEL_PACKS_DIR='/operating_model_packs'
$env:REQUIRED_OPERATING_MODEL_PACKS='digital_marketing_pro'
Remove-Item Env:\LIVE_LLM_ALLOW_BACKEND_FALLBACK -ErrorAction SilentlyContinue
```

Kafka flags may be enabled for a separate transport variant, but the live acceptance path must still work through backend-owned DB/API state when Kafka is disabled.

## How To Run

Start the normal services for the live DB path:

```powershell
docker compose up -d postgres redis
```

Run the mocked product-mode regression from `frontend/`:

```powershell
$env:USE_SQLITE='true'
npx playwright test __tests__/product-modes --project=chromium
```

Run the full live spec from `frontend/`:

```powershell
$env:LIVE_LLM_E2E='true'
$env:LIVE_LLM_PROVIDER='google'
Remove-Item Env:\LIVE_LLM_ALLOW_BACKEND_FALLBACK -ErrorAction SilentlyContinue
npx playwright test __tests__/product-modes-live/atlas-agency-full-flow.e2e.spec.ts --project=chromium
```

Run the full live spec against the Docker frontend/backend and a local OpenAI-compatible LLM on `127.0.0.1:12434`:

```powershell
npm run test:e2e:atlas:docker:local-llm
```

Before a Docker live run, check that the named Docker frontend `node_modules` volume matches `frontend/package.json`:

```powershell
npm run doctor:frontend-volume
```

From the repo root, the same checks are available as:

```powershell
make doctor-frontend-volume
make test-atlas-live-docker-local-llm
```

The live spec uses video output. Open the Playwright report after a run with:

```powershell
npx playwright show-report
```

## Expected Evidence

A passing run should show:

- `RequestClassificationRecord.classification = NEW_REQUEST`.
- A persisted customer-visible `CommunicationMessage`.
- No whiteboard before the operator clicks `Route request`.
- Exactly one whiteboard after routing.
- `WorkWhiteboard` company and organization match Legacy/ATLAS scope.
- The agency phase starts from pack files, fans out initial workstreams, blocks hard-dependent work honestly, and unblocks from backend-owned completion state.
- The agency phase gate passes according to policy-defined criteria.
- Approval exists and is resolved.
- Deployment preparation produces at least one durable `ToolExecution` evidence item.
- Missing connectors produce `CompanySignal` and `TaskRoutingRecord` blockers.
- Missing connectors do not create fake `ToolExecution` success.
- Performance review starts only after deployment evidence.
- `MetricSnapshot`, `ReportRun`, and `EvaluationRun` are created.
- Optimization routing records are created from policy rules.
- Legacy customer sees only customer-safe information.
- ATLAS operator sees internal/operator work as permitted.
- Other client cannot see Legacy communication, whiteboard, approvals, deployment, performance, artifacts, signals, reports, or routing records.
- Captured route list has no `/api/marketing/*`, `/api/atlas/*`, or `/api/legacy/*`.
- Legacy remains one `Company`; no Legacy Marketing, Accounting, Legal, or Consulting companies are created.

## Architecture Guarantees

- ForgeGraph core remains generic orchestration machinery.
- ATLAS behavior comes from the `digital_marketing_pro.v1` pack files.
- Legacy Eyewear remains one customer `Company`.
- ATLAS remains the operator `Organization`.
- The backend is the only durable source of truth.
- Redis is cache/snapshot state only.
- Kafka is optional event transport only, never source of truth.
- Client UI actions call backend-owned APIs; clients do not own durable workflow state.
- Missing connectors, missing tools, and blocked channels are represented honestly as signals and routing work.
- Deployment, performance, routing, approvals, artifacts, evaluations, and communication remain company/org scoped.

## Current Known Limitations

- Follow-up memory uplift is still helper-assisted because there is no guided follow-up authoring or memory-review UI.
- There is no real WhatsApp, social provider-publish, or landing-page deployment in this live acceptance path.
- Social deployment can use generic sandbox/manual evidence when policy enables it; it must not claim provider publish without a provider call.
- Workstream authoring remains a pragmatic v1 form, not a rich artifact editor.
- Gate evaluation and performance evaluation use default scorecards from backend-owned policy criteria.
- Kafka-enabled live transport validation is optional and not part of the default live run.

## Next Maturity Steps

- Add guided follow-up authoring and memory-review UI.
- Replace compact workstream forms with richer artifact submission and review.
- Add real connector integrations for approved deployment channels.
- Add a Kafka-enabled live variant with receipt and dedupe evidence.
- Add performance optimization UI for report review and routed optimization work.

## Do Not Regress

Future changes to this test should not:

- auto-create a whiteboard when Legacy merely posts a message
- route every customer message as a new request
- hide helper-assisted steps from evidence
- replace pack-driven ATLAS behavior with hardcoded core logic
- treat Redis or Kafka as source of truth
- record fake deployment success for missing connectors
- expose internal ATLAS notes, prompts, private configs, or routing state to Legacy
- add `/api/marketing/*`, `/api/atlas/*`, or `/api/legacy/*`
- create separate Legacy Marketing, Accounting, Legal, or Consulting companies

## Current Next Target

The next maturity target is expanding generic social provider publishing beyond guarded dry-run/manual evidence once Meta credentials, app permissions, account allowlists, and content compliance gates are mature.
