"use client";

import { useMemo } from "react";
import {
  Type,
  Braces,
  List,
  Hash,
  ToggleLeft,
  Image,
  File,
  Asterisk,
  Circle,
  AlertCircle,
} from "lucide-react";
import { cn } from "@/lib/utils";
import { DataType, DATA_TYPE_INFO, getDataTypeInfo } from "@/lib/data-types";
import {
  Tooltip,
  TooltipContent,
  TooltipTrigger,
} from "@/components/ui/tooltip";

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
  showTooltip?: boolean;
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
  showTooltip = true,
  isInferred = false,
  className,
}: DataTypeIndicatorProps) {
  const typeInfo = getDataTypeInfo(type);
  const IconComponent = TYPE_ICONS[type] || Asterisk;

  const sizeClasses = {
    sm: "h-4 w-4 text-[10px]",
    md: "h-5 w-5 text-xs",
    lg: "h-6 w-6 text-sm",
  };

  const iconSizeClasses = {
    sm: "h-2.5 w-2.5",
    md: "h-3 w-3",
    lg: "h-4 w-4",
  };

  const content = (
    <div
      className={cn(
        "inline-flex items-center gap-1 rounded-full",
        typeInfo.bgColor,
        sizeClasses[size],
        showLabel ? "px-2 py-0.5" : "p-1",
        className
      )}
    >
      <IconComponent className={cn(typeInfo.color, iconSizeClasses[size])} />
      {showLabel && (
        <span className={cn("font-medium", typeInfo.color)}>
          {typeInfo.label}
        </span>
      )}
      {isInferred && (
        <span className="text-gray-400 text-[8px]">?</span>
      )}
    </div>
  );

  if (!showTooltip) {
    return content;
  }

  return (
    <Tooltip>
      <TooltipTrigger asChild>{content}</TooltipTrigger>
      <TooltipContent side="top" className="max-w-[200px]">
        <div className="space-y-1">
          <p className="font-medium">{typeInfo.label}</p>
          <p className="text-xs text-muted-foreground">{typeInfo.description}</p>
          {isInferred && (
            <p className="text-xs text-amber-500">Type is inferred</p>
          )}
        </div>
      </TooltipContent>
    </Tooltip>
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
export function NodeTypeBadge({
  inputType,
  outputType,
  className,
}: TypeBadgeProps) {
  if (!inputType && !outputType) {
    return null;
  }

  return (
    <div className={cn("flex items-center gap-1", className)}>
      {inputType && inputType !== DataType.VOID && (
        <DataTypeIndicator type={inputType} size="sm" />
      )}
      {inputType && outputType && (
        <span className="text-muted-foreground text-[10px]">→</span>
      )}
      {outputType && outputType !== DataType.VOID && (
        <DataTypeIndicator type={outputType} size="sm" />
      )}
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
export function TypeMismatchWarning({
  sourceType,
  targetType,
  suggestion,
  className,
}: TypeMismatchWarningProps) {
  const sourceInfo = getDataTypeInfo(sourceType);
  const targetInfo = getDataTypeInfo(targetType);

  return (
    <Tooltip>
      <TooltipTrigger asChild>
        <div
          className={cn(
            "inline-flex items-center gap-1 px-2 py-1 rounded-md",
            "bg-amber-500/15 text-amber-600 dark:text-amber-400",
            "border border-amber-500/30",
            className
          )}
        >
          <AlertCircle className="h-3 w-3" />
          <span className="text-xs font-medium">Type Mismatch</span>
        </div>
      </TooltipTrigger>
      <TooltipContent side="top" className="max-w-[280px]">
        <div className="space-y-2">
          <p className="font-medium">Type Mismatch</p>
          <div className="flex items-center gap-2 text-sm">
            <DataTypeIndicator type={sourceType} showLabel size="sm" />
            <span className="text-muted-foreground">→</span>
            <DataTypeIndicator type={targetType} showLabel size="sm" />
          </div>
          <p className="text-xs text-muted-foreground">
            {sourceInfo.label} cannot be directly used as {targetInfo.label}
          </p>
          {suggestion && (
            <p className="text-xs text-amber-500">{suggestion}</p>
          )}
        </div>
      </TooltipContent>
    </Tooltip>
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
export function PortTypeIndicator({
  type,
  isInput = true,
  isRequired = false,
  portName,
  className,
}: PortTypeIndicatorProps) {
  const typeInfo = getDataTypeInfo(type);

  return (
    <Tooltip>
      <TooltipTrigger asChild>
        <div
          className={cn(
            "w-2.5 h-2.5 rounded-full border-2",
            typeInfo.bgColor,
            isRequired ? "border-current" : "border-transparent",
            typeInfo.color,
            className
          )}
        />
      </TooltipTrigger>
      <TooltipContent side={isInput ? "left" : "right"}>
        <div className="space-y-0.5">
          {portName && <p className="font-medium text-xs">{portName}</p>}
          <div className="flex items-center gap-1.5">
            <DataTypeIndicator type={type} size="sm" showTooltip={false} />
            <span className="text-xs">{typeInfo.label}</span>
          </div>
          {isRequired && (
            <p className="text-xs text-amber-500">Required</p>
          )}
        </div>
      </TooltipContent>
    </Tooltip>
  );
}

export default DataTypeIndicator;
