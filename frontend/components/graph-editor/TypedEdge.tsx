"use client";

import { memo, useMemo, useState } from "react";
import { EdgeProps, getSmoothStepPath, EdgeLabelRenderer, BaseEdge } from "@xyflow/react";
import { cn } from "@/lib/utils";
import { DataType, getDataTypeInfo, areTypesCompatible } from "@/lib/data-types";
import { AlertTriangle, Plus } from "lucide-react";

export interface TypedEdgeData {
  condition?: string;
  sourceType?: DataType;
  targetType?: DataType;
  routeLane?: number;
  label?: string;
  onInsertNode?: (edgeId: string, position: { x: number; y: number }) => void;
  [key: string]: unknown;
}

/**
 * Custom edge component that displays data type information,
 * highlights type mismatches, and shows a "+" button to insert nodes.
 */
function TypedEdgeComponent({
  id,
  sourceX,
  sourceY,
  targetX,
  targetY,
  sourcePosition,
  targetPosition,
  data,
  style,
  markerEnd,
  selected,
  label,
}: EdgeProps) {
  const [isHovered, setIsHovered] = useState(false);
  const edgeData = data as TypedEdgeData | undefined;
  const sourceType = edgeData?.sourceType ?? DataType.ANY;
  const targetType = edgeData?.targetType ?? DataType.ANY;
  const routeLane = Number(edgeData?.routeLane ?? 0);

  // Check type compatibility
  const compatibility = useMemo(() => areTypesCompatible(sourceType, targetType), [sourceType, targetType]);

  const isTypeMismatch = !compatibility.compatible;

  const laneShift = routeLane * 12;
  const mostlyVertical = Math.abs(sourceY - targetY) > Math.abs(sourceX - targetX);
  const adjustedSourceX = mostlyVertical ? sourceX + laneShift : sourceX;
  const adjustedTargetX = mostlyVertical ? targetX + laneShift : targetX;
  const adjustedSourceY = mostlyVertical ? sourceY : sourceY + laneShift;
  const adjustedTargetY = mostlyVertical ? targetY : targetY + laneShift;

  // Calculate edge path
  const [edgePath, labelX, labelY] = getSmoothStepPath({
    sourceX: adjustedSourceX,
    sourceY: adjustedSourceY,
    sourcePosition,
    targetX: adjustedTargetX,
    targetY: adjustedTargetY,
    targetPosition,
    borderRadius: 8,
    offset: 24 + Math.abs(routeLane) * 8,
  });

  // Determine edge color based on type and compatibility
  const edgeColor = useMemo(() => {
    if (isTypeMismatch) {
      return "var(--amber-500, #f59e0b)";
    }
    if (selected) {
      return "var(--primary, #3b82f6)";
    }
    // Use type color for the edge
    const colorMap: Record<DataType, string> = {
      [DataType.TEXT]: "rgb(37 99 235)", // blue-600
      [DataType.JSON]: "rgb(16 185 129)", // emerald-500
      [DataType.ARRAY]: "rgb(139 92 246)", // violet-500
      [DataType.NUMBER]: "rgb(245 158 11)", // amber-500
      [DataType.BOOLEAN]: "rgb(244 63 94)", // rose-500
      [DataType.IMAGE]: "rgb(236 72 153)", // pink-500
      [DataType.FILE]: "rgb(100 116 139)", // zinc-500
      [DataType.ANY]: "rgb(156 163 175)", // neutral-400
      [DataType.VOID]: "rgb(156 163 175)", // neutral-400
    };
    return colorMap[sourceType] ?? "var(--muted-foreground)";
  }, [isTypeMismatch, selected, sourceType]);

  const edgeStyle = {
    ...style,
    stroke: edgeColor,
    strokeWidth: selected ? 3 : 2,
    strokeDasharray: isTypeMismatch ? "5 5" : undefined,
  };

  // Display label (condition or custom label)
  const displayLabel = label || edgeData?.condition;

  // Build tooltip for type mismatch
  const mismatchTooltip = isTypeMismatch
    ? `Type Mismatch: ${compatibility.reason}${compatibility.suggestion ? `. ${compatibility.suggestion}` : ""}`
    : undefined;

  // Determine if this is a branch label (true/false)
  const isTrueLabel = typeof displayLabel === "string" && displayLabel.toLowerCase() === "true";
  const isFalseLabel = typeof displayLabel === "string" && displayLabel.toLowerCase() === "false";
  const isBranchLabel = isTrueLabel || isFalseLabel;

  const handleInsertClick = (e: React.MouseEvent) => {
    e.stopPropagation();
    edgeData?.onInsertNode?.(id, { x: labelX, y: labelY });
  };

  return (
    <>
      {/* Invisible wider path for easier hover detection */}
      <path
        d={edgePath}
        fill="none"
        stroke="transparent"
        strokeWidth={20}
        onMouseEnter={() => setIsHovered(true)}
        onMouseLeave={() => setIsHovered(false)}
      />

      <BaseEdge id={id} path={edgePath} style={edgeStyle} markerEnd={markerEnd} />

      <EdgeLabelRenderer>
        <div
          style={{
            position: "absolute",
            transform: `translate(-50%, -50%) translate(${labelX}px,${labelY}px)`,
            pointerEvents: "all",
          }}
          className="nodrag nopan"
          onMouseEnter={() => setIsHovered(true)}
          onMouseLeave={() => setIsHovered(false)}
        >
          {/* Type mismatch warning */}
          {isTypeMismatch && (
            <div
              className={cn(
                "flex items-center justify-center cursor-help",
                "size-5 rounded-full",
                "bg-amber-500/20 border border-amber-500/50",
                "text-amber-600 dark:text-amber-400",
              )}
              title={mismatchTooltip}
            >
              <AlertTriangle className="size-3" />
            </div>
          )}

          {/* Branch labels as colored pills */}
          {isBranchLabel && !isTypeMismatch && (
            <div
              className={cn(
                "px-2.5 py-0.5 rounded-full text-[11px] font-semibold border shadow-sm",
                isTrueLabel
                  ? "bg-emerald-500/20 text-emerald-400 border-emerald-500/40"
                  : "bg-rose-500/20 text-rose-400 border-rose-500/40",
              )}
            >
              {displayLabel}
            </div>
          )}

          {/* Regular edge label */}
          {displayLabel && !isBranchLabel && !isTypeMismatch && (
            <div
              className={cn(
                "px-2 py-0.5 rounded text-xs font-medium",
                "bg-background/90 border shadow-sm",
                selected ? "border-primary" : "border-border",
              )}
            >
              {displayLabel}
            </div>
          )}

          {/* "+" insert button on hover */}
          {!displayLabel && !isTypeMismatch && (isHovered || selected) && edgeData?.onInsertNode && (
            <button
              type="button"
              onClick={handleInsertClick}
              className={cn(
                "flex size-11 items-center justify-center rounded-full md:size-6",
                "bg-primary text-white shadow-lg",
                "hover:bg-primary/90 hover:scale-110",
                "transition-[color,background-color,box-shadow,transform] duration-150 motion-reduce:transition-none motion-reduce:transform-none",
              )}
              aria-label="Insert node"
              title="Insert node here"
            >
              <Plus className="size-3.5" />
            </button>
          )}
        </div>
      </EdgeLabelRenderer>
    </>
  );
}

export const TypedEdge = memo(TypedEdgeComponent);
