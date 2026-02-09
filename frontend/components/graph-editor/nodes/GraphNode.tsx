import { memo, useState, useMemo } from "react";
import { Handle, Position, type NodeProps, useReactFlow } from "@xyflow/react";
import { X, AlertCircle, AlertTriangle } from "lucide-react";

import { cn } from "@/lib/utils";
import { NODE_TYPES, type NodeType } from "../../../lib/graph-types";
import { useNodeValidation } from "@/contexts/ValidationContext";
import { NodeTypeBadge } from "../DataTypeIndicator";
import { DataType } from "@/lib/data-types";
import { getPrimaryInputType, getPrimaryOutputType } from "@/lib/type-inference";
import { getNodeVisual, type NodeVisualConfig } from "./nodeShapes";

const nodeTypeLabels: Record<string, string> = {
  [NODE_TYPES.PROMPT]: "Prompt",
  [NODE_TYPES.HTTP]: "HTTP",
  [NODE_TYPES.TRANSFORM]: "Transform",
  [NODE_TYPES.OUTPUT]: "Output",
  [NODE_TYPES.BRANCH]: "Conditional",
  [NODE_TYPES.MERGE]: "Merge",
  [NODE_TYPES.HUMAN_GATE]: "Human Gate",
  [NODE_TYPES.MEMORY]: "Memory",
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

function GraphNodeComponent({ id, data, selected, type }: NodeProps) {
  const [isHovered, setIsHovered] = useState(false);
  const { setNodes, setEdges } = useReactFlow();
  const nodeData = data as unknown as GraphNodeData;
  const nodeType = type ?? nodeData.nodeType ?? NODE_TYPES.PROMPT;
  const typeLabel = nodeTypeLabels[nodeType] ?? nodeType;
  const isDisabled = nodeData.disabled === true;
  const executionStatus = nodeData.executionStatus;

  const visual = getNodeVisual(nodeType, nodeData.isTrigger, nodeData.isEnd);

  // Validation state
  const { hasError, hasWarning, errors, warnings } = useNodeValidation(id);
  const validationMessages = [...errors, ...warnings].map((e) => e.message).join(", ");

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
    setEdges((edges) => edges.filter((e) => e.source !== id && e.target !== id));
  };

  if (visual.shape === "pill") {
    return (
      <PillNode
        id={id}
        nodeData={nodeData}
        nodeType={nodeType}
        visual={visual}
        selected={selected}
        isHovered={isHovered}
        setIsHovered={setIsHovered}
        isDisabled={isDisabled}
        isSkipped={isSkipped}
        executionDotClass={executionDotClass}
        executionStatus={executionStatus}
        hasError={hasError}
        hasWarning={hasWarning}
        validationMessages={validationMessages}
        handleDelete={handleDelete}
      />
    );
  }

  if (visual.shape === "diamond") {
    return (
      <DiamondNode
        id={id}
        nodeData={nodeData}
        nodeType={nodeType}
        typeLabel={typeLabel}
        visual={visual}
        selected={selected}
        isHovered={isHovered}
        setIsHovered={setIsHovered}
        isDisabled={isDisabled}
        isSkipped={isSkipped}
        executionDotClass={executionDotClass}
        executionStatus={executionStatus}
        hasError={hasError}
        hasWarning={hasWarning}
        validationMessages={validationMessages}
        handleDelete={handleDelete}
      />
    );
  }

  // Default: rectangle shape
  return (
    <RectangleNode
      id={id}
      nodeData={nodeData}
      nodeType={nodeType}
      typeLabel={typeLabel}
      visual={visual}
      selected={selected}
      isHovered={isHovered}
      setIsHovered={setIsHovered}
      isDisabled={isDisabled}
      isSkipped={isSkipped}
      executionDotClass={executionDotClass}
      executionStatus={executionStatus}
      hasError={hasError}
      hasWarning={hasWarning}
      validationMessages={validationMessages}
      inputType={inputType}
      outputType={outputType}
      handleDelete={handleDelete}
    />
  );
}

/* ============================================================
   Shared types & helpers
   ============================================================ */

interface BaseNodeProps {
  id: string;
  nodeData: GraphNodeData;
  nodeType: string;
  visual: NodeVisualConfig;
  selected: boolean | undefined;
  isHovered: boolean;
  setIsHovered: (v: boolean) => void;
  isDisabled: boolean;
  isSkipped: boolean;
  executionDotClass: string | null;
  executionStatus?: string;
  hasError: boolean;
  hasWarning: boolean;
  validationMessages: string;
  handleDelete: (e: React.MouseEvent) => void;
}

function ValidationBadge({ hasError, hasWarning, validationMessages }: { hasError: boolean; hasWarning: boolean; validationMessages: string }) {
  if (!hasError && !hasWarning) return null;
  return (
    <div
      className={cn(
        "absolute -top-2 -right-2 w-5 h-5 rounded-full flex items-center justify-center z-30",
        hasError ? "bg-destructive" : "bg-amber-500"
      )}
      title={validationMessages}
    >
      {hasError ? (
        <AlertCircle className="w-3 h-3 text-white" />
      ) : (
        <AlertTriangle className="w-3 h-3 text-white" />
      )}
    </div>
  );
}

function DeleteButton({ isVisible, onDelete }: { isVisible: boolean; onDelete: (e: React.MouseEvent) => void }) {
  if (!isVisible) return null;
  return (
    <button
      type="button"
      onClick={onDelete}
      className="absolute -top-2 -right-2 w-5 h-5 bg-destructive hover:bg-destructive/90 text-white rounded-full flex items-center justify-center shadow-md transition-colors z-20"
      aria-label="Delete node"
    >
      <X className="w-3 h-3" />
    </button>
  );
}

function ExecutionDot({ dotClass, status }: { dotClass: string | null; status?: string }) {
  if (!dotClass) return null;
  return (
    <span
      className={cn("h-2.5 w-2.5 rounded-full", dotClass)}
      title={`Execution: ${status}`}
      aria-hidden="true"
    />
  );
}

/* ============================================================
   PILL SHAPE (Start Trigger / End)
   ============================================================ */

function PillNode({
  id,
  nodeData,
  visual,
  selected,
  isHovered,
  setIsHovered,
  isDisabled,
  isSkipped,
  executionDotClass,
  executionStatus,
  hasError,
  hasWarning,
  validationMessages,
  handleDelete,
}: BaseNodeProps) {
  const Icon = visual.icon;
  const isTrigger = nodeData.isTrigger;
  const label = isTrigger ? "Start Trigger" : "Workflow End";
  const sublabel = isTrigger ? "Workflow Start" : "Workflow End";

  return (
    <div
      className={cn(
        "group relative",
        isDisabled && "opacity-50 grayscale",
        isSkipped && "opacity-70",
      )}
      onMouseEnter={() => setIsHovered(true)}
      onMouseLeave={() => setIsHovered(false)}
      title={validationMessages || undefined}
    >
      <div
        className={cn(
          "flex items-center gap-3 rounded-full px-5 py-3 shadow-lg border transition-all",
          isTrigger
            ? "bg-emerald-500/15 border-emerald-500/40"
            : "bg-rose-500/15 border-rose-500/40",
          selected && "ring-2 ring-primary ring-offset-2 ring-offset-background",
          hasError && !selected && "border-destructive/60 shadow-destructive/20 shadow-md",
          hasWarning && !hasError && !selected && "border-amber-500/60 shadow-amber-500/20 shadow-md",
        )}
      >
        <div
          data-testid="node-accent-strip"
          className={cn(
            "w-9 h-9 rounded-full flex items-center justify-center shadow-sm",
            visual.bgClass,
          )}
        >
          <Icon className="w-4 h-4 text-white" />
        </div>
        <div className="flex flex-col">
          <span className="text-sm font-semibold text-foreground">{nodeData.label || label}</span>
          <span className="text-[11px] text-muted-foreground">{sublabel}</span>
        </div>
        <ExecutionDot dotClass={executionDotClass} status={executionStatus} />
      </div>

      <ValidationBadge hasError={hasError} hasWarning={hasWarning} validationMessages={validationMessages} />
      <DeleteButton isVisible={isHovered || !!selected} onDelete={handleDelete} />

      {/* Handles */}
      <Handle
        type="target"
        position={Position.Left}
        className="!w-3 !h-3 !bg-muted-foreground/60 !border-2 !border-background !z-10"
      />
      <Handle
        type="source"
        position={Position.Right}
        className="!w-3 !h-3 !bg-muted-foreground/60 !border-2 !border-background !z-10"
      />
    </div>
  );
}

/* ============================================================
   DIAMOND SHAPE (Branch / Conditional)
   ============================================================ */

function DiamondNode({
  id,
  nodeData,
  nodeType,
  typeLabel,
  visual,
  selected,
  isHovered,
  setIsHovered,
  isDisabled,
  isSkipped,
  executionDotClass,
  executionStatus,
  hasError,
  hasWarning,
  validationMessages,
  handleDelete,
}: BaseNodeProps & { typeLabel: string }) {
  const Icon = visual.icon;

  return (
    <div
      className={cn(
        "group relative",
        isDisabled && "opacity-50 grayscale",
        isSkipped && "opacity-70",
      )}
      onMouseEnter={() => setIsHovered(true)}
      onMouseLeave={() => setIsHovered(false)}
      title={validationMessages || undefined}
      style={{ width: 120, height: 120 }}
    >
      {/* Diamond shape via rotation */}
      <div
        className={cn(
          "absolute inset-[10px] rotate-45 rounded-xl border shadow-lg transition-all",
          "bg-orange-500/15 border-orange-500/40",
          selected && "ring-2 ring-primary ring-offset-2 ring-offset-background",
          hasError && !selected && "border-destructive/60 shadow-destructive/20 shadow-md",
          hasWarning && !hasError && !selected && "border-amber-500/60 shadow-amber-500/20 shadow-md",
        )}
      />

      {/* Content (counter-rotated) */}
      <div className="absolute inset-0 flex flex-col items-center justify-center z-10">
        <div
          data-testid="node-accent-strip"
          className={cn(
            "w-9 h-9 rounded-full flex items-center justify-center shadow-sm mb-1",
            visual.bgClass,
          )}
        >
          <Icon className="w-4 h-4 text-white" />
        </div>
        <span className="text-xs font-semibold text-foreground">{nodeData.label || typeLabel}</span>
        <ExecutionDot dotClass={executionDotClass} status={executionStatus} />
      </div>

      <ValidationBadge hasError={hasError} hasWarning={hasWarning} validationMessages={validationMessages} />
      <DeleteButton isVisible={isHovered || !!selected} onDelete={handleDelete} />

      {/* True/False output labels */}
      <div className="absolute -bottom-6 left-[15%] transform -translate-x-1/2 z-20">
        <span className="px-2 py-0.5 rounded-full text-[10px] font-semibold bg-emerald-500/20 text-emerald-400 border border-emerald-500/40">
          True
        </span>
      </div>
      <div className="absolute -bottom-6 left-[85%] transform -translate-x-1/2 z-20">
        <span className="px-2 py-0.5 rounded-full text-[10px] font-semibold bg-rose-500/20 text-rose-400 border border-rose-500/40">
          False
        </span>
      </div>

      {/* Handles - top for input, bottom-left for True, bottom-right for False */}
      <Handle
        type="target"
        position={Position.Left}
        className="!w-3 !h-3 !bg-orange-500 !border-2 !border-background !z-10"
      />
      <Handle
        type="source"
        position={Position.Bottom}
        id="true"
        className="!w-3 !h-3 !bg-emerald-500 !border-2 !border-background !z-10"
        style={{ left: "15%" }}
      />
      <Handle
        type="source"
        position={Position.Bottom}
        id="false"
        className="!w-3 !h-3 !bg-rose-500 !border-2 !border-background !z-10"
        style={{ left: "85%" }}
      />
      <Handle
        type="source"
        position={Position.Right}
        id="default"
        className="!w-3 !h-3 !bg-muted-foreground/60 !border-2 !border-background !z-10"
        style={{ opacity: 0 }}
      />
    </div>
  );
}

/* ============================================================
   RECTANGLE SHAPE (Default for most node types)
   ============================================================ */

function RectangleNode({
  id,
  nodeData,
  nodeType,
  typeLabel,
  visual,
  selected,
  isHovered,
  setIsHovered,
  isDisabled,
  isSkipped,
  executionDotClass,
  executionStatus,
  hasError,
  hasWarning,
  validationMessages,
  inputType,
  outputType,
  handleDelete,
}: BaseNodeProps & { typeLabel: string; inputType: DataType; outputType: DataType }) {
  const Icon = visual.icon;
  const hasAdvancedConfig = Boolean(nodeData.retry_policy?.max_attempts && nodeData.retry_policy.max_attempts > 1) || Boolean(nodeData.timeout_ms);

  return (
    <div
      className={cn(
        "group relative min-w-[180px] max-w-[240px] rounded-xl border border-border bg-card shadow-sm transition-all",
        isDisabled && "opacity-50 grayscale border-dashed border-muted-foreground/40",
        isSkipped && "opacity-70",
        selected && "ring-2 ring-primary ring-offset-2 ring-offset-background",
        hasError && !selected && "border-destructive/60 shadow-destructive/20 shadow-md",
        hasWarning && !hasError && !selected && "border-amber-500/60 shadow-amber-500/20 shadow-md",
      )}
      onMouseEnter={() => setIsHovered(true)}
      onMouseLeave={() => setIsHovered(false)}
      title={validationMessages || undefined}
    >
      <ValidationBadge hasError={hasError} hasWarning={hasWarning} validationMessages={validationMessages} />
      <DeleteButton isVisible={isHovered || !!selected} onDelete={handleDelete} />

      {/* Node Content */}
      <div className="flex items-start gap-3 p-3">
        {/* Colored Icon Circle */}
        <div
          data-testid="node-accent-strip"
          className={cn(
            "w-10 h-10 rounded-lg flex items-center justify-center shadow-sm shrink-0",
            visual.bgClass,
          )}
        >
          <Icon className="w-5 h-5 text-white" />
        </div>

        {/* Text content */}
        <div className="flex-1 min-w-0">
          <div className="flex items-center gap-2">
            <span className={cn("text-sm font-semibold truncate text-foreground", isDisabled && "line-through")}>
              {nodeData.label || "Unnamed Node"}
            </span>
            <ExecutionDot dotClass={executionDotClass} status={executionStatus} />
          </div>
          <span className="text-[11px] text-muted-foreground capitalize">{typeLabel}</span>

          {/* Config Preview */}
          {nodeData.config && Object.keys(nodeData.config).length > 0 && (
            <div data-testid="node-config-preview" className="mt-1 text-[11px] text-muted-foreground/80 truncate">
              {getConfigPreview(nodeType, nodeData.config)}
            </div>
          )}

          {/* Advanced Config Indicator */}
          {hasAdvancedConfig && (
            <div className="mt-1.5 flex items-center gap-1 text-[10px] text-muted-foreground">
              {nodeData.retry_policy?.max_attempts && nodeData.retry_policy.max_attempts > 1 && (
                <span className="px-1.5 py-0.5 rounded border border-border/50 bg-muted/40" title={`Max ${nodeData.retry_policy.max_attempts} attempts`}>
                  {nodeData.retry_policy.max_attempts}x retry
                </span>
              )}
              {nodeData.timeout_ms && (
                <span className="px-1.5 py-0.5 rounded border border-border/50 bg-muted/40" title={`Timeout: ${nodeData.timeout_ms}ms`}>
                  {nodeData.timeout_ms >= 1000 ? `${Math.round(nodeData.timeout_ms / 1000)}s` : `${nodeData.timeout_ms}ms`} timeout
                </span>
              )}
            </div>
          )}

          {/* Data Type Indicators */}
          <div className="mt-1.5 flex items-center justify-end">
            <NodeTypeBadge inputType={inputType} outputType={outputType} />
          </div>
        </div>
      </div>

      {/* Input Handles */}
      {nodeType === NODE_TYPES.MERGE ? (
        <>
          <Handle
            type="target"
            position={Position.Left}
            id="input-1"
            className="!w-3 !h-3 !bg-emerald-500 !border-2 !border-card !z-10"
            style={{ top: "35%" }}
          />
          <Handle
            type="target"
            position={Position.Left}
            id="input-2"
            className="!w-3 !h-3 !bg-emerald-500 !border-2 !border-card !z-10"
            style={{ top: "65%" }}
          />
        </>
      ) : (
        <Handle
          type="target"
          position={Position.Left}
          className="!w-3 !h-3 !bg-muted-foreground/60 !border-2 !border-card !z-10"
        />
      )}

      {/* Output Handle */}
      <Handle
        type="source"
        position={Position.Right}
        className="!w-3 !h-3 !bg-muted-foreground/60 !border-2 !border-card !z-10"
      />
    </div>
  );
}

/* ============================================================
   Config Preview Helper (unchanged)
   ============================================================ */

function getConfigPreview(
  nodeType: string,
  config: Record<string, unknown>
): string {
  switch (nodeType) {
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
    case NODE_TYPES.TOOL: {
      const toolName = (config.tool as string) ?? (config.name as string) ?? "";
      const version = (config.version as string) ?? "";
      if (toolName) {
        return version ? `${toolName}@${version}`.slice(0, 32) : toolName.slice(0, 32);
      }
      return "Tool call";
    }
    case NODE_TYPES.SUBGRAPH: {
      const graphId = (config.graph_id as string) ?? "";
      const graphVersion = config.graph_version as number | undefined;
      if (graphId) {
        return graphVersion ? `Graph ${graphId} v${graphVersion}`.slice(0, 32) : `Graph ${graphId}`.slice(0, 32);
      }
      return "Subgraph";
    }
    default:
      return "";
  }
}

export const GraphNode = memo(GraphNodeComponent);
