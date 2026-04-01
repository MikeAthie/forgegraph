"use client";

import { useCallback } from "react";

import { FormField } from "@/components/ui/form-field";
import { Input } from "@/components/ui/input";
import { Separator } from "@/components/ui/separator";
import type { NodeFormProps } from "../NodeConfigDialog";
import {
  ObservationScopeField,
  ObservationSourceField,
  useObservationErrors,
  validateObservationSource,
} from "./observation-form-utils";

export function ObservationSaveNodeForm({ config, onChange, errors, setErrors }: NodeFormProps) {
  const saveConfig = config as Record<string, unknown>;

  const computedErrors = {
    type:
      typeof saveConfig.type === "string" && saveConfig.type.trim().length > 0
        ? undefined
        : "Observation type is required.",
    scope:
      typeof saveConfig.scope === "string" && saveConfig.scope.trim().length > 0 ? undefined : "Scope is required.",
    content: validateObservationSource(
      saveConfig,
      "content",
      {
        value: "content",
        path: "content_path",
        template: "content_template",
      },
      { required: true },
    ),
    title: validateObservationSource(
      saveConfig,
      "title",
      {
        value: "title",
        path: "title_path",
        template: "title_template",
      },
      { required: false },
    ),
    topic_key: validateObservationSource(
      saveConfig,
      "topic key",
      { value: "topic_key", path: "topic_key_path" },
      { required: false },
    ),
    tool_name: validateObservationSource(
      saveConfig,
      "tool name",
      { value: "tool_name", path: "tool_name_path" },
      { required: false },
    ),
    agent_id: validateObservationSource(
      saveConfig,
      "agent filter",
      { value: "agent_id", path: "agent_id_path" },
      { required: false },
    ),
    update_topic:
      saveConfig.update_topic && !saveConfig.topic_key && !saveConfig.topic_key_path
        ? "Update topic requires a topic key source."
        : undefined,
  };

  useObservationErrors(errors, setErrors, computedErrors);

  const handleFieldChange = useCallback(
    (field: string, value: unknown) => {
      const next = { ...saveConfig };
      if (typeof value === "string" && value.trim().length === 0) {
        delete next[field];
      } else if (value == null) {
        delete next[field];
      } else {
        next[field] = value;
      }
      onChange(next);
    },
    [onChange, saveConfig],
  );

  return (
    <div className="space-y-6">
      <div className="space-y-2">
        <h3 className="text-sm font-medium">Curated Observation</h3>
        <p className="text-sm text-muted-foreground">
          Save a durable observation the runtime can reuse across later steps or runs.
        </p>
      </div>

      <div className="grid gap-4 md:grid-cols-2">
        <FormField
          label="Observation Type"
          htmlFor="observation-type"
          description="A short classifier like preference, summary, fact, or insight."
          required
          error={errors.type}
        >
          <Input
            id="observation-type"
            value={String(saveConfig.type ?? "")}
            onChange={(event) => handleFieldChange("type", event.target.value)}
            placeholder="preference"
            className="text-sm"
          />
        </FormField>

        <FormField
          label="Observation ID"
          htmlFor="observation-id"
          description="Optional stable ID if you need to overwrite a specific observation."
        >
          <Input
            id="observation-id"
            value={String(saveConfig.observation_id ?? "")}
            onChange={(event) => handleFieldChange("observation_id", event.target.value)}
            placeholder="obs_jackie_profile"
            className="text-sm"
          />
        </FormField>
      </div>

      <ObservationScopeField
        value={typeof saveConfig.scope === "string" ? saveConfig.scope : undefined}
        onChange={(scope) => handleFieldChange("scope", scope)}
      />

      <Separator />

      <ObservationSourceField
        label="Content"
        description="Choose where the observation body comes from."
        placeholder="Jackie prefers direct, no-fluff status updates."
        pathPlaceholder="node.prompt_1.output"
        templatePlaceholder="Customer prefers {{input.communication_style}} updates."
        required
        valueMultiline
        config={saveConfig}
        keys={{
          value: "content",
          path: "content_path",
          template: "content_template",
        }}
        errors={errors}
        onChange={onChange}
      />

      <ObservationSourceField
        label="Title"
        description="Optional short title for the memory browser and debugger."
        placeholder="Jackie communication preference"
        pathPlaceholder="node.extract.output.title"
        templatePlaceholder="Preference from {{input.customer_name}}"
        config={saveConfig}
        keys={{
          value: "title",
          path: "title_path",
          template: "title_template",
        }}
        errors={errors}
        onChange={onChange}
      />

      <div className="grid gap-4 md:grid-cols-2">
        <ObservationSourceField
          label="Topic Key"
          description="Use a stable topic key when later saves should refresh the same topic."
          placeholder="customer:jackie:preferences"
          pathPlaceholder="node.extract.output.topic_key"
          config={saveConfig}
          keys={{ value: "topic_key", path: "topic_key_path" }}
          errors={errors}
          onChange={onChange}
        />

        <ObservationSourceField
          label="Agent ID"
          description="Optional agent affinity for filtering later context queries."
          placeholder="jackie-agent"
          pathPlaceholder="vars.agent_id"
          config={saveConfig}
          keys={{ value: "agent_id", path: "agent_id_path" }}
          errors={errors}
          onChange={onChange}
        />
      </div>

      <ObservationSourceField
        label="Tool Name"
        description="Optional source tool for tracing where this observation came from."
        placeholder="crm.lookup"
        pathPlaceholder="node.tool_node.output.tool_name"
        config={saveConfig}
        keys={{ value: "tool_name", path: "tool_name_path" }}
        errors={errors}
        onChange={onChange}
      />

      <div className="grid gap-3 rounded-xl border border-border/60 bg-muted/20 p-4 md:grid-cols-2">
        <label className="flex items-start gap-3 text-sm">
          <input
            type="checkbox"
            checked={Boolean(saveConfig.dedupe)}
            onChange={(event) => handleFieldChange("dedupe", event.target.checked)}
            className="mt-0.5"
          />
          <span>
            <span className="font-medium text-foreground">Deduplicate</span>
            <span className="mt-1 block text-xs text-muted-foreground">
              Collapse identical observations instead of creating duplicates.
            </span>
          </span>
        </label>

        <label className="flex items-start gap-3 text-sm">
          <input
            type="checkbox"
            checked={Boolean(saveConfig.update_topic)}
            onChange={(event) => handleFieldChange("update_topic", event.target.checked)}
            className="mt-0.5"
          />
          <span>
            <span className="font-medium text-foreground">Update Topic</span>
            <span className="mt-1 block text-xs text-muted-foreground">
              Replace the current topic record when the same topic key is found.
            </span>
          </span>
        </label>
      </div>
    </div>
  );
}

export default ObservationSaveNodeForm;
