"use client";

import { useMemo } from "react";
import { Type, Braces, List, Hash, ToggleLeft, Image, File, Asterisk, Circle, AlertCircle } from "lucide-react";
import { cn } from "@/lib/utils";
import { DataType, DATA_TYPE_INFO, getDataTypeInfo } from "@/lib/data-types";

/**
 * Icon mapping for data types
 */
const TYPE_ICONS: Record<DataType, React.ComponentType<{ className?: string }>> = {
  [DataType.TEXT]: Type,
  [DataType.JSON]: Braces,
  [DataType.ARRAY]: List,
  [DataType.NUMBER]: Hash,
  [DataType.BOOLEAN]: ToggleLeft,
  [DataType.IMAGE]: Image,
  [DataType.FILE]: File,
  [DataType.ANY]: Asterisk,
  [DataType.VOID]: Circle,
};

interface DataTypeIndicatorProps {
  type: DataType;
  size?: "sm" | "md" | "lg";
  showLabel?: boolean;
  isInferred?: boolean;
  className?: string;
}

/**
 * Visual indicator for a data type
 */
export function DataTypeIndicator({
  type,
  size = "sm",
  showLabel = false,
  isInferred = false,
  className,
}: DataTypeIndicatorProps) {
  const typeInfo = getDataTypeInfo(type);
  const IconComponent = TYPE_ICONS[type] || Asterisk;

  const sizeClasses = {
    sm: "size-4 text-[10px]",
    md: "size-5 text-xs",
    lg: "size-6 text-sm",
  };

  const iconSizeClasses = {
    sm: "size-2.5",
    md: "size-3",
    lg: "size-4",
  };

  const tooltipText = `${typeInfo.label}: ${typeInfo.description}${isInferred ? " (inferred)" : ""}`;

  return (
    <div
      className={cn(
        "inline-flex items-center gap-1 rounded-full cursor-help",
        typeInfo.bgColor,
        sizeClasses[size],
        showLabel ? "px-2 py-0.5" : "p-1",
        className,
      )}
      title={tooltipText}
    >
      <IconComponent className={cn(typeInfo.color, iconSizeClasses[size])} />
      {showLabel && <span className={cn("font-medium", typeInfo.color)}>{typeInfo.label}</span>}
      {isInferred && <span className="text-neutral-400 text-[8px]">?</span>}
    </div>
  );
}

interface TypeBadgeProps {
  inputType?: DataType;
  outputType?: DataType;
  className?: string;
}

/**
 * Combined input/output type badge for a node
 */
export function NodeTypeBadge({ inputType, outputType, className }: TypeBadgeProps) {
  if (!inputType && !outputType) {
    return null;
  }

  return (
    <div className={cn("flex items-center gap-1", className)}>
      {inputType && inputType !== DataType.VOID && <DataTypeIndicator type={inputType} size="sm" />}
      {inputType && outputType && <span className="text-muted-foreground text-[10px]">→</span>}
      {outputType && outputType !== DataType.VOID && <DataTypeIndicator type={outputType} size="sm" />}
    </div>
  );
}

interface TypeMismatchWarningProps {
  sourceType: DataType;
  targetType: DataType;
  suggestion?: string;
  className?: string;
}

/**
 * Warning indicator for type mismatches
 */
function TypeMismatchWarning({ sourceType, targetType, suggestion, className }: TypeMismatchWarningProps) {
  const sourceInfo = getDataTypeInfo(sourceType);
  const targetInfo = getDataTypeInfo(targetType);

  const tooltipText = `Type Mismatch: ${sourceInfo.label} → ${targetInfo.label}${suggestion ? `. ${suggestion}` : ""}`;

  return (
    <div
      className={cn(
        "inline-flex items-center gap-1 px-2 py-1 rounded-md cursor-help",
        "bg-amber-500/15 text-amber-600 dark:text-amber-400",
        "border border-amber-500/30",
        className,
      )}
      title={tooltipText}
    >
      <AlertCircle className="size-3" />
      <span className="text-xs font-medium">Type Mismatch</span>
    </div>
  );
}

interface PortTypeIndicatorProps {
  type: DataType;
  isInput?: boolean;
  isRequired?: boolean;
  portName?: string;
  className?: string;
}

/**
 * Type indicator for node ports (input/output handles)
 */
function PortTypeIndicator({ type, isInput = true, isRequired = false, portName, className }: PortTypeIndicatorProps) {
  const typeInfo = getDataTypeInfo(type);
  const tooltipText = `${portName ? `${portName}: ` : ""}${typeInfo.label}${isRequired ? " (required)" : ""}`;

  return (
    <div
      className={cn(
        "size-2.5 rounded-full border-2 cursor-help",
        typeInfo.bgColor,
        isRequired ? "border-current" : "border-transparent",
        typeInfo.color,
        className,
      )}
      title={tooltipText}
    />
  );
}
