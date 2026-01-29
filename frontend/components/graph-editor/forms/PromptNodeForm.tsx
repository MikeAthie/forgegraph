"use client";

import { useCallback } from "react";
import { Input } from "@/components/ui/input";
import { Textarea } from "@/components/ui/textarea";
import { FormField } from "@/components/ui/form-field";
import { KeyValueEditor } from "@/components/ui/key-value-editor";
import { Separator } from "@/components/ui/separator";
import { AgentFields, type AgentConfig } from "./AgentFields";
import { AdvancedSettings, type AdvancedConfig } from "./AdvancedSettings";
import type { NodeFormProps } from "../NodeConfigDialog";

/**
 * Prompt node specific configuration
 */
interface PromptConfig extends AgentConfig, AdvancedConfig {
  prompt_template?: string;
  system_prompt?: string;
  model?: string;
  temperature?: number;
  max_tokens?: number;
  variables?: Record<string, string>;
}

const AVAILABLE_MODELS = [
  { value: "gpt-4", label: "GPT-4" },
  { value: "gpt-4-turbo", label: "GPT-4 Turbo" },
  { value: "gpt-3.5-turbo", label: "GPT-3.5 Turbo" },
  { value: "claude-3-opus", label: "Claude 3 Opus" },
  { value: "claude-3-sonnet", label: "Claude 3 Sonnet" },
  { value: "claude-3-haiku", label: "Claude 3 Haiku" },
];

export function PromptNodeForm({ config, onChange, errors }: NodeFormProps) {
  const promptConfig = config as PromptConfig;

  const handleChange = useCallback(
    <K extends keyof PromptConfig>(field: K, value: PromptConfig[K]) => {
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

  const handleAdvancedChange = useCallback(
    (advancedConfig: AdvancedConfig) => {
      onChange({ ...config, ...advancedConfig });
    },
    [config, onChange]
  );

  return (
    <div className="space-y-6">
      {/* Agent Context */}
      <AgentFields
        config={promptConfig}
        onChange={handleAgentChange}
        showExamples={true}
      />

      <Separator />

      {/* Prompt Configuration */}
      <div className="space-y-4">
        <h3 className="text-sm font-medium">Prompt Configuration</h3>

        <FormField
          label="System Prompt"
          htmlFor="system-prompt"
          description="Instructions that define the assistant&apos;s behavior"
        >
          <Textarea
            id="system-prompt"
            value={promptConfig.system_prompt || ""}
            onChange={(e) => handleChange("system_prompt", e.target.value)}
            placeholder="You are a helpful assistant that..."
            rows={3}
            className="text-sm resize-none font-mono"
          />
        </FormField>

        <FormField
          label="Prompt Template"
          htmlFor="prompt-template"
          description="The main prompt. Use {{variable}} for interpolation."
          required
          error={errors.prompt_template}
        >
          <Textarea
            id="prompt-template"
            value={promptConfig.prompt_template || ""}
            onChange={(e) => handleChange("prompt_template", e.target.value)}
            placeholder="Given the following context: {{context}}

Please {{task}}"
            rows={5}
            className="text-sm resize-none font-mono"
          />
        </FormField>

        <FormField
          label="Variables"
          description="Define variables to use in the prompt template"
        >
          <KeyValueEditor
            value={promptConfig.variables || {}}
            onChange={(vars) => handleChange("variables", vars)}
            keyPlaceholder="Variable name"
            valuePlaceholder="Default value or path"
          />
        </FormField>
      </div>

      <Separator />

      {/* Model Settings */}
      <div className="space-y-4">
        <h3 className="text-sm font-medium">Model Settings</h3>

        <div className="grid grid-cols-2 gap-4">
          <FormField label="Model" htmlFor="model">
            <select
              id="model"
              value={promptConfig.model || "gpt-4"}
              onChange={(e) => handleChange("model", e.target.value)}
              className="w-full px-3 py-2 border rounded-md bg-background text-sm"
            >
              {AVAILABLE_MODELS.map((model) => (
                <option key={model.value} value={model.value}>
                  {model.label}
                </option>
              ))}
            </select>
          </FormField>

          <FormField
            label="Temperature"
            htmlFor="temperature"
            description="0 = deterministic, 2 = creative"
          >
            <div className="flex items-center gap-2">
              <input
                id="temperature"
                type="range"
                min={0}
                max={2}
                step={0.1}
                value={promptConfig.temperature ?? 0.7}
                onChange={(e) =>
                  handleChange("temperature", parseFloat(e.target.value))
                }
                className="flex-1"
              />
              <span className="text-sm text-muted-foreground w-8 text-right">
                {promptConfig.temperature ?? 0.7}
              </span>
            </div>
          </FormField>
        </div>

        <FormField
          label="Max Tokens"
          htmlFor="max-tokens"
          description="Maximum number of tokens in the response"
        >
          <Input
            id="max-tokens"
            type="number"
            min={1}
            max={128000}
            value={promptConfig.max_tokens || ""}
            onChange={(e) =>
              handleChange(
                "max_tokens",
                e.target.value ? parseInt(e.target.value, 10) : undefined
              )
            }
            placeholder="4096"
            className="text-sm"
          />
        </FormField>
      </div>

      <Separator />

      {/* Advanced Settings */}
      <AdvancedSettings config={promptConfig} onChange={handleAdvancedChange} />
    </div>
  );
}

export default PromptNodeForm;
