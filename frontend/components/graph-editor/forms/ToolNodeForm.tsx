"use client";

import { useCallback, useEffect, useMemo } from "react";
import Link from "next/link";
import { Input } from "@/components/ui/input";
import { Textarea } from "@/components/ui/textarea";
import { FormField } from "@/components/ui/form-field";
import { KeyValueEditor } from "@/components/ui/key-value-editor";
import { Separator } from "@/components/ui/separator";
import { Spinner } from "@/components/ui/spinner";
import { AgentFields, type AgentConfig } from "./AgentFields";
import { AdvancedSettings, type AdvancedConfig } from "./AdvancedSettings";
import { validateJson } from "@/lib/form-validation";
import { useCredentialOptions } from "./useCredentialOptions";
import type { NodeFormProps } from "../NodeConfigDialog";

/**
 * Tool node specific configuration
 */
interface ToolConfig extends AgentConfig, AdvancedConfig {
  [key: string]: unknown;
  tool_name?: string;
  tool_description?: string;
  parameters?: Record<string, string>;
  input_schema?: string;
  provider?: string;
  credential_id?: string;
  output_key?: string;
}

const BUILT_IN_TOOLS = [
  { value: "custom", label: "Custom Tool" },
  { value: "web_search", label: "Web Search" },
  { value: "code_interpreter", label: "Code Interpreter" },
  { value: "file_reader", label: "File Reader" },
  { value: "calculator", label: "Calculator" },
  { value: "database_query", label: "Database Query" },
] as const;
const PROVIDERS = [
  { value: "openai", label: "OpenAI" },
  { value: "anthropic", label: "Anthropic" },
  { value: "google", label: "Google AI" },
  { value: "gmail", label: "Gmail" },
  { value: "google_calendar", label: "Google Calendar" },
  { value: "google_tasks", label: "Google Tasks" },
  { value: "notion", label: "Notion" },
  { value: "slack", label: "Slack" },
  { value: "jira", label: "Jira" },
  { value: "linear", label: "Linear" },
  { value: "hubspot", label: "HubSpot" },
  { value: "google_drive", label: "Google Drive" },
  { value: "telegram", label: "Telegram" },
  { value: "twilio", label: "Twilio" },
  { value: "api_server", label: "API Server" },
  { value: "bluebubbles", label: "BlueBubbles" },
  { value: "dingtalk", label: "DingTalk" },
  { value: "feishu", label: "Feishu" },
  { value: "generic_webhook", label: "Generic Webhook" },
  { value: "homeassistant", label: "Home Assistant" },
  { value: "matrix", label: "Matrix" },
  { value: "microsoft_graph", label: "Microsoft Graph" },
  { value: "qqbot", label: "QQ Bot" },
  { value: "signal", label: "Signal" },
  { value: "sms", label: "SMS" },
  { value: "wecom", label: "WeCom" },
  { value: "weixin", label: "Weixin" },
  { value: "whatsapp", label: "WhatsApp" },
  { value: "yuanbao", label: "Yuanbao" },
];

function validateToolConfig(toolConfig: ToolConfig): Record<string, string> {
  const nextErrors: Record<string, string> = {};

  if (toolConfig.input_schema) {
    const schemaError = validateJson(toolConfig.input_schema, "Input Schema");
    if (schemaError) {
      nextErrors.input_schema = schemaError.message;
    }
  }

  return nextErrors;
}

export function ToolNodeForm({ config, onChange, errors, setErrors }: NodeFormProps) {
  const toolConfig = config as ToolConfig;
  const { credentials, loading: credentialsLoading, error: credentialsError } = useCredentialOptions();
  const configuredCredential = useMemo(
    () => credentials.find((item) => item.id === toolConfig.credential_id),
    [credentials, toolConfig.credential_id],
  );
  const provider = toolConfig.provider || configuredCredential?.provider || "openai";
  const filteredCredentials = useMemo(
    () => credentials.filter((item) => item.provider === provider),
    [credentials, provider],
  );
  const selectedCredential = useMemo(
    () => filteredCredentials.find((item) => item.id === toolConfig.credential_id),
    [filteredCredentials, toolConfig.credential_id],
  );

  const handleChange = useCallback(
    <K extends keyof ToolConfig>(field: K, value: ToolConfig[K]) => {
      const nextConfig = { ...toolConfig, [field]: value };
      onChange(nextConfig);
      setErrors(validateToolConfig(nextConfig));
    },
    [onChange, setErrors, toolConfig],
  );

  const handleAgentChange = useCallback(
    (agentConfig: AgentConfig) => {
      const nextConfig = { ...toolConfig, ...agentConfig };
      onChange(nextConfig);
      setErrors(validateToolConfig(nextConfig));
    },
    [onChange, setErrors, toolConfig],
  );

  const handleAdvancedChange = useCallback(
    (advancedConfig: AdvancedConfig) => {
      const nextConfig = { ...toolConfig, ...advancedConfig };
      onChange(nextConfig);
      setErrors(validateToolConfig(nextConfig));
    },
    [onChange, setErrors, toolConfig],
  );

  const handleProviderChange = useCallback(
    (nextProvider: string) => {
      const nextConfig: ToolConfig = { ...toolConfig, provider: nextProvider };
      if (toolConfig.credential_id && provider !== nextProvider) {
        delete nextConfig.credential_id;
      }
      onChange(nextConfig);
      setErrors(validateToolConfig(nextConfig));
    },
    [onChange, provider, setErrors, toolConfig],
  );

  const isCustomTool = !toolConfig.tool_name || toolConfig.tool_name === "custom";

  useEffect(() => {
    setErrors(validateToolConfig(toolConfig));
  }, [setErrors, toolConfig]);

  return (
    <div className="space-y-6">
      {/* Agent Context */}
      <AgentFields config={toolConfig} onChange={handleAgentChange} />

      <Separator />

      {/* Tool Configuration */}
      <div className="space-y-4">
        <h3 className="text-sm font-medium">Tool Configuration</h3>

        <FormField label="Tool" htmlFor="tool-name" description="Select a built-in tool or create a custom one">
          <select
            id="tool-name"
            value={toolConfig.tool_name || "custom"}
            onChange={(e) => handleChange("tool_name", e.target.value)}
            className="w-full px-3 py-2 border rounded-md bg-background text-sm"
          >
            {BUILT_IN_TOOLS.map((tool) => (
              <option key={tool.value} value={tool.value}>
                {tool.label}
              </option>
            ))}
          </select>
        </FormField>

        {isCustomTool && (
          <FormField
            label="Tool Description"
            htmlFor="tool-description"
            description="Describe what this tool does (helps LLM decide when to use it)"
            required
          >
            <Textarea
              id="tool-description"
              value={toolConfig.tool_description || ""}
              onChange={(e) => handleChange("tool_description", e.target.value)}
              placeholder="This tool searches the web for current information about a given query"
              rows={3}
              className="text-sm resize-none"
            />
          </FormField>
        )}

        <FormField label="Parameters" description="Map parameter names to values or state paths">
          <KeyValueEditor
            value={toolConfig.parameters || {}}
            onChange={(params) => handleChange("parameters", params)}
            keyPlaceholder="Parameter name"
            valuePlaceholder="Value or state path"
          />
        </FormField>

        <div className="grid grid-cols-2 gap-4">
          <FormField label="Credential Provider" htmlFor="provider">
            <select
              id="provider"
              value={provider}
              onChange={(e) => handleProviderChange(e.target.value)}
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
            description="Optional stored secret for this tool call."
          >
            <select
              id="credential-id"
              value={toolConfig.credential_id || ""}
              onChange={(e) => handleChange("credential_id", e.target.value || undefined)}
              className="w-full px-3 py-2 border rounded-md bg-background text-sm"
            >
              <option value="">Use manual/env auth</option>
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
                No credentials found for this provider. Add one in the Credentials page.{" "}
                <Link
                  href={`/credentials?provider=${encodeURIComponent(provider)}`}
                  className="underline underline-offset-2"
                >
                  Open credentials
                </Link>
              </div>
            )}
          </FormField>
        </div>

        {selectedCredential && selectedCredential.health_status !== "healthy" && (
          <div className="rounded-md border border-amber-500/40 bg-amber-500/10 px-3 py-2 text-xs text-amber-700 dark:text-amber-300">
            <p className="font-medium">
              {selectedCredential.health_status === "expired"
                ? "Selected credential is expired."
                : "Selected credential is expiring soon."}
            </p>
            {selectedCredential.health_message && <p className="mt-1">{selectedCredential.health_message}</p>}
            {selectedCredential.requires_reauth && (
              <Link
                href={`/credentials?provider=${encodeURIComponent(provider)}`}
                className="mt-1 inline-block underline underline-offset-2"
              >
                Reconnect this credential in Credentials
              </Link>
            )}
          </div>
        )}

        {isCustomTool && (
          <FormField
            label="Input Schema (JSON)"
            htmlFor="input-schema"
            description="JSON Schema defining expected input parameters"
            error={errors.input_schema}
          >
            <Textarea
              id="input-schema"
              value={toolConfig.input_schema || ""}
              onChange={(e) => handleChange("input_schema", e.target.value)}
              placeholder={`{
  "type": "object",
  "properties": {
    "query": { "type": "string" }
  },
  "required": ["query"]
}`}
              rows={6}
              className="text-sm resize-none font-mono"
            />
          </FormField>
        )}

        <FormField label="Output Key" htmlFor="output-key" description="Key to store the tool result under in state">
          <Input
            id="output-key"
            value={toolConfig.output_key || ""}
            onChange={(e) => handleChange("output_key", e.target.value)}
            placeholder="tool_result"
            className="text-sm"
          />
        </FormField>

        <div className="p-3 bg-muted/50 rounded-md text-xs space-y-2">
          <p className="font-medium">Tool usage:</p>
          <ul className="list-disc list-inside text-muted-foreground space-y-1">
            <li>Tools are functions the agent can call to interact with external systems</li>
            <li>
              Parameters can reference state: <code className="bg-muted px-1 rounded">node.prompt_1.output</code>
            </li>
            <li>Tool results are stored in state under the output key</li>
          </ul>
        </div>
      </div>

      <Separator />

      {/* Advanced Settings */}
      <AdvancedSettings config={toolConfig} onChange={handleAdvancedChange} />
    </div>
  );
}
