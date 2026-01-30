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

### 5.1-5.6 Create Wizard Step Components
**File:** `frontend/components/graph-editor/wizard/AgentWizard.tsx`

*All step components implemented inline in AgentWizard.tsx:*

- [x] StartNodeStep - Shows start node status, offers Quick Nodes to add
- [x] AgentRoleStep - Agent name and objective form fields
- [x] ToolsStep - Full QuickNodePalette for adding tools
- [x] MemoryStep - Memory type selection (none, session, persistent)
- [x] OutputStep - Shows output node status, offers Quick Nodes
- [x] ReviewStep - Summary with validation status

### 5.7 Implement Wizard Step Navigation
**File:** `frontend/components/graph-editor/wizard/WizardNavigation.tsx`

- [x] Step rendering based on currentStep
- [x] Next/Back navigation
- [x] Skip for optional steps
- [x] Validation before allowing Next
- [x] Progress indicator in WizardProgress

### 5.8-5.9 Contextual Help System
*Deferred - basic tooltips already in place*

- [ ] Help tooltip component
- [ ] Position near relevant UI elements
- [ ] Markdown support

### 5.10 Define Quick Node Presets
**File:** `frontend/lib/quick-node-presets.ts`

- [x] QuickNodePreset interface defined
- [x] 17 presets created across 5 categories:
  - AI: Chat Assistant, Summarizer, Classifier, Translator
  - Communication: Email Responder, Notification
  - Data: API Fetcher, API Poster, JSON Transformer, Data Extractor
  - Logic: Conditional Router, Approval Gate, Merge Paths
  - Utility: Save to Memory, Recall Memory, Final Output
- [x] Category metadata for display
- [x] Search and filter functions

### 5.11 Create QuickNodePalette Component
**File:** `frontend/components/graph-editor/QuickNodePalette.tsx`

- [x] Grid display of Quick Node presets
- [x] Search/filter functionality
- [x] Category pills for filtering
- [x] Compact and full modes
- [x] Click to add node

### 5.12 Integrate Quick Nodes with NodePalette
*Quick Nodes integrated via wizard, can add to main palette later*

- [ ] Add "Quick Nodes" section to NodePalette
- [ ] Popular presets display

### 5.13 Canvas Highlighting System
*Deferred - validation overlay provides guidance*

- [ ] Region highlight component
- [ ] Node highlight
- [ ] Dim non-highlighted areas

### 5.14 Implement Wizard-Canvas Interaction
**File:** `frontend/components/graph-editor/GraphEditor.tsx`

- [x] handleWizardAddNode callback
- [x] Pass onAddNode to AgentWizard
- [x] Auto-mark first node as trigger

### 5.15 Create Wizard Completion Handler
**File:** `frontend/components/graph-editor/wizard/AgentWizard.tsx`

- [x] Handle wizard completion (exitWizard + callback)
- [x] Show success message
- [x] Escape key to exit

### 5.16-5.18 Advanced Features
*Deferred*

- [ ] Keyboard shortcuts (Enter, Backspace, 1-9)
- [ ] Tutorial mode for first-time users
- [ ] Persist wizard state to localStorage

### 5.19-5.20 Tests
*Deferred to Stage 7*

- [ ] Unit tests for wizard steps
- [ ] E2E tests for wizard flow

---

## Acceptance Criteria

1. ✅ Wizard guides user through all steps to create agent
2. ✅ Each step clearly explains what to do
3. ✅ Steps validate before allowing progress (where required)
4. ✅ Quick Node presets appear and work correctly
5. ✅ Wizard can be cancelled (Escape key)
6. ✅ Completed wizard produces valid, runnable graph
7. ⏳ Canvas highlights relevant areas during wizard (partial)
8. ⏳ Contextual help available at each step (partial)
9. ⏳ Progress persists across page reloads (not implemented)
10. ⏳ Keyboard shortcuts work throughout wizard (partial)

## Dependencies

- Stage 1-4 complete ✅

## Output

- ✅ Wizard step components (in AgentWizard.tsx)
- ✅ Quick Node preset system (quick-node-presets.ts)
- ✅ QuickNodePalette component
- ⏳ Contextual help system (basic)
- ⏳ Canvas highlighting during wizard (via validation overlay)
- ⏳ Wizard persistence (not implemented)

## Files Created/Modified

```
frontend/lib/quick-node-presets.ts                           # Created
frontend/components/graph-editor/QuickNodePalette.tsx        # Created
frontend/components/graph-editor/wizard/AgentWizard.tsx      # Enhanced
frontend/components/graph-editor/GraphEditor.tsx             # Modified
```

## Status: ✅ CORE COMPLETE (Advanced features pending)
