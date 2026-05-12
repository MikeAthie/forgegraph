"use client";

import { useCallback } from "react";
import { Input } from "@/components/ui/input";
import { FormField } from "@/components/ui/form-field";
import { Separator } from "@/components/ui/separator";
import { AgentFields, type AgentConfig } from "./AgentFields";
import { AdvancedSettings, type AdvancedConfig } from "./AdvancedSettings";
import type { NodeFormProps } from "../NodeConfigDialog";

/**
 * Merge node specific configuration
 */
interface MergeConfig extends AgentConfig, AdvancedConfig {
  merge_strategy?: "first" | "all" | "latest" | "combine";
  output_key?: string;
  wait_for_all?: boolean;
}

const MERGE_STRATEGIES = [
  { value: "all", label: "Wait for All", description: "Wait for all incoming branches before proceeding" },
  { value: "first", label: "First Complete", description: "Proceed when first branch completes" },
  { value: "latest", label: "Latest Value", description: "Use the most recent value from any branch" },
  { value: "combine", label: "Combine All", description: "Merge all branch outputs into an array" },
] as const;

export function MergeNodeForm({ config, onChange }: NodeFormProps) {
  const mergeConfig = config as MergeConfig;

  const handleChange = useCallback(
    <K extends keyof MergeConfig>(field: K, value: MergeConfig[K]) => {
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
      {/* Agent Context - Minimal for Merge */}
      <AgentFields
        config={mergeConfig}
        onChange={handleAgentChange}
        visibleSections={{ role: false, jobDescription: false, examples: false }}
      />

      <Separator />

      {/* Merge Configuration */}
      <div className="space-y-4">
        <h3 className="text-sm font-medium">Merge Configuration</h3>

        <p className="text-sm text-muted-foreground">
          Configure how this node merges data from multiple incoming branches.
        </p>

        <FormField
          label="Merge Strategy"
          htmlFor="merge-strategy"
          description="How to handle data from multiple branches"
        >
          <div className="space-y-2">
            {MERGE_STRATEGIES.map((strategy) => (
              <label
                htmlFor={`merge-strategy-${strategy.value}`}
                aria-label={strategy.label}
                key={strategy.value}
                className={`flex items-start gap-3 p-3 border rounded-md cursor-pointer transition-colors ${
                  mergeConfig.merge_strategy === strategy.value ? "border-primary bg-primary/5" : "hover:bg-muted/50"
                }`}
              >
                <input
                  id={`merge-strategy-${strategy.value}`}
                  type="radio"
                  name="merge-strategy"
                  value={strategy.value}
                  checked={mergeConfig.merge_strategy === strategy.value}
                  onChange={(e) => handleChange("merge_strategy", e.target.value as MergeConfig["merge_strategy"])}
                  className="mt-1"
                />
                <div>
                  <div className="text-sm font-medium">{strategy.label}</div>
                  <div className="text-xs text-muted-foreground">{strategy.description}</div>
                </div>
              </label>
            ))}
          </div>
        </FormField>

        <FormField label="Output Key" htmlFor="output-key" description="Key to store the merged data under in state">
          <Input
            id="output-key"
            value={mergeConfig.output_key || ""}
            onChange={(e) => handleChange("output_key", e.target.value)}
            placeholder="merged"
            className="text-sm"
          />
        </FormField>

        <div className="p-3 bg-muted/50 rounded-md text-xs space-y-2">
          <p className="font-medium">Strategy behavior:</p>
          <ul className="list-disc list-inside text-muted-foreground space-y-1">
            <li>
              <strong>Wait for All</strong> - Blocks until all branches complete, outputs object with all values
            </li>
            <li>
              <strong>First Complete</strong> - Proceeds immediately when any branch finishes
            </li>
            <li>
              <strong>Latest Value</strong> - Continuously updates with newest value
            </li>
            <li>
              <strong>Combine All</strong> - Collects all outputs into an array
            </li>
          </ul>
        </div>
      </div>

      <Separator />

      {/* Advanced Settings */}
      <AdvancedSettings config={mergeConfig} onChange={handleAdvancedChange} />
    </div>
  );
}
