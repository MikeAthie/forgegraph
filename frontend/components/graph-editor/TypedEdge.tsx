"use client";

import { memo, useMemo } from "react";
import {
  EdgeProps,
  getSmoothStepPath,
  EdgeLabelRenderer,
  BaseEdge,
} from "@xyflow/react";
import { cn } from "@/lib/utils";
import { DataType, getDataTypeInfo, areTypesCompatible } from "@/lib/data-types";
import { AlertTriangle } from "lucide-react";

export interface TypedEdgeData {
  condition?: string;
  sourceType?: DataType;
  targetType?: DataType;
  routeLane?: number;
  label?: string;
  [key: string]: unknown;
}

/**
 * Custom edge component that displays data type information
 * and highlights type mismatches
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
  const edgeData = data as TypedEdgeData | undefined;
  const sourceType = edgeData?.sourceType ?? DataType.ANY;
  const targetType = edgeData?.targetType ?? DataType.ANY;
  const routeLane = Number(edgeData?.routeLane ?? 0);

  // Check type compatibility
  const compatibility = useMemo(
    () => areTypesCompatible(sourceType, targetType),
    [sourceType, targetType]
  );

  const isTypeMismatch = !compatibility.compatible;
  const sourceTypeInfo = getDataTypeInfo(sourceType);

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
      [DataType.FILE]: "rgb(100 116 139)", // slate-500
      [DataType.ANY]: "rgb(156 163 175)", // gray-400
      [DataType.VOID]: "rgb(156 163 175)", // gray-400
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

  return (
    <>
      <BaseEdge
        id={id}
        path={edgePath}
        style={edgeStyle}
        markerEnd={markerEnd}
      />

      <EdgeLabelRenderer>
        <div
          style={{
            position: "absolute",
            transform: `translate(-50%, -50%) translate(${labelX}px,${labelY}px)`,
            pointerEvents: "all",
          }}
          className="nodrag nopan"
        >
          {/* Type mismatch warning */}
          {isTypeMismatch && (
            <div
              className={cn(
                "flex items-center justify-center cursor-help",
                "w-5 h-5 rounded-full",
                "bg-amber-500/20 border border-amber-500/50",
                "text-amber-600 dark:text-amber-400"
              )}
              title={mismatchTooltip}
            >
              <AlertTriangle className="h-3 w-3" />
            </div>
          )}

          {/* Edge label (condition or custom) */}
          {displayLabel && !isTypeMismatch && (
            <div
              className={cn(
                "px-2 py-0.5 rounded text-xs font-medium",
                "bg-background/90 border shadow-sm",
                selected
                  ? "border-primary"
                  : "border-border"
              )}
            >
              {displayLabel}
            </div>
          )}
        </div>
      </EdgeLabelRenderer>
    </>
  );
}

export const TypedEdge = memo(TypedEdgeComponent);

export default TypedEdge;
