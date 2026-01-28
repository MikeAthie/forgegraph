/**
 * Frontend Graph Validator
 *
 * Validates graph structure and provides real-time feedback for the graph editor.
 * Mirrors backend validation logic for immediate user feedback.
 */

import type { Node, Edge } from "@xyflow/react";
import { NODE_TYPES, START_NODE_ID, END_NODE_ID } from "./graph-types";

/**
 * Validation error severity levels
 */
export type ValidationSeverity = "error" | "warning";

/**
 * Validation error codes
 */
export enum ValidationErrorCode {
  NO_START_NODE = "NO_START_NODE",
  NO_OUTPUT_NODE = "NO_OUTPUT_NODE",
  NO_END_NODE = "NO_END_NODE",
  DISCONNECTED_NODE = "DISCONNECTED_NODE",
  CYCLE_DETECTED = "CYCLE_DETECTED",
  TYPE_MISMATCH = "TYPE_MISMATCH",
  MISSING_REQUIRED_FIELD = "MISSING_REQUIRED_FIELD",
  INVALID_EXPRESSION = "INVALID_EXPRESSION",
  SELF_CONNECTION = "SELF_CONNECTION",
  DUPLICATE_EDGE = "DUPLICATE_EDGE",
  EMPTY_GRAPH = "EMPTY_GRAPH",
}

/**
 * A single validation error
 */
export interface ValidationError {
  code: ValidationErrorCode;
  severity: ValidationSeverity;
  message: string;
  nodeId?: string;
  edgeId?: string;
  field?: string;
  suggestion?: string;
}

/**
 * Validation result containing all errors and warnings
 */
export interface ValidationResult {
  isValid: boolean;
  errors: ValidationError[];
  warnings: ValidationError[];
  hasStartNode: boolean;
  hasOutputNode: boolean;
  hasEndNode: boolean;
}

/**
 * Filter nodes to only executable nodes (exclude notes)
 */
function getExecutableNodes(nodes: Node[]): Node[] {
  return nodes.filter((node) => node.type !== "note");
}

/**
 * Check if graph has a start node (trigger edge from START)
 */
function checkStartNode(nodes: Node[], edges: Edge[]): ValidationError | null {
  const executableNodes = getExecutableNodes(nodes);
  if (executableNodes.length === 0) {
    return null; // Empty graph check handled separately
  }

  // Check for explicit trigger node
  const hasTrigger = executableNodes.some(
    (node) => (node.data as Record<string, unknown>)?.isTrigger === true
  );

  // Check for START -> node edge
  const hasStartEdge = edges.some((edge) => edge.source === START_NODE_ID);

  if (!hasTrigger && !hasStartEdge) {
    return {
      code: ValidationErrorCode.NO_START_NODE,
      severity: "error",
      message: "Graph needs a start node",
      suggestion: "Mark a node as the entry point or add an edge from START",
    };
  }

  return null;
}

/**
 * Check if graph has at least one output node
 */
function checkOutputNode(nodes: Node[]): ValidationError | null {
  const executableNodes = getExecutableNodes(nodes);
  if (executableNodes.length === 0) {
    return null; // Empty graph check handled separately
  }

  const hasOutput = executableNodes.some(
    (node) => node.type === NODE_TYPES.OUTPUT
  );

  if (!hasOutput) {
    return {
      code: ValidationErrorCode.NO_OUTPUT_NODE,
      severity: "error",
      message: "Graph needs an output node",
      suggestion: "Add an Output node to define the workflow result",
    };
  }

  return null;
}

/**
 * Check if graph has end nodes (sink nodes or explicit end flags)
 */
function checkEndNode(nodes: Node[], edges: Edge[]): ValidationError | null {
  const executableNodes = getExecutableNodes(nodes);
  if (executableNodes.length === 0) {
    return null;
  }

  // Check for explicit end node
  const hasExplicitEnd = executableNodes.some(
    (node) => (node.data as Record<string, unknown>)?.isEnd === true
  );

  // Check for END edge
  const hasEndEdge = edges.some((edge) => edge.target === END_NODE_ID);

  // Check for sink nodes (nodes with no outgoing edges to other nodes)
  const executableIds = new Set(executableNodes.map((n) => n.id));
  const sourcesWithOutgoing = new Set(
    edges
      .filter((e) => executableIds.has(e.source) && executableIds.has(e.target))
      .map((e) => e.source)
  );
  const sinkNodes = executableNodes.filter(
    (node) => !sourcesWithOutgoing.has(node.id)
  );

  if (!hasExplicitEnd && !hasEndEdge && sinkNodes.length === 0) {
    return {
      code: ValidationErrorCode.NO_END_NODE,
      severity: "warning",
      message: "Graph has no clear end point",
      suggestion:
        "Mark a node as the end point or ensure sink nodes exist",
    };
  }

  return null;
}

/**
 * Check for disconnected nodes
 */
function checkDisconnectedNodes(
  nodes: Node[],
  edges: Edge[]
): ValidationError[] {
  const errors: ValidationError[] = [];
  const executableNodes = getExecutableNodes(nodes);

  if (executableNodes.length <= 1) {
    return errors; // Single node graphs don't need connections
  }

  const connectedNodeIds = new Set<string>();

  // Add all nodes that are sources or targets of edges
  for (const edge of edges) {
    if (edge.source !== START_NODE_ID) {
      connectedNodeIds.add(edge.source);
    }
    if (edge.target !== END_NODE_ID) {
      connectedNodeIds.add(edge.target);
    }
  }

  // Also consider trigger nodes as connected
  for (const node of executableNodes) {
    if ((node.data as Record<string, unknown>)?.isTrigger === true) {
      connectedNodeIds.add(node.id);
    }
  }

  // Find disconnected nodes
  for (const node of executableNodes) {
    if (!connectedNodeIds.has(node.id)) {
      errors.push({
        code: ValidationErrorCode.DISCONNECTED_NODE,
        severity: "warning",
        message: `Node "${(node.data as Record<string, unknown>)?.label || node.id}" is disconnected`,
        nodeId: node.id,
        suggestion: "Connect this node to the workflow or remove it",
      });
    }
  }

  return errors;
}

/**
 * Check for cycles in the graph using DFS
 */
function checkCycles(nodes: Node[], edges: Edge[]): ValidationError | null {
  const executableNodes = getExecutableNodes(nodes);
  const executableIds = new Set(executableNodes.map((n) => n.id));

  // Build adjacency list
  const adjacency = new Map<string, string[]>();
  for (const id of executableIds) {
    adjacency.set(id, []);
  }

  for (const edge of edges) {
    if (executableIds.has(edge.source) && executableIds.has(edge.target)) {
      adjacency.get(edge.source)?.push(edge.target);
    }
  }

  // DFS with coloring: 0=white (unvisited), 1=gray (in progress), 2=black (done)
  const color = new Map<string, number>();
  for (const id of executableIds) {
    color.set(id, 0);
  }

  function hasCycle(nodeId: string): boolean {
    color.set(nodeId, 1); // Mark as in progress

    const neighbors = adjacency.get(nodeId) || [];
    for (const neighbor of neighbors) {
      const neighborColor = color.get(neighbor);
      if (neighborColor === 1) {
        // Found a back edge - cycle detected
        return true;
      }
      if (neighborColor === 0 && hasCycle(neighbor)) {
        return true;
      }
    }

    color.set(nodeId, 2); // Mark as done
    return false;
  }

  for (const id of executableIds) {
    if (color.get(id) === 0 && hasCycle(id)) {
      return {
        code: ValidationErrorCode.CYCLE_DETECTED,
        severity: "error",
        message: "Graph contains a cycle",
        suggestion: "Remove edges to break the cycle - workflows must be acyclic",
      };
    }
  }

  return null;
}

/**
 * Check for self-connections
 */
function checkSelfConnections(edges: Edge[]): ValidationError[] {
  const errors: ValidationError[] = [];

  for (const edge of edges) {
    if (edge.source === edge.target) {
      errors.push({
        code: ValidationErrorCode.SELF_CONNECTION,
        severity: "error",
        message: "Node cannot connect to itself",
        edgeId: edge.id,
        suggestion: "Remove this self-referencing edge",
      });
    }
  }

  return errors;
}

/**
 * Check for empty graph
 */
function checkEmptyGraph(nodes: Node[]): ValidationError | null {
  const executableNodes = getExecutableNodes(nodes);

  if (executableNodes.length === 0) {
    return {
      code: ValidationErrorCode.EMPTY_GRAPH,
      severity: "warning",
      message: "Graph is empty",
      suggestion: "Add nodes to build your workflow",
    };
  }

  return null;
}

/**
 * Validate a graph and return all errors and warnings
 */
export function validateGraph(nodes: Node[], edges: Edge[]): ValidationResult {
  const errors: ValidationError[] = [];
  const warnings: ValidationError[] = [];

  // Check empty graph
  const emptyError = checkEmptyGraph(nodes);
  if (emptyError) {
    if (emptyError.severity === "error") {
      errors.push(emptyError);
    } else {
      warnings.push(emptyError);
    }
  }

  // Check start node
  const startError = checkStartNode(nodes, edges);
  if (startError) {
    if (startError.severity === "error") {
      errors.push(startError);
    } else {
      warnings.push(startError);
    }
  }

  // Check output node
  const outputError = checkOutputNode(nodes);
  if (outputError) {
    if (outputError.severity === "error") {
      errors.push(outputError);
    } else {
      warnings.push(outputError);
    }
  }

  // Check end node
  const endError = checkEndNode(nodes, edges);
  if (endError) {
    if (endError.severity === "error") {
      errors.push(endError);
    } else {
      warnings.push(endError);
    }
  }

  // Check self-connections
  const selfConnectionErrors = checkSelfConnections(edges);
  errors.push(...selfConnectionErrors);

  // Check cycles
  const cycleError = checkCycles(nodes, edges);
  if (cycleError) {
    errors.push(cycleError);
  }

  // Check disconnected nodes
  const disconnectedErrors = checkDisconnectedNodes(nodes, edges);
  warnings.push(...disconnectedErrors);

  // Compute summary flags
  const executableNodes = getExecutableNodes(nodes);
  const hasStartNode =
    executableNodes.some(
      (n) => (n.data as Record<string, unknown>)?.isTrigger === true
    ) || edges.some((e) => e.source === START_NODE_ID);

  const hasOutputNode = executableNodes.some(
    (n) => n.type === NODE_TYPES.OUTPUT
  );

  const hasEndNode =
    executableNodes.some(
      (n) => (n.data as Record<string, unknown>)?.isEnd === true
    ) || edges.some((e) => e.target === END_NODE_ID);

  return {
    isValid: errors.length === 0,
    errors,
    warnings,
    hasStartNode,
    hasOutputNode,
    hasEndNode,
  };
}

/**
 * Get quick fix actions for common validation errors
 */
export interface QuickFix {
  errorCode: ValidationErrorCode;
  label: string;
  description: string;
}

export function getQuickFixesForError(error: ValidationError): QuickFix[] {
  switch (error.code) {
    case ValidationErrorCode.NO_START_NODE:
      return [
        {
          errorCode: error.code,
          label: "Add Start",
          description: "Mark the first node as the entry point",
        },
      ];
    case ValidationErrorCode.NO_OUTPUT_NODE:
      return [
        {
          errorCode: error.code,
          label: "Add Output",
          description: "Add an Output node to define the result",
        },
      ];
    case ValidationErrorCode.DISCONNECTED_NODE:
      return [
        {
          errorCode: error.code,
          label: "Connect",
          description: "Connect this node to the workflow",
        },
        {
          errorCode: error.code,
          label: "Remove",
          description: "Remove this disconnected node",
        },
      ];
    default:
      return [];
  }
}
