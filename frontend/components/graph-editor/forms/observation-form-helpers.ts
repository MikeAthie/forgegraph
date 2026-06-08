export type ObservationScope = "graph" | "run" | "session";
export type ObservationSourceMode = "value" | "path" | "template";

export interface ObservationSourceKeys {
  value: string;
  path?: string;
  template?: string;
}

function hasObservationValue(value: unknown): boolean {
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
    Boolean(key && hasObservationValue(config[key])),
  );

  if (populatedFields.length > 1) {
    return `Choose a single source for ${field}.`;
  }
  if (options.required && populatedFields.length === 0) {
    return `${field} requires one configured source.`;
  }
  return undefined;
}

export function compactObservationErrors(errors: Record<string, string | undefined>): Record<string, string> {
  return Object.fromEntries(Object.entries(errors).filter(([, value]) => Boolean(value))) as Record<string, string>;
}
