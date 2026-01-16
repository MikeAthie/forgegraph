# Phase 2 - Graph Builder UI (Weeks 4-5)

**Goal:** Visual editing experience.

**Deliverable:** Visual graph editor fully functional, with graph JSON persisted (GraphVersion) and loadable back into the editor.

---

## 1. Scope & Contracts

- [x] 1.1 Confirm UI stack decision
  - [x] Use existing NextJS app (`frontend/`) for the Graph Builder (no Django templates)
  - [x] Document any remaining rationale/tradeoffs (optional) - covered in CLAUDE.md architecture section
- [x] 1.2 Align Graph JSON contract across frontend/backend/engine
  - [x] Use `SPECS.md` section 8 ("Graph JSON contract (MVP)") as the canonical schema
  - [x] Ensure editor emits backend-valid structures:
    - [x] Top-level includes `graph_id` (and `version_id` when available), plus `metadata`
    - [x] `graph_json.nodes[]` entries include `id`, `type`, `name`, `config`
    - [x] `graph_json.edges[]` entries include `id`, `from`, `to` (plus optional `condition`, `label`)
  - [x] Decide where to store editor-only fields (positions, viewport, UI flags) so the engine can ignore them safely - stored in `editor_state`
  - [x] Add a single frontend source of truth for types (NodeType enum/union + GraphJson types) - `lib/graph-types.ts`
- [x] 1.3 Verify backend compatibility with planned payloads
  - [x] GraphVersion endpoints exist (`/api/graphs/{id}/versions`, `/latest`, `/versions/{version_id}`)
  - [x] Backend validates node/edge shape + DAG (cycle detection) via `GraphValidator`
  - [x] Backend accepts extra UI fields (positions, viewport) - they pass through without stripping
  - [x] Backend does not require `metadata`, `graph_id`, `version_id` at top level (flexible for Phase 2)

---

## 2. Integrate React Flow (Editor Foundation)

- [x] 2.1 Add React Flow dependency
  - [x] Install React Flow (`reactflow` or `@xyflow/react`) and any required peer deps
  - [x] Add React Flow CSS to the NextJS app (`styles/globals.css` or `_app.tsx`)
- [x] 2.2 Replace placeholder graph page with editor shell (`/graphs/[graphId]`)
  - [x] Keep `ProtectedRoute` + `Header` layout
  - [x] Create 3-panel layout: node palette (left) + canvas (center) + inspector (right)
  - [x] Add loading and error states for graph/version fetches
- [x] 2.3 Ensure NextJS compatibility
  - [x] If needed, use `next/dynamic` with `ssr: false` for the React Flow canvas
  - [x] Confirm `npm run build` succeeds after integration

---

## 3. Editor Data Model (GraphJson <-> React Flow)

- [x] 3.1 Add TypeScript types aligned with `SPECS.md` section 8
  - [x] `GraphJson` top-level (`graph_id`, `version_id`, `nodes`, `edges`, `metadata`)
  - [x] `GraphNodeJson` (`id`, `type`, `name`, `config`, optional `retry_policy`, `timeout_ms`, `outputs`)
  - [x] `GraphEdgeJson` (`id`, `from`, `to`, optional `condition`, `label`)
  - [x] `NodeType` union/enum matching backend node types (prompt/http/transform/branch/merge/human_gate/output)
- [x] 3.2 Implement conversion utilities (pure functions, testable)
  - [x] `fromGraphJson(graphJson) -> { nodes, edges, viewport }` for React Flow - implemented as `graphJsonToReactFlow`
  - [x] `toGraphJson({ nodes, edges, viewport, metadata }) -> graphJson` for persistence - implemented as `reactFlowToGraphJson`
  - [x] Preserve unknown keys for forward compatibility (do not drop fields the engine may need later)
- [x] 3.3 Add "empty graph" factory for graphs with no versions
  - [x] Default `nodes=[]`, `edges=[]`
  - [x] Include `metadata.name/description` from the Graph model
  - [x] Include editor UI defaults (viewport) in a dedicated, engine-safe location

---

## 4. Node Palette (Initial Node Types)

- [x] 4.1 Define Phase 2 "initial node types" set
  - [x] Provide palette entries for: Prompt, HTTP, Transform, Output
  - [x] Optionally show disabled "coming soon" entries for: Branch, Merge, Human Gate
- [x] 4.2 Implement palette UI
  - [x] Left panel listing node types with icon + short description
  - [x] Drag-to-canvas to create nodes at drop position
  - [x] Click-to-add node at viewport center (fast workflow)
- [x] 4.3 Implement node rendering (React Flow `nodeTypes`)
  - [x] Consistent node card styling (type badge + display name)
  - [x] Source/target handles for connections (single in/out for MVP)
  - [x] Selected state + focus styles

---

## 5. Canvas Interactions (Drag / Connect / Delete)

- [x] 5.1 Drag and reposition nodes
  - [x] Update positions in state on drag end
  - [x] Mark editor state as "dirty" when user changes anything
- [x] 5.2 Connect nodes with edges
  - [x] Create edges via React Flow `onConnect`
  - [x] Generate stable edge ids
  - [x] Prevent invalid edges (self-edge, duplicate edge) and surface errors clearly
- [x] 5.3 Delete nodes and edges
  - [x] Support Delete/Backspace to remove the current selection
  - [x] Ensure deleting a node removes attached edges
  - [x] Optional: confirm destructive deletion for multi-select
- [x] 5.4 Selection behavior
  - [x] Selecting a node opens its config in the inspector
  - [x] Clicking canvas clears selection
  - [x] Selecting an edge opens edge settings (label/condition) (optional)

---

## 6. Node Config Side Panel

- [x] 6.1 Build inspector panel framework
  - [x] Graph view when nothing is selected (name, description, version info, save status)
  - [x] Node view when a node is selected (type, id, name, config)
  - [x] Basic validation + inline error display for invalid fields
- [x] 6.2 Implement per-node config editors (persist into `node.config`)
  - [x] Prompt node
    - [x] Select a prompt template (fetch from prompts API; show built-in vs user prompts)
    - [x] Store `prompt_id` (or `template_id`) + a placeholder variable mapping structure
  - [x] HTTP node
    - [x] Method, URL, headers, body
    - [x] Output key/name (where this node writes into state)
  - [x] Transform node
    - [x] Expression editor (string) + output key/name
  - [x] Output node
    - [x] Final output mapping (what to return at end of run)
- [ ] 6.3 Optional advanced fields (align with `SPECS.md` section 8)
  - [ ] `timeout_ms` editor
  - [ ] `retry_policy` editor (max attempts, backoff)
  - [ ] `outputs` editor (named outputs, for future branch/merge)

---

## 7. Persist Graph JSON (Save/Load GraphVersion)

- [x] 7.1 Extend the frontend graphs API client
  - [x] `getLatestVersion(graphId)` -> GET `/api/graphs/{id}/versions/latest`
  - [x] `getVersion(graphId, versionId)` -> GET `/api/graphs/{id}/versions/{versionId}`
  - [x] `createVersion(graphId, graph_json)` -> POST `/api/graphs/{id}/versions`
- [x] 7.2 Load graph into editor
  - [x] Fetch Graph metadata (`/api/graphs/{id}`) on page load
  - [x] Fetch latest version and populate the editor, or use the empty graph factory if none exist
  - [x] Handle "no versions yet" and permission/404 errors gracefully
- [x] 7.3 Save graph JSON as a new version
  - [x] Save button (and optional Cmd/Ctrl+S) calls `createVersion`
  - [x] Serialize editor state to `graph_json` using the conversion utilities
  - [x] Update UI with returned `version` + `version_id`, and refresh versions list
- [x] 7.4 Validation and error UX
  - [x] Surface backend validation errors (missing fields, invalid node types, cycle detection)
  - [x] Map common errors to helpful UI hints (highlight offending nodes/edges when possible)
  - [x] Disable save while request is in-flight; recover cleanly on failure
- [ ] 7.5 Load older versions
  - [ ] Versions list/dropdown in editor
  - [ ] Switching versions prompts if there are unsaved changes
  - [ ] Loading an older version keeps editing enabled, but saving creates a new version (no overwrite)

---

## 8. Graph Metadata & Editor UX

- [x] 8.1 Edit graph name/description from the editor
  - [x] Inline edit or modal
  - [x] Persist via `PATCH /api/graphs/{id}`
  - [x] Keep `graph_json.metadata` in sync with Graph model fields
- [x] 8.2 Persist editor-only UI metadata
  - [x] Store node positions + viewport in `graph_json` (engine-safe location)
  - [x] Restore viewport/layout when loading a version

---

## 9. Testing & Quality

- [x] 9.1 Unit tests for graph conversion utilities
  - [x] Round-trip: GraphJson -> React Flow -> GraphJson
  - [x] Required keys always present (`nodes`, `edges`, `id/type/name`, `from/to`)
- [ ] 9.2 Component tests for editor behavior
  - [x] Add node from palette and render it
  - [x] Select node and edit config
  - [ ] Create and delete edges/nodes
- [ ] 9.3 Playwright E2E tests for graph editor flow
  - [x] Create graph -> open editor
  - [ ] Add nodes -> connect -> configure -> save
  - [x] Reload editor and verify persisted graph renders the same
- [x] 9.4 Build and regression checks
  - [x] `npm test` (unit/integration)
  - [x] `npm run test:e2e`
  - [x] `npm run build`

---

## 10. Documentation

- [ ] 10.1 Update project docs for Phase 2
  - [ ] Add a short "Graph Builder" section to `README.md` (how to use, how to save/load)
  - [ ] Update `TESTING.md` with graph editor E2E coverage and how to run it
  - [ ] Ensure `CLAUDE.md` Phase status remains accurate

---

## 11. Final Verification

- [ ] 11.1 End-to-end manual QA
  - [ ] Login -> create graph -> open editor
  - [ ] Add >= 3 nodes, connect them, configure them
  - [ ] Save and verify a new GraphVersion is created
  - [ ] Reload and confirm the graph loads identically (nodes, edges, layout)
- [ ] 11.2 Contract verification
  - [ ] Saved `graph_json` matches `SPECS.md` section 8 and passes backend validation
  - [ ] Cycle detection is enforced (backend error surfaced cleanly)
- [ ] 11.3 Clean up
  - [ ] No secrets committed; `.env*` remains untracked
  - [ ] All tests passing

---

## Summary Checklist

| Section | Tasks | Status |
|---------|-------|--------|
| 1. Scope & Contracts | 3 | ✅ |
| 2. React Flow Integration | 3 | ✅ |
| 3. Data Model | 3 | ✅ |
| 4. Node Palette | 3 | ✅ |
| 5. Canvas Interactions | 4 | ✅ |
| 6. Node Inspector | 3 | 🟡 (6.3 pending) |
| 7. Save/Load Versions | 5 | 🟡 (7.5 pending) |
| 8. Metadata & UX | 2 | ✅ |
| 9. Testing & Quality | 4 | ? |
| 10. Documentation | 1 | ? |
| 11. Verification | 3 | ? |

**Total: ~34 tasks**
