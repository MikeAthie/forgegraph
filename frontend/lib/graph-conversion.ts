import type { Edge, Node } from "@xyflow/react";

import type {
  GraphEdge,
  GraphJson,
  GraphMetadata,
  GraphNode,
  NoteEditorNode,
  NodeConfig,
  NodeOutput,
  NodeType,
  RetryPolicy,
} from "./graph-types";
import { END_NODE_ID, START_NODE_ID, isValidNodeType } from "./graph-types";

const NOTE_NODE_TYPE = "note";

export function graphJsonToReactFlow(graphJson: GraphJson): {
  nodes: Node[];
  edges: Edge[];
} {
  const positions = graphJson.editor_state?.nodePositions ?? {};
  const noteState = graphJson.editor_state?.notes ?? [];

  const triggerNodeIds = new Set<string>();
  const endNodeIds = new Set<string>();

  for (const edge of graphJson.edges ?? []) {
    if (edge.from === START_NODE_ID && typeof edge.to === "string") {
      triggerNodeIds.add(edge.to);
      continue;
    }
    if (edge.to === END_NODE_ID && typeof edge.from === "string") {
      endNodeIds.add(edge.from);
    }
  }

  const nodes: Node[] = graphJson.nodes.map((node, index) => ({
    id: node.id,
    type: node.type,
    position: positions[node.id] ?? { x: 100 + (index % 4) * 250, y: 100 + Math.floor(index / 4) * 150 },
    data: {
      label: node.name,
      nodeType: node.type,
      config: node.config,
      disabled: node.disabled,
      retry_policy: node.retry_policy,
      timeout_ms: node.timeout_ms,
      outputs: node.outputs,
      isTrigger: triggerNodeIds.has(node.id),
      isEnd: endNodeIds.has(node.id),
    },
  }));

  const noteNodes: Node[] = (noteState as NoteEditorNode[]).flatMap((note, index) =>
    typeof note?.id === "string" && note.id.length > 0
      ? [
          {
            id: note.id,
            type: NOTE_NODE_TYPE,
            position: positions[note.id] ?? { x: 450, y: 100 + index * 160 },
            data: {
              label: note.label ?? "Note",
              text: note.text ?? "",
            },
            connectable: false,
          },
        ]
      : [],
  );

  const edges: Edge[] = (graphJson.edges ?? []).flatMap((edge) =>
    edge.from !== START_NODE_ID && edge.to !== END_NODE_ID
      ? [
          {
            id: edge.id,
            source: edge.from,
            target: edge.to,
            label: edge.label,
            data: {
              condition: edge.condition,
            },
          },
        ]
      : [],
  );

  return { nodes: [...nodes, ...noteNodes], edges };
}

export function reactFlowToGraphJson(
  nodes: Node[],
  edges: Edge[],
  metadata: GraphMetadata,
  graphId?: string,
  versionId?: string,
  viewport?: { x: number; y: number; zoom: number },
): GraphJson {
  const executableNodes = nodes.filter((node): node is Node & { type: NodeType } => isValidNodeType(node.type ?? ""));

  const noteNodes = nodes.filter((node) => node.type === NOTE_NODE_TYPE);

  const graphNodes: GraphNode[] = executableNodes.map((node) => {
    const result: GraphNode = {
      id: node.id,
      type: node.type as NodeType,
      name: node.data.label as string,
      config: (node.data.config as NodeConfig) ?? {},
    };
    if (node.data.disabled === true) {
      result.disabled = true;
    }
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

  const executableNodeIds = new Set(executableNodes.map((node) => node.id));
  const graphEdges: GraphEdge[] = edges.flatMap((edge) =>
    executableNodeIds.has(edge.source) && executableNodeIds.has(edge.target)
      ? [
          {
            id: edge.id,
            from: edge.source,
            to: edge.target,
            label: edge.label as string | undefined,
            condition: edge.data?.condition as string | undefined,
          },
        ]
      : [],
  );

  const startEndEdges: GraphEdge[] = [];

  for (const node of executableNodes) {
    const isTrigger = (node.data as any)?.isTrigger === true;
    if (isTrigger) {
      startEndEdges.push({
        id: `start-${node.id}`,
        from: START_NODE_ID,
        to: node.id,
      });
    }

    const isEnd = (node.data as any)?.isEnd === true;
    if (isEnd) {
      startEndEdges.push({
        id: `end-${node.id}`,
        from: node.id,
        to: END_NODE_ID,
      });
    }
  }

  const nodePositions: Record<string, { x: number; y: number }> = {};
  for (const node of nodes) {
    nodePositions[node.id] = node.position;
  }

  const notes: NoteEditorNode[] = noteNodes.map((node) => ({
    id: node.id,
    label: (node.data as any)?.label ? String((node.data as any).label) : undefined,
    text: (node.data as any)?.text ? String((node.data as any).text) : "",
  }));

  return {
    graph_id: graphId,
    version_id: versionId,
    nodes: graphNodes,
    edges: [...startEndEdges, ...graphEdges],
    metadata,
    editor_state: {
      nodePositions,
      notes: notes.length > 0 ? notes : undefined,
      viewport: viewport ?? undefined,
    },
  };
}
