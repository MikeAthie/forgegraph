# P1-F03 Implementation Tickets

## Goal
Convert `P1-F03` into reviewable implementation slices with explicit file targets, acceptance criteria, tests, and PR boundaries.

`P1-F03` is the product-surface epic for curated memory:
- users need a Memory Browser, not just APIs
- builders need graph authoring support for observation nodes
- run/debugger surfaces need to explain curated-memory usage clearly
- the Jackie-style journey must become a real, browser-proven MVP story

## Status
`P1-F03` is complete as of March 13, 2026.

Close-out references:
- `docs/mvp/p1-memory-qa-matrix.md`
- `docs/mvp/p1-memory-narrative.md`

## Dependency
`P1-F01` and the runtime/read-model parts of `P1-F02` should be merged or stable first.

This ticket set assumes:
- `MemoryObservation` exists
- observation APIs exist
- observation runtime nodes exist
- run detail exposes memory activity needed for debugger UI

## Current Repo Reality
The current codebase already has:
- graph editor, palette, node forms, inspector, and wizard infrastructure
- run detail pages, debugger surfaces, and Playwright authoring harnesses
- agent authoring and Jackie-style mocked workflows
- marketplace-backed integration install flows and browser proofs

The current gap is specific:
- there is no Memory Browser page
- there are no observation-node authoring forms in the editor
- run pages do not yet explain curated-memory save/reuse behavior as a first-class UX
- the Jackie memory-first journey is not yet packaged as the supported MVP proof

## Ticketing Strategy
The safest split is:
1. Memory Browser page and API consumption
2. graph editor authoring support for observation nodes
3. run/debugger memory UX
4. Jackie-style workflow packaging and template/demo assets
5. browser-level proof and QA matrix

This keeps product UX changes reviewable and avoids one giant frontend PR.

---

## PR-1: Memory Browser Page and API Integration

### Objective
Create the first product-level curated-memory surface: a Memory Browser that lets users search, filter, inspect detail, and view timelines.

### Scope
- page route
- API client additions
- search/detail/timeline views
- read-only UX

### Expected Files

#### Frontend files
- `frontend/pages/memory.tsx` (new)
- `frontend/lib/api.ts`
- `frontend/components/memory/*` (new components as needed)
- `frontend/__tests__/unit/pages/memory.test.tsx` (new)

#### Optional backend files if response shaping must change
- `backend/adapters/api/memory/serializers.py`
- `backend/adapters/api/memory/views.py`

### Acceptance Criteria
- [x] Users can search observations from product UI.
- [x] Users can inspect observation detail and timeline.
- [x] Scope, recency, and observation type are visible.
- [x] Empty, loading, and no-results states are handled cleanly.

### Tests
- frontend unit tests for page states and API consumption
- backend integration tests only if read-model changes are needed

### PR Boundary Notes
- Keep graph authoring out of this PR.
- Keep heavy debugger changes out of this PR.

---

## PR-2: Observation Node Authoring in the Graph Editor

### Objective
Allow users to add and configure curated-memory node types directly from the editor.

### Scope
- palette entries
- node config forms
- inspector support
- node rendering labels and validation states

### Expected Files

#### Frontend files
- `frontend/components/graph-editor/GraphEditor.tsx`
- `frontend/components/graph-editor/NodeConfigDialog.tsx`
- `frontend/components/graph-editor/NodeInspector.tsx`
- `frontend/components/graph-editor/forms/ObservationSaveNodeForm.tsx` (new)
- `frontend/components/graph-editor/forms/ObservationSearchNodeForm.tsx` (new)
- `frontend/components/graph-editor/forms/ObservationContextNodeForm.tsx` (new)
- `frontend/components/graph-editor/forms/ObservationTimelineNodeForm.tsx` (new)
- `frontend/components/graph-editor/NodePalette.tsx`
- `frontend/lib/node-palette-catalog.ts`
- `frontend/__tests__/components/graph-editor/*`

### Acceptance Criteria
- [x] All curated-memory node types can be added from the editor.
- [x] Users can configure required node fields without raw JSON editing.
- [x] Validation and empty-state guidance are clear.
- [x] Node labels and inspector views make curated-memory nodes understandable.

### Tests
- graph editor interaction tests
- node form rendering and save tests
- validation tests for required config

### PR Boundary Notes
- Do not attempt the full Jackie journey in this PR.
- Authoring should consume the already-stable runtime contracts.

---

## PR-3: Run and Debugger UX for Curated Memory

### Objective
Make run pages and debugger surfaces explain what memory was saved, what was reused, and how it affected the run.

### Scope
- run detail rendering
- node trace drill-down
- memory event grouping
- memory influence summaries

### Expected Files

#### Frontend files
- `frontend/pages/runs/[runId].tsx`
- `frontend/components/runs/*` or equivalent run-detail components
- `frontend/lib/api.ts`
- `frontend/__tests__/unit/pages/runs.test.tsx`

#### Optional backend files if payload shaping is still needed
- `backend/adapters/api/runs/serializers.py`
- `backend/adapters/api/runs/views.py`

### Acceptance Criteria
- [x] Run pages show memory saves, searches, and context use in readable groups.
- [x] Users can tell which memory items influenced a prompt/agent step.
- [x] Raw payloads remain drill-down, not the default UX.
- [x] Non-memory runs do not regress.

### Tests
- run-page rendering tests
- backend integration tests only if read-model changes are required

### PR Boundary Notes
- Keep the Memory Browser route out of this PR if already landed in PR-1.
- Focus on understanding, not on adding new runtime behavior.

---

## PR-4: Jackie-Style Supported Journey and Template Packaging

### Objective
Package one supported memory-first workflow that demonstrates the MVP story clearly and honestly.

### Scope
- one memory-first template or seeded graph
- product copy and prerequisites
- narrow integration set for the demo
- no broad template expansion

### Expected Files

#### Frontend / docs files
- template metadata files or seeded data locations used by the app
- onboarding/help copy if needed for the supported journey
- `docs/mvp/mvp-tasks-p1.md`
- related product docs where the supported journey is listed

#### Optional backend files
- seed or template endpoints only if the supported workflow is server-seeded

### Acceptance Criteria
- [x] One supported Jackie-style workflow exists and is documented.
- [x] The workflow demonstrates:
  - explicit observation save
  - later retrieval through context
  - final agent answer using that context
- [x] Required integrations are narrow and clearly documented.
- [x] The product story is memory-first, not a generic template gallery.

### Tests
- template metadata tests if applicable
- smoke coverage for seeded/demo graph validity

### PR Boundary Notes
- Do not broaden the marketplace or template catalog here.
- Keep the supported journey opinionated and narrow.

---

## PR-5: Browser Proof and QA Matrix

### Objective
Prove the supported memory-first journey in Playwright and formalize the QA matrix for the P1 phase.

### Scope
- Playwright E2E
- QA checklist updates
- known limitations documentation

### Expected Files

#### Frontend tests
- `frontend/__tests__/e2e/*.spec.ts` covering:
  - Memory Browser search/detail
  - observation-node authoring
  - save -> later retrieval workflow
  - Jackie-style memory-backed run

#### Docs
- `docs/ops/*` or `docs/mvp/*` QA notes as appropriate
- `docs/mvp/mvp-tasks-p1.md`
- `docs/mvp/p1-f03-implementation-tickets.md`

### Acceptance Criteria
- [x] Browser-level proof exists for the supported memory journey.
- [x] The proof covers authoring, run execution, and visible memory influence.
- [x] Known limitations are documented explicitly.
- [x] P1 has a usable QA matrix instead of ad hoc demo steps.

### Tests
- Playwright specs for the supported journey
- supporting unit tests if selectors or run components change significantly

### PR Boundary Notes
- This is where the feature should feel complete from a buyer/demo perspective.
- Keep the QA proof deterministic; use mocks where external providers would make the run flaky.

---

## Recommended Merge Order
1. PR-1
2. PR-2
3. PR-3
4. PR-4
5. PR-5

## Final Ticket-Level Definition of Done
- [x] Users can browse curated memory from the product UI
- [x] Builders can author curated-memory nodes in the graph editor
- [x] Run/debugger surfaces explain memory usage clearly
- [x] One Jackie-style workflow demonstrates the full memory-first story
- [x] Browser-level proof exists for the supported P1 journey
