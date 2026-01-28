# Stage 5: Wizard Flow & Guided Experience

## Objective
Build the complete step-by-step wizard experience with contextual help, tooltips, and Quick Node presets for accelerated agent creation.

## Prerequisites
- Stage 1-4 complete
- Wizard infrastructure ready
- Node forms ready
- Validation system ready

---

## Task List

### 5.1 Create StartNodeStep Component
**File:** `frontend/components/graph-editor/wizard/steps/StartNodeStep.tsx`

- [ ] Create first wizard step for adding start node
- [ ] Content:
  - Explanation of what a start node is
  - Visual showing start node on canvas
  - Option to select which node is the entry point
  - Or auto-create a trigger edge to first node
- [ ] Canvas interaction:
  - Highlight where start should be (left side)
  - Show placeholder/ghost node
  - Click to place or auto-place
- [ ] Validation: Step complete when start edge exists
- [ ] Quick action: "Auto-add Start" button

### 5.2 Create AgentRoleStep Component
**File:** `frontend/components/graph-editor/wizard/steps/AgentRoleStep.tsx`

- [ ] Create step for defining agent's role/persona
- [ ] Form fields:
  - Agent Name (required)
  - Role/Persona (e.g., "Customer Support Agent")
  - Primary Objective (what the agent should accomplish)
  - Personality traits (optional checkboxes)
- [ ] Store in graph metadata or first prompt node
- [ ] Examples/templates for common roles
- [ ] Preview of how role affects prompts

### 5.3 Create ToolsStep Component
**File:** `frontend/components/graph-editor/wizard/steps/ToolsStep.tsx`

- [ ] Create step for adding tools/actions
- [ ] Content:
  - List of available tool types
  - Quick Node presets for common tools
  - "Add Custom Tool" option
- [ ] For each tool added:
  - Open NodeConfigDialog for configuration
  - Show tool on canvas
  - Auto-connect to previous node
- [ ] Allow adding multiple tools
- [ ] Show tool chain visualization
- [ ] This step is optional (can skip)

### 5.4 Create MemoryStep Component
**File:** `frontend/components/graph-editor/wizard/steps/MemoryStep.tsx`

- [ ] Create optional step for memory configuration
- [ ] Options:
  - "No memory" (stateless agent)
  - "Session memory" (within conversation)
  - "Persistent memory" (across sessions)
- [ ] If memory selected:
  - Add memory node(s) to graph
  - Configure namespace/keys
  - Explain memory patterns
- [ ] This step is optional (can skip)

### 5.5 Create OutputStep Component
**File:** `frontend/components/graph-editor/wizard/steps/OutputStep.tsx`

- [ ] Create step for defining agent output
- [ ] Content:
  - What should the agent return?
  - Output format selection (text, JSON, etc.)
  - Output schema definition (optional)
- [ ] Actions:
  - Add output node if not exists
  - Configure output mappings
  - Connect to end of flow
- [ ] Validation: Step complete when output node exists

### 5.6 Create ReviewStep Component
**File:** `frontend/components/graph-editor/wizard/steps/ReviewStep.tsx`

- [ ] Create final review step
- [ ] Content:
  - Summary of agent configuration
  - Graph preview (minimap or simplified view)
  - Validation status (all checks passed?)
  - Estimated complexity/cost indicator
- [ ] Actions:
  - "Edit" buttons to go back to specific steps
  - "Test Run" button to try agent
  - "Save & Finish" button
- [ ] Confetti or success animation on completion

### 5.7 Implement Wizard Step Navigation
**File:** `frontend/components/graph-editor/wizard/AgentWizard.tsx`

- [ ] Implement step rendering based on currentStep
- [ ] Handle Next/Back navigation
- [ ] Handle Skip for optional steps
- [ ] Validate current step before allowing Next
- [ ] Track completed steps for progress indicator
- [ ] Allow jumping to completed steps
- [ ] Persist wizard progress in localStorage

### 5.8 Create Contextual Help System
**File:** `frontend/components/graph-editor/wizard/ContextualHelp.tsx`

- [ ] Create help tooltip component
- [ ] Position near relevant UI elements
- [ ] Content varies by current step/context
- [ ] Include:
  - Brief explanation
  - Example
  - Link to docs (if available)
- [ ] Dismissible (with "Don't show again" option)

### 5.9 Create Help Tooltip Component
**File:** `frontend/components/ui/help-tooltip.tsx`

- [ ] Create reusable help icon + tooltip
- [ ] Trigger on hover or click
- [ ] Support markdown content
- [ ] Position automatically (avoid overflow)
- [ ] Use consistently across wizard forms

### 5.10 Define Quick Node Presets
**File:** `frontend/lib/quick-node-presets.ts`

- [ ] Define preset interface:
  ```typescript
  interface QuickNodePreset {
    id: string
    name: string
    description: string
    icon: string
    category: 'communication' | 'data' | 'ai' | 'utility'
    nodeType: NodeType
    defaultConfig: Partial<NodeConfig>
    tags: string[]
  }
  ```
- [ ] Create presets:
  - **WhatsApp Bot**: Prompt node with WhatsApp-specific role
  - **Telegram Agent**: Prompt node with Telegram role
  - **Email Responder**: HTTP + Prompt for email handling
  - **Data Fetcher**: HTTP node for API calls
  - **JSON Transformer**: Transform node for data mapping
  - **Decision Maker**: Branch node with common conditions
  - **Approval Gate**: Human gate with standard prompts
  - **Memory Store**: Memory node with set action
  - **Memory Recall**: Memory node with get action

### 5.11 Create QuickNodePalette Component
**File:** `frontend/components/graph-editor/QuickNodePalette.tsx`

- [ ] Create palette of Quick Node presets
- [ ] Design:
  - Grid of preset "pills" or cards
  - Icon + name for each
  - Category grouping
  - Search/filter functionality
- [ ] Click behavior:
  - Open NodeConfigDialog with preset values pre-filled
  - Or directly add node (configurable)
- [ ] Show in:
  - Wizard's ToolsStep
  - Standalone panel in NodePalette

### 5.12 Integrate Quick Nodes with NodePalette
**File:** `frontend/components/graph-editor/NodePalette.tsx`

- [ ] Add "Quick Nodes" section above/below node types
- [ ] Show popular presets
- [ ] "See All" button to expand full list
- [ ] Maintain existing node type list

### 5.13 Create Canvas Highlighting System
**File:** `frontend/components/graph-editor/CanvasHighlight.tsx`

- [ ] Create component to highlight canvas areas
- [ ] Support:
  - Region highlight (rectangle glow)
  - Node highlight (specific node glow)
  - Arrow pointer to location
  - Dimming of non-highlighted areas
- [ ] Use during wizard to guide user attention
- [ ] Animate highlight for visibility

### 5.14 Implement Wizard-Canvas Interaction
**File:** `frontend/components/graph-editor/GraphEditor.tsx`

- [ ] When wizard active:
  - Receive highlight instructions from wizard steps
  - Apply CanvasHighlight to specified areas
  - Handle node creation requests from wizard
  - Auto-pan to relevant area
  - Auto-select created nodes
- [ ] Expose functions to wizard context:
  - `addNodeAtPosition(type, config, position)`
  - `highlightArea(region)`
  - `focusNode(nodeId)`
  - `connectNodes(sourceId, targetId)`

### 5.15 Create Wizard Completion Handler
**File:** `frontend/components/graph-editor/wizard/AgentWizard.tsx`

- [ ] Handle wizard completion:
  - Validate entire graph
  - Save graph automatically (or prompt)
  - Show success message
  - Offer to test run
  - Close wizard overlay
- [ ] Handle wizard cancellation:
  - Confirm if progress exists
  - Option to save partial progress
  - Clean up any wizard-added nodes (optional)

### 5.16 Add Keyboard Shortcuts for Wizard
**File:** `frontend/components/graph-editor/GraphEditor.tsx`

- [ ] Add wizard-specific shortcuts:
  - `Enter`: Next step (if validation passes)
  - `Backspace`: Previous step
  - `Escape`: Close wizard (with confirmation)
  - `1-9`: Jump to step N
  - `?`: Show help for current step
- [ ] Show shortcuts in wizard footer

### 5.17 Create Wizard Tutorial Mode
**File:** `frontend/components/graph-editor/wizard/TutorialMode.tsx`

- [ ] Create optional tutorial overlay
- [ ] First-time user detection (localStorage flag)
- [ ] Explain each wizard element
- [ ] Step-by-step walkthrough
- [ ] "Skip Tutorial" option
- [ ] Re-trigger from help menu

### 5.18 Persist Wizard State
**File:** `frontend/lib/wizard-persistence.ts`

- [ ] Save wizard state to localStorage:
  - Current step
  - Completed steps
  - Step data
  - Graph ID (if editing existing)
- [ ] Restore on page reload
- [ ] Clear on wizard completion
- [ ] Handle graph mismatch (different graph loaded)

### 5.19 Unit Tests for Wizard Steps
**Files:** `frontend/__tests__/components/graph-editor/wizard/steps/`

- [ ] Test each step component renders
- [ ] Test step validation logic
- [ ] Test step completion detection
- [ ] Test step data persistence

### 5.20 Integration Tests for Wizard Flow
**Files:** `frontend/__tests__/e2e/wizard.spec.ts`

- [ ] Test complete wizard flow (happy path)
- [ ] Test wizard cancellation
- [ ] Test step navigation
- [ ] Test Quick Node presets
- [ ] Test wizard with existing graph

---

## Acceptance Criteria

1. Wizard guides user through all steps to create agent
2. Each step clearly explains what to do
3. Steps validate before allowing progress
4. Quick Node presets appear and work correctly
5. Canvas highlights relevant areas during wizard
6. Contextual help available at each step
7. Wizard can be cancelled with confirmation
8. Progress persists across page reloads
9. Completed wizard produces valid, runnable graph
10. Keyboard shortcuts work throughout wizard

## Dependencies

- Stage 1-4 complete
- All node forms ready
- Validation system ready

## Output

- Complete wizard step components
- Quick Node preset system
- Contextual help system
- Canvas highlighting during wizard
- Wizard persistence
- Keyboard shortcut integration
- Tutorial mode for first-time users
