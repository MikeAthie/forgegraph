import type { Connection, Edge } from "@xyflow/react";

export const GRAPH_EDITOR_SNAP_GRID: [number, number] = [15, 15];

export type InvalidConnectionReason = "missing_endpoint" | "self_connection" | "duplicate_connection";

export type ConnectionValidationResult = { valid: true } | { valid: false; reason: InvalidConnectionReason };

export function validateGraphConnection(
  connection: Connection,
  edges: Pick<Edge, "source" | "target">[],
): ConnectionValidationResult {
  if (!connection.source || !connection.target) {
    return { valid: false, reason: "missing_endpoint" };
  }

  if (connection.source === connection.target) {
    return { valid: false, reason: "self_connection" };
  }

  const isDuplicate = edges.some((edge) => edge.source === connection.source && edge.target === connection.target);
  if (isDuplicate) {
    return { valid: false, reason: "duplicate_connection" };
  }

  return { valid: true };
}

export function getConnectionFeedback(reason: InvalidConnectionReason): {
  title: string;
  description: string;
} {
  switch (reason) {
    case "missing_endpoint":
      return {
        title: "Connection not created",
        description: "Pick both a source and target handle to create an edge.",
      };
    case "self_connection":
      return {
        title: "Connection blocked",
        description: "A node cannot connect to itself.",
      };
    case "duplicate_connection":
      return {
        title: "Connection already exists",
        description: "Use a different target or remove the existing edge first.",
      };
    default:
      return {
        title: "Connection not created",
        description: "This connection is not valid for the current graph.",
      };
  }
}

export function snapPositionToGrid(
  position: { x: number; y: number },
  grid: [number, number] = GRAPH_EDITOR_SNAP_GRID,
): { x: number; y: number } {
  const [gridX, gridY] = grid;
  const safeGridX = gridX > 0 ? gridX : 1;
  const safeGridY = gridY > 0 ? gridY : 1;

  return {
    x: Math.round(position.x / safeGridX) * safeGridX,
    y: Math.round(position.y / safeGridY) * safeGridY,
  };
}

function getUndirectedPairKey(source: string, target: string): string {
  return source <= target ? `${source}::${target}` : `${target}::${source}`;
}

export function buildEdgeRouteLanes(edges: Pick<Edge, "id" | "source" | "target">[]): Map<string, number> {
  const groupedByPair = new Map<string, Pick<Edge, "id" | "source" | "target">[]>();

  for (const edge of edges) {
    const key = getUndirectedPairKey(edge.source, edge.target);
    const group = groupedByPair.get(key);
    if (group) {
      group.push(edge);
    } else {
      groupedByPair.set(key, [edge]);
    }
  }

  const lanesByEdgeId = new Map<string, number>();

  for (const group of groupedByPair.values()) {
    const sorted = group.toSorted((a, b) => {
      const aKey = `${a.source}->${a.target}:${a.id}`;
      const bKey = `${b.source}->${b.target}:${b.id}`;
      return aKey.localeCompare(bKey);
    });

    const middle = (sorted.length - 1) / 2;
    sorted.forEach((edge, index) => {
      lanesByEdgeId.set(edge.id, index - middle);
    });
  }

  return lanesByEdgeId;
}
