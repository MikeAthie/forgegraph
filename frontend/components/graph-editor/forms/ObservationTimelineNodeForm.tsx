"use client";

import { FormField } from "@/components/ui/form-field";
import { Input } from "@/components/ui/input";
import type { NodeFormProps } from "../NodeConfigDialog";
import {
  ObservationScopeField,
  ObservationSourceField,
  updateObservationNumberField,
  useObservationErrors,
  validateObservationSource,
} from "./observation-form-utils";

export function ObservationTimelineNodeForm({ config, onChange, errors, setErrors }: NodeFormProps) {
  const timelineConfig = config as Record<string, unknown>;

  const computedErrors = {
    scope:
      typeof timelineConfig.scope === "string" && timelineConfig.scope.trim().length > 0
        ? undefined
        : "Scope is required.",
    agent_id: validateObservationSource(
      timelineConfig,
      "agent filter",
      { value: "agent_id", path: "agent_id_path" },
      { required: false },
    ),
  };

  useObservationErrors(errors, setErrors, computedErrors);

  return (
    <div className="space-y-6">
      <div className="space-y-2">
        <h3 className="text-sm font-medium">Observation Timeline</h3>
        <p className="text-sm text-muted-foreground">
          Pull the most recent observations in scope order for audits, debugging, or memory browsing flows.
        </p>
      </div>

      <ObservationScopeField
        value={typeof timelineConfig.scope === "string" ? timelineConfig.scope : undefined}
        onChange={(scope) => onChange({ ...timelineConfig, scope })}
      />

      <div className="grid gap-4 md:grid-cols-2">
        <ObservationSourceField
          label="Agent ID"
          description="Optional agent filter."
          placeholder="jackie-agent"
          pathPlaceholder="vars.agent_id"
          config={timelineConfig}
          keys={{ value: "agent_id", path: "agent_id_path" }}
          errors={errors}
          onChange={onChange}
        />

        <FormField
          label="Result Limit"
          htmlFor="observation-timeline-limit"
          description="Maximum number of observations to return."
        >
          <Input
            id="observation-timeline-limit"
            type="number"
            min={1}
            value={String(timelineConfig.limit ?? "")}
            onChange={(event) => onChange(updateObservationNumberField(timelineConfig, "limit", event.target.value))}
            placeholder="10"
            className="text-sm"
          />
        </FormField>
      </div>

      <label
        htmlFor="components-graph-editor-forms-observationtimelinenodeform-75"
        aria-label="Include deleted observations"
        className="flex items-start gap-3 rounded-xl border border-border/60 bg-muted/20 p-4 text-sm"
      >
        <input
          id="components-graph-editor-forms-observationtimelinenodeform-75"
          type="checkbox"
          checked={Boolean(timelineConfig.include_deleted)}
          onChange={(event) =>
            onChange({
              ...timelineConfig,
              include_deleted: event.target.checked,
            })
          }
          className="mt-0.5"
        />
        <span>
          <span className="font-medium text-foreground">Include deleted observations</span>
          <span className="mt-1 block text-xs text-muted-foreground">
            Show soft-deleted entries in the audit trail.
          </span>
        </span>
      </label>
    </div>
  );
}
