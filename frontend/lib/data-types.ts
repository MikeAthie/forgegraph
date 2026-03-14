/**
 * Data Type System
 *
 * Defines the data types that flow between nodes in a graph.
 * Used for type visualization and compatibility checking.
 */

/**
 * Core data types that can flow between nodes
 */
export enum DataType {
  TEXT = "text",
  JSON = "json",
  ARRAY = "array",
  NUMBER = "number",
  BOOLEAN = "boolean",
  IMAGE = "image",
  FILE = "file",
  ANY = "any",
  VOID = "void",
}

/**
 * Display information for data types
 */
export interface DataTypeInfo {
  label: string;
  description: string;
  icon: string;
  color: string;
  bgColor: string;
}

/**
 * Data type display metadata
 */
export const DATA_TYPE_INFO: Record<DataType, DataTypeInfo> = {
  [DataType.TEXT]: {
    label: "Text",
    description: "Plain text string",
    icon: "Type",
    color: "text-blue-600 dark:text-blue-400",
    bgColor: "bg-blue-500/15",
  },
  [DataType.JSON]: {
    label: "JSON",
    description: "Structured JSON object",
    icon: "Braces",
    color: "text-emerald-600 dark:text-emerald-400",
    bgColor: "bg-emerald-500/15",
  },
  [DataType.ARRAY]: {
    label: "Array",
    description: "List of items",
    icon: "List",
    color: "text-violet-600 dark:text-violet-400",
    bgColor: "bg-violet-500/15",
  },
  [DataType.NUMBER]: {
    label: "Number",
    description: "Numeric value",
    icon: "Hash",
    color: "text-amber-600 dark:text-amber-400",
    bgColor: "bg-amber-500/15",
  },
  [DataType.BOOLEAN]: {
    label: "Boolean",
    description: "True or false value",
    icon: "ToggleLeft",
    color: "text-rose-600 dark:text-rose-400",
    bgColor: "bg-rose-500/15",
  },
  [DataType.IMAGE]: {
    label: "Image",
    description: "Image data or URL",
    icon: "Image",
    color: "text-pink-600 dark:text-pink-400",
    bgColor: "bg-pink-500/15",
  },
  [DataType.FILE]: {
    label: "File",
    description: "File data or path",
    icon: "File",
    color: "text-slate-600 dark:text-slate-400",
    bgColor: "bg-slate-500/15",
  },
  [DataType.ANY]: {
    label: "Any",
    description: "Accepts any type",
    icon: "Asterisk",
    color: "text-gray-600 dark:text-gray-400",
    bgColor: "bg-gray-500/15",
  },
  [DataType.VOID]: {
    label: "Void",
    description: "No data output",
    icon: "Circle",
    color: "text-gray-400 dark:text-gray-500",
    bgColor: "bg-gray-500/10",
  },
};

/**
 * Detailed data type schema with optional JSON Schema
 */
export interface DataTypeSchema {
  type: DataType;
  schema?: Record<string, unknown>; // JSON Schema
  description?: string;
  example?: unknown;
  isInferred?: boolean;
}

/**
 * Type compatibility result
 */
export interface TypeCompatibility {
  compatible: boolean;
  reason?: string;
  suggestion?: string;
}

/**
 * Type compatibility matrix
 * Defines which source types can be used with which target types
 */
const COMPATIBILITY_MATRIX: Record<DataType, Set<DataType>> = {
  [DataType.TEXT]: new Set([DataType.TEXT, DataType.ANY]),
  [DataType.JSON]: new Set([DataType.JSON, DataType.TEXT, DataType.ANY]),
  [DataType.ARRAY]: new Set([DataType.ARRAY, DataType.JSON, DataType.ANY]),
  [DataType.NUMBER]: new Set([DataType.NUMBER, DataType.TEXT, DataType.ANY]),
  [DataType.BOOLEAN]: new Set([DataType.BOOLEAN, DataType.TEXT, DataType.ANY]),
  [DataType.IMAGE]: new Set([DataType.IMAGE, DataType.FILE, DataType.ANY]),
  [DataType.FILE]: new Set([DataType.FILE, DataType.ANY]),
  [DataType.ANY]: new Set([
    DataType.TEXT,
    DataType.JSON,
    DataType.ARRAY,
    DataType.NUMBER,
    DataType.BOOLEAN,
    DataType.IMAGE,
    DataType.FILE,
    DataType.ANY,
    DataType.VOID,
  ]),
  [DataType.VOID]: new Set([DataType.ANY]),
};

/**
 * Check if two data types are compatible
 *
 * @param sourceType - The type being output
 * @param targetType - The type expected as input
 * @returns Compatibility result with reason if incompatible
 */
export function areTypesCompatible(sourceType: DataType, targetType: DataType): TypeCompatibility {
  // ANY target accepts everything
  if (targetType === DataType.ANY) {
    return { compatible: true };
  }

  // VOID source produces nothing
  if (sourceType === DataType.VOID) {
    return {
      compatible: false,
      reason: "Source node produces no output",
      suggestion: "Connect to a node that produces output",
    };
  }

  // Check compatibility matrix
  const compatibleTargets = COMPATIBILITY_MATRIX[sourceType];
  if (compatibleTargets?.has(targetType)) {
    return { compatible: true };
  }

  // Exact match
  if (sourceType === targetType) {
    return { compatible: true };
  }

  // Generate specific suggestions
  const sourceInfo = DATA_TYPE_INFO[sourceType];
  const targetInfo = DATA_TYPE_INFO[targetType];

  let suggestion: string | undefined;

  if (sourceType === DataType.JSON && targetType === DataType.TEXT) {
    suggestion = "JSON will be stringified to text";
    return { compatible: true, suggestion };
  }

  if (sourceType === DataType.TEXT && targetType === DataType.JSON) {
    suggestion = "Add a Transform node to parse the text as JSON";
  } else if (sourceType === DataType.JSON && targetType === DataType.ARRAY) {
    suggestion = "Add a Transform node to extract the array from JSON";
  } else {
    suggestion = `Add a Transform node to convert ${sourceInfo.label} to ${targetInfo.label}`;
  }

  return {
    compatible: false,
    reason: `Type mismatch: ${sourceInfo.label} → ${targetInfo.label}`,
    suggestion,
  };
}

/**
 * Get the display info for a data type
 */
export function getDataTypeInfo(type: DataType): DataTypeInfo {
  return DATA_TYPE_INFO[type] || DATA_TYPE_INFO[DataType.ANY];
}

/**
 * Parse a data type string into the enum
 */
export function parseDataType(value: string | undefined): DataType {
  if (!value) return DataType.ANY;
  const normalized = value.toLowerCase();
  const types = Object.values(DataType);
  return types.includes(normalized as DataType) ? (normalized as DataType) : DataType.ANY;
}
