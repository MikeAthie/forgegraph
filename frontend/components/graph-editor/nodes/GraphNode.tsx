import { memo, useState } from "react";
import { Handle, Position, type NodeProps, useReactFlow } from "@xyflow/react";
import { X } from "lucide-react";
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
  disabled?: boolean;
}

function GraphNodeComponent({ id, data, selected, type }: NodeProps) {
  const [isHovered, setIsHovered] = useState(false);
  const { setNodes, setEdges } = useReactFlow();
  const nodeData = data as unknown as GraphNodeData;
  const nodeType = type ?? nodeData.nodeType ?? NODE_TYPES.PROMPT;
  const colors = nodeTypeColors[nodeType] ?? nodeTypeColors[NODE_TYPES.PROMPT];
  const typeLabel = nodeTypeLabels[nodeType] ?? nodeType;
  const isDisabled = nodeData.disabled === true;

  const handleDelete = (e: React.MouseEvent) => {
    e.stopPropagation();
    setNodes((nodes) => nodes.filter((n) => n.id !== id));
    setEdges((edges) => edges.filter((e) => e.source !== id && e.target !== id));
  };

  return (
    <div
      className={`
        relative min-w-[180px] rounded-lg border-2 shadow-sm transition-all
        ${isDisabled ? "bg-gray-100 border-gray-300 opacity-60" : `${colors.bg} ${colors.border}`}
        ${selected ? "ring-2 ring-primary ring-offset-2" : ""}
      `}
      onMouseEnter={() => setIsHovered(true)}
      onMouseLeave={() => setIsHovered(false)}
    >
      {/* Delete button on hover */}
      {(isHovered || selected) && (
        <button
          type="button"
          onClick={handleDelete}
          className="absolute -top-2 -right-2 w-5 h-5 bg-red-500 hover:bg-red-600 text-white rounded-full flex items-center justify-center shadow-md transition-colors z-20"
          aria-label="Delete node"
        >
          <X className="w-3 h-3" />
        </button>
      )}

      {/* Node Content */}
      <div className="p-3">
        {/* Type Badge */}
        <div className="flex items-center gap-2 mb-2">
          <span
            className={`
              px-2 py-0.5 rounded text-xs font-medium text-white
              ${isDisabled ? "bg-gray-400" : colors.badge}
            `}
          >
            {typeLabel}
          </span>
          {isDisabled && (
            <span className="text-xs text-gray-500 italic">disabled</span>
          )}
        </div>

        {/* Node Name */}
        <div className={`text-sm font-medium truncate ${isDisabled ? "text-gray-500 line-through" : "text-gray-900"}`}>
          {nodeData.label || "Unnamed Node"}
        </div>

        {/* Config Preview */}
        {nodeData.config && Object.keys(nodeData.config).length > 0 && (
          <div className="mt-2 text-xs text-gray-500 truncate">
            {getConfigPreview(nodeType, nodeData.config)}
          </div>
        )}
      </div>

      {/* Input Handles */}
      {nodeType === NODE_TYPES.MERGE ? (
        // Merge node: multiple inputs
        <>
          <Handle
            type="target"
            position={Position.Top}
            id="input-1"
            className="!w-3 !h-3 !bg-teal-500 !border-2 !border-white !z-10"
            style={{ left: "30%" }}
          />
          <Handle
            type="target"
            position={Position.Top}
            id="input-2"
            className="!w-3 !h-3 !bg-teal-500 !border-2 !border-white !z-10"
            style={{ left: "70%" }}
          />
        </>
      ) : (
        <Handle
          type="target"
          position={Position.Top}
          className="!w-3 !h-3 !bg-gray-400 !border-2 !border-white !z-10"
        />
      )}

      {/* Output Handles */}
      {nodeType === NODE_TYPES.BRANCH ? (
        // Branch node: two outputs (True/False)
        <>
          <div className="absolute -bottom-5 left-[30%] transform -translate-x-1/2 text-[10px] text-green-600 font-medium">
            True
          </div>
          <Handle
            type="source"
            position={Position.Bottom}
            id="true"
            className="!w-3 !h-3 !bg-green-500 !border-2 !border-white !z-10"
            style={{ left: "30%" }}
          />
          <div className="absolute -bottom-5 left-[70%] transform -translate-x-1/2 text-[10px] text-red-600 font-medium">
            False
          </div>
          <Handle
            type="source"
            position={Position.Bottom}
            id="false"
            className="!w-3 !h-3 !bg-red-500 !border-2 !border-white !z-10"
            style={{ left: "70%" }}
          />
        </>
      ) : (
        <Handle
          type="source"
          position={Position.Bottom}
          className="!w-3 !h-3 !bg-gray-400 !border-2 !border-white !z-10"
        />
      )}
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
