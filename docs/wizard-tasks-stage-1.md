# Stage 1: Foundation & UI Infrastructure

## Objective
Build the foundational components and infrastructure needed for the Agent Creation Wizard.

## Prerequisites
- Existing GraphEditor component functional
- Shadcn UI components available
- React Flow integration working

---

## Task List

### 1.1 Create Wizard Context & State Management
**File:** `frontend/contexts/WizardContext.tsx`

- [x] Create WizardContext with React Context API
- [x] Define wizard state interface:
  ```typescript
  interface WizardState {
    isActive: boolean
    currentStep: number
    totalSteps: number
    completedSteps: Set<number>
    wizardData: Record<string, any>
    canProceed: boolean
    canGoBack: boolean
  }
  ```
- [x] Implement state reducer for wizard actions:
  - `START_WIZARD`
  - `EXIT_WIZARD`
  - `NEXT_STEP`
  - `PREV_STEP`
  - `GO_TO_STEP`
  - `SET_STEP_DATA`
  - `MARK_STEP_COMPLETE`
- [x] Create WizardProvider component
- [x] Export useWizard hook for consuming context

### 1.2 Create Wizard Entry Point
**File:** `frontend/components/graph-editor/GraphEditor.tsx`

- [x] Add "Agent Wizard" button to GraphEditor toolbar
- [x] Position button prominently (near save/run buttons)
- [x] Wire button to WizardContext's `START_WIZARD` action
- [ ] Add keyboard shortcut (Ctrl+Shift+W) for wizard toggle *(deferred to Stage 5)*
- [x] Conditionally render AgentWizard component when active

### 1.3 Create Base Wizard Container
**File:** `frontend/components/graph-editor/wizard/AgentWizard.tsx`

- [x] Create AgentWizard component as overlay on canvas
- [x] Implement semi-transparent backdrop (like Shadcn Dialog)
- [x] Create wizard panel (fixed position, center)
- [x] Add close button (Exit in navigation)
- [x] Wire to WizardContext for state management
- [x] Handle Escape key to close

### 1.4 Create Wizard Step Wrapper
**File:** `frontend/components/graph-editor/wizard/WizardStep.tsx`

- [x] Create reusable WizardStep component
- [x] Props: `title`, `description`, `children`, `className`
- [x] Include step header with title and description
- [x] Handle step validation via canProceed state
- [x] Step completion handled via WizardNavigation

### 1.5 Create Wizard Progress Indicator
**File:** `frontend/components/graph-editor/wizard/WizardProgress.tsx`

- [x] Create horizontal step progress indicator
- [x] Show all steps with labels
- [x] Highlight current step
- [x] Mark completed steps with checkmark
- [x] Allow clicking on completed steps to navigate back
- [x] Show step numbers (1, 2, 3...) or icons

### 1.6 Create Wizard Navigation Component
**File:** `frontend/components/graph-editor/wizard/WizardNavigation.tsx`

- [x] Create footer navigation bar
- [x] Include "Back" button (disabled on first step)
- [x] Include "Next" / "Finish" button
- [x] Include "Skip" button for optional steps
- [x] Include "Exit" button
- [ ] Show keyboard shortcuts hints *(deferred to Stage 5)*

### 1.7 Define Wizard Steps Configuration
**File:** `frontend/contexts/WizardContext.tsx` *(embedded in context)*

- [x] Define step configuration interface:
  ```typescript
  interface WizardStepConfig {
    id: string
    title: string
    description: string
    isRequired: boolean
    canSkip: boolean
  }
  ```
- [x] Create default agent wizard steps array:
  1. "Add Start Node" (required)
  2. "Define Agent Role" (required)
  3. "Add Tools & Actions" (optional)
  4. "Configure Memory" (optional)
  5. "Add Output Node" (required)
  6. "Review & Save" (required)
- [x] Export steps configuration

### 1.8 Update GraphEditor Layout for Wizard
**File:** `frontend/components/graph-editor/GraphEditor.tsx`

- [x] Adjust layout to accommodate wizard overlay
- [x] Ensure canvas remains interactive when wizard active (overlay design)
- [x] Add visual dimming effect (backdrop)
- [ ] Implement focus ring/highlight on wizard-relevant nodes *(deferred to Stage 5)*
- [x] Maintain scroll/pan functionality during wizard

### 1.9 Create Wizard Styles
**File:** Tailwind classes in components

- [x] Define wizard overlay styles (backdrop, positioning)
- [x] Define wizard panel styles (card-like appearance)
- [x] Define step indicator styles
- [x] Define button styles consistent with existing UI
- [ ] Add animations for step transitions *(deferred to Stage 5)*
- [x] Ensure dark mode compatibility

### 1.10 Integration Testing Setup
**Files:** `frontend/__tests__/components/graph-editor/wizard/`

- [ ] Create test file structure *(deferred to Stage 7)*
- [ ] Set up mock WizardContext for testing *(deferred to Stage 7)*
- [ ] Write basic render tests for AgentWizard *(deferred to Stage 7)*
- [ ] Write basic render tests for WizardStep *(deferred to Stage 7)*
- [ ] Write basic render tests for WizardProgress *(deferred to Stage 7)*

---

## Acceptance Criteria

1. ✅ "Agent Wizard" button visible in GraphEditor toolbar
2. ✅ Clicking button opens wizard overlay on canvas
3. ✅ Wizard shows progress indicator with all steps
4. ✅ Navigation between steps works (Next/Back)
5. ✅ Wizard can be closed (Exit button, Escape key)
6. ✅ Canvas remains visible behind wizard overlay
7. ✅ All components render correctly in light/dark mode
8. ⚠️ Keyboard shortcuts: Escape works, Ctrl+Shift+W deferred

## Status: COMPLETE ✅

Core functionality implemented. Deferred items (keyboard shortcut, animations, tests) scheduled for later stages.

## Dependencies

- None (first stage)

## Output

- ✅ WizardContext and useWizard hook
- ✅ AgentWizard container component
- ✅ WizardStep, WizardProgress, WizardNavigation components
- ✅ Wizard configuration system (DEFAULT_WIZARD_STEPS)
- ⏳ Basic test coverage (deferred to Stage 7)
