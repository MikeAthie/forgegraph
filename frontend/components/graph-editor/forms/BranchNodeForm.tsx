"use client";

import { useCallback, useEffect } from "react";
import { Input } from "@/components/ui/input";
import { Textarea } from "@/components/ui/textarea";
import { FormField } from "@/components/ui/form-field";
import { Button } from "@/components/ui/button";
import { Separator } from "@/components/ui/separator";
import { AgentFields, type AgentConfig } from "./AgentFields";
import { AdvancedSettings, type AdvancedConfig } from "./AdvancedSettings";
import { validateExpression } from "@/lib/form-validation";
import { Plus, Trash2 } from "lucide-react";
import type { NodeFormProps } from "../NodeConfigDialog";

/**
 * Branch condition definition
 */
interface BranchCondition {
  id: string;
  name: string;
  expression: string;
  target_node?: string;
}

/**
 * Branch node specific configuration
 */
interface BranchConfig extends AgentConfig, AdvancedConfig {
  conditions?: BranchCondition[];
  default_branch?: string;
}

export function BranchNodeForm({ config, onChange, errors, setErrors }: NodeFormProps) {
  const branchConfig = config as BranchConfig;

  const handleChange = useCallback(
    <K extends keyof BranchConfig>(field: K, value: BranchConfig[K]) => {
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

  const handleConditionChange = useCallback(
    (index: number, field: keyof BranchCondition, value: string) => {
      const conditions = [...(branchConfig.conditions || [])];
      conditions[index] = { ...conditions[index], [field]: value };
      handleChange("conditions", conditions);
    },
    [branchConfig.conditions, handleChange]
  );

  const addCondition = useCallback(() => {
    const conditions = [...(branchConfig.conditions || [])];
    conditions.push({
      id: `condition_${Date.now()}`,
      name: `Branch ${conditions.length + 1}`,
      expression: "",
    });
    handleChange("conditions", conditions);
  }, [branchConfig.conditions, handleChange]);

  const removeCondition = useCallback(
    (index: number) => {
      const conditions = [...(branchConfig.conditions || [])];
      conditions.splice(index, 1);
      handleChange("conditions", conditions);
    },
    [branchConfig.conditions, handleChange]
  );

  // Validate conditions on change
  useEffect(() => {
    const newErrors: Record<string, string> = {};

    branchConfig.conditions?.forEach((condition, index) => {
      if (condition.expression) {
        const expressionError = validateExpression(
          condition.expression,
          `Condition ${index + 1}`
        );
        if (expressionError) {
          newErrors[`condition_${index}_expression`] = expressionError.message;
        }
      }
    });

    setErrors(newErrors);
  }, [branchConfig.conditions, setErrors]);

  return (
    <div className="space-y-6">
      {/* Agent Context - Minimal for Branch */}
      <AgentFields
        config={branchConfig}
        onChange={handleAgentChange}
        showRole={false}
        showExamples={false}
      />

      <Separator />

      {/* Branch Configuration */}
      <div className="space-y-4">
        <div className="flex items-center justify-between">
          <h3 className="text-sm font-medium">Branch Conditions</h3>
          <Button
            type="button"
            variant="outline"
            size="sm"
            onClick={addCondition}
          >
            <Plus className="h-4 w-4 mr-1" />
            Add Condition
          </Button>
        </div>

        <p className="text-sm text-muted-foreground">
          Define conditions to route data to different branches. Conditions are
          evaluated in order, first matching condition wins.
        </p>

        {(!branchConfig.conditions || branchConfig.conditions.length === 0) ? (
          <div className="p-4 border border-dashed rounded-md text-center text-sm text-muted-foreground">
            No conditions defined. Add a condition to create branches.
          </div>
        ) : (
          <div className="space-y-4">
            {branchConfig.conditions.map((condition, index) => (
              <div
                key={condition.id}
                className="p-4 border rounded-md space-y-3 bg-muted/30"
              >
                <div className="flex items-center justify-between">
                  <span className="text-sm font-medium">
                    Condition {index + 1}
                  </span>
                  <Button
                    type="button"
                    variant="ghost"
                    size="sm"
                    onClick={() => removeCondition(index)}
                  >
                    <Trash2 className="h-4 w-4 text-destructive" />
                  </Button>
                </div>

                <FormField label="Branch Name" htmlFor={`condition-name-${index}`}>
                  <Input
                    id={`condition-name-${index}`}
                    value={condition.name}
                    onChange={(e) =>
                      handleConditionChange(index, "name", e.target.value)
                    }
                    placeholder="e.g., High Priority"
                    className="text-sm"
                  />
                </FormField>

                <FormField
                  label="Expression"
                  htmlFor={`condition-expr-${index}`}
                  description="JavaScript expression that returns true/false"
                  error={errors[`condition_${index}_expression`]}
                >
                  <Textarea
                    id={`condition-expr-${index}`}
                    value={condition.expression}
                    onChange={(e) =>
                      handleConditionChange(index, "expression", e.target.value)
                    }
                    placeholder="state.score > 0.8"
                    rows={2}
                    className="text-sm resize-none font-mono"
                  />
                </FormField>
              </div>
            ))}
          </div>
        )}

        <FormField
          label="Default Branch"
          htmlFor="default-branch"
          description="Branch to use when no conditions match"
        >
          <Input
            id="default-branch"
            value={branchConfig.default_branch || ""}
            onChange={(e) => handleChange("default_branch", e.target.value)}
            placeholder="default"
            className="text-sm"
          />
        </FormField>

        <div className="p-3 bg-muted/50 rounded-md text-xs space-y-2">
          <p className="font-medium">Expression examples:</p>
          <ul className="list-disc list-inside text-muted-foreground space-y-1">
            <li><code className="bg-muted px-1 rounded">state.sentiment === &quot;positive&quot;</code></li>
            <li><code className="bg-muted px-1 rounded">node.classifier.output.score &gt; 0.8</code></li>
            <li><code className="bg-muted px-1 rounded">input.priority === &quot;high&quot;</code></li>
          </ul>
        </div>
      </div>

      <Separator />

      {/* Advanced Settings */}
      <AdvancedSettings config={branchConfig} onChange={handleAdvancedChange} />
    </div>
  );
}

export default BranchNodeForm;
