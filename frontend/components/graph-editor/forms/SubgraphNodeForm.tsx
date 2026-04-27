"use client";

import { useCallback } from "react";
import { Input } from "@/components/ui/input";
import { FormField } from "@/components/ui/form-field";
import { KeyValueEditor } from "@/components/ui/key-value-editor";
import { Separator } from "@/components/ui/separator";
import { AgentFields, type AgentConfig } from "./AgentFields";
import { AdvancedSettings, type AdvancedConfig } from "./AdvancedSettings";
import { ExternalLink } from "lucide-react";
import type { NodeFormProps } from "../NodeConfigDialog";

/**
 * Reusable operating model step configuration
 */
interface SubgraphConfig extends AgentConfig, AdvancedConfig {
  graph_id?: string;
  graph_version?: string;
  input_mapping?: Record<string, string>;
  output_mapping?: Record<string, string>;
}

export function SubgraphNodeForm({ config, onChange }: NodeFormProps) {
  const subgraphConfig = config as SubgraphConfig;

  const handleChange = useCallback(
    <K extends keyof SubgraphConfig>(field: K, value: SubgraphConfig[K]) => {
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

  return (
    <div className="space-y-6">
      {/* Agent Context */}
      <AgentFields config={subgraphConfig} onChange={handleAgentChange} showExamples={false} />

      <Separator />

      {/* Reusable operating model configuration */}
      <div className="space-y-4">
        <h3 className="text-sm font-medium">Reusable Operating Model Reference</h3>

        <p className="text-sm text-muted-foreground">
          Run another operating model as one step inside this advanced operating model. This enables modular, reusable
          company capabilities.
        </p>

        <div className="grid grid-cols-2 gap-4">
          <FormField label="Operating Model ID" htmlFor="graph-id" description="ID of the model to run" required>
            <div className="flex gap-2">
              <Input
                id="graph-id"
                value={subgraphConfig.graph_id || ""}
                onChange={(e) => handleChange("graph_id", e.target.value)}
                placeholder="model_abc123"
                className="text-sm font-mono"
              />
              {subgraphConfig.graph_id && (
                <a
                  href={`/graphs/${subgraphConfig.graph_id}`}
                  target="_blank"
                  rel="noopener noreferrer"
                  className="flex items-center justify-center px-3 border rounded-md hover:bg-muted transition-colors"
                >
                  <ExternalLink className="h-4 w-4" />
                </a>
              )}
            </div>
          </FormField>

          <FormField label="Saved Version" htmlFor="graph-version" description="Specific version (blank = latest)">
            <Input
              id="graph-version"
              value={subgraphConfig.graph_version || ""}
              onChange={(e) => handleChange("graph_version", e.target.value)}
              placeholder="latest"
              className="text-sm font-mono"
            />
          </FormField>
        </div>

        <Separator />

        <h4 className="text-sm font-medium">Data Mapping</h4>

        <FormField label="Input Mapping" description="Map parent company state into the reusable model inputs">
          <KeyValueEditor
            value={subgraphConfig.input_mapping || {}}
            onChange={(mapping) => handleChange("input_mapping", mapping)}
            keyPlaceholder="Reusable model input key"
            valuePlaceholder="Parent state path"
          />
        </FormField>

        <FormField label="Output Mapping" description="Map reusable model outputs back to parent company state">
          <KeyValueEditor
            value={subgraphConfig.output_mapping || {}}
            onChange={(mapping) => handleChange("output_mapping", mapping)}
            keyPlaceholder="Parent state key"
            valuePlaceholder="Reusable model output path"
          />
        </FormField>

        <div className="p-3 bg-muted/50 rounded-md text-xs space-y-2">
          <p className="font-medium">Mapping examples:</p>
          <ul className="list-disc list-inside text-muted-foreground space-y-1">
            <li>
              Input: <code className="bg-muted px-1 rounded">query</code> ←{" "}
              <code className="bg-muted px-1 rounded">node.prompt_1.output</code>
            </li>
            <li>
              Output: <code className="bg-muted px-1 rounded">campaign_summary</code> ←{" "}
              <code className="bg-muted px-1 rounded">output.final</code>
            </li>
          </ul>
        </div>

        <div className="p-3 bg-amber-500/10 border border-amber-500/20 rounded-md text-xs text-amber-600 dark:text-amber-400">
          <p className="font-medium">Saved version pinning recommended</p>
          <p className="mt-1">
            Pin to a specific saved version for production operating models to ensure consistent behavior when the
            referenced model is updated.
          </p>
        </div>
      </div>

      <Separator />

      {/* Advanced Settings */}
      <AdvancedSettings config={subgraphConfig} onChange={handleAdvancedChange} />
    </div>
  );
}

export default SubgraphNodeForm;
