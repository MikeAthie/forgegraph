# Phase 2.5 - Graph Builder UX Improvements (n8n-inspired)

**Goal:** Enhance ForgeGraph's graph editor UX with features inspired by n8n.

**Status:** Mostly Complete

---

## 1. Node Discovery & Addition

- [x] 1.1 Add search bar in NodePalette
  - [x] Text input to filter node types
  - [x] Search across label, description, and type
  - [x] Empty state when no matches
- [x] 1.2 Quick-add mechanism (connect to selected node)
  - [x] When a node is selected, clicking palette item adds node AND creates edge
  - [x] New node positioned below selected node
  - [x] Link icon indicator when node is selected
- [x] 1.3 Categorize nodes in NodePalette
  - [x] Group nodes under category headers (AI / Logic / I/O / Annotations)
  - [x] Search includes category labels

---

## 2. Canvas Controls & Layout

- [x] 2.1 Zoom controls (React Flow Controls)
- [x] 2.2 Fit-to-view (React Flow Controls)
- [x] 2.3 MiniMap for navigation
- [x] 2.4 Auto-layout / "Tidy up" button
  - [x] Added dagre dependency for DAG layout
  - [x] "Tidy" button in canvas toolbar
  - [x] Top-to-bottom layout with configurable spacing
- [x] 2.5 Pan canvas (React Flow default)
- [x] 2.6 Multi-select nodes
  - [x] Box selection on drag (selectionOnDrag)
  - [x] Ctrl+A to select all nodes
  - [x] Updated keyboard shortcuts in palette

---

## 3. Node Interaction & Utilities

- [x] 3.1 Duplicate button in NodeInspector
- [x] 3.2 Delete icon overlay on node hover
  - [x] Red X button appears on hover/selection
  - [x] Click to delete node and connected edges
- [ ] 3.3 Node toolbar on selection (skipped - covered by 3.1, 3.2)
- [x] 3.4 Disable/enable node toggle
  - [x] Toggle switch in NodeInspector
  - [x] Visual indicator on node (grayed out, strikethrough label)
  - [x] "disabled" badge on disabled nodes
- [x] 3.5 Sticky notes / comment nodes
  - [x] "Note" node type (editor-only) in palette
  - [x] Notes persisted in `editor_state.notes`
  - [x] Note text editable in inspector

---

## 4. Workflow Execution & Testing

> Note: Requires backend engine integration (Phase 3+). All items deferred.

- [ ] 4.1 "Run Workflow" button (deferred - needs engine)
- [ ] 4.2 Node execution status indicators (deferred - needs engine)
- [ ] 4.3 Execute single node (deferred - needs engine)
- [ ] 4.4 Output display panel (deferred - needs engine)

---

## 5. Version History & Collaboration

- [x] 5.1 Version dropdown in editor
- [x] 5.2 Unsaved changes warning on version switch
- [x] 5.3 Loading older version keeps editing enabled
- [x] 5.4 Saving after loading old version creates new version
- [ ] 5.5 Enhanced version history modal (deferred)

---

## 6. Advanced Nodes & Configuration

- [x] 6.1 Multiple output handles for Branch node
  - [x] "True" (green) and "False" (red) labeled handles
  - [x] Positioned at 30% and 70% of node width
- [x] 6.2 Multiple input handles for Merge node
  - [x] Two teal input handles at 30% and 70%
- [x] 6.3 Advanced config accordion in NodeInspector
  - [x] Collapsible "Advanced" section
  - [x] Timeout (ms) field
  - [x] Retry policy (max attempts, backoff, strategy)
  - [x] "configured" indicator when collapsed

---

## Summary

| Section | Completed | Total | Status |
|---------|-----------|-------|--------|
| 1. Node Discovery | 3 | 3 | ✅ |
| 2. Canvas Controls | 6 | 6 | ✅ |
| 3. Node Interaction | 4 | 5 | ✅ (1 skipped) |
| 4. Execution | 0 | 4 | ⏸️ (deferred to Phase 3+) |
| 5. Version History | 4 | 5 | 🟡 (1 deferred) |
| 6. Advanced Nodes | 3 | 3 | ✅ |

**Completed: 20/26 tasks** (4 deferred to engine integration, 1 deferred, 1 skipped)

---

## Files Modified

- `frontend/components/graph-editor/NodePalette.tsx` - Search, categories, quick-add indicator, note entry
- `frontend/components/graph-editor/GraphEditor.tsx` - Quick-add, multi-select, auto-layout, notes, keyboard shortcuts
- `frontend/components/graph-editor/NodeInspector.tsx` - Duplicate button, disable toggle, note editor, advanced config accordion
- `frontend/components/graph-editor/nodes/GraphNode.tsx` - Delete on hover, disable visual, Branch/Merge handles
- `frontend/components/graph-editor/nodes/NoteNode.tsx` - Sticky note rendering
- `frontend/lib/graph-conversion.ts` - Persist/load notes via `editor_state.notes` (filter from executable graph)
- `frontend/lib/graph-layout.ts` - New file for dagre auto-layout utility
- `frontend/lib/graph-types.ts` - Note editor-state type
- `frontend/package.json` - Added dagre dependency
