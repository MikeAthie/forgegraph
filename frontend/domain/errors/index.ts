export type ProductErrorContext =
  | "company"
  | "operation"
  | "department"
  | "deliverable"
  | "approval"
  | "accounting"
  | "knowledge"
  | "settings";

const FALLBACKS: Record<ProductErrorContext, string> = {
  company: "The company could not be updated. Please try again.",
  operation: "The operation could not continue. Please try again.",
  department: "A department needs attention before work can continue.",
  deliverable: "The deliverable is not available yet. Please try again.",
  approval: "The approval could not be submitted. Please try again.",
  accounting: "Accounting records could not be loaded. Please try again.",
  knowledge: "The knowledge records could not be loaded. Please try again.",
  settings: "The setting could not be saved. Please try again.",
};

const PRODUCT_ERROR_PATTERNS: Array<{ pattern: RegExp; message: string }> = [
  {
    pattern: /timeout|timed out/i,
    message: "A department waited too long for an AI response. Retry the operation or narrow the assignment.",
  },
  {
    pattern: /connection|refused|unavailable|network|503|502/i,
    message: "A department could not reach the AI service. Retry when the provider is available.",
  },
  {
    pattern: /quota|rate.?limit|budget|limit|429/i,
    message: "The operation hit an AI access limit. Try again later or switch AI access mode.",
  },
  {
    pattern: /validation|required|missing/i,
    message: "Some required information is missing. Review the company setup and try again.",
  },
  {
    pattern: /401|403|forbidden|permission|unauthori[sz]ed/i,
    message: "The backend rejected this approval decision. Refresh your session or ask an admin to grant access.",
  },
  {
    pattern: /404|not found/i,
    message: "This approval is no longer available in the backend.",
  },
  {
    pattern: /409|conflict|already resolved|different decision/i,
    message: "The backend has already recorded a different decision for this approval.",
  },
  {
    pattern: /approval|paused|human/i,
    message: "The operation is waiting for an approval before the next department can continue.",
  },
  {
    pattern: /output|json|parse|schema/i,
    message: "The operation finished without a readable deliverable. Retry or simplify the assignment.",
  },
];

function extractRawMessage(error: unknown): string {
  if (error instanceof Error) {
    return error.message;
  }
  if (typeof error === "string") {
    return error;
  }
  const response = (error as { response?: { status?: number; data?: unknown } } | null)?.response;
  if (response) {
    const data = response.data as
      | {
          detail?: unknown;
          message?: unknown;
          error?: unknown;
        }
      | undefined;
    const nestedError =
      data && typeof data.error === "object" && data.error !== null
        ? (data.error as { message?: unknown; detail?: unknown; code?: unknown })
        : null;
    const message =
      nestedError?.message ?? nestedError?.detail ?? nestedError?.code ?? data?.detail ?? data?.message ?? data?.error;
    if (typeof message === "string" && message.trim()) {
      return `${response.status ?? ""} ${message}`.trim();
    }
    if (response.status) {
      return String(response.status);
    }
  }
  return "";
}

export function translateProductError(error: unknown, context: ProductErrorContext): string {
  const raw = extractRawMessage(error);
  for (const { pattern, message } of PRODUCT_ERROR_PATTERNS) {
    if (pattern.test(raw)) {
      return message;
    }
  }
  return FALLBACKS[context];
}

export function translateFailureDetails(rawMessage: string | null | undefined, context: ProductErrorContext): string {
  if (!rawMessage) {
    return FALLBACKS[context];
  }
  for (const { pattern, message } of PRODUCT_ERROR_PATTERNS) {
    if (pattern.test(rawMessage)) {
      return message;
    }
  }
  return FALLBACKS[context];
}
