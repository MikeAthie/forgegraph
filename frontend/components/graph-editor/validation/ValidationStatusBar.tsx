"use client";

import { useState } from "react";
import {
  CheckCircle,
  AlertCircle,
  AlertTriangle,
  ChevronUp,
  ChevronDown,
  ExternalLink,
} from "lucide-react";
import { cn } from "@/lib/utils";
import { useValidation } from "@/contexts/ValidationContext";
import { type ValidationError, getQuickFixesForError } from "@/lib/graph-validator";
import { Button } from "@/components/ui/button";

export interface ValidationStatusBarProps {
  onFocusNode?: (nodeId: string) => void;
  onFocusEdge?: (edgeId: string) => void;
  onQuickFix?: (error: ValidationError, fixLabel: string) => void;
  className?: string;
}

/**
 * Status bar showing validation status at the bottom of the graph editor
 */
export function ValidationStatusBar({
  onFocusNode,
  onFocusEdge,
  onQuickFix,
  className,
}: ValidationStatusBarProps) {
  const {
    isValid,
    errors,
    warnings,
    isStatusBarExpanded,
    setStatusBarExpanded,
  } = useValidation();

  const totalIssues = errors.length + warnings.length;

  if (totalIssues === 0 && isValid) {
    return (
      <div
        className={cn(
          "flex items-center justify-between px-4 py-2 bg-emerald-500/10 border-t border-emerald-500/30",
          className
        )}
      >
        <div className="flex items-center gap-2">
          <CheckCircle className="w-4 h-4 text-emerald-500" />
          <span className="text-sm font-medium text-emerald-600 dark:text-emerald-400">
            Graph Valid
          </span>
        </div>
      </div>
    );
  }

  return (
    <div
      className={cn(
        "bg-background border-t",
        errors.length > 0 ? "border-destructive/50" : "border-amber-500/50",
        className
      )}
    >
      {/* Summary Bar */}
      <button
        type="button"
        onClick={() => setStatusBarExpanded(!isStatusBarExpanded)}
        className={cn(
          "w-full flex items-center justify-between px-4 py-2 hover:bg-muted/50 transition-colors",
          errors.length > 0
            ? "bg-destructive/10"
            : "bg-amber-500/10"
        )}
      >
        <div className="flex items-center gap-3">
          {errors.length > 0 ? (
            <>
              <AlertCircle className="w-4 h-4 text-destructive" />
              <span className="text-sm font-medium text-destructive">
                {errors.length} error{errors.length !== 1 ? "s" : ""}
              </span>
            </>
          ) : (
            <>
              <AlertTriangle className="w-4 h-4 text-amber-500" />
              <span className="text-sm font-medium text-amber-600 dark:text-amber-400">
                {warnings.length} warning{warnings.length !== 1 ? "s" : ""}
              </span>
            </>
          )}
          {errors.length > 0 && warnings.length > 0 && (
            <span className="text-sm text-muted-foreground">
              ({warnings.length} warning{warnings.length !== 1 ? "s" : ""})
            </span>
          )}
        </div>
        <div className="flex items-center gap-2">
          <span className="text-xs text-muted-foreground">
            {isStatusBarExpanded ? "Hide" : "Show"} details
          </span>
          {isStatusBarExpanded ? (
            <ChevronDown className="w-4 h-4 text-muted-foreground" />
          ) : (
            <ChevronUp className="w-4 h-4 text-muted-foreground" />
          )}
        </div>
      </button>

      {/* Expanded Error List */}
      {isStatusBarExpanded && (
        <div className="max-h-48 overflow-y-auto divide-y divide-border">
          {/* Errors first */}
          {errors.map((error, index) => (
            <ValidationErrorItem
              key={`error-${index}`}
              error={error}
              onFocusNode={onFocusNode}
              onFocusEdge={onFocusEdge}
              onQuickFix={onQuickFix}
            />
          ))}
          {/* Then warnings */}
          {warnings.map((warning, index) => (
            <ValidationErrorItem
              key={`warning-${index}`}
              error={warning}
              onFocusNode={onFocusNode}
              onFocusEdge={onFocusEdge}
              onQuickFix={onQuickFix}
            />
          ))}
        </div>
      )}
    </div>
  );
}

interface ValidationErrorItemProps {
  error: ValidationError;
  onFocusNode?: (nodeId: string) => void;
  onFocusEdge?: (edgeId: string) => void;
  onQuickFix?: (error: ValidationError, fixLabel: string) => void;
}

function ValidationErrorItem({
  error,
  onFocusNode,
  onFocusEdge,
  onQuickFix,
}: ValidationErrorItemProps) {
  const isError = error.severity === "error";
  const quickFixes = getQuickFixesForError(error);

  const handleGoTo = () => {
    if (error.nodeId && onFocusNode) {
      onFocusNode(error.nodeId);
    } else if (error.edgeId && onFocusEdge) {
      onFocusEdge(error.edgeId);
    }
  };

  return (
    <div className="flex items-start gap-3 px-4 py-3 hover:bg-muted/30 transition-colors">
      {isError ? (
        <AlertCircle className="w-4 h-4 text-destructive mt-0.5 shrink-0" />
      ) : (
        <AlertTriangle className="w-4 h-4 text-amber-500 mt-0.5 shrink-0" />
      )}
      <div className="flex-1 min-w-0">
        <p
          className={cn(
            "text-sm font-medium",
            isError ? "text-destructive" : "text-amber-600 dark:text-amber-400"
          )}
        >
          {error.message}
        </p>
        {error.suggestion && (
          <p className="text-xs text-muted-foreground mt-0.5">
            {error.suggestion}
          </p>
        )}
      </div>
      <div className="flex items-center gap-2 shrink-0">
        {(error.nodeId || error.edgeId) && (
          <Button
            variant="ghost"
            size="sm"
            onClick={handleGoTo}
            className="h-7 px-2 text-xs"
          >
            <ExternalLink className="w-3 h-3 mr-1" />
            Go to
          </Button>
        )}
        {quickFixes.map((fix) => (
          <Button
            key={fix.label}
            variant="outline"
            size="sm"
            onClick={() => onQuickFix?.(error, fix.label)}
            className="h-7 px-2 text-xs"
            title={fix.description}
          >
            {fix.label}
          </Button>
        ))}
      </div>
    </div>
  );
}

export default ValidationStatusBar;
