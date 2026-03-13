/**
 * Type Inference Engine
 *
 * Infers data types for nodes based on their configuration and connections.
 * Used for visual type indicators and compatibility warnings.
 */

import { DataType, DataTypeSchema, areTypesCompatible, TypeCompatibility } from "./data-types";
import { type NodeType, NODE_TYPES, type GraphNode, type GraphEdge, START_NODE_ID, END_NODE_ID } from "./graph-types";
import { NODE_SIGNATURES, getNodeSignature, NodeSignature } from "./node-type-signatures";

/**
 * Inferred type information for a node
 */
export interface NodeTypeInfo {
  nodeId: string;
  inputTypes: DataTypeSchema[];
  outputType: DataTypeSchema;
  signature: NodeSignature | null;
}

/**
 * Type mismatch warning for an edge
 */
export interface EdgeTypeMismatch {
  edgeId: string;
  sourceNodeId: string;
  targetNodeId: string;
  sourceType: DataType;
  targetType: DataType;
  compatibility: TypeCompatibility;
}

/**
 * Available data from upstream nodes
 */
export interface AvailableData {
  nodeId: string;
  nodeName: string;
  outputType: DataType;
  path: string; // e.g., "nodeId.output" or "nodeId.output.field"
}

/**
 * Infer the output type of a node based on its type and configuration
 */
export function inferOutputType(node: GraphNode): DataTypeSchema {
  const signature = getNodeSignature(node.type);
  const config = node.config || {};

  // Get base output type from signature
  let baseType = signature?.outputs[0]?.type ?? DataType.ANY;

  // Refine based on node type and config
  switch (node.type) {
    case NODE_TYPES.AGENT:
      return {
        type: DataType.ANY,
        description: "Agent final output",
        isInferred: true,
      };

    case NODE_TYPES.PROMPT:
      // Prompts always output text (LLM responses)
      return {
        type: DataType.TEXT,
        description: "LLM response text",
        isInferred: true,
      };

    case NODE_TYPES.HTTP:
      // HTTP usually returns JSON, but could be text
      return {
        type: DataType.JSON,
        description: "HTTP response data",
        isInferred: true,
      };

    case NODE_TYPES.TRANSFORM:
      // Transform output type depends on expression
      // We can try to analyze the expression for hints
      const expr = (config.expression as string) || "";
      if (expr.includes("JSON.stringify") || expr.includes(".toString()")) {
        return { type: DataType.TEXT, isInferred: true };
      }
      if (expr.includes("JSON.parse")) {
        return { type: DataType.JSON, isInferred: true };
      }
      if (expr.includes(".map(") || expr.includes(".filter(") || expr.includes("[")) {
        return { type: DataType.ARRAY, isInferred: true };
      }
      // Default to JSON for object returns
      return { type: DataType.JSON, isInferred: true };

    case NODE_TYPES.BRANCH:
      // Branch passes through the input value
      return { type: DataType.ANY, isInferred: true };

    case NODE_TYPES.MERGE:
      // Merge combines inputs into JSON
      return {
        type: DataType.JSON,
        description: "Merged data from all branches",
        isInferred: true,
      };

    case NODE_TYPES.MEMORY:
      // Memory retrieval type depends on what was stored
      const action = config.action as string;
      if (action === "set" || action === "delete") {
        // These don't really output useful data
        return { type: DataType.JSON, isInferred: true };
      }
      // Get returns the stored value (type unknown)
      return { type: DataType.ANY, isInferred: true };

    case NODE_TYPES.TOOL:
      // Tool output depends on the specific tool
      return { type: DataType.JSON, isInferred: true };

    case NODE_TYPES.SUBGRAPH:
      // Subgraph output depends on the nested graph
      return { type: DataType.JSON, isInferred: true };

    case NODE_TYPES.HUMAN_GATE:
      // Human gate passes through (potentially modified) data
      return { type: DataType.ANY, isInferred: true };

    case NODE_TYPES.OUTPUT:
      // Output node doesn't produce further output
      return { type: DataType.VOID, isInferred: true };

    default:
      return { type: baseType, isInferred: true };
  }
}

/**
 * Infer what input types a node expects
 */
export function inferInputTypes(node: GraphNode): DataTypeSchema[] {
  const signature = getNodeSignature(node.type);

  if (!signature) {
    return [{ type: DataType.ANY, isInferred: true }];
  }

  return signature.inputs.map((input) => ({
    type: input.type,
    description: input.description,
    isInferred: false,
  }));
}

/**
 * Get the primary input type for a node
 */
export function getPrimaryInputType(node: GraphNode): DataType {
  const inputs = inferInputTypes(node);
  return inputs[0]?.type ?? DataType.ANY;
}

/**
 * Get the primary output type for a node
 */
export function getPrimaryOutputType(node: GraphNode): DataType {
  return inferOutputType(node).type;
}

/**
 * Analyze type compatibility for all edges in a graph
 */
export function analyzeEdgeTypes(
  nodes: GraphNode[],
  edges: GraphEdge[]
): EdgeTypeMismatch[] {
  const mismatches: EdgeTypeMismatch[] = [];
  const nodeMap = new Map(nodes.map((n) => [n.id, n]));

  for (const edge of edges) {
    // Skip sentinel edges
    if (edge.from === START_NODE_ID || edge.to === END_NODE_ID) {
      continue;
    }

    const sourceNode = nodeMap.get(edge.from);
    const targetNode = nodeMap.get(edge.to);

    if (!sourceNode || !targetNode) {
      continue;
    }

    const sourceType = getPrimaryOutputType(sourceNode);
    const targetType = getPrimaryInputType(targetNode);

    const compatibility = areTypesCompatible(sourceType, targetType);

    if (!compatibility.compatible) {
      mismatches.push({
        edgeId: edge.id,
        sourceNodeId: edge.from,
        targetNodeId: edge.to,
        sourceType,
        targetType,
        compatibility,
      });
    }
  }

  return mismatches;
}

/**
 * Get all data available to a node from its upstream connections
 */
export function getAvailableData(
  nodeId: string,
  nodes: GraphNode[],
  edges: GraphEdge[]
): AvailableData[] {
  const available: AvailableData[] = [];
  const nodeMap = new Map(nodes.map((n) => [n.id, n]));

  // Find all incoming edges to this node
  const incomingEdges = edges.filter((e) => e.to === nodeId);

  for (const edge of incomingEdges) {
    if (edge.from === START_NODE_ID) {
      // START provides initial input
      available.push({
        nodeId: START_NODE_ID,
        nodeName: "Input",
        outputType: DataType.JSON,
        path: "input",
      });
      continue;
    }

    const sourceNode = nodeMap.get(edge.from);
    if (!sourceNode) continue;

    const outputType = getPrimaryOutputType(sourceNode);

    available.push({
      nodeId: sourceNode.id,
      nodeName: sourceNode.name || sourceNode.id,
      outputType,
      path: `state.${sourceNode.id}.output`,
    });
  }

  return available;
}

/**
 * Get all upstream nodes for a given node (traverses the graph backwards)
 */
export function getUpstreamNodes(
  nodeId: string,
  nodes: GraphNode[],
  edges: GraphEdge[],
  visited: Set<string> = new Set()
): GraphNode[] {
  if (visited.has(nodeId)) {
    return [];
  }
  visited.add(nodeId);

  const upstream: GraphNode[] = [];
  const nodeMap = new Map(nodes.map((n) => [n.id, n]));

  // Find all incoming edges
  const incomingEdges = edges.filter((e) => e.to === nodeId);

  for (const edge of incomingEdges) {
    if (edge.from === START_NODE_ID) {
      continue;
    }

    const sourceNode = nodeMap.get(edge.from);
    if (!sourceNode) continue;

    upstream.push(sourceNode);
    // Recursively get upstream nodes
    upstream.push(...getUpstreamNodes(edge.from, nodes, edges, visited));
  }

  return upstream;
}

/**
 * Build a complete type map for all nodes in a graph
 */
export function buildTypeMap(
  nodes: GraphNode[],
  edges: GraphEdge[]
): Map<string, NodeTypeInfo> {
  const typeMap = new Map<string, NodeTypeInfo>();

  for (const node of nodes) {
    typeMap.set(node.id, {
      nodeId: node.id,
      inputTypes: inferInputTypes(node),
      outputType: inferOutputType(node),
      signature: getNodeSignature(node.type),
    });
  }

  return typeMap;
}

/**
 * Check if a node produces a specific type
 */
export function nodeProducesType(node: GraphNode, type: DataType): boolean {
  const outputType = getPrimaryOutputType(node);

  // ANY matches everything
  if (outputType === DataType.ANY || type === DataType.ANY) {
    return true;
  }

  return outputType === type;
}

/**
 * Check if a node accepts a specific type
 */
export function nodeAcceptsType(node: GraphNode, type: DataType): boolean {
  const inputType = getPrimaryInputType(node);

  // ANY accepts everything
  if (inputType === DataType.ANY || type === DataType.ANY) {
    return true;
  }

  const compatibility = areTypesCompatible(type, inputType);
  return compatibility.compatible;
}

/**
 * Get suggested nodes that could connect after a given node
 */
export function getSuggestedNextNodes(
  node: GraphNode,
  availableNodeTypes: NodeType[]
): NodeType[] {
  const outputType = getPrimaryOutputType(node);

  return availableNodeTypes.filter((nodeType) => {
    const signature = NODE_SIGNATURES[nodeType];
    if (!signature || signature.inputs.length === 0) {
      return true; // Nodes with no inputs can always be added
    }

    const inputType = signature.inputs[0].type;
    const compatibility = areTypesCompatible(outputType, inputType);
    return compatibility.compatible;
  });
}
