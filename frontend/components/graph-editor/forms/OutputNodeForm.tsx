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
        visibleSections={{ role: false, jobDescription: false, examples: false }}
      />

      <Separator />

      {/* Output Configuration */}
      <div className="space-y-4">
        <h3 className="text-sm font-medium">Output Configuration</h3>

        <p className="text-sm text-muted-foreground">
          Define what data to expose as the final deliverable from this operating model. Map deliverable fields to state
          paths.
        </p>

        <FormField label="Deliverable Mapping" description="Map deliverable keys to values from the operating state">
          <KeyValueEditor
            value={outputConfig.output_mapping || {}}
            onChange={(mapping) => handleChange("output_mapping", mapping)}
            keyPlaceholder="Deliverable key"
            valuePlaceholder="State path (e.g., node.prompt.output)"
          />
        </FormField>

        <div className="p-3 bg-muted/50 rounded-md text-xs space-y-2">
          <p className="font-medium">State path examples:</p>
          <ul className="list-disc list-inside text-muted-foreground space-y-1">
            <li>
              <code className="bg-muted px-1 rounded">node.prompt_1.output</code> - Output from an AI worker step
            </li>
            <li>
              <code className="bg-muted px-1 rounded">node.http_1.output.data</code> - Nested data from a tool response
            </li>
            <li>
              <code className="bg-muted px-1 rounded">input.userId</code> - Original company input
            </li>
          </ul>
        </div>
      </div>
    </div>
  );
}
