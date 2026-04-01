"use client";

import { useCallback, useEffect, useLayoutEffect, useRef, useState } from "react";
import {
  Dialog,
  DialogContent,
  DialogHeader,
  DialogTitle,
  DialogFooter,
  DialogDescription,
} from "@/components/ui/dialog";
import { Button } from "@/components/ui/button";
import { AlertCircle } from "lucide-react";
import { cn } from "@/lib/utils";
import type { NodeType, NodeConfig } from "@/lib/graph-types";
import { NODE_TYPES, PHASE2_NODE_TYPES } from "@/lib/graph-types";

/**
 * Props for node-specific form components
 */
export interface NodeFormProps {
  config: NodeConfig;
  onChange: (config: NodeConfig) => void;
  errors: Record<string, string>;
  setErrors: (errors: Record<string, string>) => void;
}

/**
 * Node type display info
 */
const NODE_TYPE_INFO: Record<string, { label: string; color: string; icon: string }> = {
  [NODE_TYPES.AGENT]: { label: "Agent", color: "bg-sky-500", icon: "A" },
  [NODE_TYPES.PROMPT]: { label: "Prompt", color: "bg-violet-500", icon: "P" },
  [NODE_TYPES.HTTP]: { label: "HTTP", color: "bg-blue-500", icon: "H" },
  [NODE_TYPES.TRANSFORM]: { label: "Transform", color: "bg-amber-500", icon: "T" },
  [NODE_TYPES.OUTPUT]: { label: "Output", color: "bg-emerald-500", icon: "O" },
  [NODE_TYPES.BRANCH]: { label: "Branch", color: "bg-orange-500", icon: "B" },
  [NODE_TYPES.MERGE]: { label: "Merge", color: "bg-cyan-500", icon: "M" },
  [NODE_TYPES.HUMAN_GATE]: { label: "Human Gate", color: "bg-rose-500", icon: "G" },
  [NODE_TYPES.MEMORY]: { label: "Memory", color: "bg-indigo-500", icon: "M" },
  [NODE_TYPES.OBSERVATION_SAVE]: {
    label: "Observation Save",
    color: "bg-teal-700",
    icon: "OS",
  },
  [NODE_TYPES.OBSERVATION_SEARCH]: {
    label: "Observation Search",
    color: "bg-sky-700",
    icon: "SR",
  },
  [NODE_TYPES.OBSERVATION_CONTEXT]: {
    label: "Observation Context",
    color: "bg-blue-700",
    icon: "CX",
  },
  [NODE_TYPES.OBSERVATION_TIMELINE]: {
    label: "Observation Timeline",
    color: "bg-violet-700",
    icon: "TL",
  },
  [NODE_TYPES.TOOL]: { label: "Tool", color: "bg-teal-500", icon: "T" },
  [NODE_TYPES.SUBGRAPH]: { label: "Subgraph", color: "bg-purple-500", icon: "S" },
};

export interface NodeConfigDialogProps {
  isOpen: boolean;
  onClose: () => void;
  nodeType: NodeType | null;
  initialConfig?: NodeConfig;
  initialLabel?: string;
  onSave: (config: NodeConfig, label: string) => void;
  FormComponent?: React.ComponentType<NodeFormProps>;
}

/**
 * Default placeholder form for nodes without a specific form
 */
function DefaultNodeForm({ config, onChange }: NodeFormProps) {
  return (
    <div className="py-4">
      <p className="text-sm text-muted-foreground">Configure this node using the inspector panel after creation.</p>
      <pre className="mt-4 p-3 bg-muted rounded-md text-xs overflow-auto max-h-48">
        {JSON.stringify(config, null, 2)}
      </pre>
    </div>
  );
}

export function NodeConfigDialog({
  isOpen,
  onClose,
  nodeType,
  initialConfig,
  initialLabel,
  onSave,
  FormComponent,
}: NodeConfigDialogProps) {
  const fallbackConfigRef = useRef<NodeConfig>({});
  const resolvedInitialConfig = initialConfig ?? fallbackConfigRef.current;
  const [config, setConfig] = useState<NodeConfig>(resolvedInitialConfig);
  const [errors, setErrors] = useState<Record<string, string>>({});
  const [label, setLabel] = useState("");
  const [isDirty, setIsDirty] = useState(false);
  const [showCloseConfirm, setShowCloseConfirm] = useState(false);

  // Reset state when dialog opens with new node type
  useLayoutEffect(() => {
    if (isOpen && nodeType) {
      setConfig(resolvedInitialConfig);
      setErrors({});
      setLabel(initialLabel?.trim() || NODE_TYPE_INFO[nodeType]?.label || nodeType);
      setIsDirty(false);
      setShowCloseConfirm(false);
    }
  }, [initialLabel, isOpen, nodeType, resolvedInitialConfig]);

  const handleConfigChange = useCallback((newConfig: NodeConfig) => {
    setConfig(newConfig);
    setIsDirty(true);
  }, []);

  const handleClose = useCallback(() => {
    if (isDirty) {
      setShowCloseConfirm(true);
    } else {
      onClose();
    }
  }, [isDirty, onClose]);

  const handleConfirmClose = useCallback(() => {
    setShowCloseConfirm(false);
    onClose();
  }, [onClose]);

  const handleCancelClose = useCallback(() => {
    setShowCloseConfirm(false);
  }, []);

  const handleSave = useCallback(() => {
    // Check for errors
    if (Object.keys(errors).length > 0) {
      return;
    }

    onSave(config, label.trim() || NODE_TYPE_INFO[nodeType || ""]?.label || "Node");
    onClose();
  }, [config, errors, label, nodeType, onClose, onSave]);

  // Handle escape key
  useEffect(() => {
    const handleKeyDown = (e: KeyboardEvent) => {
      if (e.key === "Escape" && isOpen) {
        e.preventDefault();
        handleClose();
      }
    };

    window.addEventListener("keydown", handleKeyDown);
    return () => window.removeEventListener("keydown", handleKeyDown);
  }, [isOpen, handleClose]);

  if (!nodeType) {
    return null;
  }

  const typeInfo = NODE_TYPE_INFO[nodeType] || { label: nodeType, color: "bg-gray-500", icon: "?" };
  const hasErrors = Object.keys(errors).length > 0;
  const Form = FormComponent || DefaultNodeForm;

  return (
    <>
      <Dialog open={isOpen && !showCloseConfirm} onOpenChange={(open) => !open && handleClose()}>
        <DialogContent className="max-w-2xl max-h-[85vh] overflow-hidden flex flex-col">
          <DialogHeader>
            <div className="flex items-center gap-3">
              <div
                className={cn(
                  "w-8 h-8 rounded-md flex items-center justify-center text-white font-bold text-sm",
                  typeInfo.color,
                )}
              >
                {typeInfo.icon}
              </div>
              <div className="flex-1">
                <DialogTitle className="text-lg">Configure {typeInfo.label} Node</DialogTitle>
                <DialogDescription className="text-sm">
                  Set up the node configuration before adding it to your workflow.
                </DialogDescription>
              </div>
            </div>
          </DialogHeader>

          {/* Node Label */}
          <div className="px-1">
            <label className="text-sm font-medium" htmlFor="node-label">
              Node Label
            </label>
            <input
              id="node-label"
              type="text"
              autoComplete="off"
              value={label}
              onChange={(e) => {
                setLabel(e.target.value);
                setIsDirty(true);
              }}
              placeholder={typeInfo.label}
              className="w-full mt-1 px-3 py-2 border rounded-md bg-background text-sm"
            />
          </div>

          {/* Form Content - Scrollable */}
          <div className="flex-1 overflow-y-auto px-1 py-2 min-h-0">
            <Form config={config} onChange={handleConfigChange} errors={errors} setErrors={setErrors} />
          </div>

          {/* Error Summary */}
          {hasErrors && (
            <div className="flex items-start gap-2 p-3 bg-destructive/10 border border-destructive/30 rounded-md mx-1">
              <AlertCircle className="w-4 h-4 text-destructive mt-0.5 shrink-0" />
              <div>
                <p className="text-sm font-medium text-destructive">Please fix the following errors:</p>
                <ul className="text-xs text-destructive mt-1 list-disc list-inside">
                  {Object.entries(errors).map(([field, message]) => (
                    <li key={field}>{message}</li>
                  ))}
                </ul>
              </div>
            </div>
          )}

          <DialogFooter className="gap-2 sm:gap-0">
            <Button variant="outline" onClick={handleClose}>
              Cancel
            </Button>
            <Button onClick={handleSave} disabled={hasErrors}>
              Add Node
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>

      {/* Close Confirmation Dialog */}
      <Dialog open={showCloseConfirm} onOpenChange={setShowCloseConfirm}>
        <DialogContent className="max-w-sm">
          <DialogHeader>
            <DialogTitle>Discard changes?</DialogTitle>
            <DialogDescription>
              You have unsaved changes. Are you sure you want to close without saving?
            </DialogDescription>
          </DialogHeader>
          <DialogFooter className="gap-2 sm:gap-0">
            <Button variant="outline" onClick={handleCancelClose}>
              Keep Editing
            </Button>
            <Button variant="destructive" onClick={handleConfirmClose}>
              Discard
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>
    </>
  );
}

export default NodeConfigDialog;
