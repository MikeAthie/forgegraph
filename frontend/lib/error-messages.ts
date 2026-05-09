/**
 * Error message sanitization and user-friendly error mapping.
 *
 * This module provides utilities to convert technical backend errors into
 * user-friendly messages that are appropriate for display in the UI.
 */

/** Maximum length for error messages displayed to users */
const MAX_ERROR_LENGTH = 200;

/**
 * Pattern-based error mappings. Each pattern is tested against the raw error
 * message, and if matched, the corresponding user-friendly message is returned.
 *
 * Patterns are tested in order, so more specific patterns should come first.
 */
const ERROR_PATTERNS: Array<{
  pattern: RegExp;
  message: string;
  /** Optional: extract details from the match for a more specific message */
  formatMessage?: (match: RegExpMatchArray) => string;
}> = [
  // Credential-specific errors
  {
    pattern: /encryption.?key.*not.*configured|ENCRYPTION_KEY/i,
    message: "Unable to securely store credentials. Please contact support.",
  },
  {
    pattern: /invalid.*api.?key|api.?key.*invalid|authentication.*failed|unauthorized/i,
    message: "Invalid API key. Please check your credentials and try again.",
  },
  {
    pattern: /api.?key.*expired|token.*expired|credentials.*expired/i,
    message: "Your API key has expired. Please add a new one.",
  },
  {
    pattern: /rate.?limit|too.?many.?requests|429/i,
    message: "Rate limit exceeded. Please wait a moment and try again.",
  },
  {
    pattern: /quota.*exceeded|insufficient.*quota|billing/i,
    message: "API quota exceeded. Please check your provider account.",
  },
  {
    pattern: /invalid.*model|model.*not.*found|model.*unavailable/i,
    message: "The selected model is not available. Please choose a different model.",
  },

  // Network and connection errors
  {
    pattern: /network.*error|connection.*refused|ECONNREFUSED|fetch.*failed/i,
    message: "Unable to connect to the server. Please check your connection.",
  },
  {
    pattern: /timeout|ETIMEDOUT|request.*timed.*out/i,
    message: "Request timed out. Please try again.",
  },
  {
    pattern: /503|service.*unavailable/i,
    message: "Service temporarily unavailable. Please try again later.",
  },
  {
    pattern: /502|bad.*gateway/i,
    message: "Server is temporarily unreachable. Please try again.",
  },
  {
    pattern: /500|internal.*server.*error/i,
    message: "Something went wrong on our end. Please try again.",
  },

  // Permission errors
  {
    pattern: /permission.*denied|access.*denied|forbidden|403/i,
    message: "You don't have permission to perform this action.",
  },
  {
    pattern: /not.*found|404|does.*not.*exist/i,
    message: "The requested resource was not found.",
  },

  // Validation errors
  {
    pattern: /invalid.*json|json.*parse|syntax.*error.*json/i,
    message: "Invalid data format. Please check your input.",
  },
  {
    pattern: /required.*field|field.*required|missing.*required/i,
    message: "Please fill in all required fields.",
  },
  {
    pattern: /already.*exists|duplicate|unique.*constraint/i,
    message: "This item already exists. Please use a different name.",
  },

  // OAuth-specific errors
  {
    pattern: /oauth.*error|oauth.*failed|authorization.*failed/i,
    message: "OAuth authorization failed. Please try connecting again.",
  },
  {
    pattern: /invalid.*redirect|callback.*error/i,
    message: "OAuth callback failed. Please try connecting again.",
  },

  // Generic provider errors (these should be near the end)
  {
    pattern: /openai.*error/i,
    message: "OpenAI returned an error. Please verify your API key.",
  },
  {
    pattern: /anthropic.*error/i,
    message: "Anthropic returned an error. Please verify your API key.",
  },
  {
    pattern: /google.*error/i,
    message: "Google returned an error. Please verify your credentials.",
  },
];

/**
 * Patterns that indicate the error message contains technical details
 * that should not be shown to users.
 */
const TECHNICAL_PATTERNS = [
  /traceback/i,
  /stack.?trace/i,
  /file.*line.*\d+/i,
  /at\s+\w+.*\(.*:\d+:\d+\)/i, // JavaScript stack trace
  /^\s*at\s+/m, // Python/Node stack trace lines
  /exception|error.*class|\.py"|\.js"|\.ts"/i,
  /django\.|python|node_modules/i,
];

/**
 * Check if an error message contains technical details that should be sanitized.
 */
function containsTechnicalDetails(message: string): boolean {
  return TECHNICAL_PATTERNS.some((pattern) => pattern.test(message));
}

/**
 * Extract the first meaningful line from a potentially multi-line error message.
 */
function extractFirstLine(message: string): string {
  const lines = message.split(/\r?\n/).filter((line) => line.trim());
  return lines[0] || message;
}

/**
 * Sanitize an error message for display to users.
 *
 * This function:
 * 1. Checks for known error patterns and returns user-friendly messages
 * 2. Removes technical details like stack traces
 * 3. Truncates overly long messages
 * 4. Falls back to a generic message if the error is too technical
 *
 * @param rawMessage - The raw error message from the backend
 * @param fallback - Fallback message if no pattern matches
 * @returns A user-friendly error message
 */
export function sanitizeErrorMessage(rawMessage: string, fallback: string): string {
  if (!rawMessage || typeof rawMessage !== "string") {
    return fallback;
  }

  // Check for known error patterns first
  for (const { pattern, message, formatMessage } of ERROR_PATTERNS) {
    const match = rawMessage.match(pattern);
    if (match) {
      return formatMessage ? formatMessage(match) : message;
    }
  }

  // If the message contains technical details, use fallback
  if (containsTechnicalDetails(rawMessage)) {
    return fallback;
  }

  // Extract first line for multi-line errors
  let cleanMessage = extractFirstLine(rawMessage);

  // Truncate if too long
  if (cleanMessage.length > MAX_ERROR_LENGTH) {
    cleanMessage = cleanMessage.substring(0, MAX_ERROR_LENGTH - 1) + "…";
  }

  // If the message still looks technical, use fallback
  if (containsTechnicalDetails(cleanMessage)) {
    return fallback;
  }

  return cleanMessage || fallback;
}

/**
 * Context-specific fallback messages for different operations.
 */
export const ERROR_FALLBACKS = {
  credential: {
    create: "Unable to save credential. Please check your API key and try again.",
    delete: "Unable to delete credential. Please try again.",
    verify: "Unable to verify credential. Please check your API key.",
    oauth: "OAuth connection failed. Please try again.",
  },
  graph: {
    create: "Unable to create graph. Please try again.",
    update: "Unable to save changes. Please try again.",
    delete: "Unable to delete graph. Please try again.",
    clone: "Unable to clone graph. Please try again.",
    load: "Unable to load graph. Please try again.",
  },
  run: {
    start: "Unable to start run. Please try again.",
    stop: "Unable to stop run. Please try again.",
    resume: "Unable to resume run. Please try again.",
    cancel: "Unable to cancel run. Please try again.",
  },
  prompt: {
    create: "Unable to create prompt. Please try again.",
    update: "Unable to save prompt. Please try again.",
    delete: "Unable to delete prompt. Please try again.",
    clone: "Unable to clone prompt. Please try again.",
    publish: "Unable to publish prompt. Please try again.",
  },
  auth: {
    login: "Unable to sign in. Please check your credentials.",
    register: "Unable to create account. Please try again.",
    logout: "Unable to sign out. Please try again.",
  },
  analytics: {
    load: "Unable to load analytics. Please try again.",
    update: "Unable to update settings. Please try again.",
  },
  generic: "Something went wrong. Please try again.",
} as const;
