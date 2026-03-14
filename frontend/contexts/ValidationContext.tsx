"use client";

import { createContext, useCallback, useContext, useMemo, useState, useEffect, useRef, type ReactNode } from "react";
import type { Node, Edge } from "@xyflow/react";
import { validateGraph, type ValidationResult, type ValidationError, ValidationErrorCode } from "@/lib/graph-validator";

/**
 * Validation context state
 */
interface ValidationContextValue {
  result: ValidationResult | null;
  errors: ValidationError[];
  warnings: ValidationError[];
  isValid: boolean;
  hasStartNode: boolean;
  hasOutputNode: boolean;
  hasEndNode: boolean;

  // Actions
  validate: (nodes: Node[], edges: Edge[]) => void;
  clearValidation: () => void;

  // UI state
  isStatusBarExpanded: boolean;
  setStatusBarExpanded: (expanded: boolean) => void;
  focusedErrorId: string | null;
  setFocusedErrorId: (id: string | null) => void;
}

const emptyResult: ValidationResult = {
  isValid: true,
  errors: [],
  warnings: [],
  hasStartNode: false,
  hasOutputNode: false,
  hasEndNode: false,
};

const ValidationContext = createContext<ValidationContextValue | undefined>(undefined);

interface ValidationProviderProps {
  children: ReactNode;
  debounceMs?: number;
}

export function ValidationProvider({ children, debounceMs = 300 }: ValidationProviderProps) {
  const [result, setResult] = useState<ValidationResult | null>(null);
  const [isStatusBarExpanded, setStatusBarExpanded] = useState(false);
  const [focusedErrorId, setFocusedErrorId] = useState<string | null>(null);

  const debounceTimerRef = useRef<NodeJS.Timeout | null>(null);

  const validate = useCallback(
    (nodes: Node[], edges: Edge[]) => {
      // Clear existing timer
      if (debounceTimerRef.current) {
        clearTimeout(debounceTimerRef.current);
      }

      // Debounce validation
      debounceTimerRef.current = setTimeout(() => {
        const validationResult = validateGraph(nodes, edges);
        setResult(validationResult);
      }, debounceMs);
    },
    [debounceMs],
  );

  const clearValidation = useCallback(() => {
    if (debounceTimerRef.current) {
      clearTimeout(debounceTimerRef.current);
    }
    setResult(null);
    setFocusedErrorId(null);
  }, []);

  // Cleanup on unmount
  useEffect(() => {
    return () => {
      if (debounceTimerRef.current) {
        clearTimeout(debounceTimerRef.current);
      }
    };
  }, []);

  const value = useMemo<ValidationContextValue>(() => {
    const currentResult = result ?? emptyResult;

    return {
      result,
      errors: currentResult.errors,
      warnings: currentResult.warnings,
      isValid: currentResult.isValid,
      hasStartNode: currentResult.hasStartNode,
      hasOutputNode: currentResult.hasOutputNode,
      hasEndNode: currentResult.hasEndNode,
      validate,
      clearValidation,
      isStatusBarExpanded,
      setStatusBarExpanded,
      focusedErrorId,
      setFocusedErrorId,
    };
  }, [result, validate, clearValidation, isStatusBarExpanded, focusedErrorId]);

  return <ValidationContext.Provider value={value}>{children}</ValidationContext.Provider>;
}

export function useValidation(): ValidationContextValue {
  const context = useContext(ValidationContext);
  if (!context) {
    throw new Error("useValidation must be used within a ValidationProvider");
  }
  return context;
}

/**
 * Hook to get validation state for a specific node
 */
export function useNodeValidation(nodeId: string): {
  hasError: boolean;
  hasWarning: boolean;
  errors: ValidationError[];
  warnings: ValidationError[];
} {
  const { errors, warnings } = useValidation();

  return useMemo(() => {
    const nodeErrors = errors.filter((e) => e.nodeId === nodeId);
    const nodeWarnings = warnings.filter((w) => w.nodeId === nodeId);

    return {
      hasError: nodeErrors.length > 0,
      hasWarning: nodeWarnings.length > 0,
      errors: nodeErrors,
      warnings: nodeWarnings,
    };
  }, [errors, warnings, nodeId]);
}

/**
 * Hook to get validation state for a specific edge
 */
export function useEdgeValidation(edgeId: string): {
  hasError: boolean;
  hasWarning: boolean;
  errors: ValidationError[];
  warnings: ValidationError[];
} {
  const { errors, warnings } = useValidation();

  return useMemo(() => {
    const edgeErrors = errors.filter((e) => e.edgeId === edgeId);
    const edgeWarnings = warnings.filter((w) => w.edgeId === edgeId);

    return {
      hasError: edgeErrors.length > 0,
      hasWarning: edgeWarnings.length > 0,
      errors: edgeErrors,
      warnings: edgeWarnings,
    };
  }, [errors, warnings, edgeId]);
}

export default ValidationContext;
