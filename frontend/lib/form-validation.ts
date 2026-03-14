/**
 * Form Validation System
 *
 * Provides validation utilities for node configuration forms.
 */

/**
 * Validation error for a single field
 */
export interface FieldError {
  field: string;
  message: string;
}

/**
 * Validation result
 */
export interface ValidationResult {
  isValid: boolean;
  errors: FieldError[];
}

/**
 * Validate that a value is not empty
 */
export function validateRequired(value: unknown, fieldName: string): FieldError | null {
  if (value === undefined || value === null || value === "") {
    return { field: fieldName, message: `${fieldName} is required` };
  }
  if (typeof value === "string" && value.trim() === "") {
    return { field: fieldName, message: `${fieldName} is required` };
  }
  return null;
}

/**
 * Validate URL format
 */
export function validateUrl(value: string, fieldName: string): FieldError | null {
  if (!value || value.trim() === "") {
    return null; // Empty is handled by validateRequired
  }

  // Allow variable interpolation like {{variable}}
  const valueWithoutVars = value.replace(/\{\{[^}]+\}\}/g, "placeholder");

  try {
    new URL(valueWithoutVars);
    return null;
  } catch {
    // Check if it's a relative URL or has protocol-relative format
    if (valueWithoutVars.startsWith("/") || valueWithoutVars.startsWith("//")) {
      return null;
    }
    return { field: fieldName, message: "Invalid URL format" };
  }
}

/**
 * Validate JSON format
 */
export function validateJson(value: string, fieldName: string): FieldError | null {
  if (!value || value.trim() === "") {
    return null; // Empty is valid (optional JSON)
  }

  try {
    JSON.parse(value);
    return null;
  } catch {
    return { field: fieldName, message: "Invalid JSON format" };
  }
}

/**
 * Validate expression syntax (basic check)
 */
export function validateExpression(value: string, fieldName: string): FieldError | null {
  if (!value || value.trim() === "") {
    return null;
  }

  // Check for balanced brackets
  const brackets: Record<string, string> = { "(": ")", "[": "]", "{": "}" };
  const stack: string[] = [];

  for (const char of value) {
    if (brackets[char]) {
      stack.push(brackets[char]);
    } else if (Object.values(brackets).includes(char)) {
      if (stack.pop() !== char) {
        return { field: fieldName, message: "Unbalanced brackets in expression" };
      }
    }
  }

  if (stack.length > 0) {
    return { field: fieldName, message: "Unbalanced brackets in expression" };
  }

  return null;
}

/**
 * Validate number within range
 */
export function validateNumberRange(
  value: number | undefined,
  fieldName: string,
  min?: number,
  max?: number,
): FieldError | null {
  if (value === undefined || value === null) {
    return null;
  }

  if (typeof value !== "number" || isNaN(value)) {
    return { field: fieldName, message: "Must be a valid number" };
  }

  if (min !== undefined && value < min) {
    return { field: fieldName, message: `Must be at least ${min}` };
  }

  if (max !== undefined && value > max) {
    return { field: fieldName, message: `Must be at most ${max}` };
  }

  return null;
}

/**
 * Validate string length
 */
export function validateLength(
  value: string | undefined,
  fieldName: string,
  minLength?: number,
  maxLength?: number,
): FieldError | null {
  if (!value) {
    return null;
  }

  if (minLength !== undefined && value.length < minLength) {
    return { field: fieldName, message: `Must be at least ${minLength} characters` };
  }

  if (maxLength !== undefined && value.length > maxLength) {
    return { field: fieldName, message: `Must be at most ${maxLength} characters` };
  }

  return null;
}

/**
 * Combine multiple validation errors
 */
export function combineValidationErrors(...errors: (FieldError | null)[]): ValidationResult {
  const validErrors = errors.filter((e): e is FieldError => e !== null);
  return {
    isValid: validErrors.length === 0,
    errors: validErrors,
  };
}

/**
 * Get error message for a specific field
 */
export function getFieldError(errors: FieldError[], fieldName: string): string | undefined {
  return errors.find((e) => e.field === fieldName)?.message;
}

/**
 * Form state hook return type
 */
export interface UseFormValidationReturn<T> {
  values: T;
  errors: FieldError[];
  isValid: boolean;
  setValue: <K extends keyof T>(field: K, value: T[K]) => void;
  setValues: (values: Partial<T>) => void;
  getError: (field: keyof T) => string | undefined;
  validate: () => boolean;
  reset: (initialValues?: T) => void;
}
