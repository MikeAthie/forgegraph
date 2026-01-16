import type { Edge, Node } from "@xyflow/react";

import type {
  GraphEdge,
  GraphJson,
  GraphMetadata,
  GraphNode,
  NodeConfig,
  NodeOutput,
  NodeType,
  RetryPolicy,
} from "./graph-types";

export function graphJsonToReactFlow(graphJson: GraphJson): {
  nodes: Node[];
  edges: Edge[];
} {
  const positions = graphJson.editor_state?.nodePositions ?? {};

  const nodes: Node[] = graphJson.nodes.map((node, index) => ({
    id: node.id,
    type: node.type,
    position: positions[node.id] ?? { x: 100 + (index % 4) * 250, y: 100 + Math.floor(index / 4) * 150 },
    data: {
      label: node.name,
      nodeType: node.type,
      config: node.config,
      retry_policy: node.retry_policy,
      timeout_ms: node.timeout_ms,
      outputs: node.outputs,
    },
  }));

  const edges: Edge[] = graphJson.edges.map((edge) => ({
    id: edge.id,
    source: edge.from,
    target: edge.to,
    label: edge.label,
    data: {
      condition: edge.condition,
    },
  }));

  return { nodes, edges };
}

export function reactFlowToGraphJson(
  nodes: Node[],
  edges: Edge[],
  metadata: GraphMetadata,
  graphId?: string,
  versionId?: string
): GraphJson {
  const graphNodes: GraphNode[] = nodes.map((node) => {
    const result: GraphNode = {
      id: node.id,
      type: node.type as NodeType,
      name: node.data.label as string,
      config: (node.data.config as NodeConfig) ?? {},
    };
    if (node.data.retry_policy) {
      result.retry_policy = node.data.retry_policy as RetryPolicy;
    }
    if (node.data.timeout_ms) {
      result.timeout_ms = node.data.timeout_ms as number;
    }
    if (node.data.outputs) {
      result.outputs = node.data.outputs as NodeOutput[];
    }
    return result;
  });

  const graphEdges: GraphEdge[] = edges.map((edge) => ({
    id: edge.id,
    from: edge.source,
    to: edge.target,
    label: edge.label as string | undefined,
    condition: edge.data?.condition as string | undefined,
  }));

  const nodePositions: Record<string, { x: number; y: number }> = {};
  for (const node of nodes) {
    nodePositions[node.id] = node.position;
  }

  return {
    graph_id: graphId,
    version_id: versionId,
    nodes: graphNodes,
    edges: graphEdges,
    metadata,
    editor_state: {
      nodePositions,
    },
  };
}

