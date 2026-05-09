"use client";

import { useCallback, useEffect, useMemo, useState, type ComponentType } from "react";
import { useWizard } from "@/contexts/WizardContext";
import { cn } from "@/lib/utils";
import { WizardProgress } from "./WizardProgress";
import { WizardNavigation } from "./WizardNavigation";
import { WizardStep } from "./WizardStep";
import {
  AGENT_WIZARD_PRESETS,
  buildAgentWizardBlueprint,
  getAgentWizardPreset,
  type AgentMemoryMode,
  type AgentWizardBlueprint,
  type AgentWizardPreset,
  type AgentWizardPresetSeed,
} from "@/lib/agent-wizard-presets";
import { CheckCircle, Sparkles, Brain, FileOutput, Bot } from "lucide-react";
import { Input } from "@/components/ui/input";
import { Textarea } from "@/components/ui/textarea";

type WizardRoleData = {
  agentLabel?: string;
  instructions?: string;
  systemPrompt?: string;
  provider?: string;
  model?: string;
  temperature?: number;
  role?: string;
  jobDescription?: string;
  notes?: string;
};

type WizardToolsData = {
  tools?: string[];
  approvalRequiredTools?: string[];
};

type WizardMemoryData = {
  type?: AgentMemoryMode;
};

type WizardOutputData = {
  outputKey?: string;
};

export interface AgentWizardCompletePayload {
  runTest?: boolean;
  blueprint: AgentWizardBlueprint;
}

function parseListInput(value: string): string[] {
  return value
    .split(/[\n,]/)
    .map((item) => item.trim())
    .filter(Boolean);
}

function formatListInput(items?: string[]): string {
  return Array.isArray(items) ? items.join("\n") : "";
}

function applyPresetDefaults(preset: AgentWizardPreset, setStepData: (stepId: string, data: unknown) => void) {
  setStepData("start", { selectedPresetId: preset.id });
  setStepData("role", {
    agentLabel: preset.seed.agentLabel,
    instructions: preset.seed.instructions,
    systemPrompt: preset.seed.system_prompt,
    provider: preset.seed.provider ?? "openai",
    model: preset.seed.model ?? "gpt-4.1-mini",
    temperature: preset.seed.temperature ?? 0.3,
    role: preset.seed.role,
    jobDescription: preset.seed.job_description,
    notes: preset.seed.notes,
  } satisfies WizardRoleData);
  setStepData("tools", {
    tools: preset.seed.tools,
    approvalRequiredTools: preset.seed.approval_required_tools ?? [],
  } satisfies WizardToolsData);
  setStepData("memory", { type: preset.seed.memoryMode ?? "none" } satisfies WizardMemoryData);
  setStepData("output", { outputKey: preset.seed.outputKey ?? "response" } satisfies WizardOutputData);
}

function buildBlueprintFromState(stepData: Record<string, unknown>): AgentWizardBlueprint {
  const roleData = (stepData.role as WizardRoleData | undefined) ?? {};
  const toolsData = (stepData.tools as WizardToolsData | undefined) ?? {};
  const memoryData = (stepData.memory as WizardMemoryData | undefined) ?? {};
  const outputData = (stepData.output as WizardOutputData | undefined) ?? {};

  const seed: AgentWizardPresetSeed = {
    agentLabel: roleData.agentLabel?.trim() || "AI Worker Step",
    instructions: roleData.instructions?.trim() || "",
    system_prompt: roleData.systemPrompt?.trim() || undefined,
    provider: roleData.provider || "openai",
    model: roleData.model || "gpt-4.1-mini",
    temperature: roleData.temperature ?? 0.3,
    role: roleData.role?.trim() || undefined,
    job_description: roleData.jobDescription?.trim() || undefined,
    notes: roleData.notes?.trim() || undefined,
    tools: toolsData.tools ?? [],
    approval_required_tools: toolsData.approvalRequiredTools ?? [],
    memoryMode: memoryData.type ?? "none",
    outputKey: outputData.outputKey?.trim() || "response",
  };

  return buildAgentWizardBlueprint(seed);
}

function StartNodeStep() {
  const { setCanProceed, setStepData, state } = useWizard();
  const selectedPresetId = (state.stepData.start as { selectedPresetId?: string } | undefined)?.selectedPresetId;

  useEffect(() => {
    setCanProceed(true);
    setStepData("start", { selectedPresetId });
  }, [selectedPresetId, setCanProceed, setStepData]);

  return (
    <div className="space-y-4">
      <p className="text-muted-foreground">
        Choose a starter if you want seeded tools and instructions, or continue with a blank AI worker setup and define
        the operating model step by step.
      </p>

      <div className="space-y-2">
        <p className="text-sm font-medium">Starter presets</p>
        <div className="space-y-2">
          {AGENT_WIZARD_PRESETS.map((preset) => (
            <PresetButton
              key={preset.id}
              preset={preset}
              selected={selectedPresetId === preset.id}
              onSelect={() => applyPresetDefaults(preset, setStepData)}
            />
          ))}
        </div>
      </div>

      <div
        className={cn(
          "p-4 border rounded-lg flex items-center gap-3",
          selectedPresetId ? "border-emerald-500/50 bg-emerald-500/10" : "border-border bg-muted/30",
        )}
      >
        {selectedPresetId ? (
          <>
            <CheckCircle className="w-5 h-5 text-emerald-500 shrink-0" />
            <div>
              <p className="text-sm font-medium text-emerald-600 dark:text-emerald-400">Preset applied</p>
              <p className="text-xs text-muted-foreground">
                The next steps are prefilled. You can still change everything before finishing.
              </p>
            </div>
          </>
        ) : (
          <>
            <Bot className="w-5 h-5 text-muted-foreground shrink-0" />
            <div>
              <p className="text-sm font-medium">Blank AI worker setup</p>
              <p className="text-xs text-muted-foreground">
                The wizard will create a real AI worker step plus a deliverable step when you finish.
              </p>
            </div>
          </>
        )}
      </div>
    </div>
  );
}

function PresetButton({
  preset,
  selected,
  onSelect,
}: {
  preset: AgentWizardPreset;
  selected: boolean;
  onSelect: () => void;
}) {
  return (
    <button
      type="button"
      onClick={onSelect}
      className={cn(
        "w-full rounded-lg border p-3 text-left transition-colors",
        selected ? "border-primary bg-primary/5" : "border-border hover:bg-muted/50",
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
            <p className="text-[11px] text-primary/80">Credential: {preset.credentialHints[0]}</p>
          )}
        </div>
        <span className="text-xs text-primary font-medium">{selected ? "Selected" : "Use"}</span>
      </div>
    </button>
  );
}

function RoleStep() {
  const { setCanProceed, state, setStepData } = useWizard();
  const initial = (state.stepData.role as WizardRoleData | undefined) ?? {};
  const [agentLabel, setAgentLabel] = useState(initial.agentLabel || "AI Worker Step");
  const [instructions, setInstructions] = useState(initial.instructions || "");
  const [systemPrompt, setSystemPrompt] = useState(initial.systemPrompt || "");
  const [provider, setProvider] = useState(initial.provider || "openai");
  const [model, setModel] = useState(initial.model || "gpt-4.1-mini");
  const [temperature, setTemperature] = useState(initial.temperature ?? 0.3);
  const [role, setRole] = useState(initial.role || "");
  const [jobDescription, setJobDescription] = useState(initial.jobDescription || "");
  const [notes, setNotes] = useState(initial.notes || "");

  useEffect(() => {
    const isValid = Boolean(agentLabel.trim()) && Boolean(instructions.trim()) && Boolean(model.trim());
    setCanProceed(isValid);
    setStepData("role", {
      agentLabel,
      instructions,
      systemPrompt,
      provider,
      model,
      temperature,
      role,
      jobDescription,
      notes,
    } satisfies WizardRoleData);
  }, [
    agentLabel,
    instructions,
    jobDescription,
    model,
    notes,
    provider,
    role,
    setCanProceed,
    setStepData,
    systemPrompt,
    temperature,
  ]);

  return (
    <div className="space-y-4">
      <p className="text-muted-foreground">
        Define the actual runtime behavior for the new AI worker step. These values become the advanced step config the
        AI worker uses.
      </p>

      <div className="space-y-4">
        <div>
          <label htmlFor="agent-label" className="text-sm font-medium">
            Step Label <span className="text-destructive">*</span>
          </label>
          <Input
            id="agent-label"
            type="text"
            placeholder="Customer Success Department"
            value={agentLabel}
            onChange={(event) => setAgentLabel(event.target.value)}
            className="mt-1"
          />
        </div>

        <div>
          <label htmlFor="agent-instructions" className="text-sm font-medium">
            Task Instructions <span className="text-destructive">*</span>
          </label>
          <Textarea
            id="agent-instructions"
            placeholder="Resolve the user's request using the allowed tools, then return a final answer."
            value={instructions}
            onChange={(event) => setInstructions(event.target.value)}
            rows={4}
            className="mt-1 resize-none"
          />
        </div>

        <div>
          <label htmlFor="agent-system-prompt" className="text-sm font-medium">
            System Prompt
          </label>
          <Textarea
            id="agent-system-prompt"
            placeholder="You are a reliable operations assistant. Verify before acting."
            value={systemPrompt}
            onChange={(event) => setSystemPrompt(event.target.value)}
            rows={3}
            className="mt-1 resize-none"
          />
        </div>

        <div className="grid grid-cols-2 gap-4">
          <div>
            <label htmlFor="agent-provider" className="text-sm font-medium">
              Provider
            </label>
            <select
              id="agent-provider"
              value={provider}
              onChange={(event) => setProvider(event.target.value)}
              className="mt-1 w-full rounded-md border border-input bg-transparent px-3 py-2 text-sm"
            >
              <option value="openai">OpenAI</option>
              <option value="anthropic">Anthropic</option>
              <option value="google">Google AI</option>
            </select>
          </div>

          <div>
            <label htmlFor="agent-model" className="text-sm font-medium">
              Model <span className="text-destructive">*</span>
            </label>
            <select
              id="agent-model"
              value={model}
              onChange={(event) => setModel(event.target.value)}
              className="mt-1 w-full rounded-md border border-input bg-transparent px-3 py-2 text-sm"
            >
              <option value="gpt-4.1-mini">GPT-4.1 Mini</option>
              <option value="gpt-4.1">GPT-4.1</option>
              <option value="gpt-4o-mini">GPT-4o Mini</option>
              <option value="claude-3-7-sonnet">Claude 3.7 Sonnet</option>
              <option value="claude-3-5-sonnet">Claude 3.5 Sonnet</option>
            </select>
          </div>
        </div>

        <div>
          <label htmlFor="agent-temperature" className="text-sm font-medium">
            Temperature
          </label>
          <div className="mt-1 flex items-center gap-3">
            <input
              id="agent-temperature"
              type="range"
              min={0}
              max={2}
              step={0.1}
              value={temperature}
              onChange={(event) => setTemperature(parseFloat(event.target.value))}
              className="flex-1"
            />
            <span className="w-10 text-right text-sm text-muted-foreground">{temperature}</span>
          </div>
        </div>

        <div>
          <label htmlFor="agent-role" className="text-sm font-medium">
            Role / Persona
          </label>
          <Input
            id="agent-role"
            type="text"
            placeholder="Customer Support Agent"
            value={role}
            onChange={(event) => setRole(event.target.value)}
            className="mt-1"
          />
        </div>

        <div>
          <label htmlFor="agent-objective" className="text-sm font-medium">
            Primary Objective
          </label>
          <Textarea
            id="agent-objective"
            placeholder="Help customers resolve account and billing issues."
            value={jobDescription}
            onChange={(event) => setJobDescription(event.target.value)}
            rows={3}
            className="mt-1 resize-none"
          />
        </div>

        <div>
          <label htmlFor="agent-notes" className="text-sm font-medium">
            Notes
          </label>
          <Textarea
            id="agent-notes"
            placeholder="Optional constraints or response style notes."
            value={notes}
            onChange={(event) => setNotes(event.target.value)}
            rows={2}
            className="mt-1 resize-none"
          />
        </div>
      </div>
    </div>
  );
}

function ToolsStep() {
  const { setCanProceed, state, setStepData } = useWizard();
  const initial = (state.stepData.tools as WizardToolsData | undefined) ?? {};
  const [toolsText, setToolsText] = useState(formatListInput(initial.tools));
  const [approvalText, setApprovalText] = useState(formatListInput(initial.approvalRequiredTools));

  const tools = useMemo(() => parseListInput(toolsText), [toolsText]);
  const approvalTools = useMemo(() => parseListInput(approvalText), [approvalText]);
  const invalidApproval = approvalTools.filter((tool) => !tools.includes(tool));

  useEffect(() => {
    const isValid = tools.length > 0 && invalidApproval.length === 0;
    setCanProceed(isValid);
    setStepData("tools", {
      tools,
      approvalRequiredTools: approvalTools,
    } satisfies WizardToolsData);
  }, [approvalTools, invalidApproval.length, setCanProceed, setStepData, tools]);

  return (
    <div className="space-y-4">
      <p className="text-muted-foreground">
        Configure the exact tools this AI worker is allowed to call. The runtime enforces this list.
      </p>

      <div>
        <label htmlFor="agent-tools-list" className="text-sm font-medium">
          Allowed Tools <span className="text-destructive">*</span>
        </label>
        <Textarea
          id="agent-tools-list"
          value={toolsText}
          onChange={(event) => setToolsText(event.target.value)}
          placeholder={"crm.lookup\nslack.send_message"}
          rows={5}
          className="mt-1 resize-none font-mono text-sm"
        />
        <p className="mt-2 text-xs text-muted-foreground">Use one tool name per line, or separate them with commas.</p>
      </div>

      <div>
        <label htmlFor="agent-approval-list" className="text-sm font-medium">
          Approval-Required Tools
        </label>
        <Textarea
          id="agent-approval-list"
          value={approvalText}
          onChange={(event) => setApprovalText(event.target.value)}
          placeholder={"send_email"}
          rows={3}
          className="mt-1 resize-none font-mono text-sm"
        />
        <p className="mt-2 text-xs text-muted-foreground">
          These tools pause the operation with an approval-required outcome before execution.
        </p>
      </div>

      {invalidApproval.length > 0 && (
        <div className="rounded-lg border border-destructive/40 bg-destructive/10 p-3 text-sm text-destructive">
          Approval-required tools must also appear in the allowed tools list.
        </div>
      )}
    </div>
  );
}

function MemoryStep() {
  const { setCanProceed, setStepData, state } = useWizard();
  const [selectedMemory, setSelectedMemory] = useState<AgentMemoryMode>(
    ((state.stepData.memory as WizardMemoryData | undefined)?.type as AgentMemoryMode | undefined) || "none",
  );

  useEffect(() => {
    setCanProceed(true);
    setStepData("memory", { type: selectedMemory } satisfies WizardMemoryData);
  }, [selectedMemory, setCanProceed, setStepData]);

  const memoryOptions = [
    {
      id: "none" as const,
      label: "No Memory",
      description: "Create a simple AI-worker-plus-deliverable flow.",
      icon: FileOutput,
    },
    {
      id: "session" as const,
      label: "Session Memory",
      description: "Keep the operating model simple now. Add persistent storage later if you need it.",
      icon: Brain,
    },
    {
      id: "persistent" as const,
      label: "Persistent Memory",
      description: "Add memory load/store steps around the AI worker.",
      icon: Brain,
    },
  ];

  return (
    <div className="space-y-4">
      <p className="text-muted-foreground">
        Choose whether the wizard should wrap the AI worker with memory steps. Persistent mode adds explicit memory
        read/write steps to the operating model.
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
                selectedMemory === option.id ? "border-primary bg-primary/5" : "hover:bg-muted/50",
              )}
            >
              <Icon
                className={cn(
                  "w-5 h-5 mt-0.5 shrink-0",
                  selectedMemory === option.id ? "text-primary" : "text-muted-foreground",
                )}
              />
              <div>
                <span className="text-sm font-medium">{option.label}</span>
                <p className="text-xs text-muted-foreground">{option.description}</p>
              </div>
            </button>
          );
        })}
      </div>
    </div>
  );
}

function OutputStep() {
  const { setCanProceed, setStepData, state } = useWizard();
  const [outputKey, setOutputKey] = useState(
    (state.stepData.output as WizardOutputData | undefined)?.outputKey || "response",
  );

  useEffect(() => {
    const isValid = Boolean(outputKey.trim());
    setCanProceed(isValid);
    setStepData("output", { outputKey } satisfies WizardOutputData);
  }, [outputKey, setCanProceed, setStepData]);

  return (
    <div className="space-y-4">
      <p className="text-muted-foreground">
        Define the key exposed by the final deliverable step. The wizard will map the AI worker&apos;s final answer into
        this field.
      </p>

      <div className="p-4 border rounded-lg flex items-center gap-3 border-emerald-500/50 bg-emerald-500/10">
        <CheckCircle className="w-5 h-5 text-emerald-500 shrink-0" />
        <div>
          <p className="text-sm font-medium text-emerald-600 dark:text-emerald-400">
            Deliverable step will be created automatically
          </p>
          <p className="text-xs text-muted-foreground">
            You do not need to add a final deliverable step manually anymore.
          </p>
        </div>
      </div>

      <div>
        <label htmlFor="agent-output-key" className="text-sm font-medium">
          Output Key
        </label>
        <Input
          id="agent-output-key"
          type="text"
          value={outputKey}
          onChange={(event) => setOutputKey(event.target.value)}
          placeholder="response"
          className="mt-1"
        />
      </div>
    </div>
  );
}

function ReviewStep() {
  const { setCanProceed, state } = useWizard();
  const selectedPresetId = (state.stepData.start as { selectedPresetId?: string } | undefined)?.selectedPresetId;
  const preset = selectedPresetId ? getAgentWizardPreset(selectedPresetId) : undefined;
  const roleData = (state.stepData.role as WizardRoleData | undefined) ?? {};
  const toolsData = (state.stepData.tools as WizardToolsData | undefined) ?? {};
  const memoryData = (state.stepData.memory as WizardMemoryData | undefined) ?? {};
  const outputData = (state.stepData.output as WizardOutputData | undefined) ?? {};

  const tools = toolsData.tools ?? [];
  const approvalTools = toolsData.approvalRequiredTools ?? [];
  const invalidApproval = approvalTools.filter((tool) => !tools.includes(tool));
  const isValid =
    Boolean(roleData.agentLabel?.trim()) &&
    Boolean(roleData.instructions?.trim()) &&
    Boolean(roleData.model?.trim()) &&
    tools.length > 0 &&
    invalidApproval.length === 0 &&
    Boolean(outputData.outputKey?.trim());

  useEffect(() => {
    setCanProceed(isValid);
  }, [isValid, setCanProceed]);

  return (
    <div className="space-y-4">
      <p className="text-muted-foreground">
        Review the operating model the wizard will generate. Finish to create the steps on the canvas.
      </p>

      <div className="p-4 border rounded-lg bg-muted/30 space-y-3">
        <div className="flex justify-between items-center text-sm">
          <span className="text-muted-foreground">Starter preset</span>
          <span>{preset?.name || "Custom"}</span>
        </div>
        <div className="flex justify-between items-center text-sm">
          <span className="text-muted-foreground">Step label</span>
          <span>{roleData.agentLabel || "Missing"}</span>
        </div>
        <div className="flex justify-between items-center text-sm">
          <span className="text-muted-foreground">Model</span>
          <span>{roleData.model || "Missing"}</span>
        </div>
        <div className="flex justify-between items-center text-sm">
          <span className="text-muted-foreground">Allowed tool actions</span>
          <span>{tools.length}</span>
        </div>
        <div className="flex justify-between items-center text-sm">
          <span className="text-muted-foreground">Memory mode</span>
          <span className="capitalize">{memoryData.type || "none"}</span>
        </div>
        <div className="flex justify-between items-center text-sm">
          <span className="text-muted-foreground">Deliverable key</span>
          <span>{outputData.outputKey || "response"}</span>
        </div>
      </div>

      {!isValid && (
        <div className="p-3 border border-destructive/50 bg-destructive/10 rounded-lg space-y-2">
          <p className="text-sm font-medium text-destructive">The AI worker setup is incomplete.</p>
          <ul className="text-xs text-destructive/80 list-disc list-inside space-y-1">
            {!roleData.agentLabel?.trim() && <li>Add a step label.</li>}
            {!roleData.instructions?.trim() && <li>Add task instructions.</li>}
            {!roleData.model?.trim() && <li>Select a model.</li>}
            {tools.length === 0 && <li>Add at least one allowed tool.</li>}
            {invalidApproval.length > 0 && <li>Remove approval-required tools that are not allowed.</li>}
            {!outputData.outputKey?.trim() && <li>Set the output key.</li>}
          </ul>
        </div>
      )}

      {isValid && (
        <div className="flex items-center gap-2 p-3 border border-emerald-500/50 bg-emerald-500/10 rounded-lg">
          <Sparkles className="w-5 h-5 text-emerald-500" />
          <div>
            <p className="text-sm font-medium text-emerald-600 dark:text-emerald-400">AI worker flow ready</p>
            <p className="text-xs text-muted-foreground">Finish to add a real AI worker flow to the canvas.</p>
          </div>
        </div>
      )}
    </div>
  );
}

const STEP_COMPONENTS: Record<string, ComponentType> = {
  start: StartNodeStep,
  role: RoleStep,
  tools: ToolsStep,
  memory: MemoryStep,
  output: OutputStep,
  review: ReviewStep,
};

export interface AgentWizardProps {
  onComplete?: (payload: AgentWizardCompletePayload) => void;
  onExit?: () => void;
  className?: string;
}

export function AgentWizard({ onComplete, onExit, className }: AgentWizardProps) {
  const { state, currentStepConfig, exitWizard } = useWizard();

  const blueprint = useMemo(() => buildBlueprintFromState(state.stepData), [state.stepData]);

  const handleComplete = useCallback(
    (options?: { runTest?: boolean }) => {
      onComplete?.({
        runTest: options?.runTest,
        blueprint,
      });
      exitWizard();
    },
    [blueprint, exitWizard, onComplete],
  );

  const handleExit = useCallback(() => {
    onExit?.();
    exitWizard();
  }, [onExit, exitWizard]);

  useEffect(() => {
    const handleKeyDown = (event: KeyboardEvent) => {
      if (event.key === "Escape") {
        handleExit();
      }
    };

    window.addEventListener("keydown", handleKeyDown);
    return () => window.removeEventListener("keydown", handleKeyDown);
  }, [handleExit]);

  if (!state.isActive) {
    return null;
  }

  const StepComponent = currentStepConfig ? STEP_COMPONENTS[currentStepConfig.id] : null;

  return (
    <div
      role="dialog"
      aria-modal="true"
      aria-label="Operating Model Wizard"
      className={cn("fixed inset-0 z-50 flex items-center justify-center", className)}
    >
      <div className="absolute inset-0 bg-black/50 backdrop-blur-sm" onClick={handleExit} />

      <div className="relative z-10 w-full max-w-lg mx-4 bg-background border rounded-xl shadow-2xl overflow-hidden flex flex-col max-h-[85vh]">
        <WizardProgress />

        <div className="flex-1 overflow-y-auto">
          {currentStepConfig && StepComponent && (
            <WizardStep title={currentStepConfig.title} description={currentStepConfig.description}>
              <StepComponent />
            </WizardStep>
          )}
        </div>

        <WizardNavigation onComplete={handleComplete} />
      </div>
    </div>
  );
}

export default AgentWizard;
