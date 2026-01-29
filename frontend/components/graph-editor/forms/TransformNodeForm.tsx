"use client";

import { useCallback, useEffect } from "react";
import { Input } from "@/components/ui/input";
import { Textarea } from "@/components/ui/textarea";
import { FormField } from "@/components/ui/form-field";
import { Separator } from "@/components/ui/separator";
import { AgentFields, type AgentConfig } from "./AgentFields";
import { AdvancedSettings, type AdvancedConfig } from "./AdvancedSettings";
import { validateExpression } from "@/lib/form-validation";
import type { NodeFormProps } from "../NodeConfigDialog";

/**
 * Transform node specific configuration
 */
interface TransformConfig extends AgentConfig, AdvancedConfig {
  expression?: string;
  output_key?: string;
}

export function TransformNodeForm({ config, onChange, errors, setErrors }: NodeFormProps) {
  const transformConfig = config as TransformConfig;

  const handleChange = useCallback(
    <K extends keyof TransformConfig>(field: K, value: TransformConfig[K]) => {
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

  // Validate expression on change
  useEffect(() => {
    const newErrors: Record<string, string> = {};

    if (transformConfig.expression) {
      const expressionError = validateExpression(
        transformConfig.expression,
        "Expression"
      );
      if (expressionError) {
        newErrors.expression = expressionError.message;
      }
    }

    setErrors(newErrors);
  }, [transformConfig.expression, setErrors]);

  return (
    <div className="space-y-6">
      {/* Agent Context - Minimal for Transform */}
      <AgentFields
        config={transformConfig}
        onChange={handleAgentChange}
        showRole={false}
        showExamples={false}
      />

      <Separator />

      {/* Transform Configuration */}
      <div className="space-y-4">
        <h3 className="text-sm font-medium">Transform Expression</h3>

        <FormField
          label="Expression"
          htmlFor="expression"
          description="JavaScript expression or JSONPath to transform data"
          required
          error={errors.expression}
        >
          <Textarea
            id="expression"
            value={transformConfig.expression || ""}
            onChange={(e) => handleChange("expression", e.target.value)}
            placeholder="// JavaScript expression
const input = state.previousNode.output;
return {
  transformed: input.data.map(item => item.name)
};"
            rows={8}
            className="text-sm resize-none font-mono"
          />
        </FormField>

        <div className="p-3 bg-muted/50 rounded-md text-xs space-y-2">
          <p className="font-medium">Available variables:</p>
          <ul className="list-disc list-inside text-muted-foreground space-y-1">
            <li><code className="bg-muted px-1 rounded">state</code> - Current workflow state</li>
            <li><code className="bg-muted px-1 rounded">input</code> - Graph input data</li>
            <li><code className="bg-muted px-1 rounded">node.&lt;id&gt;.output</code> - Output from specific node</li>
          </ul>
        </div>

        <FormField
          label="Output Key"
          htmlFor="output-key"
          description="Key to store the transformed data under in state"
        >
          <Input
            id="output-key"
            value={transformConfig.output_key || ""}
            onChange={(e) => handleChange("output_key", e.target.value)}
            placeholder="transformed"
            className="text-sm"
          />
        </FormField>
      </div>

      <Separator />

      {/* Advanced Settings */}
      <AdvancedSettings config={transformConfig} onChange={handleAdvancedChange} />
    </div>
  );
}

export default TransformNodeForm;
