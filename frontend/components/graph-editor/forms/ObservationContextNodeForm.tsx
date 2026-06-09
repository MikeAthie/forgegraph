"use client";

import { useCallback } from "react";

import { Separator } from "@/components/ui/separator";
import { FormField } from "@/components/ui/form-field";
import { Input } from "@/components/ui/input";
import type { NodeFormProps } from "../NodeConfigDialog";
import {
  compactObservationErrors,
  updateObservationNumberField,
  validateObservationSource,
} from "./observation-form-helpers";
import { ObservationSourceField } from "./observation-form-utils";

export function ObservationContextNodeForm({ config, onChange, errors, setErrors }: NodeFormProps) {
  const contextConfig = config as Record<string, unknown>;

  const validateConfig = useCallback(
    (nextConfig: Record<string, unknown>) =>
      compactObservationErrors({
        query: validateObservationSource(
          nextConfig,
          "query",
          {
            value: "query",
            path: "query_path",
            template: "query_template",
          },
          { required: true },
        ),
        agent_id: validateObservationSource(
          nextConfig,
          "agent filter",
          { value: "agent_id", path: "agent_id_path" },
          { required: false },
        ),
      }),
    [],
  );
  const updateConfig = useCallback(
    (nextConfig: Record<string, unknown>) => {
      onChange(nextConfig);
      setErrors(validateConfig(nextConfig));
    },
    [onChange, setErrors, validateConfig],
  );

  return (
    <div className="space-y-6">
      <div className="space-y-2">
        <h3 className="text-sm font-medium">Observation Context</h3>
        <p className="text-sm text-muted-foreground">
          Build the curated context pack that prompt and agent nodes can consume explicitly.
        </p>
      </div>

      <ObservationSourceField
        label="Query"
        description="Tell the runtime what context it should retrieve."
        placeholder="What should I remember about Jackie?"
        pathPlaceholder="input.user_question"
        templatePlaceholder="Prepare context for {{input.customer_name}} follow-up"
        required
        config={contextConfig}
        keys={{
          value: "query",
          path: "query_path",
          template: "query_template",
        }}
        errors={errors}
        onChange={updateConfig}
      />

      <Separator />

      <div className="grid gap-4 md:grid-cols-2">
        <ObservationSourceField
          label="Agent ID"
          description="Optional agent filter when one graph has multiple memory-aware agents."
          placeholder="jackie-agent"
          pathPlaceholder="vars.agent_id"
          config={contextConfig}
          keys={{ value: "agent_id", path: "agent_id_path" }}
          errors={errors}
          onChange={updateConfig}
        />

        <FormField
          label="Result Limit"
          htmlFor="observation-context-limit"
          description="How many observations should be assembled into the context pack."
        >
          <Input
            id="observation-context-limit"
            type="number"
            min={1}
            value={String(contextConfig.limit ?? "")}
            onChange={(event) => updateConfig(updateObservationNumberField(contextConfig, "limit", event.target.value))}
            placeholder="5"
            className="text-sm"
          />
        </FormField>
      </div>
    </div>
  );
}
