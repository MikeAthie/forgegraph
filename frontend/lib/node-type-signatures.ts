/**
 * Node Type Signatures
 *
 * Defines the input/output type signatures for each node type.
 * Used for type inference and compatibility checking.
 */

import { NODE_TYPES, type NodeType } from "./graph-types";
import { DataType } from "./data-types";

/**
 * A single input or output port on a node
 */
export interface NodePort {
  name: string;
  type: DataType;
  required?: boolean;
  multiple?: boolean; // For inputs that accept multiple connections (like merge)
  description?: string;
}

/**
 * Complete type signature for a node type
 */
export interface NodeSignature {
  inputs: NodePort[];
  outputs: NodePort[];
  description?: string;
}

/**
 * Node type signatures defining what each node type accepts and produces
 */
export const NODE_SIGNATURES: Record<NodeType, NodeSignature> = {
  [NODE_TYPES.AGENT]: {
    inputs: [
      {
        name: "context",
        type: DataType.JSON,
        required: false,
        description: "Structured state or user input available to the agent",
      },
    ],
    outputs: [
      {
        name: "result",
        type: DataType.ANY,
        description: "Final agent output after tool-assisted reasoning",
      },
    ],
    description: "Runs a bounded model-to-tool loop and returns the final result",
  },

  [NODE_TYPES.PROMPT]: {
    inputs: [
      {
        name: "context",
        type: DataType.JSON,
        required: false,
        description: "Variables to interpolate into the prompt",
      },
    ],
    outputs: [
      {
        name: "response",
        type: DataType.TEXT,
        description: "LLM response text",
      },
    ],
    description: "Sends a prompt to an LLM and returns the response",
  },

  [NODE_TYPES.HTTP]: {
    inputs: [
      {
        name: "body",
        type: DataType.JSON,
        required: false,
        description: "Request body for POST/PUT/PATCH",
      },
      {
        name: "headers",
        type: DataType.JSON,
        required: false,
        description: "HTTP headers",
      },
    ],
    outputs: [
      {
        name: "response",
        type: DataType.JSON,
        description: "HTTP response data",
      },
    ],
    description: "Makes an HTTP request to an external API",
  },

  [NODE_TYPES.TRANSFORM]: {
    inputs: [
      {
        name: "input",
        type: DataType.ANY,
        required: true,
        description: "Data to transform",
      },
    ],
    outputs: [
      {
        name: "output",
        type: DataType.ANY, // Dynamic based on expression
        description: "Transformed data",
      },
    ],
    description: "Transforms data using a JavaScript expression",
  },

  [NODE_TYPES.BRANCH]: {
    inputs: [
      {
        name: "value",
        type: DataType.ANY,
        required: true,
        description: "Value to evaluate conditions against",
      },
    ],
    outputs: [
      {
        name: "true",
        type: DataType.ANY,
        description: "Output when condition is true",
      },
      {
        name: "false",
        type: DataType.ANY,
        description: "Output when condition is false",
      },
    ],
    description: "Routes data based on conditions",
  },

  [NODE_TYPES.MERGE]: {
    inputs: [
      {
        name: "sources",
        type: DataType.ANY,
        required: true,
        multiple: true,
        description: "Multiple inputs to merge",
      },
    ],
    outputs: [
      {
        name: "merged",
        type: DataType.JSON,
        description: "Merged data from all sources",
      },
    ],
    description: "Combines data from multiple branches",
  },

  [NODE_TYPES.OUTPUT]: {
    inputs: [
      {
        name: "data",
        type: DataType.ANY,
        required: true,
        description: "Data to output",
      },
    ],
    outputs: [],
    description: "Defines the final output of the workflow",
  },

  [NODE_TYPES.HUMAN_GATE]: {
    inputs: [
      {
        name: "data",
        type: DataType.ANY,
        required: false,
        description: "Data to review",
      },
    ],
    outputs: [
      {
        name: "approved",
        type: DataType.ANY,
        description: "Data after approval (may be modified)",
      },
    ],
    description: "Pauses execution for human approval",
  },

  [NODE_TYPES.MEMORY]: {
    inputs: [
      {
        name: "data",
        type: DataType.ANY,
        required: false,
        description: "Data to store (for store operations)",
      },
    ],
    outputs: [
      {
        name: "retrieved",
        type: DataType.ANY,
        description: "Retrieved data (for recall operations)",
      },
    ],
    description: "Stores or retrieves data from memory",
  },

  [NODE_TYPES.OBSERVATION_SAVE]: {
    inputs: [
      {
        name: "context",
        type: DataType.ANY,
        required: false,
        description: "Structured state available for resolving content or template inputs",
      },
    ],
    outputs: [
      {
        name: "output",
        type: DataType.JSON,
        description: "Saved observation payload",
      },
    ],
    description: "Saves a curated observation to durable memory",
  },

  [NODE_TYPES.OBSERVATION_SEARCH]: {
    inputs: [
      {
        name: "context",
        type: DataType.ANY,
        required: false,
        description: "Structured state available for resolving search inputs",
      },
    ],
    outputs: [
      {
        name: "output",
        type: DataType.JSON,
        description: "List of matching observations",
      },
    ],
    description: "Searches curated observations with explicit filters",
  },

  [NODE_TYPES.OBSERVATION_CONTEXT]: {
    inputs: [
      {
        name: "context",
        type: DataType.ANY,
        required: false,
        description: "Structured state available for context assembly",
      },
    ],
    outputs: [
      {
        name: "output",
        type: DataType.JSON,
        description: "Curated observation context pack",
      },
    ],
    description: "Assembles memory-backed context for prompts and agents",
  },

  [NODE_TYPES.OBSERVATION_TIMELINE]: {
    inputs: [
      {
        name: "context",
        type: DataType.ANY,
        required: false,
        description: "Structured state available for runtime filters",
      },
    ],
    outputs: [
      {
        name: "output",
        type: DataType.JSON,
        description: "Ordered timeline of observations",
      },
    ],
    description: "Retrieves recent curated observations in timeline order",
  },

  [NODE_TYPES.TOOL]: {
    inputs: [
      {
        name: "params",
        type: DataType.JSON,
        required: false,
        description: "Tool parameters",
      },
    ],
    outputs: [
      {
        name: "result",
        type: DataType.JSON,
        description: "Tool execution result",
      },
    ],
    description: "Executes an external tool or function",
  },

  [NODE_TYPES.SUBGRAPH]: {
    inputs: [
      {
        name: "input",
        type: DataType.JSON,
        required: false,
        description: "Input data for the subgraph",
      },
    ],
    outputs: [
      {
        name: "output",
        type: DataType.JSON,
        description: "Output from the subgraph",
      },
    ],
    description: "Executes another graph as a nested workflow",
  },
};

/**
 * Get the type signature for a node type
 */
export function getNodeSignature(nodeType: NodeType): NodeSignature | null {
  return NODE_SIGNATURES[nodeType] || null;
}

/**
 * Get the primary output type for a node type
 */
export function getPrimaryOutputType(nodeType: NodeType): DataType {
  const signature = NODE_SIGNATURES[nodeType];
  if (!signature || signature.outputs.length === 0) {
    return DataType.VOID;
  }
  return signature.outputs[0].type;
}

/**
 * Get the primary input type for a node type
 */
export function getPrimaryInputType(nodeType: NodeType): DataType {
  const signature = NODE_SIGNATURES[nodeType];
  if (!signature || signature.inputs.length === 0) {
    return DataType.ANY;
  }
  return signature.inputs[0].type;
}

/**
 * Check if a node type has multiple outputs (like Branch)
 */
export function hasMultipleOutputs(nodeType: NodeType): boolean {
  const signature = NODE_SIGNATURES[nodeType];
  return signature ? signature.outputs.length > 1 : false;
}

/**
 * Check if a node type accepts multiple inputs (like Merge)
 */
export function acceptsMultipleInputs(nodeType: NodeType): boolean {
  const signature = NODE_SIGNATURES[nodeType];
  if (!signature) return false;
  return signature.inputs.some((input) => input.multiple);
}
