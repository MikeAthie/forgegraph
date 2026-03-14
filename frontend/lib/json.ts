type JsonDisplayOptions = {
  maxDepth?: number;
  maxKeys?: number;
  maxArrayLength?: number;
  maxStringLength?: number;
  maxTotalLength?: number;
};

const DEFAULT_OPTIONS: Required<JsonDisplayOptions> = {
  maxDepth: 6,
  maxKeys: 50,
  maxArrayLength: 50,
  maxStringLength: 5000,
  maxTotalLength: 100_000,
};

function normalizeJsonForDisplay(
  value: unknown,
  options: Required<JsonDisplayOptions>,
  depth: number,
  seen: WeakSet<object>,
): unknown {
  if (value === null || value === undefined) return null;

  const valueType = typeof value;
  if (typeof value === "string") {
    if (value.length <= options.maxStringLength) return value;
    const truncated = value.slice(0, options.maxStringLength);
    return `${truncated}… (truncated ${value.length - options.maxStringLength} chars)`;
  }
  if (valueType === "number" || valueType === "boolean") return value;
  if (valueType === "bigint") return value.toString();
  if (valueType === "symbol") return String(value);
  if (valueType === "function") return "[Function]";

  if (depth >= options.maxDepth) {
    return "[Truncated: max depth]";
  }

  if (Array.isArray(value)) {
    const items = value
      .slice(0, options.maxArrayLength)
      .map((item) => normalizeJsonForDisplay(item, options, depth + 1, seen));
    if (value.length > options.maxArrayLength) {
      items.push(`… (${value.length - options.maxArrayLength} more items)`);
    }
    return items;
  }

  if (value instanceof Date) return value.toISOString();

  if (value && valueType === "object") {
    if (seen.has(value)) return "[Circular]";
    seen.add(value);

    const entries = Object.entries(value as Record<string, unknown>);
    const limited = entries.slice(0, options.maxKeys);
    const result: Record<string, unknown> = {};
    for (const [key, entryValue] of limited) {
      result[key] = normalizeJsonForDisplay(entryValue, options, depth + 1, seen);
    }
    if (entries.length > options.maxKeys) {
      result["__truncated_keys__"] = entries.length - options.maxKeys;
    }
    return result;
  }

  return String(value);
}

export function formatJsonForDisplay(value: unknown, opts?: JsonDisplayOptions): string {
  const options = { ...DEFAULT_OPTIONS, ...(opts ?? {}) };
  try {
    const normalized = normalizeJsonForDisplay(value, options, 0, new WeakSet());
    const json = JSON.stringify(normalized ?? null, null, 2);
    if (json.length <= options.maxTotalLength) return json;
    return `${json.slice(0, options.maxTotalLength)}\n… (truncated ${json.length - options.maxTotalLength} chars)`;
  } catch {
    return String(value);
  }
}
