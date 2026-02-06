"use client";

import {
  createContext,
  useCallback,
  useContext,
  useMemo,
  useReducer,
  type ReactNode,
} from "react";

/**
 * Wizard step configuration
 */
export interface WizardStepConfig {
  id: string;
  title: string;
  description: string;
  isRequired: boolean;
  canSkip: boolean;
}

/**
 * Wizard state
 */
export interface WizardState {
  isActive: boolean;
  currentStep: number;
  totalSteps: number;
  completedSteps: Set<number>;
  skippedSteps: Set<number>;
  stepData: Record<string, unknown>;
  canProceed: boolean;
  canGoBack: boolean;
  isNewGraph: boolean;
}

/**
 * Wizard action types
 */
type WizardAction =
  | { type: "START_WIZARD"; payload?: { isNewGraph?: boolean } }
  | { type: "EXIT_WIZARD" }
  | { type: "NEXT_STEP" }
  | { type: "PREV_STEP" }
  | { type: "GO_TO_STEP"; payload: number }
  | { type: "SET_STEP_DATA"; payload: { stepId: string; data: unknown } }
  | { type: "MARK_STEP_COMPLETE"; payload: number }
  | { type: "MARK_STEP_SKIPPED"; payload: number }
  | { type: "SET_CAN_PROCEED"; payload: boolean }
  | { type: "RESET_WIZARD" };

/**
 * Default wizard steps configuration
 */
export const DEFAULT_WIZARD_STEPS: WizardStepConfig[] = [
  {
    id: "start",
    title: "Add Start Node",
    description: "Define the entry point of your agent workflow",
    isRequired: true,
    canSkip: false,
  },
  {
    id: "role",
    title: "Configure Prompt",
    description: "Define the core task and response style for your agent",
    isRequired: true,
    canSkip: false,
  },
  {
    id: "tools",
    title: "Add Tools & Actions",
    description: "Configure the tools and actions your agent can use",
    isRequired: false,
    canSkip: true,
  },
  {
    id: "memory",
    title: "Configure Memory",
    description: "Set up persistent memory for your agent",
    isRequired: false,
    canSkip: true,
  },
  {
    id: "output",
    title: "Add Output Node",
    description: "Define what your agent returns",
    isRequired: true,
    canSkip: false,
  },
  {
    id: "review",
    title: "Preflight Check",
    description: "Validate your setup and finish the wizard",
    isRequired: true,
    canSkip: false,
  },
];

const initialState: WizardState = {
  isActive: false,
  currentStep: 0,
  totalSteps: DEFAULT_WIZARD_STEPS.length,
  completedSteps: new Set(),
  skippedSteps: new Set(),
  stepData: {},
  canProceed: false,
  canGoBack: false,
  isNewGraph: false,
};

function wizardReducer(state: WizardState, action: WizardAction): WizardState {
  switch (action.type) {
    case "START_WIZARD":
      return {
        ...initialState,
        isActive: true,
        totalSteps: DEFAULT_WIZARD_STEPS.length,
        isNewGraph: action.payload?.isNewGraph ?? false,
      };

    case "EXIT_WIZARD":
      return {
        ...state,
        isActive: false,
      };

    case "NEXT_STEP":
      if (state.currentStep >= state.totalSteps - 1) {
        return state;
      }
      return {
        ...state,
        currentStep: state.currentStep + 1,
        canGoBack: true,
        canProceed: false, // Reset until step validates
      };

    case "PREV_STEP":
      if (state.currentStep <= 0) {
        return state;
      }
      return {
        ...state,
        currentStep: state.currentStep - 1,
        canGoBack: state.currentStep - 1 > 0,
        canProceed: true, // Previous steps are already validated
      };

    case "GO_TO_STEP": {
      const targetStep = action.payload;
      if (targetStep < 0 || targetStep >= state.totalSteps) {
        return state;
      }
      // Can only jump to completed steps or current step
      if (targetStep > state.currentStep && !state.completedSteps.has(targetStep)) {
        return state;
      }
      return {
        ...state,
        currentStep: targetStep,
        canGoBack: targetStep > 0,
        canProceed: state.completedSteps.has(targetStep),
      };
    }

    case "SET_STEP_DATA":
      return {
        ...state,
        stepData: {
          ...state.stepData,
          [action.payload.stepId]: action.payload.data,
        },
      };

    case "MARK_STEP_COMPLETE": {
      const newCompleted = new Set(state.completedSteps);
      newCompleted.add(action.payload);
      return {
        ...state,
        completedSteps: newCompleted,
        canProceed: true,
      };
    }

    case "MARK_STEP_SKIPPED": {
      const newSkipped = new Set(state.skippedSteps);
      newSkipped.add(action.payload);
      // Also mark as complete for navigation purposes
      const newCompleted = new Set(state.completedSteps);
      newCompleted.add(action.payload);
      return {
        ...state,
        skippedSteps: newSkipped,
        completedSteps: newCompleted,
        canProceed: true,
      };
    }

    case "SET_CAN_PROCEED":
      return {
        ...state,
        canProceed: action.payload,
      };

    case "RESET_WIZARD":
      return initialState;

    default:
      return state;
  }
}

/**
 * Wizard context value
 */
interface WizardContextValue {
  state: WizardState;
  steps: WizardStepConfig[];
  currentStepConfig: WizardStepConfig | null;

  // Actions
  startWizard: (isNewGraph?: boolean) => void;
  exitWizard: () => void;
  nextStep: () => void;
  prevStep: () => void;
  goToStep: (step: number) => void;
  setStepData: (stepId: string, data: unknown) => void;
  markStepComplete: (step?: number) => void;
  markStepSkipped: (step?: number) => void;
  setCanProceed: (canProceed: boolean) => void;
  resetWizard: () => void;

  // Computed
  isFirstStep: boolean;
  isLastStep: boolean;
  progress: number;
}

const WizardContext = createContext<WizardContextValue | undefined>(undefined);

export function WizardProvider({ children }: { children: ReactNode }) {
  const [state, dispatch] = useReducer(wizardReducer, initialState);

  const startWizard = useCallback((isNewGraph?: boolean) => {
    dispatch({ type: "START_WIZARD", payload: { isNewGraph } });
  }, []);

  const exitWizard = useCallback(() => {
    dispatch({ type: "EXIT_WIZARD" });
  }, []);

  const nextStep = useCallback(() => {
    dispatch({ type: "NEXT_STEP" });
  }, []);

  const prevStep = useCallback(() => {
    dispatch({ type: "PREV_STEP" });
  }, []);

  const goToStep = useCallback((step: number) => {
    dispatch({ type: "GO_TO_STEP", payload: step });
  }, []);

  const setStepData = useCallback((stepId: string, data: unknown) => {
    dispatch({ type: "SET_STEP_DATA", payload: { stepId, data } });
  }, []);

  const markStepComplete = useCallback((step?: number) => {
    dispatch({ type: "MARK_STEP_COMPLETE", payload: step ?? state.currentStep });
  }, [state.currentStep]);

  const markStepSkipped = useCallback((step?: number) => {
    dispatch({ type: "MARK_STEP_SKIPPED", payload: step ?? state.currentStep });
  }, [state.currentStep]);

  const setCanProceed = useCallback((canProceed: boolean) => {
    dispatch({ type: "SET_CAN_PROCEED", payload: canProceed });
  }, []);

  const resetWizard = useCallback(() => {
    dispatch({ type: "RESET_WIZARD" });
  }, []);

  const currentStepConfig = useMemo(() => {
    return DEFAULT_WIZARD_STEPS[state.currentStep] ?? null;
  }, [state.currentStep]);

  const isFirstStep = state.currentStep === 0;
  const isLastStep = state.currentStep === state.totalSteps - 1;
  const progress = state.totalSteps > 0
    ? ((state.completedSteps.size / state.totalSteps) * 100)
    : 0;

  const value = useMemo<WizardContextValue>(
    () => ({
      state,
      steps: DEFAULT_WIZARD_STEPS,
      currentStepConfig,
      startWizard,
      exitWizard,
      nextStep,
      prevStep,
      goToStep,
      setStepData,
      markStepComplete,
      markStepSkipped,
      setCanProceed,
      resetWizard,
      isFirstStep,
      isLastStep,
      progress,
    }),
    [
      state,
      currentStepConfig,
      startWizard,
      exitWizard,
      nextStep,
      prevStep,
      goToStep,
      setStepData,
      markStepComplete,
      markStepSkipped,
      setCanProceed,
      resetWizard,
      isFirstStep,
      isLastStep,
      progress,
    ],
  );

  return (
    <WizardContext.Provider value={value}>{children}</WizardContext.Provider>
  );
}

export function useWizard(): WizardContextValue {
  const context = useContext(WizardContext);
  if (!context) {
    throw new Error("useWizard must be used within a WizardProvider");
  }
  return context;
}

export default WizardContext;
