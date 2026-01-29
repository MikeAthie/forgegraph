"use client";

import { useMemo } from "react";
import type { Node, Edge } from "@xyflow/react";
import { DataType } from "@/lib/data-types";
import { NODE_TYPES, type NodeType } from "@/lib/graph-types";
import { getPrimaryOutputType, getPrimaryInputType } from "@/lib/type-inference";
import type { TypedEdgeData } from "@/components/graph-editor/TypedEdge";

/**
 * Convert React Flow node data to GraphNode format for type inference
 */
function toGraphNode(node: Node) {
  return {
    id: node.id,
    type: (node.type || NODE_TYPES.PROMPT) as NodeType,
    name: (node.data?.label as string) || node.id,
    config: (node.data?.config as Record<string, unknown>) || {},
  };
}

/**
 * Hook that enriches edges with source/target type information
 * for the TypedEdge component to display type indicators
 */
export function useEdgeTypes(
  nodes: Node[],
  edges: Edge[]
): Edge<TypedEdgeData>[] {
  return useMemo(() => {
    // Build a map of node IDs to their output types
    const nodeOutputTypes = new Map<string, DataType>();
    const nodeInputTypes = new Map<string, DataType>();

    for (const node of nodes) {
      const graphNode = toGraphNode(node);
      nodeOutputTypes.set(node.id, getPrimaryOutputType(graphNode));
      nodeInputTypes.set(node.id, getPrimaryInputType(graphNode));
    }

    // Enrich edges with type information
    return edges.map((edge) => {
      const sourceType = nodeOutputTypes.get(edge.source) ?? DataType.ANY;
      const targetType = nodeInputTypes.get(edge.target) ?? DataType.ANY;

      return {
        ...edge,
        type: "typed", // Use our custom edge type
        data: {
          ...edge.data,
          sourceType,
          targetType,
        } as TypedEdgeData,
      };
    });
  }, [nodes, edges]);
}

/**
 * Get type information for a specific edge
 */
export function getEdgeTypeInfo(
  edge: Edge,
  nodes: Node[]
): { sourceType: DataType; targetType: DataType } {
  const sourceNode = nodes.find((n) => n.id === edge.source);
  const targetNode = nodes.find((n) => n.id === edge.target);

  let sourceType = DataType.ANY;
  let targetType = DataType.ANY;

  if (sourceNode) {
    const graphNode = toGraphNode(sourceNode);
    sourceType = getPrimaryOutputType(graphNode);
  }

  if (targetNode) {
    const graphNode = toGraphNode(targetNode);
    targetType = getPrimaryInputType(graphNode);
  }

  return { sourceType, targetType };
}

export default useEdgeTypes;
