"use client";

import { useEffect, useMemo } from "react";

import { FormField } from "@/components/ui/form-field";
import { Input } from "@/components/ui/input";
import { Textarea } from "@/components/ui/textarea";

export type ObservationScope = "graph" | "run" | "session";
export type ObservationSourceMode = "value" | "path" | "template";

export interface ObservationSourceKeys {
  value: string;
  path?: string;
  template?: string;
}

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

export const OBSERVATION_SCOPE_OPTIONS: Array<{
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

function hasValue(value: unknown): boolean {
  if (value == null) {
    return false;
  }
  if (typeof value === "string") {
    return value.trim().length > 0;
  }
  return true;
}

export function selectObservationSourceMode(
  config: Record<string, unknown>,
  keys: ObservationSourceKeys,
): ObservationSourceMode {
  if (keys.path && Object.prototype.hasOwnProperty.call(config, keys.path)) {
    return "path";
  }
  if (keys.template && Object.prototype.hasOwnProperty.call(config, keys.template)) {
    return "template";
  }
  if (Object.prototype.hasOwnProperty.call(config, keys.value)) {
    return "value";
  }
  return "value";
}

export function updateObservationSourceMode(
  config: Record<string, unknown>,
  keys: ObservationSourceKeys,
  mode: ObservationSourceMode,
): Record<string, unknown> {
  const next = { ...config };
  const activeKey = mode === "path" ? keys.path : mode === "template" ? keys.template : keys.value;

  for (const key of [keys.value, keys.path, keys.template]) {
    if (!key || key === activeKey) {
      continue;
    }
    delete next[key];
  }

  if (activeKey && !Object.prototype.hasOwnProperty.call(next, activeKey)) {
    next[activeKey] = "";
  }

  return next;
}

export function updateObservationSourceValue(
  config: Record<string, unknown>,
  keys: ObservationSourceKeys,
  mode: ObservationSourceMode,
  rawValue: string,
): Record<string, unknown> {
  const next = updateObservationSourceMode(config, keys, mode);
  const targetKey = mode === "path" ? keys.path : mode === "template" ? keys.template : keys.value;

  if (!targetKey) {
    return next;
  }

  if (rawValue.trim().length === 0) {
    if (mode === "value") {
      delete next[targetKey];
    } else {
      next[targetKey] = "";
    }
    return next;
  }

  next[targetKey] = rawValue;
  return next;
}

export function updateObservationNumberField(
  config: Record<string, unknown>,
  field: string,
  rawValue: string,
): Record<string, unknown> {
  const next = { ...config };
  if (!rawValue.trim()) {
    delete next[field];
    return next;
  }

  const parsed = Number.parseInt(rawValue, 10);
  if (!Number.isFinite(parsed) || parsed <= 0) {
    return next;
  }

  next[field] = parsed;
  return next;
}

export function validateObservationSource(
  config: Record<string, unknown>,
  field: string,
  keys: ObservationSourceKeys,
  options: {
    required: boolean;
  },
): string | undefined {
  const populatedFields = [keys.value, keys.path, keys.template].filter((key): key is string =>
    Boolean(key && hasValue(config[key])),
  );

  if (populatedFields.length > 1) {
    return `Choose a single source for ${field}.`;
  }
  if (options.required && populatedFields.length === 0) {
    return `${field} requires one configured source.`;
  }
  return undefined;
}

export function useObservationErrors(
  errors: Record<string, string>,
  setErrors: (errors: Record<string, string>) => void,
  computedErrors: Record<string, string | undefined>,
): void {
  const serializedErrors = useMemo(
    () => JSON.stringify(Object.fromEntries(Object.entries(computedErrors).filter(([, value]) => Boolean(value)))),
    [computedErrors],
  );

  useEffect(() => {
    const nextErrors = JSON.parse(serializedErrors) as Record<string, string>;
    if (JSON.stringify(errors) === serializedErrors) {
      return;
    }
    setErrors(nextErrors);
  }, [errors, serializedErrors, setErrors]);
}

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
            {MODE_OPTIONS.filter(
              (option) =>
                option.value === "value" ||
                (option.value === "path" && keys.path) ||
                (option.value === "template" && keys.template),
            ).map((option) => (
              <option key={option.value} value={option.value}>
                {option.label}
              </option>
            ))}
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
