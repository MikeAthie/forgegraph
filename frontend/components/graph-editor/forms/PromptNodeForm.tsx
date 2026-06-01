"use client";

import { useCallback, useMemo } from "react";
import { Input } from "@/components/ui/input";
import { Textarea } from "@/components/ui/textarea";
import { FormField } from "@/components/ui/form-field";
import { KeyValueEditor } from "@/components/ui/key-value-editor";
import { Separator } from "@/components/ui/separator";
import { Spinner } from "@/components/ui/spinner";
import { AgentFields, type AgentConfig } from "./AgentFields";
import { AdvancedSettings, type AdvancedConfig } from "./AdvancedSettings";
import { useCredentialOptions } from "./useCredentialOptions";
import type { NodeFormProps } from "../NodeConfigDialog";

/**
 * Prompt node specific configuration
 */
interface PromptConfig extends AgentConfig, AdvancedConfig {
  prompt_template?: string;
  system_prompt?: string;
  provider?: string;
  credential_id?: string;
  model?: string;
  temperature?: number;
  max_tokens?: number;
  variables?: Record<string, string>;
  observation_context_paths?: string[];
}

const AVAILABLE_MODELS = [
  { value: "gpt-4", label: "GPT-4" },
  { value: "gpt-4-turbo", label: "GPT-4 Turbo" },
  { value: "gpt-3.5-turbo", label: "GPT-3.5 Turbo" },
  { value: "claude-3-opus", label: "Claude 3 Opus" },
  { value: "claude-3-sonnet", label: "Claude 3 Sonnet" },
  { value: "claude-3-haiku", label: "Claude 3 Haiku" },
];

const PROVIDERS = [
  { value: "openai", label: "OpenAI" },
  { value: "anthropic", label: "Anthropic" },
  { value: "google", label: "Google AI" },
];

export function PromptNodeForm({ config, onChange, errors }: NodeFormProps) {
  const promptConfig = config as PromptConfig;
  const { credentials, loading: credentialsLoading, error: credentialsError } = useCredentialOptions();

  const handleChange = useCallback(
    <K extends keyof PromptConfig>(field: K, value: PromptConfig[K]) => {
      onChange({ ...config, [field]: value });
    },
    [config, onChange],
  );

  const handleAgentChange = useCallback(
    (agentConfig: AgentConfig) => {
      onChange({ ...config, ...agentConfig });
    },
    [config, onChange],
  );

  const handleAdvancedChange = useCallback(
    (advancedConfig: AdvancedConfig) => {
      onChange({ ...config, ...advancedConfig });
    },
    [config, onChange],
  );

  const provider = promptConfig.provider || "openai";
  const filteredCredentials = useMemo(
    () => credentials.filter((item) => item.provider === provider),
    [credentials, provider],
  );
  const observationContextPaths = useMemo(
    () =>
      Array.isArray(promptConfig.observation_context_paths) ? promptConfig.observation_context_paths.join("\n") : "",
    [promptConfig.observation_context_paths],
  );

  return (
    <div className="space-y-6">
      {/* Agent Context */}
      <AgentFields config={promptConfig} onChange={handleAgentChange} />

      <Separator />

      {/* Prompt Configuration */}
      <div className="space-y-4">
        <h3 className="text-sm font-medium">Prompt Configuration</h3>

        <FormField
          label="System Prompt"
          htmlFor="system-prompt"
          description="Instructions that define the assistant's behavior"
        >
          <Textarea
            id="system-prompt"
            value={promptConfig.system_prompt || ""}
            onChange={(e) => handleChange("system_prompt", e.target.value)}
            placeholder="You are a helpful assistant that"
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

        <FormField label="Variables" description="Define variables to use in the prompt template">
          <KeyValueEditor
            value={promptConfig.variables || {}}
            onChange={(vars) => handleChange("variables", vars)}
            keyPlaceholder="Variable name"
            valuePlaceholder="Default value or path"
          />
        </FormField>

        <FormField
          label="Curated Context Paths"
          htmlFor="prompt-observation-context-paths"
          description="Optional observation_context output paths to prepend before the prompt executes."
        >
          <Textarea
            id="prompt-observation-context-paths"
            value={observationContextPaths}
            onChange={(event) =>
              handleChange(
                "observation_context_paths",
                event.target.value.split(/[\n,]/).flatMap((item) => {
                  const trimmed = item.trim();
                  return trimmed ? [trimmed] : [];
                }),
              )
            }
            placeholder={"node.recall_jackie_context.output"}
            rows={3}
            className="text-sm resize-none font-mono"
          />
        </FormField>
      </div>

      <Separator />

      {/* Model Settings */}
      <div className="space-y-4">
        <h3 className="text-sm font-medium">Model Settings</h3>

        <div className="grid grid-cols-2 gap-4">
          <FormField label="Provider" htmlFor="provider">
            <select
              id="provider"
              value={provider}
              onChange={(e) => handleChange("provider", e.target.value)}
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
            htmlFor="credential-id"
            description="Select the stored API key to use for this provider."
          >
            <select
              id="credential-id"
              value={promptConfig.credential_id || ""}
              onChange={(e) => handleChange("credential_id", e.target.value || undefined)}
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
            {!credentialsLoading && !credentialsError && filteredCredentials.length === 0 && (
              <div className="mt-2 text-xs text-muted-foreground">
                No credentials found for this provider. Add one in the Credentials page.
              </div>
            )}
          </FormField>

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

          <FormField label="Temperature" htmlFor="temperature" description="0 = deterministic, 2 = creative">
            <div className="flex items-center gap-2">
              <input
                id="temperature"
                type="range"
                min={0}
                max={2}
                step={0.1}
                value={promptConfig.temperature ?? 0.7}
                onChange={(e) => handleChange("temperature", parseFloat(e.target.value))}
                className="flex-1"
              />
              <span className="text-sm text-muted-foreground w-8 text-right">{promptConfig.temperature ?? 0.7}</span>
            </div>
          </FormField>
        </div>

        <FormField label="Max Tokens" htmlFor="max-tokens" description="Maximum number of tokens in the response">
          <Input
            id="max-tokens"
            type="number"
            min={1}
            max={128000}
            value={promptConfig.max_tokens || ""}
            onChange={(e) => handleChange("max_tokens", e.target.value ? parseInt(e.target.value, 10) : undefined)}
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
