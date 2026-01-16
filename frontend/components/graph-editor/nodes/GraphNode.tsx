import { memo } from "react";
import { Handle, Position, type NodeProps } from "@xyflow/react";
import { NODE_TYPES } from "../../../lib/graph-types";

const nodeTypeColors: Record<string, { bg: string; border: string; badge: string }> = {
  [NODE_TYPES.PROMPT]: {
    bg: "bg-purple-50",
    border: "border-purple-300",
    badge: "bg-purple-500",
  },
  [NODE_TYPES.HTTP]: {
    bg: "bg-blue-50",
    border: "border-blue-300",
    badge: "bg-blue-500",
  },
  [NODE_TYPES.TRANSFORM]: {
    bg: "bg-green-50",
    border: "border-green-300",
    badge: "bg-green-500",
  },
  [NODE_TYPES.OUTPUT]: {
    bg: "bg-orange-50",
    border: "border-orange-300",
    badge: "bg-orange-500",
  },
  [NODE_TYPES.BRANCH]: {
    bg: "bg-yellow-50",
    border: "border-yellow-300",
    badge: "bg-yellow-500",
  },
  [NODE_TYPES.MERGE]: {
    bg: "bg-teal-50",
    border: "border-teal-300",
    badge: "bg-teal-500",
  },
  [NODE_TYPES.HUMAN_GATE]: {
    bg: "bg-pink-50",
    border: "border-pink-300",
    badge: "bg-pink-500",
  },
};

const nodeTypeLabels: Record<string, string> = {
  [NODE_TYPES.PROMPT]: "Prompt",
  [NODE_TYPES.HTTP]: "HTTP",
  [NODE_TYPES.TRANSFORM]: "Transform",
  [NODE_TYPES.OUTPUT]: "Output",
  [NODE_TYPES.BRANCH]: "Branch",
  [NODE_TYPES.MERGE]: "Merge",
  [NODE_TYPES.HUMAN_GATE]: "Human Gate",
};

interface GraphNodeData {
  label: string;
  nodeType: string;
  config?: Record<string, unknown>;
}

function GraphNodeComponent({ data, selected, type }: NodeProps) {
  const nodeData = data as unknown as GraphNodeData;
  const nodeType = type ?? nodeData.nodeType ?? NODE_TYPES.PROMPT;
  const colors = nodeTypeColors[nodeType] ?? nodeTypeColors[NODE_TYPES.PROMPT];
  const typeLabel = nodeTypeLabels[nodeType] ?? nodeType;

  return (
    <div
      className={`
        min-w-[180px] rounded-lg border-2 shadow-sm transition-all
        ${colors.bg} ${colors.border}
        ${selected ? "ring-2 ring-primary ring-offset-2" : ""}
      `}
    >
      {/* Input Handle */}
      <Handle
        type="target"
        position={Position.Top}
        className="!w-3 !h-3 !bg-gray-400 !border-2 !border-white"
      />

      {/* Node Content */}
      <div className="p-3">
        {/* Type Badge */}
        <div className="flex items-center gap-2 mb-2">
          <span
            className={`
              px-2 py-0.5 rounded text-xs font-medium text-white
              ${colors.badge}
            `}
          >
            {typeLabel}
          </span>
        </div>

        {/* Node Name */}
        <div className="text-sm font-medium text-gray-900 truncate">
          {nodeData.label || "Unnamed Node"}
        </div>

        {/* Config Preview */}
        {nodeData.config && Object.keys(nodeData.config).length > 0 && (
          <div className="mt-2 text-xs text-gray-500 truncate">
            {getConfigPreview(nodeType, nodeData.config)}
          </div>
        )}
      </div>

      {/* Output Handle */}
      <Handle
        type="source"
        position={Position.Bottom}
        className="!w-3 !h-3 !bg-gray-400 !border-2 !border-white"
      />
    </div>
  );
}

function getConfigPreview(
  nodeType: string,
  config: Record<string, unknown>
): string {
  switch (nodeType) {
    case NODE_TYPES.PROMPT:
      return config.prompt_id ? `Prompt: ${config.prompt_id}` : "No prompt selected";
    case NODE_TYPES.HTTP:
      return config.url
        ? `${config.method ?? "GET"} ${String(config.url).slice(0, 30)}...`
        : "No URL configured";
    case NODE_TYPES.TRANSFORM:
      return config.expression
        ? `${String(config.expression).slice(0, 30)}...`
        : "No expression";
    case NODE_TYPES.OUTPUT:
      return "Final output";
    default:
      return "";
  }
}

export const GraphNode = memo(GraphNodeComponent);
