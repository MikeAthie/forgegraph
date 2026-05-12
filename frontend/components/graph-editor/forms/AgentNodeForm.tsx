"use client";

import { useCallback, useEffect, useEffectEvent, useMemo } from "react";
import { Input } from "@/components/ui/input";
import { Textarea } from "@/components/ui/textarea";
import { FormField } from "@/components/ui/form-field";
import { Separator } from "@/components/ui/separator";
import { Spinner } from "@/components/ui/spinner";
import { AgentFields } from "./AgentFields";
import { AdvancedSettings, type AdvancedConfig } from "./AdvancedSettings";
import { useCredentialOptions } from "./useCredentialOptions";
import type { NodeFormProps } from "../NodeConfigDialog";

interface AgentFormConfig extends AdvancedConfig {
  role?: string;
  job_description?: string;
  notes?: string;
  instructions?: string;
  system_prompt?: string;
  provider?: string;
  credential_id?: string;
  model?: string;
  tools?: string[];
  approval_required_tools?: string[];
  max_steps?: number;
  max_tool_calls?: number;
  max_tokens?: number;
  temperature?: number;
  stop_condition?: "final_answer";
  observation_context_paths?: string[];
}

const AVAILABLE_MODELS = [
  { value: "gpt-4.1-mini", label: "GPT-4.1 Mini" },
  { value: "gpt-4.1", label: "GPT-4.1" },
  { value: "gpt-4o-mini", label: "GPT-4o Mini" },
  { value: "claude-3-7-sonnet", label: "Claude 3.7 Sonnet" },
  { value: "claude-3-5-sonnet", label: "Claude 3.5 Sonnet" },
];

const PROVIDERS = [
  { value: "openai", label: "OpenAI" },
  { value: "anthropic", label: "Anthropic" },
  { value: "google", label: "Google AI" },
];

function parseToolList(value: string): string[] {
  return value
    .split(/[\n,]/)
    .flatMap((item) => {
      const trimmed = item.trim();
      return trimmed ? [trimmed] : [];
    });
}

function serializeToolList(value?: string[]): string {
  return Array.isArray(value) ? value.join("\n") : "";
}

function AgentToolPolicySection({
  toolsText,
  approvalToolsText,
  errors,
  onToolsChange,
  onApprovalToolsChange,
}: {
  toolsText: string;
  approvalToolsText: string;
  errors: Record<string, string>;
  onToolsChange: (tools: string[]) => void;
  onApprovalToolsChange: (tools: string[]) => void;
}) {
  return (
    <div className="space-y-4">
      <h3 className="text-sm font-medium">Tool Policy</h3>

      <FormField
        label="Allowed Tools"
        htmlFor="agent-tools"
        description="One tool name per line, or separate with commas."
        required
        error={errors.tools}
      >
        <Textarea
          id="agent-tools"
          value={toolsText}
          onChange={(event) => onToolsChange(parseToolList(event.target.value))}
          placeholder={"crm.lookup\nslack.send_message"}
          rows={4}
          className="text-sm resize-none font-mono"
        />
      </FormField>

      <FormField
        label="Approval-Required Tools"
        htmlFor="agent-approval-tools"
        description="Optional subset of allowed tools that should stop for review."
        error={errors.approval_required_tools}
      >
        <Textarea
          id="agent-approval-tools"
          value={approvalToolsText}
          onChange={(event) => onApprovalToolsChange(parseToolList(event.target.value))}
          placeholder={"send_email"}
          rows={3}
          className="text-sm resize-none font-mono"
        />
      </FormField>
    </div>
  );
}

function AgentRuntimeSection({
  agentConfig,
  observationContextText,
  errors,
  onChange,
}: {
  agentConfig: AgentFormConfig;
  observationContextText: string;
  errors: Record<string, string>;
  onChange: <K extends keyof AgentFormConfig>(field: K, value: AgentFormConfig[K]) => void;
}) {
  return (
    <div className="space-y-4">
      <h3 className="text-sm font-medium">Agent Runtime</h3>

      <FormField
        label="Task Instructions"
        htmlFor="agent-instructions"
        description="The task the internal model-to-tool loop should complete."
        required
        error={errors.instructions}
      >
        <Textarea
          id="agent-instructions"
          value={agentConfig.instructions || ""}
          onChange={(event) => onChange("instructions", event.target.value)}
          placeholder="Resolve the user's request using the allowed tools, then return a final answer."
          rows={4}
          className="text-sm resize-none"
        />
      </FormField>

      <FormField
        label="System Prompt"
        htmlFor="agent-system-prompt"
        description="Optional higher-level behavior guidance applied to the model."
      >
        <Textarea
          id="agent-system-prompt"
          value={agentConfig.system_prompt || ""}
          onChange={(event) => onChange("system_prompt", event.target.value)}
          placeholder="You are a reliable ops assistant. Be concise and verify before acting."
          rows={3}
          className="text-sm resize-none font-mono"
        />
      </FormField>

      <FormField
        label="Curated Context Paths"
        htmlFor="agent-observation-context-paths"
        description="Optional observation_context output paths to prepend before the agent answers."
      >
        <Textarea
          id="agent-observation-context-paths"
          value={observationContextText}
          onChange={(event) => onChange("observation_context_paths", parseToolList(event.target.value))}
          placeholder={"node.recall_jackie_context.output"}
          rows={3}
          className="text-sm resize-none font-mono"
        />
      </FormField>
    </div>
  );
}

export function AgentNodeForm({ config, onChange, errors, setErrors }: NodeFormProps) {
  const agentConfig = config as AgentFormConfig;
  const { credentials, loading: credentialsLoading, error: credentialsError } = useCredentialOptions();
  const toolsText = serializeToolList(agentConfig.tools);
  const approvalToolsText = serializeToolList(agentConfig.approval_required_tools);
  const observationContextText = serializeToolList(agentConfig.observation_context_paths);
  const reportErrors = useEffectEvent((nextErrors: Record<string, string>) => setErrors(nextErrors));

  const updateAgentConfig = useCallback(
    <K extends keyof AgentFormConfig>(field: K, value: AgentFormConfig[K]) => {
      onChange({ ...config, [field]: value });
    },
    [config, onChange],
  );

  const handleAgentFieldsChange = useCallback(
    (agentFields: { role?: string; jobDescription?: string; notes?: string }) => {
      onChange({
        ...config,
        role: agentFields.role,
        job_description: agentFields.jobDescription,
        notes: agentFields.notes,
      });
    },
    [config, onChange],
  );

  const handleAdvancedChange = useCallback(
    (advancedConfig: AdvancedConfig) => {
      onChange({ ...config, ...advancedConfig });
    },
    [config, onChange],
  );

  useEffect(() => {
    const nextDefaults: Partial<AgentFormConfig> = {};

    if (!agentConfig.provider) {
      nextDefaults.provider = "openai";
    }
    if (!agentConfig.model) {
      nextDefaults.model = "gpt-4.1-mini";
    }
    if (agentConfig.temperature === undefined) {
      nextDefaults.temperature = 0.2;
    }
    if (agentConfig.max_steps === undefined) {
      nextDefaults.max_steps = 6;
    }
    if (agentConfig.max_tool_calls === undefined) {
      nextDefaults.max_tool_calls = 4;
    }

    if (Object.keys(nextDefaults).length > 0) {
      onChange({ ...config, ...nextDefaults });
    }
  }, [
    agentConfig.max_steps,
    agentConfig.max_tool_calls,
    agentConfig.model,
    agentConfig.provider,
    agentConfig.temperature,
    config,
    onChange,
  ]);

  useEffect(() => {
    const nextErrors: Record<string, string> = {};
    const tools = agentConfig.tools ?? [];
    const approvalTools = agentConfig.approval_required_tools ?? [];

    if (!String(agentConfig.model || "").trim()) {
      nextErrors.model = "Model is required.";
    }

    if (!String(agentConfig.instructions || "").trim()) {
      nextErrors.instructions = "Task instructions are required.";
    }

    if (tools.length === 0) {
      nextErrors.tools = "At least one allowed tool is required.";
    }

    if (
      typeof agentConfig.max_steps === "number" &&
      typeof agentConfig.max_tool_calls === "number" &&
      agentConfig.max_tool_calls > agentConfig.max_steps
    ) {
      nextErrors.max_tool_calls = "Max tool calls cannot exceed max steps.";
    }

    if (approvalTools.some((tool) => !tools.includes(tool))) {
      nextErrors.approval_required_tools = "Approval-required tools must also appear in the allowed tools list.";
    }

    reportErrors(nextErrors);
  }, [
    agentConfig.approval_required_tools,
    agentConfig.instructions,
    agentConfig.max_steps,
    agentConfig.max_tool_calls,
    agentConfig.model,
    agentConfig.tools,
  ]);

  const provider = agentConfig.provider || "openai";
  const filteredCredentials = useMemo(
    () => credentials.filter((item) => item.provider === provider),
    [credentials, provider],
  );

  return (
    <div className="space-y-6">
      <AgentFields
        config={{
          role: agentConfig.role,
          jobDescription: agentConfig.job_description,
          notes: agentConfig.notes,
        }}
        onChange={handleAgentFieldsChange}
        visibleSections={{ examples: false }}
      />

      <Separator />

      <AgentRuntimeSection
        agentConfig={agentConfig}
        observationContextText={observationContextText}
        errors={errors}
        onChange={updateAgentConfig}
      />
      <Separator />

      <div className="space-y-4">
        <h3 className="text-sm font-medium">Model Settings</h3>

        <div className="grid grid-cols-2 gap-4">
          <FormField label="Provider" htmlFor="agent-provider">
            <select
              id="agent-provider"
              value={provider}
              onChange={(event) => updateAgentConfig("provider", event.target.value)}
              className="w-full px-3 py-2 border rounded-md bg-background text-sm"
            >
              {PROVIDERS.map((item) => (
                <option key={item.value} value={item.value}>
                  {item.label}
                </option>
              ))}
            </select>
          </FormField>

          <FormField
            label="Credential"
            htmlFor="agent-credential-id"
            description="Optional provider credential override."
          >
            <select
              id="agent-credential-id"
              value={agentConfig.credential_id || ""}
              onChange={(event) => updateAgentConfig("credential_id", event.target.value || undefined)}
              className="w-full px-3 py-2 border rounded-md bg-background text-sm"
            >
              <option value="">Use default (env)</option>
              {filteredCredentials.map((cred) => (
                <option key={cred.id} value={cred.id}>
                  {cred.name} ({cred.key_hint})
                </option>
              ))}
            </select>
            {credentialsLoading && (
              <div className="mt-2 flex items-center gap-2 text-xs text-muted-foreground">
                <Spinner className="size-3" />
                Loading credentials…
              </div>
            )}
            {!credentialsLoading && credentialsError && (
              <div className="mt-2 text-xs text-destructive">{credentialsError}</div>
            )}
          </FormField>

          <FormField label="Model" htmlFor="agent-model" required error={errors.model}>
            <select
              id="agent-model"
              value={agentConfig.model || "gpt-4.1-mini"}
              onChange={(event) => updateAgentConfig("model", event.target.value)}
              className="w-full px-3 py-2 border rounded-md bg-background text-sm"
            >
              {AVAILABLE_MODELS.map((model) => (
                <option key={model.value} value={model.value}>
                  {model.label}
                </option>
              ))}
            </select>
          </FormField>

          <FormField label="Temperature" htmlFor="agent-temperature">
            <div className="flex items-center gap-2">
              <input
                id="agent-temperature"
                type="range"
                min={0}
                max={2}
                step={0.1}
                value={agentConfig.temperature ?? 0.2}
                onChange={(event) => updateAgentConfig("temperature", parseFloat(event.target.value))}
                className="flex-1"
              />
              <span className="text-sm text-muted-foreground w-8 text-right">{agentConfig.temperature ?? 0.2}</span>
            </div>
          </FormField>

          <FormField label="Max Steps" htmlFor="agent-max-steps">
            <Input
              id="agent-max-steps"
              type="number"
              min={1}
              value={agentConfig.max_steps || ""}
              onChange={(event) =>
                updateAgentConfig("max_steps", event.target.value ? parseInt(event.target.value, 10) : undefined)
              }
              placeholder="6"
              className="text-sm"
            />
          </FormField>

          <FormField label="Max Tool Calls" htmlFor="agent-max-tool-calls" error={errors.max_tool_calls}>
            <Input
              id="agent-max-tool-calls"
              type="number"
              min={1}
              value={agentConfig.max_tool_calls || ""}
              onChange={(event) =>
                updateAgentConfig("max_tool_calls", event.target.value ? parseInt(event.target.value, 10) : undefined)
              }
              placeholder="4"
              className="text-sm"
            />
          </FormField>

          <FormField label="Max Tokens" htmlFor="agent-max-tokens">
            <Input
              id="agent-max-tokens"
              type="number"
              min={1}
              value={agentConfig.max_tokens || ""}
              onChange={(event) =>
                updateAgentConfig("max_tokens", event.target.value ? parseInt(event.target.value, 10) : undefined)
              }
              placeholder="800"
              className="text-sm"
            />
          </FormField>
        </div>
      </div>

      <Separator />

      <AgentToolPolicySection
        toolsText={toolsText}
        approvalToolsText={approvalToolsText}
        errors={errors}
        onToolsChange={(tools) => updateAgentConfig("tools", tools)}
        onApprovalToolsChange={(tools) => updateAgentConfig("approval_required_tools", tools)}
      />

      <Separator />

      <AdvancedSettings config={agentConfig} onChange={handleAdvancedChange} />
    </div>
  );
}
