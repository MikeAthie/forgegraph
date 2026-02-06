import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { AgentWizard } from "@/components/graph-editor/wizard/AgentWizard";
import { ValidationErrorCode } from "@/lib/graph-validator";

const mockUseWizard = jest.fn();
const mockUseValidation = jest.fn();

jest.mock("@/contexts/WizardContext", () => ({
  useWizard: () => mockUseWizard(),
}));

jest.mock("@/contexts/ValidationContext", () => ({
  useValidation: () => mockUseValidation(),
}));

jest.mock("@/components/graph-editor/QuickNodePalette", () => ({
  QuickNodePalette: () => <div data-testid="quick-node-palette" />,
}));

type WizardStepConfig = {
  id: string;
  title: string;
  description: string;
  isRequired: boolean;
  canSkip: boolean;
};

const stepConfigs: WizardStepConfig[] = [
  { id: "start", title: "Add Start Node", description: "", isRequired: true, canSkip: false },
  { id: "role", title: "Configure Prompt", description: "", isRequired: true, canSkip: false },
  { id: "tools", title: "Add Tools & Actions", description: "", isRequired: false, canSkip: true },
  { id: "memory", title: "Configure Memory", description: "", isRequired: false, canSkip: true },
  { id: "output", title: "Add Output Node", description: "", isRequired: true, canSkip: false },
  { id: "review", title: "Preflight Check", description: "", isRequired: true, canSkip: false },
];

function configureWizardMock(overrides?: {
  currentStep?: number;
  canProceed?: boolean;
  stepData?: Record<string, unknown>;
  isLastStep?: boolean;
}) {
  const currentStep = overrides?.currentStep ?? 0;
  const canProceed = overrides?.canProceed ?? true;
  const stepData = overrides?.stepData ?? {};
  const markStepComplete = jest.fn();
  const goToStep = jest.fn();
  const exitWizard = jest.fn();
  const setCanProceed = jest.fn();
  const setStepData = jest.fn();

  mockUseWizard.mockReturnValue({
    state: {
      isActive: true,
      currentStep,
      totalSteps: stepConfigs.length,
      completedSteps: new Set<number>(),
      skippedSteps: new Set<number>(),
      stepData,
      canProceed,
      canGoBack: currentStep > 0,
      isNewGraph: false,
    },
    steps: stepConfigs,
    currentStepConfig: stepConfigs[currentStep] ?? null,
    nextStep: jest.fn(),
    prevStep: jest.fn(),
    markStepComplete,
    markStepSkipped: jest.fn(),
    exitWizard,
    isFirstStep: currentStep === 0,
    isLastStep: overrides?.isLastStep ?? currentStep === stepConfigs.length - 1,
    goToStep,
    setCanProceed,
    setStepData,
    startWizard: jest.fn(),
    resetWizard: jest.fn(),
    progress: 0,
  });

  return { markStepComplete, goToStep, exitWizard, setCanProceed, setStepData };
}

function configureValidationMock(overrides?: {
  isValid?: boolean;
  hasStartNode?: boolean;
  hasOutputNode?: boolean;
  errors?: Array<{ code: ValidationErrorCode; message: string; suggestion?: string }>;
}) {
  mockUseValidation.mockReturnValue({
    isValid: overrides?.isValid ?? true,
    hasStartNode: overrides?.hasStartNode ?? true,
    hasOutputNode: overrides?.hasOutputNode ?? true,
    hasEndNode: true,
    errors: overrides?.errors ?? [],
    warnings: [],
    result: null,
    validate: jest.fn(),
    clearValidation: jest.fn(),
    isStatusBarExpanded: false,
    setStatusBarExpanded: jest.fn(),
    focusedErrorId: null,
    setFocusedErrorId: jest.fn(),
  });
}

describe("AgentWizard", () => {
  beforeEach(() => {
    jest.clearAllMocks();
  });

  it("applies starter presets from the start step", async () => {
    configureWizardMock({ currentStep: 0, canProceed: false });
    configureValidationMock({ hasStartNode: false, hasOutputNode: false, isValid: false });
    const onApplyPreset = jest.fn();
    const user = userEvent.setup();

    render(<AgentWizard onApplyPreset={onApplyPreset} />);

    await user.click(screen.getByRole("button", { name: /telegram bot/i }));
    expect(onApplyPreset).toHaveBeenCalledWith(expect.objectContaining({ id: "telegram-bot" }));
  });

  it("shows preflight fix actions and jumps to target steps", async () => {
    const { goToStep } = configureWizardMock({ currentStep: 5, canProceed: false, isLastStep: true });
    configureValidationMock({
      isValid: false,
      hasStartNode: true,
      hasOutputNode: false,
      errors: [
        {
          code: ValidationErrorCode.NO_OUTPUT_NODE,
          message: "Graph needs an output node",
          suggestion: "Add an Output node to define the workflow result",
        },
      ],
    });
    const user = userEvent.setup();

    render(<AgentWizard />);

    await user.click(screen.getByRole("button", { name: /fix in add output node/i }));
    expect(goToStep).toHaveBeenCalledWith(4);
  });

  it("supports create-and-run-test completion from the review step", async () => {
    const { markStepComplete, exitWizard } = configureWizardMock({
      currentStep: 5,
      canProceed: true,
      isLastStep: true,
    });
    configureValidationMock({ isValid: true, hasStartNode: true, hasOutputNode: true });
    const onComplete = jest.fn();
    const user = userEvent.setup();

    render(<AgentWizard onComplete={onComplete} />);

    await user.click(screen.getByRole("button", { name: /create & run test/i }));

    expect(markStepComplete).toHaveBeenCalled();
    expect(onComplete).toHaveBeenCalledWith({ runTest: true });
    expect(exitWizard).toHaveBeenCalled();
  });
});
