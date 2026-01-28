# Stage 7: Testing & Documentation

## Objective
Comprehensive testing of all wizard functionality and creation of user documentation.

## Prerequisites
- Stage 1-6 complete
- All features implemented

---

## Task List

### 7.1 Unit Tests: Wizard Context
**File:** `frontend/__tests__/contexts/WizardContext.test.tsx`

- [ ] Test initial state
- [ ] Test START_WIZARD action
- [ ] Test EXIT_WIZARD action
- [ ] Test NEXT_STEP action
- [ ] Test PREV_STEP action
- [ ] Test GO_TO_STEP action
- [ ] Test SET_STEP_DATA action
- [ ] Test MARK_STEP_COMPLETE action
- [ ] Test step validation integration

### 7.2 Unit Tests: Wizard Components
**Files:** `frontend/__tests__/components/graph-editor/wizard/`

- [ ] Test AgentWizard renders when active
- [ ] Test AgentWizard closes on escape
- [ ] Test WizardStep renders title and content
- [ ] Test WizardProgress shows correct step
- [ ] Test WizardNavigation button states
- [ ] Test ContextualHelp displays

### 7.3 Unit Tests: Wizard Steps
**Files:** `frontend/__tests__/components/graph-editor/wizard/steps/`

- [ ] Test StartNodeStep validation
- [ ] Test AgentRoleStep form fields
- [ ] Test ToolsStep preset loading
- [ ] Test MemoryStep option selection
- [ ] Test OutputStep configuration
- [ ] Test ReviewStep summary display

### 7.4 Unit Tests: Node Forms
**Files:** `frontend/__tests__/components/graph-editor/forms/`

- [ ] Test NodeConfigDialog open/close
- [ ] Test PromptNodeForm validation
- [ ] Test HttpNodeForm URL validation
- [ ] Test TransformNodeForm expression field
- [ ] Test BranchNodeForm condition field
- [ ] Test MergeNodeForm strategy selection
- [ ] Test MemoryNodeForm action-based fields
- [ ] Test ToolNodeForm tool selection
- [ ] Test SubgraphNodeForm graph selection
- [ ] Test HumanGateNodeForm prompt field
- [ ] Test OutputNodeForm mapping editor
- [ ] Test AdvancedSettings collapse/expand

### 7.5 Unit Tests: Validation
**Files:** `frontend/__tests__/lib/`

- [ ] Test graph-validator.ts:
  - NO_START_NODE detection
  - NO_OUTPUT_NODE detection
  - DISCONNECTED_NODE detection
  - CYCLE_DETECTED detection
  - Valid graph passes
- [ ] Test quick-fixes.ts:
  - Add start fix
  - Add output fix
  - Connect node fix
- [ ] Test type-compatibility.ts:
  - Compatible types
  - Incompatible types
  - ANY type handling

### 7.6 Unit Tests: Data Types
**Files:** `frontend/__tests__/lib/`

- [ ] Test data-types.ts enum values
- [ ] Test node-type-signatures.ts for all types
- [ ] Test type-inference.ts:
  - Prompt node output
  - HTTP node output
  - Transform node output
  - Branch node (no output)
  - Merge node output

### 7.7 Unit Tests: Quick Node Presets
**File:** `frontend/__tests__/lib/quick-node-presets.test.ts`

- [ ] Test all presets have required fields
- [ ] Test preset configs are valid
- [ ] Test preset categories are valid
- [ ] Test preset search/filter

### 7.8 Component Tests: Validation UI
**Files:** `frontend/__tests__/components/graph-editor/validation/`

- [ ] Test ValidationOverlay renders
- [ ] Test MissingStartIndicator click action
- [ ] Test MissingEndIndicator click action
- [ ] Test ValidationStatusBar states
- [ ] Test ValidationErrorList interactions
- [ ] Test error highlighting on nodes
- [ ] Test error highlighting on edges

### 7.9 Component Tests: Data Type UI
**Files:** `frontend/__tests__/components/graph-editor/`

- [ ] Test DataTypeIndicator renders
- [ ] Test DataTypeTooltip content
- [ ] Test TypeMismatchWarning display
- [ ] Test TypedEdge rendering
- [ ] Test AvailableDataPanel content

### 7.10 E2E Test: Complete Wizard Flow
**File:** `frontend/__tests__/e2e/wizard-flow.spec.ts`

- [ ] Test wizard opens from button
- [ ] Test wizard opens from keyboard shortcut
- [ ] Test Step 1: Add start node
- [ ] Test Step 2: Define agent role
- [ ] Test Step 3: Add tools (with quick node)
- [ ] Test Step 4: Configure memory (skip)
- [ ] Test Step 5: Add output node
- [ ] Test Step 6: Review and save
- [ ] Test resulting graph is valid
- [ ] Test resulting graph can be run

### 7.11 E2E Test: Validation Feedback
**File:** `frontend/__tests__/e2e/validation.spec.ts`

- [ ] Test missing start shows indicator
- [ ] Test missing output shows indicator
- [ ] Test clicking indicator adds node
- [ ] Test validation status bar updates
- [ ] Test error list shows issues
- [ ] Test quick fix buttons work
- [ ] Test run blocked with errors

### 7.12 E2E Test: Node Configuration
**File:** `frontend/__tests__/e2e/node-config.spec.ts`

- [ ] Test clicking node type opens dialog
- [ ] Test form validation prevents save
- [ ] Test saving creates node on canvas
- [ ] Test quick node preset fills form
- [ ] Test agent fields save correctly
- [ ] Test advanced settings work

### 7.13 E2E Test: Data Type Display
**File:** `frontend/__tests__/e2e/data-types.spec.ts`

- [ ] Test edge shows type indicator
- [ ] Test type tooltip on hover
- [ ] Test type mismatch warning
- [ ] Test available data panel
- [ ] Test manual type override

### 7.14 Backend Tests: Enhanced Validation
**File:** `backend/tests/unit/domain/services/test_graph_validator.py`

- [ ] Test start edge validation
- [ ] Test output node validation
- [ ] Test disconnected node detection
- [ ] Test node config validation (strict mode)
- [ ] Test structured error format
- [ ] Test suggestions in errors

### 7.15 Backend Tests: Quick Templates API
**File:** `backend/tests/integration/adapters/test_quick_templates.py`

- [ ] Test list templates
- [ ] Test create user template
- [ ] Test delete template
- [ ] Test filter by category
- [ ] Test search by name
- [ ] Test system templates protected

### 7.16 Engine Tests: Data Types
**File:** `engine/test/graph_data_types_test.go`

- [ ] Test Edge.DataType parsing
- [ ] Test Graph with type metadata
- [ ] Test execution ignores types (no behavior change)
- [ ] Test type logging (debug mode)

### 7.17 Performance Testing
**File:** `frontend/__tests__/performance/`

- [ ] Test validation performance with large graphs (100+ nodes)
- [ ] Test type inference performance
- [ ] Test wizard rendering performance
- [ ] Test debounce timing for real-time validation
- [ ] Ensure no performance regression

### 7.18 Accessibility Testing
**File:** `frontend/__tests__/a11y/`

- [ ] Test wizard keyboard navigation
- [ ] Test form field labels and ARIA
- [ ] Test focus management in dialogs
- [ ] Test color contrast for indicators
- [ ] Test screen reader compatibility
- [ ] Run axe-core on wizard components

### 7.19 Create User Guide
**File:** `docs/user-guide/agent-wizard.md`

- [ ] Introduction to Agent Wizard
- [ ] When to use the wizard
- [ ] Step-by-step walkthrough:
  - Step 1: Add Start Node
  - Step 2: Define Agent Role
  - Step 3: Add Tools
  - Step 4: Configure Memory
  - Step 5: Add Output
  - Step 6: Review & Save
- [ ] Quick Node presets reference
- [ ] Keyboard shortcuts
- [ ] Troubleshooting common issues
- [ ] Screenshots for each step

### 7.20 Create Quick Reference Card
**File:** `docs/user-guide/wizard-quick-reference.md`

- [ ] One-page quick reference
- [ ] Keyboard shortcuts table
- [ ] Node types quick guide
- [ ] Data types quick guide
- [ ] Validation error codes
- [ ] Quick fixes reference

### 7.21 Update API Documentation
**Files:** `backend/` (OpenAPI/Swagger)

- [ ] Document `/api/graphs/validate` endpoint
- [ ] Document `/api/quick-templates` endpoints
- [ ] Include request/response examples
- [ ] Document error response format

### 7.22 Create Developer Documentation
**File:** `docs/developer/wizard-architecture.md`

- [ ] Wizard architecture overview
- [ ] Component structure diagram
- [ ] State management explanation
- [ ] Adding new wizard steps
- [ ] Adding new quick node presets
- [ ] Adding new node type forms
- [ ] Testing guidelines

### 7.23 Create Changelog Entry
**File:** `CHANGELOG.md`

- [ ] Document all new features:
  - Agent Creation Wizard
  - Node Configuration Dialog
  - Quick Node Presets
  - Graph Validation with Visual Feedback
  - Data Type Propagation
  - Contextual Help System
- [ ] List breaking changes (if any)
- [ ] List deprecations (if any)

### 7.24 Final Integration Test
**Manual Testing Checklist:**

- [ ] Fresh install: wizard works
- [ ] Existing graphs: no regression
- [ ] Create agent via wizard end-to-end
- [ ] Run created agent successfully
- [ ] Edit agent after creation
- [ ] All quick nodes work
- [ ] All node forms work
- [ ] Validation catches all errors
- [ ] Data types display correctly
- [ ] Help tooltips appear
- [ ] Keyboard shortcuts work
- [ ] Dark mode works
- [ ] Mobile responsive (if applicable)

---

## Acceptance Criteria

1. All unit tests passing (>90% coverage for new code)
2. All E2E tests passing
3. All backend tests passing
4. All engine tests passing
5. No performance regression
6. Accessibility audit passing
7. User guide complete and accurate
8. API documentation updated
9. Developer docs complete
10. Changelog updated

## Dependencies

- Stage 1-6 complete
- CI/CD pipeline configured
- Test environment ready

## Output

- Comprehensive test suite
- User documentation
- Developer documentation
- API documentation
- Changelog entry
- Performance benchmarks
- Accessibility audit report
