"use client";

import { AlertCircle, Plus } from "lucide-react";
import { cn } from "@/lib/utils";
import { useValidation } from "@/contexts/ValidationContext";
import { ValidationErrorCode } from "@/lib/graph-validator";

export interface ValidationOverlayProps {
  onAddStartNode?: () => void;
  onAddOutputNode?: () => void;
  className?: string;
}

/**
 * Validation overlay that shows indicators for missing start/end nodes
 * Positioned on the canvas to guide users to fix validation issues
 */
export function ValidationOverlay({
  onAddStartNode,
  onAddOutputNode,
  className,
}: ValidationOverlayProps) {
  const { hasStartNode, hasOutputNode, errors } = useValidation();

  const showStartIndicator =
    !hasStartNode &&
    errors.some((e) => e.code === ValidationErrorCode.NO_START_NODE);

  const showOutputIndicator =
    !hasOutputNode &&
    errors.some((e) => e.code === ValidationErrorCode.NO_OUTPUT_NODE);

  if (!showStartIndicator && !showOutputIndicator) {
    return null;
  }

  return (
    <div
      className={cn("pointer-events-none absolute inset-0 z-10", className)}
    >
      {/* Missing Start Node Indicator */}
      {showStartIndicator && (
        <div className="absolute left-4 top-1/2 -translate-y-1/2 pointer-events-auto">
          <button
            type="button"
            onClick={onAddStartNode}
            className="group flex flex-col items-center gap-2 p-4 rounded-xl border-2 border-dashed border-amber-500/50 bg-amber-500/10 hover:bg-amber-500/20 hover:border-amber-500 transition-all"
          >
            <div className="flex items-center justify-center w-12 h-12 rounded-full bg-amber-500/20 group-hover:bg-amber-500/30 transition-colors">
              <AlertCircle className="w-6 h-6 text-amber-500" />
            </div>
            <div className="text-center">
              <p className="text-sm font-medium text-amber-600 dark:text-amber-400">
                Add Start Node
              </p>
              <p className="text-xs text-muted-foreground mt-0.5">
                Click to add entry point
              </p>
            </div>
            <div className="flex items-center justify-center w-8 h-8 rounded-full border-2 border-dashed border-amber-500/50 group-hover:border-amber-500 transition-colors">
              <Plus className="w-4 h-4 text-amber-500" />
            </div>
          </button>
        </div>
      )}

      {/* Missing Output Node Indicator */}
      {showOutputIndicator && (
        <div className="absolute right-4 top-1/2 -translate-y-1/2 pointer-events-auto">
          <button
            type="button"
            onClick={onAddOutputNode}
            className="group flex flex-col items-center gap-2 p-4 rounded-xl border-2 border-dashed border-rose-500/50 bg-rose-500/10 hover:bg-rose-500/20 hover:border-rose-500 transition-all"
          >
            <div className="flex items-center justify-center w-12 h-12 rounded-full bg-rose-500/20 group-hover:bg-rose-500/30 transition-colors">
              <AlertCircle className="w-6 h-6 text-rose-500" />
            </div>
            <div className="text-center">
              <p className="text-sm font-medium text-rose-600 dark:text-rose-400">
                Add Output Node
              </p>
              <p className="text-xs text-muted-foreground mt-0.5">
                Click to define result
              </p>
            </div>
            <div className="flex items-center justify-center w-8 h-8 rounded-full border-2 border-dashed border-rose-500/50 group-hover:border-rose-500 transition-colors">
              <Plus className="w-4 h-4 text-rose-500" />
            </div>
          </button>
        </div>
      )}
    </div>
  );
}

export default ValidationOverlay;
