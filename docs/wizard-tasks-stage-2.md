# Stage 2: Node Generator Forms

## Objective
Create the universal Node Configuration Dialog with specialized forms for each node type, including the required fields (Role, Job Description, Examples, Notes).

## Prerequisites
- Stage 1 complete (wizard infrastructure)
- Existing NodeInspector patterns understood
- Shadcn Dialog component available

---

## Task List

### 2.1 Create NodeConfigDialog Base Component
**File:** `frontend/components/graph-editor/NodeConfigDialog.tsx`

- [x] Create modal dialog using Shadcn Dialog
- [x] Props: `isOpen`, `onClose`, `nodeType`, `initialConfig`, `onSave`
- [x] Implement header with node type icon and title
- [x] Add "Cancel" and "Save" action buttons
- [x] Wire form validation to "Save" button disabled state
- [x] Handle Escape key to close
- [x] Prevent closing if form has unsaved changes (confirmation)

### 2.2 Define Extended Node Config Types
**File:** `frontend/lib/form-validation.ts` and form components

- [x] Extended base node config with agent fields
- [x] Update each node type's config interface to extend AgentNodeConfig
- [x] Add `output_key` field to relevant node configs

### 2.3 Create Common Form Fields Component
**File:** `frontend/components/graph-editor/forms/AgentFields.tsx`

- [x] Create reusable component for Role/Job/Examples/Notes fields
- [x] **Role field**: Text input with placeholder examples
- [x] **Job Description field**: Textarea with character count
- [x] **Examples field**: Dynamic list of input/output pairs
  - Add/remove example buttons
  - Input textarea and Output textarea per example
- [x] **Notes field**: Textarea for special instructions
- [x] Include helpful tooltips for each field
- [x] Make all fields optional with clear labeling

### 2.4 Create PromptNodeForm
**File:** `frontend/components/graph-editor/forms/PromptNodeForm.tsx`

- [x] Include AgentFields component
- [x] Add prompt-specific fields:
  - System prompt textarea
  - User prompt textarea with variable interpolation hints
  - Model selector dropdown
  - Temperature slider (0-2)
  - Max tokens input
  - Variables key-value editor
- [x] Validate required fields (prompt text)

### 2.5 Create HttpNodeForm
**File:** `frontend/components/graph-editor/forms/HttpNodeForm.tsx`

- [x] Include AgentFields component
- [x] Add HTTP-specific fields:
  - Method selector (GET, POST, PUT, DELETE, PATCH)
  - URL input with variable support and validation
  - Headers key-value editor
  - Body textarea (JSON) with syntax highlighting hint
  - Output key input
- [x] Validate URL format
- [x] Validate JSON body

### 2.6 Create TransformNodeForm
**File:** `frontend/components/graph-editor/forms/TransformNodeForm.tsx`

- [x] Include AgentFields component
- [x] Add transform-specific fields:
  - Expression textarea with syntax help
  - Output key input
- [x] Add expression validation
- [x] Show available variables documentation

### 2.7 Create BranchNodeForm
**File:** `frontend/components/graph-editor/forms/BranchNodeForm.tsx`

- [x] Include AgentFields component (minimal)
- [x] Add branch-specific fields:
  - Dynamic condition list with add/remove
  - Condition name input
  - Condition expression textarea
  - Default branch input
- [x] Show expression syntax help

### 2.8 Create MergeNodeForm
**File:** `frontend/components/graph-editor/forms/MergeNodeForm.tsx`

- [x] Include AgentFields component (minimal)
- [x] Add merge-specific fields:
  - Strategy selector (all, first, latest, combine)
  - Strategy description text
  - Output key input

### 2.9 Create MemoryNodeForm
**File:** `frontend/components/graph-editor/forms/MemoryNodeForm.tsx`

- [x] Include AgentFields component
- [x] Add memory-specific fields:
  - Memory type selector (conversation, buffer, summary, vector)
  - Memory key input
  - Max messages input (for buffer)
  - Max tokens input (for summary)
  - Retrieval query (for vector)
  - Top K results (for vector)
- [x] Conditional field visibility based on memory type

### 2.10 Create ToolNodeForm
**File:** `frontend/components/graph-editor/forms/ToolNodeForm.tsx`

- [x] Include AgentFields component
- [x] Add tool-specific fields:
  - Tool name selector (built-in tools + custom)
  - Tool description (for custom tools)
  - Parameters key-value editor
  - Input schema (JSON) for custom tools
  - Output key input
- [x] Show tool description and usage hints

### 2.11 Create SubgraphNodeForm
**File:** `frontend/components/graph-editor/forms/SubgraphNodeForm.tsx`

- [x] Include AgentFields component
- [x] Add subgraph-specific fields:
  - Graph ID input
  - Version input (or latest)
  - Input mappings key-value editor
  - Output mappings key-value editor
- [x] Show version pinning recommendation

### 2.12 Create HumanGateNodeForm
**File:** `frontend/components/graph-editor/forms/HumanGateNodeForm.tsx`

- [x] Include AgentFields component
- [x] Add human gate-specific fields:
  - Approval message textarea
  - Instructions textarea
  - Timeout settings
  - Notification emails
  - Auto-approve on timeout toggle
  - Require comment toggle
  - Show context toggle
- [x] Show auto-approval warning

### 2.13 Create OutputNodeForm
**File:** `frontend/components/graph-editor/forms/OutputNodeForm.tsx`

- [x] Include AgentFields component (minimal)
- [x] Add output-specific fields:
  - Output mappings key-value editor
- [x] Show state path examples

### 2.14 Create Advanced Settings Collapsible
**File:** `frontend/components/graph-editor/forms/AdvancedSettings.tsx`

- [x] Create collapsible section for advanced settings
- [x] Include fields:
  - Cache enabled toggle
  - Cache TTL input
  - Timeout (ms) input
  - Retry policy:
    - Max attempts input
    - Backoff strategy (fixed, exponential)
    - Initial backoff (ms) input
- [x] Default collapsed state

### 2.15 Create Form Registry
**File:** `frontend/components/graph-editor/forms/node-form-registry.ts`

- [x] Create mapping of node types to form components
- [x] Export getFormForNodeType utility function
- [x] Export getNodeTypeInfo utility function
- [x] Handle unknown node types gracefully
- [x] Include node type metadata (label, description, icon, category, color)

### 2.16 Integrate NodeConfigDialog with GraphEditor
**File:** `frontend/components/graph-editor/GraphEditor.tsx`

- [x] Add state for NodeConfigDialog open/close
- [x] Hook "Add Node" from NodePalette to open dialog
- [x] Pass selected node type to dialog
- [x] Handle dialog save → create node on canvas
- [x] Handle dialog close → cancel node creation
- [x] Position new node appropriately after creation

### 2.17 Update NodePalette for Dialog Integration
**File:** `frontend/components/graph-editor/NodePalette.tsx`

- [x] Change node click behavior to open NodeConfigDialog (via handleAddNode)
- [x] Exception: Prompt nodes use PromptNodeWizardDialog
- [x] Exception: "Note" nodes add directly (no config needed)

### 2.18 Form Validation System
**File:** `frontend/lib/form-validation.ts`

- [x] Create validation rules for each field type
- [x] Implement validation functions:
  - `validateRequired(value)`
  - `validateUrl(value)`
  - `validateJson(value)`
  - `validateExpression(value)`
- [x] Return field errors for display

### 2.19 Unit Tests for Forms
**Files:** `frontend/__tests__/components/graph-editor/forms/`

- [ ] Test each form component renders correctly
- [ ] Test form validation logic
- [ ] Test form submission with valid data
- [ ] Test form error display
- [ ] Test conditional field visibility

*Note: Tests deferred to Stage 7 as per implementation plan.*

---

## Acceptance Criteria

1. ✅ Clicking any node type in palette opens NodeConfigDialog
2. ✅ Dialog shows appropriate form for selected node type
3. ✅ All forms include Role, Job Description, Examples, Notes fields
4. ✅ Form validation prevents saving invalid configurations
5. ✅ Saving form creates properly configured node on canvas
6. ✅ Cancel closes dialog without creating node
7. ✅ All forms render correctly in light/dark mode (using Shadcn/Tailwind)
8. ✅ Keyboard navigation works within forms

## Dependencies

- Stage 1 (wizard infrastructure) ✅
- Existing Shadcn form components ✅
- Existing KeyValueEditor component ✅

## Output

- ✅ NodeConfigDialog component
- ✅ 10 node-specific form components
- ✅ Common AgentFields component
- ✅ Form validation system
- ✅ Form registry for node type → form mapping

## Files Created

```
frontend/lib/form-validation.ts
frontend/components/graph-editor/NodeConfigDialog.tsx
frontend/components/graph-editor/forms/
├── index.ts
├── node-form-registry.ts
├── AgentFields.tsx
├── AdvancedSettings.tsx
├── PromptNodeForm.tsx
├── HttpNodeForm.tsx
├── TransformNodeForm.tsx
├── OutputNodeForm.tsx
├── BranchNodeForm.tsx
├── MergeNodeForm.tsx
├── MemoryNodeForm.tsx
├── ToolNodeForm.tsx
├── SubgraphNodeForm.tsx
└── HumanGateNodeForm.tsx
```

## Status: ✅ COMPLETE
