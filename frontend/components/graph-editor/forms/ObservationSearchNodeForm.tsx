"use client";

import { useCallback } from "react";

import { FormField } from "@/components/ui/form-field";
import { Input } from "@/components/ui/input";
import { Separator } from "@/components/ui/separator";
import type { NodeFormProps } from "../NodeConfigDialog";
import {
  ObservationScopeField,
  ObservationSourceField,
  updateObservationNumberField,
  useObservationErrors,
  validateObservationSource,
} from "./observation-form-utils";

export function ObservationSearchNodeForm({ config, onChange, errors, setErrors }: NodeFormProps) {
  const searchConfig = config as Record<string, unknown>;

  const computedErrors = {
    scope:
      typeof searchConfig.scope === "string" && searchConfig.scope.trim().length > 0 ? undefined : "Scope is required.",
    query: validateObservationSource(
      searchConfig,
      "query",
      {
        value: "query",
        path: "query_path",
        template: "query_template",
      },
      { required: true },
    ),
    topic_key: validateObservationSource(
      searchConfig,
      "topic key",
      { value: "topic_key", path: "topic_key_path" },
      { required: false },
    ),
    agent_id: validateObservationSource(
      searchConfig,
      "agent filter",
      { value: "agent_id", path: "agent_id_path" },
      { required: false },
    ),
  };

  useObservationErrors(errors, setErrors, computedErrors);

  const handleFieldChange = useCallback(
    (field: string, value: unknown) => {
      const next = { ...searchConfig };
      if (typeof value === "string" && value.trim().length === 0) {
        delete next[field];
      } else if (value == null) {
        delete next[field];
      } else {
        next[field] = value;
      }
      onChange(next);
    },
    [onChange, searchConfig],
  );

  return (
    <div className="space-y-6">
      <div className="space-y-2">
        <h3 className="text-sm font-medium">Observation Search</h3>
        <p className="text-sm text-muted-foreground">
          Search curated observations with filters instead of assembling a ready-made context pack.
        </p>
      </div>

      <ObservationScopeField
        value={typeof searchConfig.scope === "string" ? searchConfig.scope : undefined}
        onChange={(scope) => handleFieldChange("scope", scope)}
      />

      <ObservationSourceField
        label="Query"
        description="Choose the search query source."
        placeholder="What does Jackie care about?"
        pathPlaceholder="input.user_question"
        templatePlaceholder="Recall {{input.customer_name}} preferences"
        required
        config={searchConfig}
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
        <FormField
          label="Type Filter"
          htmlFor="observation-search-type"
          description="Optional observation type filter."
        >
          <Input
            id="observation-search-type"
            value={String(searchConfig.type ?? "")}
            onChange={(event) => handleFieldChange("type", event.target.value)}
            placeholder="preference"
            className="text-sm"
          />
        </FormField>

        <FormField
          label="Result Limit"
          htmlFor="observation-search-limit"
          description="Maximum number of observations to return."
        >
          <Input
            id="observation-search-limit"
            type="number"
            min={1}
            value={String(searchConfig.limit ?? "")}
            onChange={(event) => onChange(updateObservationNumberField(searchConfig, "limit", event.target.value))}
            placeholder="5"
            className="text-sm"
          />
        </FormField>
      </div>

      <div className="grid gap-4 md:grid-cols-2">
        <ObservationSourceField
          label="Topic Key"
          description="Optional topic key filter."
          placeholder="customer:jackie:preferences"
          pathPlaceholder="vars.topic_key"
          config={searchConfig}
          keys={{ value: "topic_key", path: "topic_key_path" }}
          errors={errors}
          onChange={onChange}
        />

        <ObservationSourceField
          label="Agent ID"
          description="Optional agent filter."
          placeholder="jackie-agent"
          pathPlaceholder="vars.agent_id"
          config={searchConfig}
          keys={{ value: "agent_id", path: "agent_id_path" }}
          errors={errors}
          onChange={onChange}
        />
      </div>

      <label
        htmlFor="components-graph-editor-forms-observationsearchnodeform-153"
        aria-label="Include deleted observations"
        className="flex items-start gap-3 rounded-xl border border-border/60 bg-muted/20 p-4 text-sm"
      >
        <input
          id="components-graph-editor-forms-observationsearchnodeform-153"
          type="checkbox"
          checked={Boolean(searchConfig.include_deleted)}
          onChange={(event) => handleFieldChange("include_deleted", event.target.checked)}
          className="mt-0.5"
        />
        <span>
          <span className="font-medium text-foreground">Include deleted observations</span>
          <span className="mt-1 block text-xs text-muted-foreground">
            Useful for audits and timeline-style investigations.
          </span>
        </span>
      </label>
    </div>
  );
}
