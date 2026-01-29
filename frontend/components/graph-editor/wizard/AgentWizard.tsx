"use client";

import { useCallback, useEffect, useState } from "react";
import { useWizard } from "@/contexts/WizardContext";
import { useValidation } from "@/contexts/ValidationContext";
import { cn } from "@/lib/utils";
import { WizardProgress } from "./WizardProgress";
import { WizardNavigation } from "./WizardNavigation";
import { WizardStep } from "./WizardStep";
import { QuickNodePalette } from "../QuickNodePalette";
import { CheckCircle, AlertCircle, Sparkles, Zap, Brain, FileOutput } from "lucide-react";
import { Input } from "@/components/ui/input";
import { Textarea } from "@/components/ui/textarea";
import type { QuickNodePreset } from "@/lib/quick-node-presets";

interface StepProps {
  onAddNode?: (preset: QuickNodePreset) => void;
}

// Step 1: Start Node
function StartNodeStep({ onAddNode }: StepProps) {
  const { setCanProceed, setStepData } = useWizard();
  const { hasStartNode } = useValidation();

  useEffect(() => {
    setCanProceed(hasStartNode);
    setStepData("start", { hasStartNode });
  }, [hasStartNode, setCanProceed, setStepData]);

  return (
    <div className="space-y-4">
      <p className="text-muted-foreground">
        Every agent workflow needs a starting point. The start node defines where your agent begins processing.
      </p>

      <div className={cn(
        "p-4 border rounded-lg flex items-center gap-3",
        hasStartNode
          ? "border-emerald-500/50 bg-emerald-500/10"
          : "border-amber-500/50 bg-amber-500/10"
      )}>
        {hasStartNode ? (
          <>
            <CheckCircle className="w-5 h-5 text-emerald-500 shrink-0" />
            <div>
              <p className="text-sm font-medium text-emerald-600 dark:text-emerald-400">Start node configured</p>
              <p className="text-xs text-muted-foreground">Your workflow has an entry point</p>
            </div>
          </>
        ) : (
          <>
            <AlertCircle className="w-5 h-5 text-amber-500 shrink-0" />
            <div>
              <p className="text-sm font-medium text-amber-600 dark:text-amber-400">No start node yet</p>
              <p className="text-xs text-muted-foreground">Add a node from the palette or use a Quick Node below</p>
            </div>
          </>
        )}
      </div>

      {!hasStartNode && onAddNode && (
        <div className="pt-2">
          <p className="text-sm font-medium mb-3">Quick Start - Add a Prompt Node:</p>
          <QuickNodePalette
            onSelectPreset={onAddNode}
            showSearch={false}
            showCategories={false}
            compact
          />
        </div>
      )}
    </div>
  );
}

// Step 2: Agent Role
function AgentRoleStep() {
  const { setCanProceed, state, setStepData } = useWizard();
  const [agentName, setAgentName] = useState(
    (state.stepData.role as { agentName?: string })?.agentName || ""
  );
  const [objective, setObjective] = useState(
    (state.stepData.role as { objective?: string })?.objective || ""
  );

  useEffect(() => {
    const isValid = agentName.trim().length > 0;
    setCanProceed(isValid);
    setStepData("role", { agentName, objective });
  }, [agentName, objective, setCanProceed, setStepData]);

  return (
    <div className="space-y-4">
      <p className="text-muted-foreground">
        Define your agent&apos;s persona. This helps guide the behavior of AI prompts in your workflow.
      </p>

      <div className="space-y-4">
        <div>
          <label htmlFor="agent-name" className="text-sm font-medium">Agent Name <span className="text-destructive">*</span></label>
          <Input
            id="agent-name"
            type="text"
            placeholder="e.g., Customer Support Agent"
            value={agentName}
            onChange={(e) => setAgentName(e.target.value)}
            className="mt-1"
          />
        </div>
        <div>
          <label htmlFor="objective" className="text-sm font-medium">Primary Objective</label>
          <Textarea
            id="objective"
            placeholder="e.g., Help customers resolve issues and answer questions about our products"
            value={objective}
            onChange={(e) => setObjective(e.target.value)}
            rows={3}
            className="mt-1 resize-none"
          />
        </div>
      </div>

      <div className="p-3 bg-muted/50 rounded-md text-xs space-y-1.5">
        <p className="font-medium">Role examples:</p>
        <ul className="list-disc list-inside text-muted-foreground">
          <li>Technical Support Engineer at Acme Corp</li>
          <li>Sales Assistant for E-commerce Platform</li>
          <li>Content Writer specialized in Blog Posts</li>
        </ul>
      </div>
    </div>
  );
}

// Step 3: Tools
function ToolsStep({ onAddNode }: StepProps) {
  const { setCanProceed } = useWizard();

  useEffect(() => {
    // Tools step is optional, always allow proceeding
    setCanProceed(true);
  }, [setCanProceed]);

  return (
    <div className="space-y-4">
      <p className="text-muted-foreground">
        Add tools and actions your agent can use. This step is optional - you can skip it or add tools later.
      </p>

      {onAddNode && (
        <QuickNodePalette
          onSelectPreset={onAddNode}
          showSearch
          showCategories
          compact={false}
        />
      )}

      <div className="p-3 bg-muted/50 rounded-md text-xs">
        <p className="text-muted-foreground">
          <strong>Tip:</strong> You can always add more nodes later from the Node Palette on the left.
        </p>
      </div>
    </div>
  );
}

// Step 4: Memory
function MemoryStep({ onAddNode }: StepProps) {
  const { setCanProceed, setStepData } = useWizard();
  const [selectedMemory, setSelectedMemory] = useState<string | null>(null);

  useEffect(() => {
    // Memory step is optional
    setCanProceed(true);
    setStepData("memory", { type: selectedMemory });
  }, [selectedMemory, setCanProceed, setStepData]);

  const memoryOptions = [
    {
      id: "none",
      label: "No Memory",
      description: "Stateless agent - each run is independent",
      icon: Zap,
    },
    {
      id: "session",
      label: "Session Memory",
      description: "Remember within a single conversation",
      icon: Brain,
    },
    {
      id: "persistent",
      label: "Persistent Memory",
      description: "Remember across all sessions (requires memory node)",
      icon: Brain,
    },
  ];

  return (
    <div className="space-y-4">
      <p className="text-muted-foreground">
        Configure memory for your agent. Memory allows your agent to remember information across interactions.
      </p>

      <div className="space-y-2">
        {memoryOptions.map((option) => {
          const Icon = option.icon;
          return (
            <button
              key={option.id}
              type="button"
              onClick={() => setSelectedMemory(option.id)}
              className={cn(
                "w-full p-3 border rounded-lg text-left transition-colors flex items-start gap-3",
                selectedMemory === option.id
                  ? "border-primary bg-primary/5"
                  : "hover:bg-muted/50"
              )}
            >
              <Icon className={cn(
                "w-5 h-5 mt-0.5 shrink-0",
                selectedMemory === option.id ? "text-primary" : "text-muted-foreground"
              )} />
              <div>
                <span className="text-sm font-medium">{option.label}</span>
                <p className="text-xs text-muted-foreground">{option.description}</p>
              </div>
            </button>
          );
        })}
      </div>

      {selectedMemory === "persistent" && onAddNode && (
        <div className="p-3 bg-muted/50 rounded-md">
          <p className="text-xs text-muted-foreground mb-2">
            Add a Memory node to enable persistent memory:
          </p>
          <QuickNodePalette
            onSelectPreset={onAddNode}
            showSearch={false}
            showCategories={false}
            compact
          />
        </div>
      )}
    </div>
  );
}

// Step 5: Output
function OutputStep({ onAddNode }: StepProps) {
  const { setCanProceed } = useWizard();
  const { hasOutputNode } = useValidation();

  useEffect(() => {
    setCanProceed(hasOutputNode);
  }, [hasOutputNode, setCanProceed]);

  return (
    <div className="space-y-4">
      <p className="text-muted-foreground">
        Define what your agent returns. The output node captures the final result of your workflow.
      </p>

      <div className={cn(
        "p-4 border rounded-lg flex items-center gap-3",
        hasOutputNode
          ? "border-emerald-500/50 bg-emerald-500/10"
          : "border-amber-500/50 bg-amber-500/10"
      )}>
        {hasOutputNode ? (
          <>
            <CheckCircle className="w-5 h-5 text-emerald-500 shrink-0" />
            <div>
              <p className="text-sm font-medium text-emerald-600 dark:text-emerald-400">Output node configured</p>
              <p className="text-xs text-muted-foreground">Your workflow has a defined output</p>
            </div>
          </>
        ) : (
          <>
            <FileOutput className="w-5 h-5 text-amber-500 shrink-0" />
            <div>
              <p className="text-sm font-medium text-amber-600 dark:text-amber-400">No output node yet</p>
              <p className="text-xs text-muted-foreground">Add an Output node to define the workflow result</p>
            </div>
          </>
        )}
      </div>

      {!hasOutputNode && onAddNode && (
        <div className="pt-2">
          <p className="text-sm font-medium mb-3">Add an Output Node:</p>
          <QuickNodePalette
            onSelectPreset={onAddNode}
            showSearch={false}
            showCategories={false}
            compact
          />
        </div>
      )}
    </div>
  );
}

// Step 6: Review
function ReviewStep() {
  const { setCanProceed, state } = useWizard();
  const { isValid, errors, warnings, hasStartNode, hasOutputNode } = useValidation();

  useEffect(() => {
    setCanProceed(isValid);
  }, [isValid, setCanProceed]);

  const roleData = state.stepData.role as { agentName?: string; objective?: string } | undefined;

  return (
    <div className="space-y-4">
      <p className="text-muted-foreground">
        Review your agent configuration before finishing.
      </p>

      <div className="p-4 border rounded-lg bg-muted/30 space-y-3">
        <div className="flex justify-between items-center text-sm">
          <span className="text-muted-foreground">Start Node</span>
          {hasStartNode ? (
            <span className="flex items-center gap-1 text-emerald-600 dark:text-emerald-400">
              <CheckCircle className="w-4 h-4" /> Configured
            </span>
          ) : (
            <span className="flex items-center gap-1 text-destructive">
              <AlertCircle className="w-4 h-4" /> Missing
            </span>
          )}
        </div>
        <div className="flex justify-between items-center text-sm">
          <span className="text-muted-foreground">Agent Name</span>
          <span>{roleData?.agentName || "Not set"}</span>
        </div>
        <div className="flex justify-between items-center text-sm">
          <span className="text-muted-foreground">Output Node</span>
          {hasOutputNode ? (
            <span className="flex items-center gap-1 text-emerald-600 dark:text-emerald-400">
              <CheckCircle className="w-4 h-4" /> Configured
            </span>
          ) : (
            <span className="flex items-center gap-1 text-destructive">
              <AlertCircle className="w-4 h-4" /> Missing
            </span>
          )}
        </div>
      </div>

      {!isValid && (
        <div className="p-3 border border-destructive/50 bg-destructive/10 rounded-lg">
          <p className="text-sm font-medium text-destructive mb-2">
            Please fix the following issues:
          </p>
          <ul className="text-xs text-destructive/80 list-disc list-inside space-y-1">
            {errors.map((error, i) => (
              <li key={i}>{error.message}</li>
            ))}
          </ul>
        </div>
      )}

      {isValid && warnings.length > 0 && (
        <div className="p-3 border border-amber-500/50 bg-amber-500/10 rounded-lg">
          <p className="text-sm font-medium text-amber-600 dark:text-amber-400 mb-2">
            Warnings (optional to fix):
          </p>
          <ul className="text-xs text-amber-600/80 dark:text-amber-400/80 list-disc list-inside space-y-1">
            {warnings.map((warning, i) => (
              <li key={i}>{warning.message}</li>
            ))}
          </ul>
        </div>
      )}

      {isValid && (
        <div className="flex items-center gap-2 p-3 border border-emerald-500/50 bg-emerald-500/10 rounded-lg">
          <Sparkles className="w-5 h-5 text-emerald-500" />
          <div>
            <p className="text-sm font-medium text-emerald-600 dark:text-emerald-400">
              Your agent is ready!
            </p>
            <p className="text-xs text-muted-foreground">
              Click &quot;Finish&quot; to complete the wizard and save your workflow.
            </p>
          </div>
        </div>
      )}
    </div>
  );
}

const STEP_COMPONENTS: Record<string, React.ComponentType<StepProps>> = {
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
  onAddNode?: (preset: QuickNodePreset) => void;
  className?: string;
}

export function AgentWizard({ onComplete, onExit, onAddNode, className }: AgentWizardProps) {
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
      <div className="relative z-10 w-full max-w-lg mx-4 bg-background border rounded-xl shadow-2xl overflow-hidden flex flex-col max-h-[85vh]">
        {/* Progress */}
        <WizardProgress />

        {/* Step Content */}
        <div className="flex-1 overflow-y-auto">
          {currentStepConfig && StepComponent && (
            <WizardStep
              title={currentStepConfig.title}
              description={currentStepConfig.description}
            >
              <StepComponent onAddNode={onAddNode} />
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
