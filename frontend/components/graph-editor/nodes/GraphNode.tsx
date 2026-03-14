import { memo, useState, useMemo } from "react";
import { Handle, Position, type NodeProps, useReactFlow } from "@xyflow/react";
import { X, AlertCircle, AlertTriangle } from "lucide-react";

import { cn } from "@/lib/utils";
import { NODE_TYPES, type NodeType } from "../../../lib/graph-types";
import { useNodeValidation } from "@/contexts/ValidationContext";
import { DataTypeIndicator, NodeTypeBadge } from "../DataTypeIndicator";
import {
  getPrimaryInputType,
  getPrimaryOutputType,
} from "@/lib/type-inference";

const nodeTypeStyles: Record<string, { strip: string; pill: string }> = {
  [NODE_TYPES.AGENT]: {
    strip: "bg-sky-500",
    pill: "bg-sky-500/15 text-sky-800 dark:text-sky-300",
  },
  [NODE_TYPES.PROMPT]: {
    strip: "bg-violet-500",
    pill: "bg-violet-500/15 text-violet-700 dark:text-violet-300",
  },
  [NODE_TYPES.HTTP]: {
    strip: "bg-amber-500",
    pill: "bg-amber-500/15 text-amber-800 dark:text-amber-300",
  },
  [NODE_TYPES.TRANSFORM]: {
    strip: "bg-blue-500",
    pill: "bg-blue-500/15 text-blue-700 dark:text-blue-300",
  },
  [NODE_TYPES.BRANCH]: {
    strip: "bg-rose-500",
    pill: "bg-rose-500/15 text-rose-700 dark:text-rose-300",
  },
  [NODE_TYPES.MERGE]: {
    strip: "bg-emerald-500",
    pill: "bg-emerald-500/15 text-emerald-700 dark:text-emerald-300",
  },
  [NODE_TYPES.OUTPUT]: {
    strip: "bg-indigo-500",
    pill: "bg-indigo-500/15 text-indigo-700 dark:text-indigo-300",
  },
  [NODE_TYPES.HUMAN_GATE]: {
    strip: "bg-orange-500",
    pill: "bg-orange-500/15 text-orange-800 dark:text-orange-300",
  },
  [NODE_TYPES.MEMORY]: {
    strip: "bg-teal-500",
    pill: "bg-teal-500/15 text-teal-800 dark:text-teal-300",
  },
  [NODE_TYPES.OBSERVATION_SAVE]: {
    strip: "bg-teal-700",
    pill: "bg-teal-700/15 text-teal-900 dark:text-teal-200",
  },
  [NODE_TYPES.OBSERVATION_SEARCH]: {
    strip: "bg-sky-700",
    pill: "bg-sky-700/15 text-sky-900 dark:text-sky-200",
  },
  [NODE_TYPES.OBSERVATION_CONTEXT]: {
    strip: "bg-blue-700",
    pill: "bg-blue-700/15 text-blue-900 dark:text-blue-200",
  },
  [NODE_TYPES.OBSERVATION_TIMELINE]: {
    strip: "bg-violet-700",
    pill: "bg-violet-700/15 text-violet-900 dark:text-violet-200",
  },
  [NODE_TYPES.TOOL]: {
    strip: "bg-cyan-500",
    pill: "bg-cyan-500/15 text-cyan-800 dark:text-cyan-300",
  },
  [NODE_TYPES.SUBGRAPH]: {
    strip: "bg-fuchsia-500",
    pill: "bg-fuchsia-500/15 text-fuchsia-800 dark:text-fuchsia-300",
  },
};

const nodeTypeLabels: Record<string, string> = {
  [NODE_TYPES.AGENT]: "Agent",
  [NODE_TYPES.PROMPT]: "Prompt",
  [NODE_TYPES.HTTP]: "HTTP",
  [NODE_TYPES.TRANSFORM]: "Transform",
  [NODE_TYPES.OUTPUT]: "Output",
  [NODE_TYPES.BRANCH]: "Branch",
  [NODE_TYPES.MERGE]: "Merge",
  [NODE_TYPES.HUMAN_GATE]: "Human Gate",
  [NODE_TYPES.MEMORY]: "Memory",
  [NODE_TYPES.OBSERVATION_SAVE]: "Observation Save",
  [NODE_TYPES.OBSERVATION_SEARCH]: "Observation Search",
  [NODE_TYPES.OBSERVATION_CONTEXT]: "Observation Context",
  [NODE_TYPES.OBSERVATION_TIMELINE]: "Observation Timeline",
  [NODE_TYPES.TOOL]: "Tool",
  [NODE_TYPES.SUBGRAPH]: "Subgraph",
};

interface GraphNodeData {
  label: string;
  nodeType: string;
  config?: Record<string, unknown>;
  disabled?: boolean;
  isTrigger?: boolean;
  isEnd?: boolean;
  executionStatus?: string;
  executionAttempt?: number;
  executionDurationMs?: number | null;
  retry_policy?: { max_attempts?: number };
  timeout_ms?: number;
}

function getHandleTestId(
  direction: "source" | "target",
  handleId: string = "default",
): string {
  return `node-handle-${direction}-${handleId}`;
}

function GraphNodeComponent({ id, data, selected, type }: NodeProps) {
  const [isHovered, setIsHovered] = useState(false);
  const { setNodes, setEdges } = useReactFlow();
  const nodeData = data as unknown as GraphNodeData;
  const nodeType = type ?? nodeData.nodeType ?? NODE_TYPES.PROMPT;
  const typeLabel = nodeTypeLabels[nodeType] ?? nodeType;
  const styles = nodeTypeStyles[nodeType] ?? nodeTypeStyles[NODE_TYPES.PROMPT];
  const isDisabled = nodeData.disabled === true;
  const executionStatus = nodeData.executionStatus;

  // Validation state
  const { hasError, hasWarning, errors, warnings } = useNodeValidation(id);
  const validationMessages = [...errors, ...warnings]
    .map((e) => e.message)
    .join(", ");

  const executionDotClass: string | null =
    executionStatus === "succeeded"
      ? "bg-emerald-500"
      : executionStatus === "failed"
        ? "bg-rose-500"
        : executionStatus === "running"
          ? "bg-blue-500"
          : executionStatus === "waiting"
            ? "bg-amber-500 animate-pulse"
            : executionStatus === "skipped"
              ? "bg-muted-foreground/50"
              : executionStatus === "pending"
                ? "bg-muted-foreground/60"
                : executionStatus
                  ? "bg-muted-foreground/60"
                  : null;

  const isSkipped = executionStatus === "skipped";
  const hasAdvancedConfig =
    Boolean(
      nodeData.retry_policy?.max_attempts &&
      nodeData.retry_policy.max_attempts > 1,
    ) || Boolean(nodeData.timeout_ms);

  // Get input/output types for this node
  const { inputType, outputType } = useMemo(() => {
    const graphNode = {
      id,
      type: nodeType as NodeType,
      name: nodeData.label || id,
      config: nodeData.config || {},
    };
    return {
      inputType: getPrimaryInputType(graphNode),
      outputType: getPrimaryOutputType(graphNode),
    };
  }, [id, nodeType, nodeData.label, nodeData.config]);

  const handleDelete = (e: React.MouseEvent) => {
    e.stopPropagation();
    setNodes((nodes) => nodes.filter((n) => n.id !== id));
    setEdges((edges) =>
      edges.filter((e) => e.source !== id && e.target !== id),
    );
  };

  return (
    <div
      data-testid="graph-node"
      data-node-id={id}
      data-node-type={nodeType}
      className={cn(
        "group relative min-w-[200px] rounded-xl border border-border bg-card shadow-sm transition-all",
        isDisabled &&
          "opacity-50 grayscale border-dashed border-muted-foreground/40",
        isSkipped && "opacity-70",
        selected && "ring-2 ring-primary ring-offset-2 ring-offset-background",
        // Validation error/warning styles
        hasError &&
          !selected &&
          "border-destructive/60 shadow-destructive/20 shadow-md",
        hasWarning &&
          !hasError &&
          !selected &&
          "border-amber-500/60 shadow-amber-500/20 shadow-md",
      )}
      onMouseEnter={() => setIsHovered(true)}
      onMouseLeave={() => setIsHovered(false)}
      title={validationMessages || undefined}
    >
      <div
        data-testid="node-accent-strip"
        className={cn(
          "pointer-events-none absolute inset-x-0 top-0 h-1",
          hasError
            ? "bg-destructive"
            : hasWarning
              ? "bg-amber-500"
              : styles.strip,
        )}
      />

      {/* Validation Error Badge */}
      {(hasError || hasWarning) && (
        <div
          className={cn(
            "absolute -top-2 -right-2 w-5 h-5 rounded-full flex items-center justify-center z-30",
            hasError ? "bg-destructive" : "bg-amber-500",
          )}
          title={validationMessages}
        >
          {hasError ? (
            <AlertCircle className="w-3 h-3 text-white" />
          ) : (
            <AlertTriangle className="w-3 h-3 text-white" />
          )}
        </div>
      )}

      {/* Delete button on hover */}
      {(isHovered || selected) && (
        <button
          type="button"
          onClick={handleDelete}
          className="absolute top-2 right-2 w-6 h-6 bg-destructive hover:bg-destructive/90 text-white rounded-full flex items-center justify-center shadow-md transition-colors z-20"
          aria-label="Delete node"
        >
          <X className="w-3 h-3" />
        </button>
      )}

      {/* Node Content */}
      <div className="p-3 pt-4">
        {/* Type Badge */}
        <div className="flex items-center gap-2 mb-2">
          <span
            className={cn(
              "px-2 py-0.5 rounded-full text-xs font-medium capitalize",
              styles.pill,
              isDisabled && "bg-muted text-muted-foreground",
            )}
          >
            {typeLabel}
          </span>
          {nodeData.isTrigger && (
            <span className="px-2 py-0.5 rounded-full text-xs font-medium bg-emerald-500/15 text-emerald-700 dark:text-emerald-300">
              Start
            </span>
          )}
          {nodeData.isEnd && (
            <span className="px-2 py-0.5 rounded-full text-xs font-medium bg-rose-500/15 text-rose-700 dark:text-rose-300">
              End
            </span>
          )}
          {isDisabled && (
            <span className="px-2 py-0.5 rounded-full text-xs font-medium bg-muted text-muted-foreground border border-dashed border-muted-foreground/30">
              disabled
            </span>
          )}
          {executionDotClass && (
            <span
              className={`ml-auto h-2.5 w-2.5 rounded-full ${executionDotClass}`}
              title={`Execution: ${executionStatus}`}
              aria-hidden="true"
            />
          )}
        </div>

        {/* Node Name */}
        <div
          className={cn(
            "text-sm font-semibold truncate text-foreground",
            isDisabled && "line-through",
          )}
        >
          <span data-testid="graph-node-label">
            {nodeData.label || "Unnamed Node"}
          </span>
        </div>

        {/* Config Preview */}
        {nodeData.config && Object.keys(nodeData.config).length > 0 && (
          <div
            data-testid="node-config-preview"
            className="mt-2 text-xs text-muted-foreground truncate"
          >
            {getConfigPreview(nodeType, nodeData.config)}
          </div>
        )}

        {/* Advanced Config Indicator */}
        {hasAdvancedConfig && (
          <div className="mt-2 flex items-center gap-1.5 text-[10px] text-muted-foreground">
            {nodeData.retry_policy?.max_attempts &&
              nodeData.retry_policy.max_attempts > 1 && (
                <span
                  className="px-1.5 py-0.5 rounded border border-border/50 bg-muted/40"
                  title={`Max ${nodeData.retry_policy.max_attempts} attempts`}
                >
                  {nodeData.retry_policy.max_attempts}x retry
                </span>
              )}
            {nodeData.timeout_ms && (
              <span
                className="px-1.5 py-0.5 rounded border border-border/50 bg-muted/40"
                title={`Timeout: ${nodeData.timeout_ms}ms`}
              >
                {nodeData.timeout_ms >= 1000
                  ? `${Math.round(nodeData.timeout_ms / 1000)}s`
                  : `${nodeData.timeout_ms}ms`}{" "}
                timeout
              </span>
            )}
          </div>
        )}

        {/* Data Type Indicators */}
        <div className="mt-2 flex items-center justify-end">
          <NodeTypeBadge inputType={inputType} outputType={outputType} />
        </div>
      </div>

      {/* Input Handles */}
      {nodeType === NODE_TYPES.MERGE ? (
        // Merge node: multiple inputs
        <>
          <Handle
            data-testid={getHandleTestId("target", "input-1")}
            type="target"
            position={Position.Top}
            id="input-1"
            className="!w-3 !h-3 !bg-emerald-500 !border-2 !border-card !z-10"
            style={{ left: "30%" }}
          />
          <Handle
            data-testid={getHandleTestId("target", "input-2")}
            type="target"
            position={Position.Top}
            id="input-2"
            className="!w-3 !h-3 !bg-emerald-500 !border-2 !border-card !z-10"
            style={{ left: "70%" }}
          />
        </>
      ) : (
        <Handle
          data-testid={getHandleTestId("target")}
          type="target"
          position={Position.Top}
          className="!w-3 !h-3 !bg-muted-foreground/60 !border-2 !border-card !z-10"
        />
      )}

      {/* Output Handles */}
      {nodeType === NODE_TYPES.BRANCH ? (
        // Branch node: two outputs (True/False)
        <>
          <div className="absolute -bottom-5 left-[30%] transform -translate-x-1/2 text-[10px] text-emerald-600 dark:text-emerald-300 font-medium">
            True
          </div>
          <Handle
            data-testid={getHandleTestId("source", "true")}
            type="source"
            position={Position.Bottom}
            id="true"
            className="!w-3 !h-3 !bg-emerald-500 !border-2 !border-card !z-10"
            style={{ left: "30%" }}
          />
          <div className="absolute -bottom-5 left-[70%] transform -translate-x-1/2 text-[10px] text-rose-600 dark:text-rose-300 font-medium">
            False
          </div>
          <Handle
            data-testid={getHandleTestId("source", "false")}
            type="source"
            position={Position.Bottom}
            id="false"
            className="!w-3 !h-3 !bg-rose-500 !border-2 !border-card !z-10"
            style={{ left: "70%" }}
          />
        </>
      ) : (
        <Handle
          data-testid={getHandleTestId("source")}
          type="source"
          position={Position.Bottom}
          className="!w-3 !h-3 !bg-muted-foreground/60 !border-2 !border-card !z-10"
        />
      )}
    </div>
  );
}

function getConfigPreview(
  nodeType: string,
  config: Record<string, unknown>,
): string {
  switch (nodeType) {
    case NODE_TYPES.AGENT: {
      const model = (config.model as string) ?? "";
      const tools = Array.isArray(config.tools) ? config.tools.length : 0;
      if (model) {
        return `${model} · ${tools} tool${tools === 1 ? "" : "s"}`.slice(0, 32);
      }
      return tools > 0
        ? `${tools} tool${tools === 1 ? "" : "s"} configured`
        : "Agent loop";
    }
    case NODE_TYPES.PROMPT:
      if (config.prompt_id) {
        return `Prompt: ${config.prompt_id}`;
      }
      return config.prompt_template
        ? `${String(config.prompt_template).slice(0, 30)}...`
        : "No prompt configured";
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
    case NODE_TYPES.BRANCH:
      return config.condition
        ? `If: ${String(config.condition).slice(0, 25)}...`
        : "No condition set";
    case NODE_TYPES.MERGE:
      return `Strategy: ${(config.merge_strategy as string) ?? "namespaced"}`;
    case NODE_TYPES.HUMAN_GATE:
      return config.prompt_message
        ? `${String(config.prompt_message).slice(0, 30)}...`
        : "Requires approval";
    case NODE_TYPES.MEMORY: {
      const action = (config.action as string) ?? "get";
      const key = (config.key as string) ?? "";
      if (key) {
        return `${action.toUpperCase()} ${key}`.slice(0, 32);
      }
      return "Memory action";
    }
    case NODE_TYPES.OBSERVATION_SAVE: {
      const scope = (config.scope as string) ?? "graph";
      const type = (config.type as string) ?? "";
      if (type) {
        return `${scope} save · ${type}`.slice(0, 32);
      }
      return "Save observation";
    }
    case NODE_TYPES.OBSERVATION_SEARCH: {
      const query =
        (config.query as string) ??
        (config.query_path as string) ??
        (config.query_template as string) ??
        "";
      if (query) {
        return `Search · ${String(query).slice(0, 24)}...`;
      }
      return "Search observations";
    }
    case NODE_TYPES.OBSERVATION_CONTEXT: {
      const query =
        (config.query as string) ??
        (config.query_path as string) ??
        (config.query_template as string) ??
        "";
      if (query) {
        return `Context · ${String(query).slice(0, 23)}...`;
      }
      return "Assemble context";
    }
    case NODE_TYPES.OBSERVATION_TIMELINE: {
      const scope = (config.scope as string) ?? "graph";
      const limit = typeof config.limit === "number" ? config.limit : null;
      return limit ? `${scope} timeline · ${limit} items` : `${scope} timeline`;
    }
    case NODE_TYPES.TOOL: {
      const toolName = (config.tool as string) ?? (config.name as string) ?? "";
      const version = (config.version as string) ?? "";
      if (toolName) {
        return version
          ? `${toolName}@${version}`.slice(0, 32)
          : toolName.slice(0, 32);
      }
      return "Tool call";
    }
    case NODE_TYPES.SUBGRAPH: {
      const graphId = (config.graph_id as string) ?? "";
      const graphVersion = config.graph_version as number | undefined;
      if (graphId) {
        return graphVersion
          ? `Graph ${graphId} v${graphVersion}`.slice(0, 32)
          : `Graph ${graphId}`.slice(0, 32);
      }
      return "Subgraph";
    }
    default:
      return "";
  }
}

export const GraphNode = memo(GraphNodeComponent);
