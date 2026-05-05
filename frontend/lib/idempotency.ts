export const newClientCommandId = (prefix: string): string => {
  const randomId =
    typeof crypto !== "undefined" && "randomUUID" in crypto
      ? crypto.randomUUID()
      : `${Date.now()}-${Math.random().toString(36).slice(2)}`;
  return `${prefix}:${randomId}`;
};

export const stableClientCommandId = (
  prefix: string,
  ...parts: Array<string | number | boolean | null | undefined>
): string => [prefix, ...parts.map((part) => String(part ?? ""))].join(":");
