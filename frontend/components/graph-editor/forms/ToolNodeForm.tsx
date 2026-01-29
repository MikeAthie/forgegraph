"use client";

import { useCallback, useEffect } from "react";
import { Input } from "@/components/ui/input";
import { Textarea } from "@/components/ui/textarea";
import { FormField } from "@/components/ui/form-field";
import { KeyValueEditor } from "@/components/ui/key-value-editor";
import { Separator } from "@/components/ui/separator";
import { AgentFields, type AgentConfig } from "./AgentFields";
import { AdvancedSettings, type AdvancedConfig } from "./AdvancedSettings";
import { validateJson } from "@/lib/form-validation";
import type { NodeFormProps } from "../NodeConfigDialog";

/**
 * Tool node specific configuration
 */
interface ToolConfig extends AgentConfig, AdvancedConfig {
  tool_name?: string;
  tool_description?: string;
  parameters?: Record<string, string>;
  input_schema?: string;
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

export function ToolNodeForm({ config, onChange, errors, setErrors }: NodeFormProps) {
  const toolConfig = config as ToolConfig;

  const handleChange = useCallback(
    <K extends keyof ToolConfig>(field: K, value: ToolConfig[K]) => {
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

  // Validate input schema on change
  useEffect(() => {
    const newErrors: Record<string, string> = {};

    if (toolConfig.input_schema) {
      const schemaError = validateJson(toolConfig.input_schema, "Input Schema");
      if (schemaError) {
        newErrors.input_schema = schemaError.message;
      }
    }

    setErrors(newErrors);
  }, [toolConfig.input_schema, setErrors]);

  const isCustomTool = !toolConfig.tool_name || toolConfig.tool_name === "custom";

  return (
    <div className="space-y-6">
      {/* Agent Context */}
      <AgentFields
        config={toolConfig}
        onChange={handleAgentChange}
        showExamples={true}
      />

      <Separator />

      {/* Tool Configuration */}
      <div className="space-y-4">
        <h3 className="text-sm font-medium">Tool Configuration</h3>

        <FormField
          label="Tool"
          htmlFor="tool-name"
          description="Select a built-in tool or create a custom one"
        >
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
              placeholder="This tool searches the web for current information about a given query..."
              rows={3}
              className="text-sm resize-none"
            />
          </FormField>
        )}

        <FormField
          label="Parameters"
          description="Map parameter names to values or state paths"
        >
          <KeyValueEditor
            value={toolConfig.parameters || {}}
            onChange={(params) => handleChange("parameters", params)}
            keyPlaceholder="Parameter name"
            valuePlaceholder="Value or state path"
          />
        </FormField>

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

        <FormField
          label="Output Key"
          htmlFor="output-key"
          description="Key to store the tool result under in state"
        >
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
            <li>Parameters can reference state: <code className="bg-muted px-1 rounded">node.prompt_1.output</code></li>
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

export default ToolNodeForm;
