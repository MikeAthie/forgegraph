"use client";

import { useCallback, useEffect, useState } from "react";
import { useWizard } from "@/contexts/WizardContext";
import { useValidation } from "@/contexts/ValidationContext";
import { cn } from "@/lib/utils";
import { WizardProgress } from "./WizardProgress";
import { WizardNavigation } from "./WizardNavigation";
import { WizardStep } from "./WizardStep";
import { QuickNodePalette } from "../QuickNodePalette";
import {
  CheckCircle,
  AlertCircle,
  Sparkles,
  Zap,
  Brain,
  FileOutput,
  Bot,
  ArrowRight,
} from "lucide-react";
import { Input } from "@/components/ui/input";
import { Textarea } from "@/components/ui/textarea";
import type { QuickNodePreset } from "@/lib/quick-node-presets";
import {
  AGENT_WIZARD_PRESETS,
  type AgentWizardPreset,
} from "@/lib/agent-wizard-presets";
import { ValidationErrorCode, type ValidationError } from "@/lib/graph-validator";

interface StepProps {
  onAddNode?: (preset: QuickNodePreset) => void;
  onApplyPreset?: (preset: AgentWizardPreset) => void;
}

// Step 1: Start Node
function StartNodeStep({ onAddNode, onApplyPreset }: StepProps) {
  const { setCanProceed, setStepData, state } = useWizard();
  const { hasStartNode } = useValidation();
  const selectedPresetId = (state.stepData.start as { selectedPresetId?: string } | undefined)?.selectedPresetId;

  useEffect(() => {
    setCanProceed(hasStartNode || Boolean(selectedPresetId));
    setStepData("start", { hasStartNode, selectedPresetId });
  }, [hasStartNode, selectedPresetId, setCanProceed, setStepData]);

  const handleApplyPreset = (preset: AgentWizardPreset) => {
    onApplyPreset?.(preset);
    setStepData("start", { hasStartNode, selectedPresetId: preset.id });
  };

  return (
    <div className="space-y-4">
      <p className="text-muted-foreground">
        Every agent workflow needs a starting point. The start node defines where your agent begins processing.
      </p>

      <div className="space-y-2">
        <p className="text-sm font-medium">Starter presets</p>
        <div className="space-y-2">
          {AGENT_WIZARD_PRESETS.map((preset) => (
            <button
              key={preset.id}
              type="button"
              onClick={() => handleApplyPreset(preset)}
              className={cn(
                "w-full rounded-lg border p-3 text-left transition-colors",
                selectedPresetId === preset.id
                  ? "border-primary bg-primary/5"
                  : "border-border hover:bg-muted/50",
              )}
            >
              <div className="flex items-start justify-between gap-3">
                <div className="space-y-1">
                  <p className="text-sm font-medium flex items-center gap-1.5">
                    <Bot className="h-4 w-4 text-primary" />
                    {preset.name}
                  </p>
                  <p className="text-xs text-muted-foreground">{preset.description}</p>
                  <p className="text-[11px] text-muted-foreground">Outcome: {preset.expectedOutcome}</p>
                  {preset.credentialHints[0] && (
                    <p className="text-[11px] text-primary/80">
                      Credential: {preset.credentialHints[0]}
                    </p>
                  )}
                </div>
                <span className="text-xs text-primary font-medium">Use</span>
              </div>
            </button>
          ))}
        </div>
      </div>

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
function PromptStep() {
  const { setCanProceed, state, setStepData } = useWizard();
  const [promptGoal, setPromptGoal] = useState(
    (state.stepData.role as { promptGoal?: string })?.promptGoal || ""
  );
  const [promptContext, setPromptContext] = useState(
    (state.stepData.role as { promptContext?: string })?.promptContext || ""
  );

  useEffect(() => {
    const isValid = promptGoal.trim().length > 0;
    setCanProceed(isValid);
    setStepData("role", { promptGoal, promptContext });
  }, [promptGoal, promptContext, setCanProceed, setStepData]);

  return (
    <div className="space-y-4">
      <p className="text-muted-foreground">
        Define the core prompt intent. This guides how your LLM node should respond.
      </p>

      <div className="space-y-4">
        <div>
          <label htmlFor="prompt-goal" className="text-sm font-medium">Prompt Goal <span className="text-destructive">*</span></label>
          <Input
            id="prompt-goal"
            type="text"
            placeholder="e.g., Answer support questions with concise steps"
            value={promptGoal}
            onChange={(e) => setPromptGoal(e.target.value)}
            className="mt-1"
          />
        </div>
        <div>
          <label htmlFor="prompt-context" className="text-sm font-medium">Prompt Context</label>
          <Textarea
            id="prompt-context"
            placeholder="e.g., Tone, domain constraints, and output format requirements"
            value={promptContext}
            onChange={(e) => setPromptContext(e.target.value)}
            rows={3}
            className="mt-1 resize-none"
          />
        </div>
      </div>

      <div className="p-3 bg-muted/50 rounded-md text-xs space-y-1.5">
        <p className="font-medium">Prompt examples:</p>
        <ul className="list-disc list-inside text-muted-foreground">
          <li>Summarize unread emails and suggest replies</li>
          <li>Draft a Telegram response with clear action items</li>
          <li>Answer with JSON fields: summary, action_items, priority</li>
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
function getPreflightTargetStepId(error: ValidationError): string | null {
  switch (error.code) {
    case ValidationErrorCode.NO_START_NODE:
      return "start";
    case ValidationErrorCode.NO_OUTPUT_NODE:
      return "output";
    case ValidationErrorCode.EMPTY_GRAPH:
      return "start";
    case ValidationErrorCode.CYCLE_DETECTED:
    case ValidationErrorCode.SELF_CONNECTION:
    case ValidationErrorCode.DUPLICATE_EDGE:
      return "tools";
    default:
      return null;
  }
}

function ReviewStep() {
  const { setCanProceed, state, steps, goToStep } = useWizard();
  const { isValid, errors, warnings, hasStartNode, hasOutputNode } = useValidation();

  useEffect(() => {
    setCanProceed(isValid);
  }, [isValid, setCanProceed]);

  const roleData = state.stepData.role as { promptGoal?: string; promptContext?: string } | undefined;

  const jumpToStepForError = (error: ValidationError) => {
    const stepId = getPreflightTargetStepId(error);
    if (!stepId) return;

    const stepIndex = steps.findIndex((step) => step.id === stepId);
    if (stepIndex >= 0) {
      goToStep(stepIndex);
    }
  };

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
          <span className="text-muted-foreground">Prompt Goal</span>
          <span>{roleData?.promptGoal || "Not set"}</span>
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
          <ul className="text-xs text-destructive/80 space-y-2">
            {errors.map((error, i) => {
              const stepId = getPreflightTargetStepId(error);
              const stepLabel = stepId ? steps.find((step) => step.id === stepId)?.title : null;

              return (
                <li key={i} className="rounded-md border border-destructive/30 bg-destructive/5 p-2.5">
                  <p>{error.message}</p>
                  {error.suggestion && (
                    <p className="mt-1 text-[11px] text-destructive/70">{error.suggestion}</p>
                  )}
                  {stepId && stepLabel && (
                    <button
                      type="button"
                      onClick={() => jumpToStepForError(error)}
                      className="mt-2 inline-flex items-center gap-1 text-xs font-medium text-destructive hover:underline"
                    >
                      Fix in {stepLabel}
                      <ArrowRight className="h-3 w-3" />
                    </button>
                  )}
                </li>
              );
            })}
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
  role: PromptStep,
  tools: ToolsStep,
  memory: MemoryStep,
  output: OutputStep,
  review: ReviewStep,
};

export interface AgentWizardProps {
  onComplete?: (options?: { runTest?: boolean }) => void;
  onExit?: () => void;
  onAddNode?: (preset: QuickNodePreset) => void;
  onApplyPreset?: (preset: AgentWizardPreset) => void;
  className?: string;
}

export function AgentWizard({ onComplete, onExit, onAddNode, onApplyPreset, className }: AgentWizardProps) {
  const { state, currentStepConfig, exitWizard } = useWizard();

  const handleComplete = useCallback((options?: { runTest?: boolean }) => {
    onComplete?.(options);
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
      role="dialog"
      aria-modal="true"
      aria-label="Agent Wizard"
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
              <StepComponent onAddNode={onAddNode} onApplyPreset={onApplyPreset} />
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
