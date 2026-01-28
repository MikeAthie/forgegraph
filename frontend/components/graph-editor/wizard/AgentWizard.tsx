"use client";

import { useCallback, useEffect } from "react";
import { useWizard } from "@/contexts/WizardContext";
import { cn } from "@/lib/utils";
import { WizardProgress } from "./WizardProgress";
import { WizardNavigation } from "./WizardNavigation";
import { WizardStep } from "./WizardStep";

// Placeholder step components - will be replaced with actual implementations
function StartNodeStep() {
  const { setCanProceed } = useWizard();

  useEffect(() => {
    // For now, allow proceeding immediately (will be replaced with actual validation)
    setCanProceed(true);
  }, [setCanProceed]);

  return (
    <div className="space-y-4">
      <p className="text-muted-foreground">
        Every agent workflow needs a starting point. The start node defines where your agent begins processing.
      </p>
      <div className="p-4 border rounded-lg bg-muted/30">
        <p className="text-sm">
          Click on the canvas to place your first node, or select an existing node to mark as the entry point.
        </p>
      </div>
    </div>
  );
}

function AgentRoleStep() {
  const { setCanProceed } = useWizard();

  useEffect(() => {
    setCanProceed(true);
  }, [setCanProceed]);

  return (
    <div className="space-y-4">
      <p className="text-muted-foreground">
        Define your agent&apos;s persona and primary objective. This helps guide the agent&apos;s behavior.
      </p>
      <div className="space-y-4">
        <div>
          <label className="text-sm font-medium">Agent Role</label>
          <input
            type="text"
            placeholder="e.g., Customer Support Agent"
            className="w-full mt-1 px-3 py-2 border rounded-md bg-background"
          />
        </div>
        <div>
          <label className="text-sm font-medium">Primary Objective</label>
          <textarea
            placeholder="e.g., Help customers resolve issues and answer questions"
            className="w-full mt-1 px-3 py-2 border rounded-md bg-background resize-none"
            rows={3}
          />
        </div>
      </div>
    </div>
  );
}

function ToolsStep() {
  const { setCanProceed } = useWizard();

  useEffect(() => {
    setCanProceed(true);
  }, [setCanProceed]);

  return (
    <div className="space-y-4">
      <p className="text-muted-foreground">
        Add tools and actions your agent can use. This step is optional.
      </p>
      <div className="grid grid-cols-2 gap-3">
        {["HTTP Request", "Transform Data", "Memory Store", "Call Tool"].map((tool) => (
          <button
            key={tool}
            type="button"
            className="p-3 border rounded-lg text-left hover:bg-muted/50 transition-colors"
          >
            <span className="text-sm font-medium">{tool}</span>
          </button>
        ))}
      </div>
    </div>
  );
}

function MemoryStep() {
  const { setCanProceed } = useWizard();

  useEffect(() => {
    setCanProceed(true);
  }, [setCanProceed]);

  return (
    <div className="space-y-4">
      <p className="text-muted-foreground">
        Configure memory for your agent. Memory allows your agent to remember information across conversations.
      </p>
      <div className="space-y-2">
        {[
          { label: "No Memory", description: "Stateless agent" },
          { label: "Session Memory", description: "Remember within conversation" },
          { label: "Persistent Memory", description: "Remember across sessions" },
        ].map((option) => (
          <button
            key={option.label}
            type="button"
            className="w-full p-3 border rounded-lg text-left hover:bg-muted/50 transition-colors"
          >
            <span className="text-sm font-medium">{option.label}</span>
            <p className="text-xs text-muted-foreground">{option.description}</p>
          </button>
        ))}
      </div>
    </div>
  );
}

function OutputStep() {
  const { setCanProceed } = useWizard();

  useEffect(() => {
    setCanProceed(true);
  }, [setCanProceed]);

  return (
    <div className="space-y-4">
      <p className="text-muted-foreground">
        Define what your agent returns. The output node captures the final result of your workflow.
      </p>
      <div className="p-4 border rounded-lg bg-muted/30">
        <p className="text-sm">
          An output node will be added to capture the final result. You can configure what data to extract.
        </p>
      </div>
    </div>
  );
}

function ReviewStep() {
  const { setCanProceed } = useWizard();

  useEffect(() => {
    setCanProceed(true);
  }, [setCanProceed]);

  return (
    <div className="space-y-4">
      <p className="text-muted-foreground">
        Review your agent configuration before saving.
      </p>
      <div className="p-4 border rounded-lg bg-muted/30 space-y-2">
        <div className="flex justify-between text-sm">
          <span className="text-muted-foreground">Start Node:</span>
          <span>Configured</span>
        </div>
        <div className="flex justify-between text-sm">
          <span className="text-muted-foreground">Agent Role:</span>
          <span>Customer Support Agent</span>
        </div>
        <div className="flex justify-between text-sm">
          <span className="text-muted-foreground">Tools:</span>
          <span>2 configured</span>
        </div>
        <div className="flex justify-between text-sm">
          <span className="text-muted-foreground">Output:</span>
          <span>Configured</span>
        </div>
      </div>
    </div>
  );
}

const STEP_COMPONENTS: Record<string, React.ComponentType> = {
  start: StartNodeStep,
  role: AgentRoleStep,
  tools: ToolsStep,
  memory: MemoryStep,
  output: OutputStep,
  review: ReviewStep,
};

export interface AgentWizardProps {
  onComplete?: () => void;
  onExit?: () => void;
  className?: string;
}

export function AgentWizard({ onComplete, onExit, className }: AgentWizardProps) {
  const { state, currentStepConfig, exitWizard } = useWizard();

  const handleComplete = useCallback(() => {
    onComplete?.();
    exitWizard();
  }, [onComplete, exitWizard]);

  const handleExit = useCallback(() => {
    onExit?.();
    exitWizard();
  }, [onExit, exitWizard]);

  // Handle Escape key
  useEffect(() => {
    const handleKeyDown = (e: KeyboardEvent) => {
      if (e.key === "Escape") {
        handleExit();
      }
    };

    window.addEventListener("keydown", handleKeyDown);
    return () => window.removeEventListener("keydown", handleKeyDown);
  }, [handleExit]);

  if (!state.isActive) {
    return null;
  }

  const StepComponent = currentStepConfig
    ? STEP_COMPONENTS[currentStepConfig.id]
    : null;

  return (
    <div
      className={cn(
        "fixed inset-0 z-50 flex items-center justify-center",
        className
      )}
    >
      {/* Backdrop */}
      <div
        className="absolute inset-0 bg-black/50 backdrop-blur-sm"
        onClick={handleExit}
      />

      {/* Wizard Panel */}
      <div className="relative z-10 w-full max-w-lg mx-4 bg-background border rounded-xl shadow-2xl overflow-hidden flex flex-col max-h-[80vh]">
        {/* Progress */}
        <WizardProgress />

        {/* Step Content */}
        <div className="flex-1 overflow-hidden">
          {currentStepConfig && StepComponent && (
            <WizardStep
              title={currentStepConfig.title}
              description={currentStepConfig.description}
            >
              <StepComponent />
            </WizardStep>
          )}
        </div>

        {/* Navigation */}
        <WizardNavigation onComplete={handleComplete} />
      </div>
    </div>
  );
}

export default AgentWizard;
