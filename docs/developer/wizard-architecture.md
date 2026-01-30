# Agent Wizard - Developer Documentation

Technical documentation for extending and maintaining the ForgeGraph Agent Creation Wizard.

## Table of Contents

- [Architecture Overview](#architecture-overview)
- [Component Structure](#component-structure)
- [State Management](#state-management)
- [Adding New Wizard Steps](#adding-new-wizard-steps)
- [Adding New Node Forms](#adding-new-node-forms)
- [Adding Quick Node Presets](#adding-quick-node-presets)
- [Testing Guidelines](#testing-guidelines)

---

## Architecture Overview

The wizard is built as a React component that overlays the graph editor canvas. It uses a context-based state management pattern for step navigation and data collection.

### Key Principles

1. **Non-destructive** - Wizard modifies the graph through the same APIs as manual editing
2. **Resumable** - Users can exit and re-enter without losing progress
3. **Validating** - Each step validates before allowing progression
4. **Composable** - Steps and forms are independent, reusable components

### Technology Stack

- **React 18** - UI framework
- **React Context** - State management for wizard flow
- **Shadcn/Radix UI** - Dialog, form, and UI components
- **React Flow** - Canvas integration for node creation

---

## Component Structure

```
frontend/components/graph-editor/
├── wizard/
│   ├── AgentWizard.tsx           # Main wizard orchestrator
│   ├── WizardContext.tsx         # State management context
│   ├── WizardStep.tsx            # Step wrapper component
│   ├── WizardProgress.tsx        # Progress indicator
│   ├── WizardNavigation.tsx      # Next/Back buttons
│   └── steps/
│       ├── StartNodeStep.tsx     # Step 1
│       ├── AgentRoleStep.tsx     # Step 2
│       ├── ToolsStep.tsx         # Step 3
│       ├── MemoryStep.tsx        # Step 4
│       ├── OutputStep.tsx        # Step 5
│       └── ReviewStep.tsx        # Step 6
├── forms/
│   ├── PromptNodeForm.tsx        # Prompt node config
│   ├── HttpNodeForm.tsx          # HTTP node config
│   ├── TransformNodeForm.tsx     # Transform node config
│   ├── BranchNodeForm.tsx        # Branch node config
│   ├── MergeNodeForm.tsx         # Merge node config
│   ├── MemoryNodeForm.tsx        # Memory node config
│   ├── ToolNodeForm.tsx          # Tool node config
│   ├── SubgraphNodeForm.tsx      # Subgraph node config
│   ├── HumanGateNodeForm.tsx     # Human gate config
│   ├── OutputNodeForm.tsx        # Output node config
│   ├── AgentFields.tsx           # Shared agent context fields
│   └── AdvancedSettings.tsx      # Shared advanced settings
├── NodeConfigDialog.tsx          # Universal node config modal
└── validation/
    ├── ValidationOverlay.tsx     # Visual error indicators
    └── ValidationStatusBar.tsx   # Status bar component
```

---

## State Management

### WizardContext

The wizard uses a React Context with a reducer pattern for state management.

**Location:** `frontend/components/graph-editor/wizard/WizardContext.tsx`

```typescript
interface WizardState {
  isActive: boolean;
  currentStep: number;
  totalSteps: number;
  stepData: Record<number, StepData>;
  completedSteps: Set<number>;
}

type WizardAction =
  | { type: 'START_WIZARD' }
  | { type: 'EXIT_WIZARD' }
  | { type: 'NEXT_STEP' }
  | { type: 'PREV_STEP' }
  | { type: 'GO_TO_STEP'; step: number }
  | { type: 'SET_STEP_DATA'; step: number; data: StepData }
  | { type: 'MARK_STEP_COMPLETE'; step: number };
```

### Using the Context

```typescript
import { useWizard } from './wizard/WizardContext';

function MyComponent() {
  const { state, dispatch } = useWizard();

  const handleNext = () => {
    dispatch({ type: 'NEXT_STEP' });
  };

  return (
    <button onClick={handleNext} disabled={!state.isActive}>
      Next
    </button>
  );
}
```

---

## Adding New Wizard Steps

### 1. Create the Step Component

Create a new file in `frontend/components/graph-editor/wizard/steps/`:

```typescript
// MyNewStep.tsx
import { useWizard } from '../WizardContext';

interface MyNewStepProps {
  onComplete: () => void;
}

export function MyNewStep({ onComplete }: MyNewStepProps) {
  const { state, dispatch } = useWizard();

  const handleAction = () => {
    // Perform step-specific logic
    dispatch({
      type: 'SET_STEP_DATA',
      step: STEP_NUMBER,
      data: { /* collected data */ }
    });
    onComplete();
  };

  return (
    <div className="space-y-4">
      <h3>Step Title</h3>
      <p>Step description and instructions.</p>
      {/* Step-specific UI */}
      <button onClick={handleAction}>Complete Step</button>
    </div>
  );
}
```

### 2. Register the Step

Update `AgentWizard.tsx` to include the new step:

```typescript
const WIZARD_STEPS = [
  { id: 1, title: 'Start', component: StartNodeStep },
  { id: 2, title: 'Role', component: AgentRoleStep },
  // ... existing steps
  { id: N, title: 'My New Step', component: MyNewStep }, // Add here
];
```

### 3. Add Step Validation (Optional)

If the step requires validation before proceeding:

```typescript
const validateStep = (stepData: StepData): string[] => {
  const errors: string[] = [];
  if (!stepData.requiredField) {
    errors.push('Required field is missing');
  }
  return errors;
};
```

---

## Adding New Node Forms

### 1. Create the Form Component

Create a new file in `frontend/components/graph-editor/forms/`:

```typescript
// MyNodeForm.tsx
"use client";

import { useCallback } from "react";
import { FormField } from "@/components/ui/form-field";
import { Input } from "@/components/ui/input";
import { AgentFields, type AgentConfig } from "./AgentFields";
import type { NodeFormProps } from "../NodeConfigDialog";

interface MyNodeConfig extends AgentConfig {
  myField?: string;
  anotherField?: number;
}

export function MyNodeForm({ config, onChange, setErrors }: NodeFormProps) {
  const nodeConfig = config as MyNodeConfig;

  const handleChange = useCallback(
    <K extends keyof MyNodeConfig>(field: K, value: MyNodeConfig[K]) => {
      onChange({ ...config, [field]: value });
    },
    [config, onChange]
  );

  const handleAgentChange = useCallback(
    (agentConfig: AgentConfig) => {
      onChange({ ...config, ...agentConfig });
    },
    [config, onChange]
  );

  return (
    <div className="space-y-6">
      {/* Shared agent context fields */}
      <AgentFields
        config={nodeConfig}
        onChange={handleAgentChange}
      />

      {/* Node-specific fields */}
      <FormField
        label="My Field"
        description="Description of what this field does"
        required
      >
        <Input
          value={nodeConfig.myField || ""}
          onChange={(e) => handleChange("myField", e.target.value)}
          placeholder="Enter value..."
        />
      </FormField>
    </div>
  );
}

export default MyNodeForm;
```

### 2. Register the Form

Update the form registry in `NodeConfigDialog.tsx`:

```typescript
import { MyNodeForm } from "./forms/MyNodeForm";

const NODE_FORM_COMPONENTS: Partial<Record<string, React.ComponentType<NodeFormProps>>> = {
  [NODE_TYPES.PROMPT]: PromptNodeForm,
  [NODE_TYPES.HTTP]: HttpNodeForm,
  // ... existing forms
  [NODE_TYPES.MY_NODE]: MyNodeForm, // Add here
};
```

### 3. Add the Node Type

If this is a completely new node type, update `frontend/lib/graph-types.ts`:

```typescript
export const NODE_TYPES = {
  // ... existing types
  MY_NODE: "my_node",
} as const;
```

---

## Adding Quick Node Presets

### 1. Define the Preset

Update `frontend/lib/quick-node-presets.ts`:

```typescript
export const QUICK_NODE_PRESETS: QuickNodePreset[] = [
  // ... existing presets
  {
    id: "my-preset",
    name: "My Preset",
    description: "Description of what this preset does",
    category: "integration", // or "ai", "logic"
    nodeType: NODE_TYPES.HTTP,
    config: {
      url: "https://api.example.com/endpoint",
      method: "GET",
      headers: {
        "Content-Type": "application/json",
      },
    },
  },
];
```

### 2. Preset Categories

Available categories:
- `ai` - AI/LLM related presets
- `integration` - External service integrations
- `logic` - Control flow and data processing

### 3. Preset Structure

```typescript
interface QuickNodePreset {
  id: string;           // Unique identifier
  name: string;         // Display name
  description: string;  // Short description
  category: string;     // Category for grouping
  nodeType: string;     // The node type this creates
  config: object;       // Pre-filled configuration
}
```

---

## Testing Guidelines

### Unit Tests

Location: `frontend/__tests__/components/graph-editor/`

**Test Categories:**
1. **Component rendering** - Components render correctly with various props
2. **User interactions** - Click, type, and keyboard events work
3. **State management** - Context updates correctly
4. **Validation** - Form validation and error states
5. **Accessibility** - Keyboard navigation, ARIA labels

**Example Test:**

```typescript
import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { MyNodeForm } from "@/components/graph-editor/forms/MyNodeForm";

describe("MyNodeForm", () => {
  it("should update config when field changes", async () => {
    const mockOnChange = jest.fn();
    const user = userEvent.setup();

    render(
      <MyNodeForm
        config={{}}
        onChange={mockOnChange}
        setErrors={jest.fn()}
      />
    );

    await user.type(screen.getByLabelText("My Field"), "test value");

    expect(mockOnChange).toHaveBeenCalledWith(
      expect.objectContaining({ myField: "test value" })
    );
  });
});
```

### E2E Tests

Location: `frontend/__tests__/e2e/`

**Test Scenarios:**
1. Complete wizard flow from start to finish
2. Validation feedback and error handling
3. Quick node preset functionality
4. Graph save and reload

**Example E2E Test:**

```typescript
import { test, expect } from "@playwright/test";

test("wizard creates valid agent", async ({ page }) => {
  await page.goto("/graphs");
  await page.getByRole("button", { name: /new graph/i }).click();
  // ... complete wizard steps
  await expect(page.getByText("Graph Valid")).toBeVisible();
});
```

### Running Tests

```bash
# Unit tests
npm test

# Unit tests in watch mode
npm run test:watch

# E2E tests
npm run test:e2e

# E2E tests with UI
npm run test:e2e:ui
```

---

## Best Practices

### Form Components

1. **Use controlled inputs** - All form fields should be controlled
2. **Debounce expensive operations** - Validation, API calls
3. **Provide clear error messages** - Use `setErrors` prop
4. **Support keyboard navigation** - Tab order, enter to submit

### Wizard Steps

1. **Keep steps focused** - One primary action per step
2. **Allow skipping optional steps** - Don't block on non-essential data
3. **Persist data on navigation** - Users shouldn't lose work going back
4. **Validate before proceeding** - Don't let users advance with errors

### Performance

1. **Memoize callbacks** - Use `useCallback` for handlers
2. **Lazy load forms** - Only load form components when needed
3. **Debounce validation** - Don't validate on every keystroke
4. **Virtual scrolling** - For large preset/option lists

---

## Related Documentation

- [User Guide](../user-guide/agent-wizard.md) - End-user documentation
- [Quick Reference](../user-guide/wizard-quick-reference.md) - One-page reference
- [Implementation Plan](../wizard-implementation-plan.md) - Original design document
