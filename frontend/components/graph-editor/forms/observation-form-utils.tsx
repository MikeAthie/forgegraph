"use client";

import { FormField } from "@/components/ui/form-field";
import { Input } from "@/components/ui/input";
import { Textarea } from "@/components/ui/textarea";
import {
  selectObservationSourceMode,
  updateObservationSourceMode,
  updateObservationSourceValue,
  type ObservationScope,
  type ObservationSourceKeys,
  type ObservationSourceMode,
} from "./observation-form-helpers";

export type { ObservationScope, ObservationSourceKeys, ObservationSourceMode } from "./observation-form-helpers";

export interface ObservationSourceFieldProps {
  label: string;
  description: string;
  modeLabel?: string;
  placeholder?: string;
  pathPlaceholder?: string;
  templatePlaceholder?: string;
  valueLabel?: string;
  valueMultiline?: boolean;
  required?: boolean;
  config: Record<string, unknown>;
  keys: ObservationSourceKeys;
  errors: Record<string, string>;
  onChange: (config: Record<string, unknown>) => void;
}

const MODE_OPTIONS: Array<{
  value: ObservationSourceMode;
  label: string;
}> = [
  { value: "value", label: "Text" },
  { value: "path", label: "State path" },
  { value: "template", label: "Template" },
];

const OBSERVATION_SCOPE_OPTIONS: Array<{
  value: ObservationScope;
  label: string;
  description: string;
}> = [
  {
    value: "graph",
    label: "Graph",
    description: "Share across runs for this graph.",
  },
  {
    value: "run",
    label: "Run",
    description: "Limit the memory item to the current run.",
  },
  {
    value: "session",
    label: "Session",
    description: "Reuse within the active session only.",
  },
];

export function ObservationScopeField({
  value,
  onChange,
  description,
}: {
  value?: string;
  onChange: (scope: ObservationScope) => void;
  description?: string;
}) {
  return (
    <FormField
      label="Scope"
      htmlFor="observation-scope"
      description={description ?? "Choose how broadly this observation should be reused at runtime."}
      required
    >
      <select
        id="observation-scope"
        value={value ?? "graph"}
        onChange={(event) => onChange(event.target.value as ObservationScope)}
        className="w-full rounded-md border border-input bg-background px-3 py-2 text-sm"
      >
        {OBSERVATION_SCOPE_OPTIONS.map((option) => (
          <option key={option.value} value={option.value}>
            {option.label}
          </option>
        ))}
      </select>
    </FormField>
  );
}

export function ObservationSourceField({
  label,
  description,
  modeLabel = "Source",
  placeholder,
  pathPlaceholder,
  templatePlaceholder,
  valueLabel,
  valueMultiline = false,
  required = false,
  config,
  keys,
  errors,
  onChange,
}: ObservationSourceFieldProps) {
  const mode = selectObservationSourceMode(config, keys);
  const currentValue =
    mode === "path"
      ? String(config[keys.path ?? ""] ?? "")
      : mode === "template"
        ? String(config[keys.template ?? ""] ?? "")
        : String(config[keys.value] ?? "");

  return (
    <div className="rounded-xl border border-border/60 bg-muted/20 p-4">
      <div className="grid gap-4 md:grid-cols-[180px_1fr] md:items-start">
        <FormField label={modeLabel} htmlFor={`${keys.value}-mode`} description={description}>
          <select
            id={`${keys.value}-mode`}
            value={mode}
            onChange={(event) =>
              onChange(updateObservationSourceMode(config, keys, event.target.value as ObservationSourceMode))
            }
            className="w-full rounded-md border border-input bg-background px-3 py-2 text-sm"
          >
            {MODE_OPTIONS.flatMap((option) =>
              option.value === "value" ||
              (option.value === "path" && keys.path) ||
              (option.value === "template" && keys.template)
                ? [
                    <option key={option.value} value={option.value}>
                      {option.label}
                    </option>,
                  ]
                : [],
            )}
          </select>
        </FormField>

        <FormField
          label={valueLabel ?? label}
          htmlFor={`${keys.value}-${mode}`}
          required={required}
          error={errors[keys.value]}
        >
          {valueMultiline ? (
            <Textarea
              id={`${keys.value}-${mode}`}
              value={currentValue}
              onChange={(event) => onChange(updateObservationSourceValue(config, keys, mode, event.target.value))}
              placeholder={
                mode === "path"
                  ? (pathPlaceholder ?? "node.prompt_1.output")
                  : mode === "template"
                    ? (templatePlaceholder ?? "Customer: {{input.customer_name}}")
                    : placeholder
              }
              rows={4}
              className="resize-none text-sm font-mono"
            />
          ) : (
            <Input
              id={`${keys.value}-${mode}`}
              value={currentValue}
              onChange={(event) => onChange(updateObservationSourceValue(config, keys, mode, event.target.value))}
              placeholder={
                mode === "path"
                  ? (pathPlaceholder ?? "node.prompt_1.output")
                  : mode === "template"
                    ? (templatePlaceholder ?? "Customer: {{input.customer_name}}")
                    : placeholder
              }
              className="text-sm"
            />
          )}
        </FormField>
      </div>
    </div>
  );
}
