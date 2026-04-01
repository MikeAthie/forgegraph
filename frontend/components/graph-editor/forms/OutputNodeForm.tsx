"use client";

import { useCallback } from "react";
import { FormField } from "@/components/ui/form-field";
import { KeyValueEditor } from "@/components/ui/key-value-editor";
import { Separator } from "@/components/ui/separator";
import { AgentFields, type AgentConfig } from "./AgentFields";
import type { NodeFormProps } from "../NodeConfigDialog";

/**
 * Output node specific configuration
 */
interface OutputConfig extends AgentConfig {
  output_mapping?: Record<string, string>;
}

export function OutputNodeForm({ config, onChange }: NodeFormProps) {
  const outputConfig = config as OutputConfig;

  const handleChange = useCallback(
    <K extends keyof OutputConfig>(field: K, value: OutputConfig[K]) => {
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

  return (
    <div className="space-y-6">
      {/* Agent Context - Minimal for Output */}
      <AgentFields
        config={outputConfig}
        onChange={handleAgentChange}
        showRole={false}
        showJobDescription={false}
        showExamples={false}
      />

      <Separator />

      {/* Output Configuration */}
      <div className="space-y-4">
        <h3 className="text-sm font-medium">Output Configuration</h3>

        <p className="text-sm text-muted-foreground">
          Define what data to extract as the final output of your workflow. Map output field names to state paths.
        </p>

        <FormField label="Output Mapping" description="Map output keys to values from the workflow state">
          <KeyValueEditor
            value={outputConfig.output_mapping || {}}
            onChange={(mapping) => handleChange("output_mapping", mapping)}
            keyPlaceholder="Output key"
            valuePlaceholder="State path (e.g., node.prompt.output)"
          />
        </FormField>

        <div className="p-3 bg-muted/50 rounded-md text-xs space-y-2">
          <p className="font-medium">State path examples:</p>
          <ul className="list-disc list-inside text-muted-foreground space-y-1">
            <li>
              <code className="bg-muted px-1 rounded">node.prompt_1.output</code> - Output from a prompt node
            </li>
            <li>
              <code className="bg-muted px-1 rounded">node.http_1.output.data</code> - Nested data from HTTP response
            </li>
            <li>
              <code className="bg-muted px-1 rounded">input.userId</code> - Original graph input
            </li>
          </ul>
        </div>
      </div>
    </div>
  );
}

export default OutputNodeForm;
