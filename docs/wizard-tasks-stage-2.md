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

- [ ] Create modal dialog using Shadcn Dialog
- [ ] Props: `isOpen`, `onClose`, `nodeType`, `initialConfig`, `onSave`
- [ ] Implement header with node type icon and title
- [ ] Add "Cancel" and "Save" action buttons
- [ ] Wire form validation to "Save" button disabled state
- [ ] Handle Escape key to close
- [ ] Prevent closing if form has unsaved changes (confirmation)

### 2.2 Define Extended Node Config Types
**File:** `frontend/lib/graph-types.ts`

- [ ] Extend base node config with agent fields:
  ```typescript
  interface AgentNodeConfig {
    role?: string           // e.g., "Software Engineer at OpenAI"
    jobDescription?: string // Main objective
    examples?: Array<{      // Example I/O pairs
      input: string
      output: string
    }>
    notes?: string          // Special instructions
  }
  ```
- [ ] Update each node type's config interface to extend AgentNodeConfig
- [ ] Add `outputType` field to all node configs
- [ ] Define output type enum: `text`, `json`, `image`, `file`, `any`

### 2.3 Create Common Form Fields Component
**File:** `frontend/components/graph-editor/forms/AgentFields.tsx`

- [ ] Create reusable component for Role/Job/Examples/Notes fields
- [ ] **Role field**: Text input with placeholder examples
- [ ] **Job Description field**: Textarea with character count
- [ ] **Examples field**: Dynamic list of input/output pairs
  - Add/remove example buttons
  - Input textarea and Output textarea per example
- [ ] **Notes field**: Textarea for special instructions
- [ ] Include helpful tooltips for each field
- [ ] Make all fields optional with clear labeling

### 2.4 Create PromptNodeForm
**File:** `frontend/components/graph-editor/forms/PromptNodeForm.tsx`

- [ ] Include AgentFields component
- [ ] Add prompt-specific fields:
  - Template selection (from library)
  - System prompt textarea
  - User prompt textarea with variable interpolation hints
  - Model selector dropdown
  - Temperature slider (0-2)
  - Max tokens input
  - Variables key-value editor
- [ ] Add "Use Wizard" button to open PromptNodeWizardDialog
- [ ] Validate required fields (prompt text)

### 2.5 Create HttpNodeForm
**File:** `frontend/components/graph-editor/forms/HttpNodeForm.tsx`

- [ ] Include AgentFields component
- [ ] Add HTTP-specific fields:
  - Method selector (GET, POST, PUT, DELETE, PATCH)
  - URL input with variable support and validation
  - Headers key-value editor
  - Body textarea (JSON) with syntax highlighting hint
  - Output key input
  - Timeout input (ms)
- [ ] Add "Test Request" button (optional, future)
- [ ] Validate URL format

### 2.6 Create TransformNodeForm
**File:** `frontend/components/graph-editor/forms/TransformNodeForm.tsx`

- [ ] Include AgentFields component
- [ ] Add transform-specific fields:
  - Expression textarea with syntax help
  - Language selector (JavaScript/JSONPath)
  - Output key input
  - Input preview (read from connected node)
- [ ] Add expression validation
- [ ] Show available variables from upstream nodes

### 2.7 Create BranchNodeForm
**File:** `frontend/components/graph-editor/forms/BranchNodeForm.tsx`

- [ ] Include AgentFields component (minimal)
- [ ] Add branch-specific fields:
  - Condition expression textarea
  - True path label
  - False path label
- [ ] Show expression syntax help
- [ ] Preview condition evaluation (if possible)

### 2.8 Create MergeNodeForm
**File:** `frontend/components/graph-editor/forms/MergeNodeForm.tsx`

- [ ] Include AgentFields component (minimal)
- [ ] Add merge-specific fields:
  - Strategy selector (namespaced, last_write_wins)
  - Strategy description text
- [ ] Show incoming connections preview

### 2.9 Create MemoryNodeForm
**File:** `frontend/components/graph-editor/forms/MemoryNodeForm.tsx`

- [ ] Include AgentFields component
- [ ] Add memory-specific fields:
  - Action selector (get, set, delete)
  - Key input
  - Namespace input
  - Value textarea (for set action)
  - TTL input (for set action)
- [ ] Conditional field visibility based on action

### 2.10 Create ToolNodeForm
**File:** `frontend/components/graph-editor/forms/ToolNodeForm.tsx`

- [ ] Include AgentFields component
- [ ] Add tool-specific fields:
  - Tool name selector (from available tools)
  - Tool version selector
  - Input path (JSONPath to extract from state)
  - Input template (JSON with variable interpolation)
  - Static input (fixed JSON)
  - Config overrides key-value editor
- [ ] Show tool description and required inputs

### 2.11 Create SubgraphNodeForm
**File:** `frontend/components/graph-editor/forms/SubgraphNodeForm.tsx`

- [ ] Include AgentFields component
- [ ] Add subgraph-specific fields:
  - Graph selector (from user's graphs)
  - Version selector (or "latest")
  - Input mappings key-value editor
  - Output mappings key-value editor
- [ ] Show selected graph preview/summary

### 2.12 Create HumanGateNodeForm
**File:** `frontend/components/graph-editor/forms/HumanGateNodeForm.tsx`

- [ ] Include AgentFields component
- [ ] Add human gate-specific fields:
  - Prompt message textarea
  - Required fields list (what user must provide)
  - Approval button labels (customizable)
  - Timeout settings
- [ ] Preview approval UI appearance

### 2.13 Create OutputNodeForm
**File:** `frontend/components/graph-editor/forms/OutputNodeForm.tsx`

- [ ] Include AgentFields component (minimal)
- [ ] Add output-specific fields:
  - Output mappings key-value editor
  - Output schema definition (optional)
- [ ] Show what will be extracted as final output

### 2.14 Create Advanced Settings Collapsible
**File:** `frontend/components/graph-editor/forms/AdvancedSettings.tsx`

- [ ] Create collapsible section for advanced settings
- [ ] Include fields:
  - Cache enabled toggle
  - Cache TTL input
  - Timeout (ms) input
  - Retry policy:
    - Max attempts input
    - Backoff strategy (fixed, exponential)
    - Initial backoff (ms) input
- [ ] Default collapsed state

### 2.15 Create Form Registry
**File:** `frontend/lib/node-form-registry.ts`

- [ ] Create mapping of node types to form components:
  ```typescript
  const formRegistry: Record<NodeType, React.ComponentType<FormProps>> = {
    prompt: PromptNodeForm,
    http: HttpNodeForm,
    // ...
  }
  ```
- [ ] Export getFormForNodeType utility function
- [ ] Handle unknown node types gracefully

### 2.16 Integrate NodeConfigDialog with GraphEditor
**File:** `frontend/components/graph-editor/GraphEditor.tsx`

- [ ] Add state for NodeConfigDialog open/close
- [ ] Hook "Add Node" from NodePalette to open dialog
- [ ] Pass selected node type to dialog
- [ ] Handle dialog save → create node on canvas
- [ ] Handle dialog close → cancel node creation
- [ ] Position new node appropriately after creation

### 2.17 Update NodePalette for Dialog Integration
**File:** `frontend/components/graph-editor/NodePalette.tsx`

- [ ] Change node click behavior:
  - Click → Open NodeConfigDialog (not direct add)
  - Exception: "Note" nodes add directly (no config needed)
- [ ] Add visual indicator that clicking opens config
- [ ] Maintain drag-to-add functionality (for power users)

### 2.18 Form Validation System
**File:** `frontend/lib/form-validation.ts`

- [ ] Create validation rules for each field type
- [ ] Implement validation functions:
  - `validateRequired(value)`
  - `validateUrl(value)`
  - `validateJson(value)`
  - `validateExpression(value)`
- [ ] Create useFormValidation hook
- [ ] Return field errors and overall form validity

### 2.19 Unit Tests for Forms
**Files:** `frontend/__tests__/components/graph-editor/forms/`

- [ ] Test each form component renders correctly
- [ ] Test form validation logic
- [ ] Test form submission with valid data
- [ ] Test form error display
- [ ] Test conditional field visibility

---

## Acceptance Criteria

1. Clicking any node type in palette opens NodeConfigDialog
2. Dialog shows appropriate form for selected node type
3. All forms include Role, Job Description, Examples, Notes fields
4. Form validation prevents saving invalid configurations
5. Saving form creates properly configured node on canvas
6. Cancel closes dialog without creating node
7. All forms render correctly in light/dark mode
8. Keyboard navigation works within forms

## Dependencies

- Stage 1 (wizard infrastructure)
- Existing Shadcn form components
- Existing KeyValueEditor component

## Output

- NodeConfigDialog component
- 10 node-specific form components
- Common AgentFields component
- Form validation system
- Form registry for node type → form mapping
