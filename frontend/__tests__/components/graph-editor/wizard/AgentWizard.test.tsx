import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { AgentWizard } from "@/components/graph-editor/wizard/AgentWizard";
import { NODE_TYPES } from "@/lib/graph-types";

const mockUseWizard = jest.fn();

jest.mock("@/contexts/WizardContext", () => ({
  useWizard: () => mockUseWizard(),
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

describe("AgentWizard", () => {
  beforeEach(() => {
    jest.clearAllMocks();
  });

  it("applies starter presets into wizard step data", async () => {
    const user = userEvent.setup();
    const { setStepData } = configureWizardMock({ currentStep: 0, canProceed: false });

    render(<AgentWizard />);

    await user.click(screen.getByRole("button", { name: /telegram bot/i }));
    expect(setStepData).toHaveBeenCalledWith(
      "role",
      expect.objectContaining({
        agentLabel: "Telegram Support Agent",
        model: "gpt-4.1-mini",
      }),
    );
    expect(setStepData).toHaveBeenCalledWith(
      "tools",
      expect.objectContaining({
        tools: ["telegram.send_message"],
      }),
    );
  });

  it("supports create-and-run-test completion from the review step", async () => {
    const { markStepComplete, exitWizard } = configureWizardMock({
      currentStep: 5,
      canProceed: true,
      isLastStep: true,
      stepData: {
        role: {
          agentLabel: "Inbox Agent",
          instructions: "Read unread email and send a reply when appropriate.",
          model: "gpt-4.1-mini",
          provider: "openai",
          temperature: 0.3,
        },
        tools: {
          tools: ["gmail.list_unread", "gmail.send_message"],
          approvalRequiredTools: ["gmail.send_message"],
        },
        memory: { type: "none" },
        output: { outputKey: "email_result" },
      },
    });
    const onComplete = jest.fn();
    const user = userEvent.setup();

    render(<AgentWizard onComplete={onComplete} />);

    await user.click(screen.getByRole("button", { name: /create & run test/i }));

    expect(markStepComplete).toHaveBeenCalled();
    expect(onComplete).toHaveBeenCalledWith(
      expect.objectContaining({
        runTest: true,
        blueprint: expect.objectContaining({
          nodes: expect.arrayContaining([
            expect.objectContaining({ nodeType: NODE_TYPES.AGENT }),
            expect.objectContaining({ nodeType: NODE_TYPES.OUTPUT }),
          ]),
        }),
      }),
    );
    expect(exitWizard).toHaveBeenCalled();
  });
});
