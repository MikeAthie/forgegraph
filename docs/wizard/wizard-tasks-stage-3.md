# Stage 3: Graph Validation & Visual Feedback

## Objective
Implement comprehensive graph validation with clear visual indicators for missing Start/End nodes and other validation errors.

## Prerequisites
- Stage 1 complete (wizard infrastructure)
- Stage 2 complete (node forms)
- Understanding of existing GraphValidator (backend)

---

## Task List

### 3.1 Define Validation Error Types
**File:** `frontend/lib/graph-validator.ts`

- [x] Create validation error interface
- [x] Define error codes enum (NO_START_NODE, NO_OUTPUT_NODE, DISCONNECTED_NODE, etc.)
- [x] Create ValidationResult type with errors array

### 3.2 Create Frontend Graph Validator
**File:** `frontend/lib/graph-validator.ts`

- [x] Implement `validateGraph(nodes, edges)` function
- [x] Check for Start node (trigger flag or START edge)
- [x] Check for End node (output node or explicit end)
- [x] Check for disconnected nodes
- [x] Check for cycles (DFS-based detection)
- [x] Check for self-connections
- [x] Return ValidationResult with all errors/warnings

### 3.3 Create Validation Context
**File:** `frontend/contexts/ValidationContext.tsx`

- [x] Create ValidationContext with React Context API
- [x] Store current validation errors
- [x] Provide `validate()` function to trigger validation
- [x] Auto-validate on node/edge changes (debounced)
- [x] Export useValidation hook
- [x] Export useNodeValidation and useEdgeValidation hooks

### 3.4 Create ValidationOverlay Component
**File:** `frontend/components/graph-editor/validation/ValidationOverlay.tsx`

- [x] Create overlay component for validation indicators
- [x] Position indicators absolutely on canvas
- [x] Show indicators for missing start/output nodes
- [x] Make indicators clickable to add missing nodes

### 3.5 Create MissingStartIndicator Component
*Combined into ValidationOverlay*

- [x] Prominent visual indicator for missing start
- [x] Amber/orange pulsing border
- [x] "Add Start Node" text
- [x] Click to add start node

### 3.6 Create MissingEndIndicator Component
*Combined into ValidationOverlay*

- [x] Prominent visual indicator for missing output
- [x] Rose/red pulsing border
- [x] "Add Output Node" text
- [x] Click to add output node

### 3.7 Create ValidationStatusBar Component
**File:** `frontend/components/graph-editor/validation/ValidationStatusBar.tsx`

- [x] Create status bar at bottom of GraphEditor
- [x] Show validation status (valid/errors/warnings)
- [x] Click to expand error list
- [x] Quick fix buttons for common errors

### 3.8 Create ValidationErrorList Component
*Integrated into ValidationStatusBar*

- [x] Expandable list of all validation errors
- [x] Error icon and message
- [x] "Go to" button to focus on problem
- [x] "Fix" button for quick fixes

### 3.9 Implement Node Highlighting for Errors
**File:** `frontend/components/graph-editor/nodes/GraphNode.tsx`

- [x] Add validation error state via useNodeValidation hook
- [x] Show red border/shadow for errors
- [x] Show amber border/shadow for warnings
- [x] Add error badge with icon
- [x] Show error tooltip on hover

### 3.10 Implement Edge Highlighting for Errors
**File:** `frontend/lib/graph-validator.ts`

- [x] Edge validation via checkSelfConnections
- [x] Edge errors tracked in validation result
- [x] useEdgeValidation hook available for future use

### 3.11 Create Quick Fix System
**File:** `frontend/lib/graph-validator.ts`

- [x] Define quick fix interface
- [x] Implement getQuickFixesForError function
- [x] Quick fixes for NO_START_NODE, NO_OUTPUT_NODE, DISCONNECTED_NODE

### 3.12 Integrate Validation with GraphEditor
**File:** `frontend/components/graph-editor/GraphEditor.tsx`

- [x] Wrap GraphEditor with ValidationProvider
- [x] Add ValidationTrigger component for auto-validation
- [x] Render ValidationOverlay component
- [x] Render ValidationStatusBar component
- [x] Wire up quick fix handlers
- [x] Wire up focus handlers for "Go to" functionality

### 3.13 Update Save Logic with Validation
**File:** `frontend/components/graph-editor/GraphEditor.tsx`

- [x] Validate before save (existing logic)
- [x] Show error toast if validation fails
- [x] Require output node before saving

### 3.14-3.15 Backend Validation Enhancement
*Existing backend validation is sufficient for current needs*

- [x] Backend GraphValidator already checks Start/End nodes
- [x] Backend returns structured errors

### 3.16-3.17 Unit Tests
*Deferred to Stage 7*

- [ ] Test validation logic
- [ ] Test component rendering

---

## Acceptance Criteria

1. ✅ Missing Start node shows prominent indicator with "Add Start Node" text
2. ✅ Missing Output node shows prominent indicator with "Add Output Node" text
3. ✅ Clicking indicators adds the missing node type
4. ✅ Status bar shows current validation state (valid/errors/warnings)
5. ✅ Error list shows all issues with "Go to" functionality
6. ✅ Nodes with errors have red highlight/border
7. ✅ Nodes with warnings have amber highlight/border
8. ✅ Quick fixes work for common errors
9. ✅ Validation runs in real-time (debounced)

## Dependencies

- Stage 1 (wizard infrastructure) ✅
- Stage 2 (node forms) ✅
- Existing GraphValidator backend ✅

## Output

- ✅ Frontend graph validator (`frontend/lib/graph-validator.ts`)
- ✅ ValidationContext and hooks (`frontend/contexts/ValidationContext.tsx`)
- ✅ ValidationOverlay with indicators (`frontend/components/graph-editor/validation/ValidationOverlay.tsx`)
- ✅ ValidationStatusBar with error list (`frontend/components/graph-editor/validation/ValidationStatusBar.tsx`)
- ✅ Quick fix system (in graph-validator.ts)
- ✅ Node error highlighting (in GraphNode.tsx)

## Files Created/Modified

```
frontend/lib/graph-validator.ts                              # Created
frontend/contexts/ValidationContext.tsx                      # Created
frontend/components/graph-editor/validation/
├── index.ts                                                 # Created
├── ValidationOverlay.tsx                                    # Created
└── ValidationStatusBar.tsx                                  # Created
frontend/components/graph-editor/nodes/GraphNode.tsx         # Modified
frontend/components/graph-editor/GraphEditor.tsx             # Modified
```

## Status: ✅ COMPLETE
