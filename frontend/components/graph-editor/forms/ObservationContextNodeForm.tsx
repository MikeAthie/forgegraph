"use client";

import { Separator } from "@/components/ui/separator";
import { FormField } from "@/components/ui/form-field";
import { Input } from "@/components/ui/input";
import type { NodeFormProps } from "../NodeConfigDialog";
import {
  ObservationSourceField,
  updateObservationNumberField,
  useObservationErrors,
  validateObservationSource,
} from "./observation-form-utils";

export function ObservationContextNodeForm({ config, onChange, errors, setErrors }: NodeFormProps) {
  const contextConfig = config as Record<string, unknown>;

  const computedErrors = {
    query: validateObservationSource(
      contextConfig,
      "query",
      {
        value: "query",
        path: "query_path",
        template: "query_template",
      },
      { required: true },
    ),
    agent_id: validateObservationSource(
      contextConfig,
      "agent filter",
      { value: "agent_id", path: "agent_id_path" },
      { required: false },
    ),
  };

  useObservationErrors(errors, setErrors, computedErrors);

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
        onChange={onChange}
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
          onChange={onChange}
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
            onChange={(event) => onChange(updateObservationNumberField(contextConfig, "limit", event.target.value))}
            placeholder="5"
            className="text-sm"
          />
        </FormField>
      </div>
    </div>
  );
}
