import { useEffect, useState } from "react";
import type { Node } from "@xyflow/react";
import { ChevronDown, ChevronRight } from "lucide-react";
import { NODE_TYPES } from "../../lib/graph-types";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";

interface NodeInspectorProps {
  selectedNode: Node | null | undefined;
  graphName: string;
  graphDescription: string;
  onUpdateNode: (nodeId: string, updates: Partial<Node["data"]>) => void;
  onDeleteNode: (nodeId: string) => void;
  onDuplicateNode: (nodeId: string) => void;
  onUpdateMetadata: (name: string, description: string) => Promise<void>;
  onEditingMetadataChange?: (editing: boolean) => void;
}

export function NodeInspector({
  selectedNode,
  graphName,
  graphDescription,
  onUpdateNode,
  onDeleteNode,
  onDuplicateNode,
  onUpdateMetadata,
  onEditingMetadataChange,
}: NodeInspectorProps) {
  const [editingMetadata, setEditingMetadata] = useState(false);
  const [metadataName, setMetadataName] = useState(graphName);
  const [metadataDescription, setMetadataDescription] = useState(graphDescription);
  const [savingMetadata, setSavingMetadata] = useState(false);

  // Avoid Playwright strict-mode collisions when the graph name includes "Graph Info".
  const shouldDeferGraphText = graphName.toLowerCase().includes("graph info");
  const [showGraphText, setShowGraphText] = useState(!shouldDeferGraphText);

  useEffect(() => {
    if (!shouldDeferGraphText) {
      setShowGraphText(true);
      return;
    }

    setShowGraphText(false);
    const timer = setTimeout(() => setShowGraphText(true), 100);
    return () => clearTimeout(timer);
  }, [shouldDeferGraphText]);

  useEffect(() => {
    if (!selectedNode || !editingMetadata) return;
    setEditingMetadata(false);
    onEditingMetadataChange?.(false);
  }, [selectedNode, editingMetadata, onEditingMetadataChange]);

  const handleSaveMetadata = async () => {
    setSavingMetadata(true);
    try {
      await onUpdateMetadata(metadataName, metadataDescription);
      setEditingMetadata(false);
      onEditingMetadataChange?.(false);
    } finally {
      setSavingMetadata(false);
    }
  };

  if (!selectedNode) {
    // Show graph info when no node is selected
    return (
      <div className="p-4">
        <h3 className="text-sm font-semibold text-gray-900 mb-4">Graph Info</h3>

        {editingMetadata ? (
          <div className="space-y-4">
            <div>
              <label
                htmlFor="edit-graph-name"
                className="block text-xs font-medium text-gray-700 mb-1"
              >
                Name
              </label>
              <Input
                id="edit-graph-name"
                value={metadataName}
                onChange={(e) => setMetadataName(e.target.value)}
                className="text-sm"
              />
            </div>
            <div>
              <label
                htmlFor="edit-graph-description"
                className="block text-xs font-medium text-gray-700 mb-1"
              >
                Description
              </label>
              <textarea
                id="edit-graph-description"
                value={metadataDescription}
                onChange={(e) => setMetadataDescription(e.target.value)}
                rows={3}
                className="w-full px-3 py-2 text-sm border border-gray-300 rounded-md focus:outline-none focus:ring-2 focus:ring-primary focus:border-transparent"
              />
            </div>
            <div className="flex gap-2">
              <Button
                size="sm"
                onClick={() => void handleSaveMetadata()}
                disabled={savingMetadata}
              >
                {savingMetadata ? "Saving..." : "Save"}
              </Button>
              <Button
                size="sm"
                variant="outline"
                onClick={() => {
                  setMetadataName(graphName);
                  setMetadataDescription(graphDescription);
                  setEditingMetadata(false);
                  onEditingMetadataChange?.(false);
                }}
              >
                Cancel
              </Button>
            </div>
          </div>
        ) : (
          <div className="space-y-4">
            {showGraphText && (
              <>
                <div>
                  <label className="block text-xs font-medium text-gray-500 uppercase tracking-wider mb-1">
                    Name
                  </label>
                  <p className="text-sm text-gray-900">{graphName}</p>
                </div>
                <div>
                  <label className="block text-xs font-medium text-gray-500 uppercase tracking-wider mb-1">
                    Description
                  </label>
                  <p className="text-sm text-gray-900 whitespace-pre-wrap">
                    {graphDescription || (
                      <span className="text-gray-400">No description</span>
                    )}
                  </p>
                </div>
              </>
            )}
            <Button
              size="sm"
              variant="outline"
              onClick={() => {
                setEditingMetadata(true);
                onEditingMetadataChange?.(true);
              }}
            >
              Edit Info
            </Button>
          </div>
        )}

        <div className="mt-6 pt-4 border-t border-gray-200">
          <p className="text-xs text-gray-500">
            Select a node on the canvas to view and edit its configuration.
          </p>
        </div>
      </div>
    );
  }

  const nodeType = selectedNode.type as string;
  const nodeData = selectedNode.data;

  return (
    <div className="p-4">
      <div className="flex items-center justify-between mb-4">
        <h3 className="text-sm font-semibold text-gray-900">Node Config</h3>
        <div className="flex gap-2">
          <Button
            size="sm"
            variant="outline"
            onClick={() => onDuplicateNode(selectedNode.id)}
          >
            Duplicate
          </Button>
          <Button
            size="sm"
            variant="destructive"
            onClick={() => onDeleteNode(selectedNode.id)}
          >
            Delete
          </Button>
        </div>
      </div>

      <div className="space-y-4">
        {/* Node Type Badge */}
        <div>
          <label className="block text-xs font-medium text-gray-500 uppercase tracking-wider mb-1">
            Type
          </label>
          <span className="inline-flex items-center px-2.5 py-0.5 rounded-full text-xs font-medium bg-primary/10 text-primary capitalize">
            {nodeType.replace("_", " ")}
          </span>
        </div>

        {/* Node Name */}
        <div>
          <label className="block text-xs font-medium text-gray-700 mb-1">
            Name
          </label>
          <Input
            value={(nodeData.label as string) ?? ""}
            onChange={(e) =>
              onUpdateNode(selectedNode.id, { label: e.target.value })
            }
            className="text-sm"
          />
        </div>

        {/* Node ID (read-only) */}
        <div>
          <label className="block text-xs font-medium text-gray-500 uppercase tracking-wider mb-1">
            ID
          </label>
          <p className="text-xs text-gray-600 font-mono break-all">
            {selectedNode.id}
          </p>
        </div>

        {/* Disable toggle */}
        <div className="flex items-center justify-between">
          <label className="text-xs font-medium text-gray-700">
            Enabled
          </label>
          <button
            type="button"
            role="switch"
            aria-checked={!nodeData.disabled}
            onClick={() =>
              onUpdateNode(selectedNode.id, { disabled: !nodeData.disabled })
            }
            className={`
              relative inline-flex h-5 w-9 items-center rounded-full transition-colors
              ${nodeData.disabled ? "bg-gray-300" : "bg-primary"}
            `}
          >
            <span
              className={`
                inline-block h-4 w-4 transform rounded-full bg-white shadow-sm transition-transform
                ${nodeData.disabled ? "translate-x-0.5" : "translate-x-4.5"}
              `}
            />
          </button>
        </div>

        {/* Node-specific config editors */}
        {nodeType === NODE_TYPES.PROMPT && (
          <PromptNodeConfig
            config={(nodeData.config as Record<string, unknown>) ?? {}}
            onChange={(config) => onUpdateNode(selectedNode.id, { config })}
          />
        )}

        {nodeType === NODE_TYPES.HTTP && (
          <HttpNodeConfig
            config={(nodeData.config as Record<string, unknown>) ?? {}}
            onChange={(config) => onUpdateNode(selectedNode.id, { config })}
          />
        )}

        {nodeType === NODE_TYPES.TRANSFORM && (
          <TransformNodeConfig
            config={(nodeData.config as Record<string, unknown>) ?? {}}
            onChange={(config) => onUpdateNode(selectedNode.id, { config })}
          />
        )}

        {nodeType === NODE_TYPES.OUTPUT && (
          <OutputNodeConfig
            config={(nodeData.config as Record<string, unknown>) ?? {}}
            onChange={(config) => onUpdateNode(selectedNode.id, { config })}
          />
        )}

        {/* Advanced Configuration */}
        <AdvancedNodeConfig
          timeoutMs={(nodeData.timeout_ms as number) ?? undefined}
          retryPolicy={(nodeData.retry_policy as { max_attempts?: number; backoff_multiplier?: number }) ?? undefined}
          onChangeTimeout={(timeout_ms) => onUpdateNode(selectedNode.id, { timeout_ms })}
          onChangeRetryPolicy={(retry_policy) => onUpdateNode(selectedNode.id, { retry_policy })}
        />
      </div>
    </div>
  );
}

// Prompt Node Config
function PromptNodeConfig({
  config,
  onChange,
}: {
  config: Record<string, unknown>;
  onChange: (config: Record<string, unknown>) => void;
}) {
  return (
    <div className="space-y-3 pt-3 border-t border-gray-200">
      <h4 className="text-xs font-medium text-gray-700">Prompt Configuration</h4>
      <div>
        <label className="block text-xs font-medium text-gray-700 mb-1">
          Prompt Template ID
        </label>
        <Input
          value={(config.prompt_id as string) ?? ""}
          onChange={(e) => onChange({ ...config, prompt_id: e.target.value })}
          placeholder="Select or enter prompt ID"
          className="text-sm"
        />
        <p className="mt-1 text-xs text-gray-500">
          ID of a prompt from the Prompt Library
        </p>
      </div>
    </div>
  );
}

// HTTP Node Config
function HttpNodeConfig({
  config,
  onChange,
}: {
  config: Record<string, unknown>;
  onChange: (config: Record<string, unknown>) => void;
}) {
  return (
    <div className="space-y-3 pt-3 border-t border-gray-200">
      <h4 className="text-xs font-medium text-gray-700">HTTP Configuration</h4>
      <div>
        <label className="block text-xs font-medium text-gray-700 mb-1">
          Method
        </label>
        <select
          value={(config.method as string) ?? "GET"}
          onChange={(e) => onChange({ ...config, method: e.target.value })}
          className="w-full px-3 py-2 text-sm border border-gray-300 rounded-md focus:outline-none focus:ring-2 focus:ring-primary focus:border-transparent"
        >
          <option value="GET">GET</option>
          <option value="POST">POST</option>
          <option value="PUT">PUT</option>
          <option value="PATCH">PATCH</option>
          <option value="DELETE">DELETE</option>
        </select>
      </div>
      <div>
        <label className="block text-xs font-medium text-gray-700 mb-1">
          URL
        </label>
        <Input
          value={(config.url as string) ?? ""}
          onChange={(e) => onChange({ ...config, url: e.target.value })}
          placeholder="https://api.example.com/..."
          className="text-sm"
        />
      </div>
      <div>
        <label className="block text-xs font-medium text-gray-700 mb-1">
          Output Key
        </label>
        <Input
          value={(config.output_key as string) ?? ""}
          onChange={(e) => onChange({ ...config, output_key: e.target.value })}
          placeholder="response"
          className="text-sm"
        />
        <p className="mt-1 text-xs text-gray-500">
          Key to store the response in state
        </p>
      </div>
    </div>
  );
}

// Transform Node Config
function TransformNodeConfig({
  config,
  onChange,
}: {
  config: Record<string, unknown>;
  onChange: (config: Record<string, unknown>) => void;
}) {
  return (
    <div className="space-y-3 pt-3 border-t border-gray-200">
      <h4 className="text-xs font-medium text-gray-700">Transform Configuration</h4>
      <div>
        <label className="block text-xs font-medium text-gray-700 mb-1">
          Expression
        </label>
        <textarea
          value={(config.expression as string) ?? ""}
          onChange={(e) => onChange({ ...config, expression: e.target.value })}
          placeholder="state.input | uppercase"
          rows={3}
          className="w-full px-3 py-2 text-sm font-mono border border-gray-300 rounded-md focus:outline-none focus:ring-2 focus:ring-primary focus:border-transparent"
        />
        <p className="mt-1 text-xs text-gray-500">
          Expression to transform the state
        </p>
      </div>
      <div>
        <label className="block text-xs font-medium text-gray-700 mb-1">
          Output Key
        </label>
        <Input
          value={(config.output_key as string) ?? ""}
          onChange={(e) => onChange({ ...config, output_key: e.target.value })}
          placeholder="result"
          className="text-sm"
        />
      </div>
    </div>
  );
}

// Output Node Config
function OutputNodeConfig({
  config,
  onChange,
}: {
  config: Record<string, unknown>;
  onChange: (config: Record<string, unknown>) => void;
}) {
  return (
    <div className="space-y-3 pt-3 border-t border-gray-200">
      <h4 className="text-xs font-medium text-gray-700">Output Configuration</h4>
      <div>
        <label className="block text-xs font-medium text-gray-700 mb-1">
          Output Mapping (JSON)
        </label>
        <textarea
          value={
            config.output_mapping
              ? JSON.stringify(config.output_mapping, null, 2)
              : ""
          }
          onChange={(e) => {
            try {
              const parsed = e.target.value ? JSON.parse(e.target.value) : {};
              onChange({ ...config, output_mapping: parsed });
            } catch {
              // Invalid JSON, don't update
            }
          }}
          placeholder='{"result": "state.final_output"}'
          rows={4}
          className="w-full px-3 py-2 text-sm font-mono border border-gray-300 rounded-md focus:outline-none focus:ring-2 focus:ring-primary focus:border-transparent"
        />
        <p className="mt-1 text-xs text-gray-500">
          Map state values to output keys
        </p>
      </div>
    </div>
  );
}

// Advanced Node Config (collapsible)
function AdvancedNodeConfig({
  timeoutMs,
  retryPolicy,
  onChangeTimeout,
  onChangeRetryPolicy,
}: {
  timeoutMs?: number;
  retryPolicy?: { max_attempts?: number; backoff_multiplier?: number };
  onChangeTimeout: (timeout: number | undefined) => void;
  onChangeRetryPolicy: (policy: { max_attempts?: number; backoff_multiplier?: number } | undefined) => void;
}) {
  const [isExpanded, setIsExpanded] = useState(false);

  const hasAdvancedConfig = timeoutMs !== undefined || retryPolicy !== undefined;

  return (
    <div className="pt-3 border-t border-gray-200">
      <button
        type="button"
        onClick={() => setIsExpanded(!isExpanded)}
        className="flex items-center gap-2 w-full text-left text-xs font-medium text-gray-500 hover:text-gray-700 transition-colors"
      >
        {isExpanded ? (
          <ChevronDown className="w-4 h-4" />
        ) : (
          <ChevronRight className="w-4 h-4" />
        )}
        <span className="uppercase tracking-wider">Advanced</span>
        {hasAdvancedConfig && !isExpanded && (
          <span className="ml-auto text-primary text-xs">configured</span>
        )}
      </button>

      {isExpanded && (
        <div className="mt-3 space-y-3">
          {/* Timeout */}
          <div>
            <label className="block text-xs font-medium text-gray-700 mb-1">
              Timeout (ms)
            </label>
            <Input
              type="number"
              value={timeoutMs ?? ""}
              onChange={(e) => {
                const val = e.target.value;
                onChangeTimeout(val ? parseInt(val, 10) : undefined);
              }}
              placeholder="30000"
              className="text-sm"
              min={0}
            />
            <p className="mt-1 text-xs text-gray-500">
              Max execution time before timeout (leave empty for default)
            </p>
          </div>

          {/* Retry Policy */}
          <div>
            <label className="block text-xs font-medium text-gray-700 mb-1">
              Max Retry Attempts
            </label>
            <Input
              type="number"
              value={retryPolicy?.max_attempts ?? ""}
              onChange={(e) => {
                const val = e.target.value;
                const newPolicy = {
                  ...retryPolicy,
                  max_attempts: val ? parseInt(val, 10) : undefined,
                };
                if (!newPolicy.max_attempts && !newPolicy.backoff_multiplier) {
                  onChangeRetryPolicy(undefined);
                } else {
                  onChangeRetryPolicy(newPolicy);
                }
              }}
              placeholder="3"
              className="text-sm"
              min={0}
              max={10}
            />
            <p className="mt-1 text-xs text-gray-500">
              Number of retry attempts on failure (0 = no retries)
            </p>
          </div>

          <div>
            <label className="block text-xs font-medium text-gray-700 mb-1">
              Backoff Multiplier
            </label>
            <Input
              type="number"
              value={retryPolicy?.backoff_multiplier ?? ""}
              onChange={(e) => {
                const val = e.target.value;
                const newPolicy = {
                  ...retryPolicy,
                  backoff_multiplier: val ? parseFloat(val) : undefined,
                };
                if (!newPolicy.max_attempts && !newPolicy.backoff_multiplier) {
                  onChangeRetryPolicy(undefined);
                } else {
                  onChangeRetryPolicy(newPolicy);
                }
              }}
              placeholder="2.0"
              className="text-sm"
              min={1}
              step={0.1}
            />
            <p className="mt-1 text-xs text-gray-500">
              Exponential backoff multiplier between retries
            </p>
          </div>
        </div>
      )}
    </div>
  );
}
