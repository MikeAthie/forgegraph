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
**File:** `frontend/lib/validation-types.ts`

- [ ] Create validation error interface:
  ```typescript
  interface ValidationError {
    type: 'error' | 'warning'
    code: string
    message: string
    nodeId?: string
    edgeId?: string
    field?: string
    suggestion?: string
  }
  ```
- [ ] Define error codes enum:
  - `NO_START_NODE`
  - `NO_END_NODE`
  - `NO_OUTPUT_NODE`
  - `DISCONNECTED_NODE`
  - `CYCLE_DETECTED`
  - `TYPE_MISMATCH`
  - `MISSING_REQUIRED_FIELD`
  - `INVALID_EXPRESSION`
- [ ] Create ValidationResult type with errors array

### 3.2 Create Frontend Graph Validator
**File:** `frontend/lib/graph-validator.ts`

- [ ] Implement `validateGraph(nodes, edges)` function
- [ ] Check for Start node (edges from START sentinel):
  ```typescript
  const hasStart = edges.some(e => e.source === 'START')
  if (!hasStart) errors.push({ code: 'NO_START_NODE', ... })
  ```
- [ ] Check for End node (output node or explicit end edges):
  ```typescript
  const hasOutput = nodes.some(n => n.type === 'output')
  if (!hasOutput) errors.push({ code: 'NO_OUTPUT_NODE', ... })
  ```
- [ ] Check for disconnected nodes (no incoming or outgoing edges)
- [ ] Check for cycles (DFS-based detection)
- [ ] Return ValidationResult with all errors/warnings

### 3.3 Create Validation Context
**File:** `frontend/contexts/ValidationContext.tsx`

- [ ] Create ValidationContext with React Context API
- [ ] Store current validation errors
- [ ] Provide `validate()` function to trigger validation
- [ ] Auto-validate on node/edge changes (debounced)
- [ ] Export useValidation hook

### 3.4 Create ValidationOverlay Component
**File:** `frontend/components/graph-editor/ValidationOverlay.tsx`

- [ ] Create overlay component for validation indicators
- [ ] Position indicators absolutely on canvas
- [ ] Show indicators at specific positions:
  - Start indicator at top-left if no start node
  - End indicator at bottom-right if no end node
- [ ] Make indicators dismissible (temporarily)
- [ ] Animate indicators for attention

### 3.5 Create MissingStartIndicator Component
**File:** `frontend/components/graph-editor/validation/MissingStartIndicator.tsx`

- [ ] Create prominent visual indicator for missing start
- [ ] Design:
  - Red/orange pulsing border or icon
  - Text: "Add a Start Node"
  - Arrow pointing to where start should be
  - Click to add start node directly
- [ ] Position at logical start location (left side)
- [ ] Include tooltip with explanation

### 3.6 Create MissingEndIndicator Component
**File:** `frontend/components/graph-editor/validation/MissingEndIndicator.tsx`

- [ ] Create prominent visual indicator for missing end
- [ ] Design:
  - Red/orange pulsing border or icon
  - Text: "Add an Output Node"
  - Arrow pointing to where end should be
  - Click to add output node directly
- [ ] Position at logical end location (right side)
- [ ] Include tooltip with explanation

### 3.7 Create ValidationStatusBar Component
**File:** `frontend/components/graph-editor/validation/ValidationStatusBar.tsx`

- [ ] Create status bar at bottom of GraphEditor
- [ ] Show validation status:
  - Green checkmark: "Graph Valid"
  - Red X: "X errors found"
  - Yellow warning: "X warnings"
- [ ] Click to expand error list
- [ ] Quick fix buttons for common errors

### 3.8 Create ValidationErrorList Component
**File:** `frontend/components/graph-editor/validation/ValidationErrorList.tsx`

- [ ] Create expandable list of all validation errors
- [ ] Group errors by type (structural, node, edge)
- [ ] Each error shows:
  - Error icon (error/warning)
  - Error message
  - Affected node/edge name
  - "Go to" button to focus on problem
  - "Fix" button if auto-fix available
- [ ] Sortable by severity

### 3.9 Implement Node Highlighting for Errors
**File:** `frontend/components/graph-editor/nodes/GraphNode.tsx`

- [ ] Add validation error prop to GraphNode
- [ ] If node has errors, show red border/glow
- [ ] If node has warnings, show yellow border/glow
- [ ] Add error badge with count
- [ ] Show error tooltip on hover

### 3.10 Implement Edge Highlighting for Errors
**File:** `frontend/components/graph-editor/GraphEditor.tsx`

- [ ] Add custom edge styles for error states
- [ ] Red dashed line for invalid edges
- [ ] Yellow dashed line for warning edges
- [ ] Add error label on invalid edges

### 3.11 Create Quick Fix System
**File:** `frontend/lib/quick-fixes.ts`

- [ ] Define quick fix interface:
  ```typescript
  interface QuickFix {
    errorCode: string
    label: string
    apply: (nodes, edges, setNodes, setEdges) => void
  }
  ```
- [ ] Implement quick fixes:
  - `NO_START_NODE`: Add trigger edge to first node
  - `NO_OUTPUT_NODE`: Convert last node to output or add output
  - `DISCONNECTED_NODE`: Delete or connect node
- [ ] Return applicable quick fixes for each error

### 3.12 Integrate Validation with GraphEditor
**File:** `frontend/components/graph-editor/GraphEditor.tsx`

- [ ] Wrap GraphEditor with ValidationProvider
- [ ] Trigger validation on:
  - Initial load
  - Node add/remove/update
  - Edge add/remove/update
  - Every 500ms debounced during editing
- [ ] Render ValidationOverlay component
- [ ] Render ValidationStatusBar component
- [ ] Block "Run" button if critical errors exist
- [ ] Show warning dialog before run if warnings exist

### 3.13 Update Save Logic with Validation
**File:** `frontend/components/graph-editor/GraphEditor.tsx`

- [ ] Validate before save (existing logic)
- [ ] If errors: show error dialog, prevent save
- [ ] If warnings: show warning dialog, allow save with confirmation
- [ ] Add validation errors to save error message

### 3.14 Backend Validation Enhancement
**File:** `backend/domain/services/graph_validator.py`

- [ ] Add explicit Start node check (already exists, verify)
- [ ] Add explicit End/Output node check (already exists, verify)
- [ ] Add disconnected node detection
- [ ] Return structured errors matching frontend types
- [ ] Add error suggestions to response

### 3.15 Create Validation API Endpoint
**File:** `backend/adapters/api/graphs.py`

- [ ] Add `POST /api/graphs/validate` endpoint
- [ ] Accept graph_json in body
- [ ] Return validation result with errors array
- [ ] Include suggestions for each error
- [ ] Use for real-time frontend validation (optional)

### 3.16 Unit Tests for Validation
**Files:** `frontend/__tests__/lib/graph-validator.test.ts`

- [ ] Test NO_START_NODE detection
- [ ] Test NO_OUTPUT_NODE detection
- [ ] Test DISCONNECTED_NODE detection
- [ ] Test CYCLE_DETECTED detection
- [ ] Test valid graph returns no errors
- [ ] Test quick fix applications

### 3.17 Component Tests for Indicators
**Files:** `frontend/__tests__/components/graph-editor/validation/`

- [ ] Test ValidationOverlay renders correctly
- [ ] Test MissingStartIndicator visibility
- [ ] Test MissingEndIndicator visibility
- [ ] Test ValidationStatusBar states
- [ ] Test ValidationErrorList interactions

---

## Acceptance Criteria

1. Missing Start node shows prominent red indicator with "Add Start Node" text
2. Missing Output node shows prominent red indicator with "Add Output Node" text
3. Clicking indicators adds the missing node type
4. Status bar shows current validation state (valid/errors/warnings)
5. Error list shows all issues with "Go to" functionality
6. Nodes with errors have red highlight/border
7. "Run" button disabled when critical errors exist
8. Save shows error dialog if validation fails
9. Quick fixes work for common errors
10. Validation runs in real-time (debounced)

## Dependencies

- Stage 1 (wizard infrastructure)
- Stage 2 (node forms)
- Existing GraphValidator backend

## Output

- Frontend graph validator
- ValidationContext and useValidation hook
- ValidationOverlay with indicators
- ValidationStatusBar with error list
- Quick fix system
- Enhanced backend validation endpoint
- Comprehensive test coverage
