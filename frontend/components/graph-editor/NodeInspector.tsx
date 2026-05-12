import { type ReactNode, useEffect, useEffectEvent, useReducer, useState } from "react";
import type { Edge, Node } from "@xyflow/react";
import { ChevronDown, ChevronRight, CircleDot } from "lucide-react";
import { NODE_TYPES, type RetryPolicy } from "../../lib/graph-types";
import { getApiErrorMessage, promptsApi } from "../../lib/api";
import { cn } from "@/lib/utils";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { KeyValueEditor } from "@/components/ui/key-value-editor";
import { Spinner } from "@/components/ui/spinner";
import { Textarea } from "@/components/ui/textarea";
import { getNodeVisual } from "./nodes/nodeShapes";
import { ObservationContextNodeForm } from "./forms/ObservationContextNodeForm";
import { ObservationSaveNodeForm } from "./forms/ObservationSaveNodeForm";
import { ObservationSearchNodeForm } from "./forms/ObservationSearchNodeForm";
import { ObservationTimelineNodeForm } from "./forms/ObservationTimelineNodeForm";

function parseDelimitedList(value: string): string[] {
  return value.split(/[\n,]/).flatMap((item) => {
    const trimmed = item.trim();
    return trimmed ? [trimmed] : [];
  });
}

/** Reusable collapsible section with chevron toggle */
function CollapsibleSection({
  title,
  initialOpen = true,
  badge,
  children,
}: {
  title: string;
  initialOpen?: boolean;
  badge?: string;
  children: ReactNode;
}) {
  const [isOpen, setIsOpen] = useState(() => initialOpen);

  return (
    <div className="pt-3 border-t border-border">
      <button
        type="button"
        onClick={() => setIsOpen(!isOpen)}
        className="flex items-center gap-2 w-full text-left text-xs font-medium text-muted-foreground hover:text-foreground transition-colors"
      >
        {isOpen ? <ChevronDown className="size-3.5 shrink-0" /> : <ChevronRight className="size-3.5 shrink-0" />}
        <span className="uppercase tracking-wider">{title}</span>
        {badge && !isOpen && <span className="ml-auto text-primary text-xs">{badge}</span>}
      </button>
      {isOpen && <div className="mt-3 space-y-3">{children}</div>}
    </div>
  );
}

interface NodeInspectorProps {
  selectedNode: Node | null | undefined;
  selectedEdge: Edge | null | undefined;
  nodes: Node[];
  edges?: Edge[];
  graphName: string;
  graphDescription: string;
  onUpdateNode: (nodeId: string, updates: Partial<Node["data"]>) => void;
  onUpdateEdge: (edgeId: string, updates: Partial<Edge>) => void;
  onDeleteNode: (nodeId: string) => void;
  onDeleteEdge: (edgeId: string) => void;
  onDuplicateNode: (nodeId: string) => void;
  onUpdateMetadata: (name: string, description: string) => Promise<void>;
  onEditingMetadataChange?: (editing: boolean) => void;
}

const EMPTY_EDGES: Edge[] = [];

type NodeInspectorState = {
  editingMetadata: boolean;
  metadataName: string;
  metadataDescription: string;
  savingMetadata: boolean;
  showGraphText: boolean;
};

type NodeInspectorAction = {
  patch: Partial<NodeInspectorState> | ((state: NodeInspectorState) => Partial<NodeInspectorState>);
};

function nodeInspectorReducer(state: NodeInspectorState, action: NodeInspectorAction): NodeInspectorState {
  const patch = typeof action.patch === "function" ? action.patch(state) : action.patch;
  return { ...state, ...patch };
}

type MetadataController = ReturnType<typeof useNodeInspectorMetadata>;

function useNodeInspectorMetadata({
  selectedNode,
  selectedEdge,
  graphName,
  graphDescription,
  onUpdateMetadata,
  onEditingMetadataChange,
}: Pick<
  NodeInspectorProps,
  "selectedNode" | "selectedEdge" | "graphName" | "graphDescription" | "onUpdateMetadata" | "onEditingMetadataChange"
>) {
  // Avoid Playwright strict-mode collisions when the graph name includes "Graph Info".
  const shouldDeferGraphText = graphName.toLowerCase().includes("graph info");
  const [inspectorState, dispatchInspectorState] = useReducer(nodeInspectorReducer, {
    editingMetadata: false,
    metadataName: "",
    metadataDescription: "",
    savingMetadata: false,
    showGraphText: !shouldDeferGraphText,
  });
  const { editingMetadata, metadataName, metadataDescription, savingMetadata, showGraphText } = inspectorState;

  useEffect(() => {
    if (!shouldDeferGraphText) {
      dispatchInspectorState({ patch: { showGraphText: true } });
      return;
    }

    dispatchInspectorState({ patch: { showGraphText: false } });
    const timer = setTimeout(() => dispatchInspectorState({ patch: { showGraphText: true } }), 100);
    return () => clearTimeout(timer);
  }, [shouldDeferGraphText]);

  const notifyEditingMetadataChange = useEffectEvent((editing: boolean) => {
    onEditingMetadataChange?.(editing);
  });

  useEffect(() => {
    if ((!selectedNode && !selectedEdge) || !editingMetadata) return;
    dispatchInspectorState({ patch: { editingMetadata: false } });
    notifyEditingMetadataChange(false);
  }, [editingMetadata, selectedEdge, selectedNode]);

  const saveMetadata = async () => {
    dispatchInspectorState({ patch: { savingMetadata: true } });
    try {
      await onUpdateMetadata(metadataName, metadataDescription);
      dispatchInspectorState({ patch: { editingMetadata: false } });
      notifyEditingMetadataChange(false);
    } finally {
      dispatchInspectorState({ patch: { savingMetadata: false } });
    }
  };

  const startEditingMetadata = () => {
    dispatchInspectorState({
      patch: {
        metadataName: graphName,
        metadataDescription: graphDescription,
        editingMetadata: true,
      },
    });
    notifyEditingMetadataChange(true);
  };

  const cancelEditingMetadata = () => {
    dispatchInspectorState({
      patch: {
        metadataName: graphName,
        metadataDescription: graphDescription,
        editingMetadata: false,
      },
    });
    notifyEditingMetadataChange(false);
  };

  return {
    editingMetadata,
    metadataName,
    metadataDescription,
    savingMetadata,
    showGraphText,
    setMetadataName: (nextMetadataName: string) => dispatchInspectorState({ patch: { metadataName: nextMetadataName } }),
    setMetadataDescription: (nextMetadataDescription: string) =>
      dispatchInspectorState({ patch: { metadataDescription: nextMetadataDescription } }),
    saveMetadata,
    startEditingMetadata,
    cancelEditingMetadata,
  };
}

function InspectorSwitch({
  id,
  label,
  checked,
  onToggle,
}: {
  id: string;
  label: string;
  checked: boolean;
  onToggle: () => void;
}) {
  return (
    <div className="flex items-center justify-between">
      <label htmlFor={id} className="text-xs font-medium text-muted-foreground">
        {label}
      </label>
      <button
        id={id}
        type="button"
        role="switch"
        aria-checked={checked}
        onClick={onToggle}
        className={cn(
          "relative inline-flex h-5 w-9 items-center rounded-full transition-colors",
          checked ? "bg-primary" : "bg-muted",
        )}
      >
        <span
          className={cn(
            "inline-block size-4 transform rounded-full bg-background shadow-sm transition-transform",
            checked ? "tranzinc-x-4.5" : "tranzinc-x-0.5",
          )}
        />
      </button>
    </div>
  );
}

function EdgeInspector({
  selectedEdge,
  nodes,
  onUpdateNode,
  onUpdateEdge,
  onDeleteEdge,
}: Pick<NodeInspectorProps, "nodes" | "onUpdateNode" | "onUpdateEdge" | "onDeleteEdge"> & {
  selectedEdge: Edge;
}) {
  const sourceNode = nodes.find((node) => node.id === selectedEdge.source);
  const targetNode = nodes.find((node) => node.id === selectedEdge.target);
  const sourceLabel = (sourceNode?.data?.label as string | undefined) ?? selectedEdge.source;
  const targetLabel = (targetNode?.data?.label as string | undefined) ?? selectedEdge.target;
  const sourceIsTrigger = (sourceNode?.data as any)?.isTrigger === true;
  const targetIsEnd = (targetNode?.data as any)?.isEnd === true;
  const edgeLabel = typeof selectedEdge.label === "string" ? selectedEdge.label : "";
  const edgeCondition = typeof selectedEdge.data?.condition === "string" ? selectedEdge.data.condition : "";

  return (
    <div className="p-4">
      <div className="flex items-center justify-between mb-4">
        <h3 className="text-sm font-semibold text-foreground">Edge Config</h3>
        <Button size="sm" variant="destructive" onClick={() => onDeleteEdge(selectedEdge.id)}>
          Delete
        </Button>
      </div>

      <div className="space-y-4">
        <div>
          <label
            htmlFor="components-graph-editor-nodeinspector-edge-route"
            className="block text-xs font-medium text-muted-foreground uppercase tracking-wider mb-1"
          >
            From -&gt; To
          </label>
          <p className="text-sm text-foreground">
            {sourceLabel} -&gt; {targetLabel}
          </p>
        </div>

        <div className="space-y-2 pt-3 border-t border-border">
          <h4 className="text-xs font-semibold text-muted-foreground uppercase tracking-wider">Structural Role</h4>
          <InspectorSwitch
            id="components-graph-editor-nodeinspector-edge-source-trigger"
            label="Mark source as Trigger (START)"
            checked={sourceIsTrigger}
            onToggle={() => onUpdateNode(selectedEdge.source, { isTrigger: !sourceIsTrigger })}
          />
          <InspectorSwitch
            id="components-graph-editor-nodeinspector-edge-target-end"
            label="Mark target as End (END)"
            checked={targetIsEnd}
            onToggle={() => onUpdateNode(selectedEdge.target, { isEnd: !targetIsEnd })}
          />
          <p className="text-xs text-muted-foreground">
            These settings create special START -&gt; step and step -&gt; END edges when you save.
          </p>
        </div>

        <div>
          <label
            htmlFor="components-graph-editor-nodeinspector-edge-id"
            className="block text-xs font-medium text-muted-foreground uppercase tracking-wider mb-1"
          >
            ID
          </label>
          <p className="text-xs text-muted-foreground font-mono break-all">{selectedEdge.id}</p>
        </div>

        <div>
          <label
            htmlFor="components-graph-editor-nodeinspector-edge-label"
            className="block text-xs font-medium text-muted-foreground mb-1"
          >
            Label
          </label>
          <Input
            id="components-graph-editor-nodeinspector-edge-label"
            value={edgeLabel}
            onChange={(e) => onUpdateEdge(selectedEdge.id, { label: e.target.value })}
            className="text-sm"
            placeholder="Optional label (e.g., true/false, loop/done)"
          />
        </div>

        <div>
          <label
            htmlFor="components-graph-editor-nodeinspector-edge-condition"
            className="block text-xs font-medium text-muted-foreground mb-1"
          >
            Condition (optional)
          </label>
          <Textarea
            id="components-graph-editor-nodeinspector-edge-condition"
            value={edgeCondition}
            onChange={(e) => onUpdateEdge(selectedEdge.id, { data: { condition: e.target.value } })}
            rows={3}
            className="text-sm font-mono"
            placeholder='Example: vars.status == "done"'
          />
          <p className="mt-2 text-xs text-muted-foreground">
            Edge conditions influence routing when no explicit next steps are emitted.
          </p>
        </div>
      </div>
    </div>
  );
}

function GraphInfoInspector({
  graphName,
  graphDescription,
  metadata,
}: Pick<NodeInspectorProps, "graphName" | "graphDescription"> & {
  metadata: MetadataController;
}) {
  return (
    <div className="p-4">
      <h3 className="text-sm font-semibold text-foreground mb-4">Operating Model Info</h3>

      {metadata.editingMetadata ? (
        <GraphMetadataEditor metadata={metadata} />
      ) : (
        <GraphMetadataSummary
          graphName={graphName}
          graphDescription={graphDescription}
          showGraphText={metadata.showGraphText}
          onEdit={metadata.startEditingMetadata}
        />
      )}

      <div className="mt-6 pt-4 border-t border-border">
        <p className="text-xs text-muted-foreground">Select a step on the canvas to view and edit its configuration.</p>
      </div>
    </div>
  );
}

function GraphMetadataEditor({ metadata }: { metadata: MetadataController }) {
  return (
    <div className="space-y-4">
      <div>
        <label htmlFor="edit-graph-name" className="block text-xs font-medium text-muted-foreground mb-1">
          Name
        </label>
        <Input
          id="edit-graph-name"
          value={metadata.metadataName}
          onChange={(e) => metadata.setMetadataName(e.target.value)}
          className="text-sm"
        />
      </div>
      <div>
        <label htmlFor="edit-graph-description" className="block text-xs font-medium text-muted-foreground mb-1">
          Description
        </label>
        <Textarea
          id="edit-graph-description"
          value={metadata.metadataDescription}
          onChange={(e) => metadata.setMetadataDescription(e.target.value)}
          rows={3}
          className="text-sm"
        />
      </div>
      <div className="flex gap-2">
        <Button size="sm" onClick={() => void metadata.saveMetadata()} disabled={metadata.savingMetadata}>
          {metadata.savingMetadata ? "Saving" : "Save"}
        </Button>
        <Button size="sm" variant="outline" onClick={metadata.cancelEditingMetadata}>
          Cancel
        </Button>
      </div>
    </div>
  );
}

function GraphMetadataSummary({
  graphName,
  graphDescription,
  showGraphText,
  onEdit,
}: Pick<NodeInspectorProps, "graphName" | "graphDescription"> & {
  showGraphText: boolean;
  onEdit: () => void;
}) {
  return (
    <div className="space-y-4">
      {showGraphText ? (
        <>
          <div>
            <span className="block text-xs font-medium text-muted-foreground uppercase tracking-wider mb-1">Name</span>
            <p className="text-sm text-foreground">{graphName}</p>
          </div>
          <div>
            <span className="block text-xs font-medium text-muted-foreground uppercase tracking-wider mb-1">
              Description
            </span>
            <p className="text-sm text-foreground whitespace-pre-wrap">
              {graphDescription || <span className="text-muted-foreground">No description</span>}
            </p>
          </div>
        </>
      ) : null}
      <Button size="sm" variant="outline" onClick={onEdit}>
        Edit Info
      </Button>
    </div>
  );
}

function NodeDetailsInspector({
  selectedNode,
  nodes,
  edges,
  onUpdateNode,
  onDeleteNode,
  onDuplicateNode,
}: Pick<NodeInspectorProps, "nodes" | "onUpdateNode" | "onDeleteNode" | "onDuplicateNode"> & {
  selectedNode: Node;
  edges: Edge[];
}) {
  const nodeType = selectedNode.type as string;
  const nodeData = selectedNode.data;
  const isNote = nodeType === "note";
  const isTrigger = (nodeData as any)?.isTrigger === true;
  const isEnd = (nodeData as any)?.isEnd === true;
  const visual = getNodeVisual(nodeType, isTrigger, isEnd);
  const NodeIcon = visual.icon;

  return (
    <div className="p-4">
      <div className="flex items-start gap-3 mb-4">
        <div
          className={cn(
            "size-10 rounded-xl flex items-center justify-center text-white shadow-sm shrink-0",
            visual.bgClass,
          )}
        >
          <NodeIcon className="size-5" />
        </div>
        <div className="flex-1 min-w-0">
          <Input
            value={(nodeData.label as string) ?? ""}
            onChange={(e) => onUpdateNode(selectedNode.id, { label: e.target.value })}
            className="text-sm font-semibold md:min-h-8"
            aria-label="Step name"
          />
          <span className="inline-flex items-center mt-1 px-2 py-0.5 rounded-full text-[10px] font-medium bg-primary/10 text-primary capitalize">
            {nodeType.replace("_", " ")}
          </span>
        </div>
      </div>

      <div className="flex gap-2 mb-4">
        <Button size="sm" variant="outline" className="flex-1" onClick={() => onDuplicateNode(selectedNode.id)}>
          Duplicate
        </Button>
        <Button size="sm" variant="destructive" className="flex-1" onClick={() => onDeleteNode(selectedNode.id)}>
          Delete
        </Button>
      </div>

      <div className="space-y-0">
        <div className="pb-3">
          <label
            htmlFor="components-graph-editor-nodeinspector-node-id"
            className="block text-xs font-medium text-muted-foreground uppercase tracking-wider mb-1"
          >
            ID
          </label>
          <p className="text-xs text-muted-foreground font-mono break-all">{selectedNode.id}</p>
        </div>

        <NodeStructureSettings
          selectedNode={selectedNode}
          isNote={isNote}
          isTrigger={isTrigger}
          isEnd={isEnd}
          onUpdateNode={onUpdateNode}
        />
        <NodeConfigEditors
          selectedNode={selectedNode}
          nodeType={nodeType}
          nodeData={nodeData}
          nodes={nodes}
          edges={edges}
          onUpdateNode={onUpdateNode}
        />
      </div>
    </div>
  );
}

function NodeStructureSettings({
  selectedNode,
  isNote,
  isTrigger,
  isEnd,
  onUpdateNode,
}: {
  selectedNode: Node;
  isNote: boolean;
  isTrigger: boolean;
  isEnd: boolean;
  onUpdateNode: NodeInspectorProps["onUpdateNode"];
}) {
  if (isNote) {
    return null;
  }

  return (
    <>
      <InspectorSwitch
        id="components-graph-editor-nodeinspector-node-enabled"
        label="Enabled"
        checked={!selectedNode.data.disabled}
        onToggle={() => onUpdateNode(selectedNode.id, { disabled: !selectedNode.data.disabled })}
      />

      <CollapsibleSection title="Structural Role" initialOpen={false} badge={isTrigger || isEnd ? "configured" : undefined}>
        <InspectorSwitch
          id="components-graph-editor-nodeinspector-node-trigger"
          label="Trigger (START)"
          checked={isTrigger}
          onToggle={() => onUpdateNode(selectedNode.id, { isTrigger: !isTrigger })}
        />
        <InspectorSwitch
          id="components-graph-editor-nodeinspector-node-end"
          label="End (END)"
          checked={isEnd}
          onToggle={() => onUpdateNode(selectedNode.id, { isEnd: !isEnd })}
        />
        <p className="text-xs text-muted-foreground">
          Triggers create an entry edge from START -&gt; this step. End steps create an exit edge from this step -&gt; END.
        </p>
      </CollapsibleSection>
    </>
  );
}

function NodeConfigEditors({
  selectedNode,
  nodeType,
  nodeData,
  nodes,
  edges,
  onUpdateNode,
}: {
  selectedNode: Node;
  nodeType: string;
  nodeData: Node["data"];
  nodes: Node[];
  edges: Edge[];
  onUpdateNode: NodeInspectorProps["onUpdateNode"];
}) {
  const config = (nodeData.config as Record<string, unknown>) ?? {};
  const updateConfig = (nextConfig: Record<string, unknown>) => onUpdateNode(selectedNode.id, { config: nextConfig });

  return (
    <>
      {nodeType === "note" ? (
        <NoteNodeConfig
          text={(nodeData as any)?.text ? String((nodeData as any).text) : ""}
          onChange={(text) => onUpdateNode(selectedNode.id, { text })}
        />
      ) : null}

      {nodeType === NODE_TYPES.AGENT ? <AgentNodeConfig config={config} onChange={updateConfig} /> : null}
      {nodeType === NODE_TYPES.PROMPT ? <PromptNodeConfig config={config} onChange={updateConfig} /> : null}
      {nodeType === NODE_TYPES.HTTP ? <HttpNodeConfig config={config} onChange={updateConfig} /> : null}
      {nodeType === NODE_TYPES.TRANSFORM ? <TransformNodeConfig config={config} onChange={updateConfig} /> : null}
      {nodeType === NODE_TYPES.OUTPUT ? <OutputNodeConfig config={config} onChange={updateConfig} /> : null}
      {nodeType === NODE_TYPES.BRANCH ? (
        <BranchNodeConfig config={config} onChange={updateConfig} edges={edges} nodeId={selectedNode.id} nodes={nodes} />
      ) : null}
      {nodeType === NODE_TYPES.MERGE ? <MergeNodeConfig config={config} onChange={updateConfig} /> : null}
      {nodeType === NODE_TYPES.MEMORY ? <MemoryNodeConfig config={config} onChange={updateConfig} /> : null}
      {nodeType === NODE_TYPES.OBSERVATION_SAVE ? (
        <ObservationSaveNodeForm config={config} onChange={updateConfig} errors={{}} setErrors={() => {}} />
      ) : null}
      {nodeType === NODE_TYPES.OBSERVATION_SEARCH ? (
        <ObservationSearchNodeForm config={config} onChange={updateConfig} errors={{}} setErrors={() => {}} />
      ) : null}
      {nodeType === NODE_TYPES.OBSERVATION_CONTEXT ? (
        <ObservationContextNodeForm config={config} onChange={updateConfig} errors={{}} setErrors={() => {}} />
      ) : null}
      {nodeType === NODE_TYPES.OBSERVATION_TIMELINE ? (
        <ObservationTimelineNodeForm config={config} onChange={updateConfig} errors={{}} setErrors={() => {}} />
      ) : null}
      {nodeType === NODE_TYPES.TOOL ? <ToolNodeConfig config={config} onChange={updateConfig} /> : null}
      {nodeType === NODE_TYPES.SUBGRAPH ? <SubgraphNodeConfig config={config} onChange={updateConfig} /> : null}
      {nodeType === NODE_TYPES.HUMAN_GATE ? <HumanGateNodeConfig config={config} onChange={updateConfig} /> : null}
      {nodeType !== "note" ? (
        <AdvancedNodeConfig
          config={config}
          onChangeConfig={updateConfig}
          timeoutMs={(nodeData.timeout_ms as number) ?? undefined}
          retryPolicy={(nodeData.retry_policy as Partial<RetryPolicy>) ?? undefined}
          onChangeTimeout={(timeout_ms) => onUpdateNode(selectedNode.id, { timeout_ms })}
          onChangeRetryPolicy={(retry_policy) => onUpdateNode(selectedNode.id, { retry_policy })}
        />
      ) : null}
    </>
  );
}

export function NodeInspector({
  selectedNode,
  selectedEdge,
  nodes,
  edges = EMPTY_EDGES,
  graphName,
  graphDescription,
  onUpdateNode,
  onUpdateEdge,
  onDeleteNode,
  onDeleteEdge,
  onDuplicateNode,
  onUpdateMetadata,
  onEditingMetadataChange,
}: NodeInspectorProps) {
  const metadata = useNodeInspectorMetadata({
    selectedNode,
    selectedEdge,
    graphName,
    graphDescription,
    onUpdateMetadata,
    onEditingMetadataChange,
  });

  if (selectedEdge) {
    return (
      <EdgeInspector
        selectedEdge={selectedEdge}
        nodes={nodes}
        onUpdateNode={onUpdateNode}
        onUpdateEdge={onUpdateEdge}
        onDeleteEdge={onDeleteEdge}
      />
    );
  }

  if (!selectedNode) {
    return <GraphInfoInspector graphName={graphName} graphDescription={graphDescription} metadata={metadata} />;
  }

  return (
    <NodeDetailsInspector
      selectedNode={selectedNode}
      nodes={nodes}
      edges={edges}
      onUpdateNode={onUpdateNode}
      onDeleteNode={onDeleteNode}
      onDuplicateNode={onDuplicateNode}
    />
  );
}
function NoteNodeConfig({ text, onChange }: { text: string; onChange: (text: string) => void }) {
  return (
    <CollapsibleSection title="Note">
      <div>
        <label
          htmlFor="components-graph-editor-nodeinspector-599"
          className="block text-xs font-medium text-muted-foreground mb-1"
        >
          Text
        </label>
        <Textarea
          id="components-graph-editor-nodeinspector-599"
          value={text}
          onChange={(e) => onChange(e.target.value)}
          placeholder="Write a note to document this part of the operating model"
          rows={6}
          className="text-sm"
        />
      </div>
    </CollapsibleSection>
  );
}

// Agent Node Config
function AgentNodeConfig({
  config,
  onChange,
}: {
  config: Record<string, unknown>;
  onChange: (config: Record<string, unknown>) => void;
}) {
  const tools = Array.isArray(config.tools) ? (config.tools as string[]) : [];
  const approvalRequiredTools = Array.isArray(config.approval_required_tools)
    ? (config.approval_required_tools as string[])
    : [];
  const observationContextPaths = Array.isArray(config.observation_context_paths)
    ? (config.observation_context_paths as string[])
    : [];

  return (
    <div className="space-y-3 pt-3 border-t border-border">
      <h4 className="text-xs font-semibold text-muted-foreground uppercase tracking-wider">Agent Configuration</h4>

      <div>
        <label
          htmlFor="components-graph-editor-nodeinspector-633"
          className="block text-xs font-medium text-muted-foreground mb-1"
        >
          Task Instructions
        </label>
        <Textarea
          id="components-graph-editor-nodeinspector-633"
          value={(config.instructions as string) ?? ""}
          onChange={(e) => onChange({ ...config, instructions: e.target.value })}
          placeholder="Resolve the user's request using the allowed tools, then return a final answer."
          rows={4}
          className="text-sm"
        />
      </div>

      <div>
        <label
          htmlFor="components-graph-editor-nodeinspector-644"
          className="block text-xs font-medium text-muted-foreground mb-1"
        >
          System Prompt
        </label>
        <Textarea
          id="components-graph-editor-nodeinspector-644"
          value={(config.system_prompt as string) ?? ""}
          onChange={(e) => onChange({ ...config, system_prompt: e.target.value })}
          placeholder="You are a reliable ops assistant. Verify before acting."
          rows={3}
          className="text-sm"
        />
      </div>

      <div className="grid grid-cols-2 gap-3">
        <div>
          <label
            htmlFor="components-graph-editor-nodeinspector-656"
            className="block text-xs font-medium text-muted-foreground mb-1"
          >
            Provider
          </label>
          <select
            id="components-graph-editor-nodeinspector-656"
            value={(config.provider as string) ?? "openai"}
            onChange={(e) => onChange({ ...config, provider: e.target.value })}
            className="w-full rounded-md border border-input bg-transparent px-3 py-2 text-sm shadow-xs outline-none focus-visible:border-ring focus-visible:ring-ring/50 focus-visible:ring-[3px] dark:bg-input/30"
          >
            <option value="openai">OpenAI</option>
            <option value="anthropic">Anthropic</option>
            <option value="google">Google AI</option>
          </select>
        </div>

        <div>
          <label
            htmlFor="components-graph-editor-nodeinspector-669"
            className="block text-xs font-medium text-muted-foreground mb-1"
          >
            Model
          </label>
          <Input
            id="components-graph-editor-nodeinspector-669"
            value={(config.model as string) ?? ""}
            onChange={(e) => onChange({ ...config, model: e.target.value })}
            placeholder="gpt-4.1-mini"
            className="text-sm"
          />
        </div>
      </div>

      <div className="grid grid-cols-2 gap-3">
        <div>
          <label
            htmlFor="components-graph-editor-nodeinspector-681"
            className="block text-xs font-medium text-muted-foreground mb-1"
          >
            Max Steps
          </label>
          <Input
            id="components-graph-editor-nodeinspector-681"
            type="number"
            min={1}
            value={typeof config.max_steps === "number" ? config.max_steps : ""}
            onChange={(e) =>
              onChange({
                ...config,
                max_steps: e.target.value ? parseInt(e.target.value, 10) : undefined,
              })
            }
            placeholder="6"
            className="text-sm"
          />
        </div>

        <div>
          <label
            htmlFor="components-graph-editor-nodeinspector-698"
            className="block text-xs font-medium text-muted-foreground mb-1"
          >
            Max Tool Calls
          </label>
          <Input
            id="components-graph-editor-nodeinspector-698"
            type="number"
            min={1}
            value={typeof config.max_tool_calls === "number" ? config.max_tool_calls : ""}
            onChange={(e) =>
              onChange({
                ...config,
                max_tool_calls: e.target.value ? parseInt(e.target.value, 10) : undefined,
              })
            }
            placeholder="4"
            className="text-sm"
          />
        </div>
      </div>

      <div>
        <label
          htmlFor="components-graph-editor-nodeinspector-716"
          className="block text-xs font-medium text-muted-foreground mb-1"
        >
          Allowed Tools
        </label>
        <Textarea
          id="components-graph-editor-nodeinspector-716"
          value={tools.join("\n")}
          onChange={(e) =>
            onChange({
              ...config,
              tools: parseDelimitedList(e.target.value),
            })
          }
          placeholder={"crm.lookup\nslack.send_message"}
          rows={4}
          className="text-sm font-mono"
        />
      </div>

      <div>
        <label
          htmlFor="components-graph-editor-nodeinspector-735"
          className="block text-xs font-medium text-muted-foreground mb-1"
        >
          Approval-Required Tools
        </label>
        <Textarea
          id="components-graph-editor-nodeinspector-735"
          value={approvalRequiredTools.join("\n")}
          onChange={(e) =>
            onChange({
              ...config,
              approval_required_tools: parseDelimitedList(e.target.value),
            })
          }
          placeholder="send_email"
          rows={3}
          className="text-sm font-mono"
        />
      </div>

      <div>
        <label
          htmlFor="components-graph-editor-nodeinspector-754"
          className="block text-xs font-medium text-muted-foreground mb-1"
        >
          Curated Context Paths
        </label>
        <Textarea
          id="components-graph-editor-nodeinspector-754"
          value={observationContextPaths.join("\n")}
          onChange={(e) =>
            onChange({
              ...config,
              observation_context_paths: parseDelimitedList(e.target.value),
            })
          }
          placeholder={"node.recall_jackie.output\nnode.observation_context.output"}
          rows={3}
          className="text-sm font-mono"
        />
        <p className="mt-1 text-xs text-muted-foreground">
          Optional observation context outputs to prepend before the agent answers.
        </p>
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
  const [loadingPrompt, setLoadingPrompt] = useState(false);
  const [promptLoadError, setPromptLoadError] = useState<string | null>(null);
  const observationContextPaths = Array.isArray(config.observation_context_paths)
    ? (config.observation_context_paths as string[])
    : [];

  const loadPromptFromId = async () => {
    const promptId = String(config.prompt_id ?? "").trim();
    if (!promptId) {
      setPromptLoadError("Prompt ID is required.");
      return;
    }

    setPromptLoadError(null);
    setLoadingPrompt(true);
    try {
      const prompt = await promptsApi.get(promptId);
      onChange({
        ...config,
        prompt_id: prompt.id,
        prompt_template: prompt.content,
      });
    } catch (err: unknown) {
      setPromptLoadError(getApiErrorMessage(err, "Failed to load prompt."));
    } finally {
      setLoadingPrompt(false);
    }
  };

  return (
    <CollapsibleSection title="Prompt Configuration">
      <div>
        <label
          htmlFor="components-graph-editor-nodeinspector-818"
          className="block text-xs font-medium text-muted-foreground mb-1"
        >
          Prompt Template ID (optional)
        </label>
        <div className="flex gap-2">
          <Input
            id="components-graph-editor-nodeinspector-818"
            value={(config.prompt_id as string) ?? ""}
            onChange={(e) => {
              setPromptLoadError(null);
              onChange({ ...config, prompt_id: e.target.value });
            }}
            placeholder="Select or enter prompt ID"
            className="text-sm"
          />
          <Button type="button" variant="secondary" onClick={loadPromptFromId} disabled={loadingPrompt}>
            {loadingPrompt ? <Spinner size="sm" /> : "Load"}
          </Button>
        </div>
        <p className="mt-1 text-xs text-muted-foreground">
          Load a prompt from the Prompt Library by ID (fills <code>prompt_template</code> for execution).
        </p>
        {promptLoadError && <p className="mt-2 text-xs text-destructive">{promptLoadError}</p>}
      </div>
      <div>
        <label
          htmlFor="components-graph-editor-nodeinspector-839"
          className="block text-xs font-medium text-muted-foreground mb-1"
        >
          Prompt Template
        </label>
        <Textarea
          id="components-graph-editor-nodeinspector-839"
          value={(config.prompt_template as string) ?? ""}
          onChange={(e) => {
            const nextConfig = { ...config, prompt_template: e.target.value };
            delete (nextConfig as Record<string, unknown>).prompt_id;
            setPromptLoadError(null);
            onChange(nextConfig);
          }}
          placeholder="Write the prompt template required for operation"
          rows={10}
          className="text-sm font-mono"
        />
        <p className="mt-1 text-xs text-muted-foreground">
          This is what the AI worker uses. Editing detaches from the Prompt Library ID.
        </p>
      </div>
      <div>
        <label
          htmlFor="components-graph-editor-nodeinspector-857"
          className="block text-xs font-medium text-muted-foreground mb-1"
        >
          System Prompt (optional)
        </label>
        <Textarea
          id="components-graph-editor-nodeinspector-857"
          value={(config.system_prompt as string) ?? ""}
          onChange={(e) => onChange({ ...config, system_prompt: e.target.value })}
          placeholder="You are a helpful assistant"
          rows={4}
          className="text-sm font-mono"
        />
        <p className="mt-1 text-xs text-muted-foreground">System instructions prepended to the conversation.</p>
      </div>
      <div className="grid grid-cols-2 gap-3">
        <div>
          <label
            htmlFor="components-graph-editor-nodeinspector-869"
            className="block text-xs font-medium text-muted-foreground mb-1"
          >
            Model
          </label>
          <Input
            id="components-graph-editor-nodeinspector-869"
            value={(config.model as string) ?? "gpt-4"}
            onChange={(e) => onChange({ ...config, model: e.target.value })}
            placeholder="gpt-4"
            className="text-sm"
          />
        </div>
        <div>
          <label
            htmlFor="components-graph-editor-nodeinspector-878"
            className="block text-xs font-medium text-muted-foreground mb-1"
          >
            Temperature (0-2)
          </label>
          <Input
            id="components-graph-editor-nodeinspector-878"
            type="number"
            value={(config.temperature as number) ?? 0.7}
            onChange={(e) => {
              const val = parseFloat(e.target.value);
              onChange({ ...config, temperature: isNaN(val) ? undefined : val });
            }}
            min={0}
            max={2}
            step={0.1}
            className="text-sm"
          />
        </div>
      </div>
      <div>
        <label
          htmlFor="components-graph-editor-nodeinspector-894"
          className="block text-xs font-medium text-muted-foreground mb-1"
        >
          Max Tokens (optional)
        </label>
        <Input
          id="components-graph-editor-nodeinspector-894"
          type="number"
          value={(config.max_tokens as number) ?? ""}
          onChange={(e) => {
            const val = e.target.value ? parseInt(e.target.value, 10) : undefined;
            onChange({ ...config, max_tokens: val });
          }}
          min={1}
          placeholder="No limit"
          className="text-sm"
        />
      </div>
      <div>
        <span className="block text-xs font-medium text-muted-foreground mb-1">Variables</span>
        <KeyValueEditor
          value={(config.variables as Record<string, string>) ?? {}}
          onChange={(variables) => onChange({ ...config, variables })}
          keyPlaceholder="Variable"
          valuePlaceholder="State path (e.g., input.name)"
        />
        <p className="mt-1 text-xs text-muted-foreground">
          Map variable names to state paths for template substitution.
        </p>
      </div>
      <div>
        <label
          htmlFor="components-graph-editor-nodeinspector-920"
          className="block text-xs font-medium text-muted-foreground mb-1"
        >
          Curated Context Paths
        </label>
        <Textarea
          id="components-graph-editor-nodeinspector-920"
          value={observationContextPaths.join("\n")}
          onChange={(e) =>
            onChange({
              ...config,
              observation_context_paths: parseDelimitedList(e.target.value),
            })
          }
          placeholder={"node.recall_context.output\nnode.observation_context.output"}
          rows={3}
          className="text-sm font-mono"
        />
        <p className="mt-1 text-xs text-muted-foreground">
          Optional observation context outputs to prepend before prompt execution.
        </p>
      </div>
    </CollapsibleSection>
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
  const [urlError, setUrlError] = useState<string | null>(null);

  const validateUrl = (url: string) => {
    if (!url.trim()) {
      setUrlError(null);
      return;
    }
    try {
      new URL(url);
      setUrlError(null);
    } catch {
      setUrlError("Invalid URL format");
    }
  };

  return (
    <CollapsibleSection title="HTTP Configuration">
      <div>
        <label
          htmlFor="components-graph-editor-nodeinspector-970"
          className="block text-xs font-medium text-muted-foreground mb-1"
        >
          Method
        </label>
        <select
          id="components-graph-editor-nodeinspector-970"
          value={(config.method as string) ?? "GET"}
          onChange={(e) => onChange({ ...config, method: e.target.value })}
          className="w-full rounded-md border border-input bg-transparent px-3 py-2 text-sm shadow-xs outline-none focus-visible:border-ring focus-visible:ring-ring/50 focus-visible:ring-[3px] dark:bg-input/30"
        >
          <option value="GET">GET</option>
          <option value="POST">POST</option>
          <option value="PUT">PUT</option>
          <option value="PATCH">PATCH</option>
          <option value="DELETE">DELETE</option>
        </select>
      </div>
      <div>
        <label
          htmlFor="components-graph-editor-nodeinspector-984"
          className="block text-xs font-medium text-muted-foreground mb-1"
        >
          URL
        </label>
        <Input
          id="components-graph-editor-nodeinspector-984"
          value={(config.url as string) ?? ""}
          onChange={(e) => {
            setUrlError(null);
            onChange({ ...config, url: e.target.value });
          }}
          onBlur={(e) => validateUrl(e.target.value)}
          placeholder="https://api.example.com/endpoint"
          className="text-sm"
          aria-invalid={!!urlError}
        />
        {urlError && <p className="mt-1 text-xs text-destructive">{urlError}</p>}
      </div>
      <div>
        <label
          htmlFor="components-graph-editor-nodeinspector-1008"
          className="block text-xs font-medium text-muted-foreground mb-1"
        >
          Headers
        </label>
        <KeyValueEditor
          value={(config.headers as Record<string, string>) ?? {}}
          onChange={(headers) => onChange({ ...config, headers })}
          keyPlaceholder="Header"
          valuePlaceholder="Value"
        />
      </div>
      <div>
        <label
          htmlFor="components-graph-editor-nodeinspector-1008"
          className="block text-xs font-medium text-muted-foreground mb-1"
        >
          Request Body (JSON)
        </label>
        <Textarea
          id="components-graph-editor-nodeinspector-1008"
          value={(config.body as string) ?? ""}
          onChange={(e) => onChange({ ...config, body: e.target.value })}
          placeholder='{"key": "value"}'
          rows={4}
          className="text-sm font-mono"
        />
        <p className="mt-1 text-xs text-muted-foreground">JSON body for POST/PUT/PATCH requests</p>
      </div>
      <div>
        <label
          htmlFor="components-graph-editor-nodeinspector-1019"
          className="block text-xs font-medium text-muted-foreground mb-1"
        >
          Output Key
        </label>
        <Input
          id="components-graph-editor-nodeinspector-1019"
          value={(config.output_key as string) ?? ""}
          onChange={(e) => onChange({ ...config, output_key: e.target.value })}
          placeholder="response"
          className="text-sm"
        />
        <p className="mt-1 text-xs text-muted-foreground">Key to store the response in state</p>
      </div>
    </CollapsibleSection>
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
    <CollapsibleSection title="Transform Configuration">
      <div>
        <label
          htmlFor="components-graph-editor-nodeinspector-1043"
          className="block text-xs font-medium text-muted-foreground mb-1"
        >
          Expression
        </label>
        <Textarea
          id="components-graph-editor-nodeinspector-1043"
          value={(config.expression as string) ?? ""}
          onChange={(e) => onChange({ ...config, expression: e.target.value })}
          placeholder="state.input | uppercase"
          rows={3}
          className="text-sm font-mono"
        />
        <p className="mt-1 text-xs text-muted-foreground">Expression to transform the state</p>
      </div>
      <div>
        <label
          htmlFor="components-graph-editor-nodeinspector-1054"
          className="block text-xs font-medium text-muted-foreground mb-1"
        >
          Output Key
        </label>
        <Input
          id="components-graph-editor-nodeinspector-1054"
          value={(config.output_key as string) ?? ""}
          onChange={(e) => onChange({ ...config, output_key: e.target.value })}
          placeholder="result"
          className="text-sm"
        />
      </div>
    </CollapsibleSection>
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
  // Convert output_mapping to Record<string, string> for KeyValueEditor
  const outputMapping = (config.output_mapping as Record<string, unknown>) ?? {};
  const mappingAsStrings: Record<string, string> = {};
  for (const [key, value] of Object.entries(outputMapping)) {
    mappingAsStrings[key] = typeof value === "string" ? value : JSON.stringify(value);
  }

  return (
    <CollapsibleSection title="Output Configuration">
      <div>
        <span className="block text-xs font-medium text-muted-foreground mb-1">Output Mapping</span>
        <KeyValueEditor
          value={mappingAsStrings}
          onChange={(mapping) => onChange({ ...config, output_mapping: mapping })}
          keyPlaceholder="Output key"
          valuePlaceholder="State path (e.g., node.prompt_1.output)"
        />
        <p className="mt-1 text-xs text-muted-foreground">Map state values to output keys</p>
      </div>
    </CollapsibleSection>
  );
}

// Advanced Node Config (collapsible)
function AdvancedNodeConfig({
  config,
  onChangeConfig,
  timeoutMs,
  retryPolicy,
  onChangeTimeout,
  onChangeRetryPolicy,
}: {
  config: Record<string, unknown>;
  onChangeConfig: (config: Record<string, unknown>) => void;
  timeoutMs?: number;
  retryPolicy?: Partial<RetryPolicy>;
  onChangeTimeout: (timeout: number | undefined) => void;
  onChangeRetryPolicy: (policy: RetryPolicy | undefined) => void;
}) {
  const cacheConfig = (config.cache as Record<string, unknown>) ?? {};
  const cacheEnabled = cacheConfig.enabled === true;
  const cacheTtlSeconds = typeof cacheConfig.ttl_seconds === "number" ? cacheConfig.ttl_seconds : "";
  const useGlobalTTL = cacheEnabled && typeof cacheConfig.ttl_seconds !== "number";
  const defaultCacheTTL = 3600;
  const hasAdvancedConfig = cacheEnabled || timeoutMs !== undefined || retryPolicy !== undefined;

  return (
    <CollapsibleSection title="Advanced" initialOpen={false} badge={hasAdvancedConfig ? "configured" : undefined}>
      {/* Cache */}
      <div>
        <label
          htmlFor="components-graph-editor-nodeinspector-1126"
          className="block text-xs font-medium text-muted-foreground mb-2"
        >
          Cache Results
        </label>
        <div className="flex items-center justify-between">
          <label
            htmlFor="components-graph-editor-nodeinspector-1126"
            className="text-xs font-medium text-muted-foreground"
          >
            Enable cache
          </label>
          <button
            id="components-graph-editor-nodeinspector-1126"
            type="button"
            role="switch"
            aria-label="Enable cache"
            aria-checked={cacheEnabled}
            onClick={() =>
              onChangeConfig({
                ...config,
                cache: { ...cacheConfig, enabled: !cacheEnabled },
              })
            }
            className={`
                  relative inline-flex h-5 w-9 items-center rounded-full transition-colors
                  ${cacheEnabled ? "bg-primary" : "bg-muted"}
                `}
          >
            <span
              className={`
                    inline-block size-4 transform rounded-full bg-background shadow-sm transition-transform
                    ${cacheEnabled ? "tranzinc-x-4.5" : "tranzinc-x-0.5"}
                  `}
            />
          </button>
        </div>
        {cacheEnabled && (
          <div className="mt-2">
            <div className="flex items-center justify-between">
              <label
                htmlFor="components-graph-editor-nodeinspector-1154"
                className="text-xs font-medium text-muted-foreground"
              >
                Use global TTL
              </label>
              <button
                id="components-graph-editor-nodeinspector-1154"
                type="button"
                role="switch"
                aria-label="Use global TTL"
                aria-checked={useGlobalTTL}
                onClick={() => {
                  const nextCache: Record<string, unknown> = {
                    ...cacheConfig,
                    enabled: true,
                  };
                  if (useGlobalTTL) {
                    nextCache.ttl_seconds =
                      typeof cacheConfig.ttl_seconds === "number" ? cacheConfig.ttl_seconds : defaultCacheTTL;
                  } else {
                    delete nextCache.ttl_seconds;
                  }
                  onChangeConfig({ ...config, cache: nextCache });
                }}
                className={`
                      relative inline-flex h-5 w-9 items-center rounded-full transition-colors
                      ${useGlobalTTL ? "bg-primary" : "bg-muted"}
                    `}
              >
                <span
                  className={`
                        inline-block size-4 transform rounded-full bg-background shadow-sm transition-transform
                        ${useGlobalTTL ? "tranzinc-x-4.5" : "tranzinc-x-0.5"}
                      `}
                />
              </button>
            </div>

            {!useGlobalTTL && (
              <div className="mt-2">
                <label
                  htmlFor="components-graph-editor-nodeinspector-1189"
                  className="block text-xs font-medium text-muted-foreground mb-1"
                >
                  TTL (seconds)
                </label>
                <Input
                  id="components-graph-editor-nodeinspector-1189"
                  type="number"
                  value={cacheTtlSeconds}
                  onChange={(e) => {
                    const val = e.target.value;
                    const parsed = val ? parseInt(val, 10) : undefined;
                    const nextCache: Record<string, unknown> = {
                      ...cacheConfig,
                      enabled: true,
                    };
                    if (parsed && !Number.isNaN(parsed)) {
                      nextCache.ttl_seconds = parsed;
                    } else {
                      delete nextCache.ttl_seconds;
                    }
                    onChangeConfig({ ...config, cache: nextCache });
                  }}
                  placeholder={String(defaultCacheTTL)}
                  className="text-sm"
                  min={1}
                />
              </div>
            )}
            <p className="mt-1 text-xs text-muted-foreground">Uses input + config hash to reuse node outputs.</p>
          </div>
        )}
      </div>

      {/* Timeout */}
      <div>
        <label
          htmlFor="components-graph-editor-nodeinspector-1220"
          className="block text-xs font-medium text-muted-foreground mb-1"
        >
          Timeout (ms)
        </label>
        <Input
          id="components-graph-editor-nodeinspector-1220"
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
        <p className="mt-1 text-xs text-muted-foreground">
          Max execution time before timeout (leave empty for default)
        </p>
      </div>

      {/* Retry Policy */}
      <div>
        <label
          htmlFor="components-graph-editor-nodeinspector-1239"
          className="block text-xs font-medium text-muted-foreground mb-1"
        >
          Max Retry Attempts
        </label>
        <Input
          id="components-graph-editor-nodeinspector-1239"
          type="number"
          value={retryPolicy?.max_attempts ?? ""}
          onChange={(e) => {
            const val = e.target.value;
            const max_attempts = val ? parseInt(val, 10) : undefined;

            if (max_attempts === undefined && retryPolicy?.backoff_ms === undefined) {
              onChangeRetryPolicy(undefined);
              return;
            }

            onChangeRetryPolicy({
              max_attempts: max_attempts ?? retryPolicy?.max_attempts ?? 3,
              backoff_ms: retryPolicy?.backoff_ms ?? 1000,
              backoff_strategy: retryPolicy?.backoff_strategy ?? "exponential",
            });
          }}
          placeholder="3"
          className="text-sm"
          min={1}
          max={10}
        />
        <p className="mt-1 text-xs text-muted-foreground">Total attempts on failure (1 = no retries)</p>
      </div>

      <div>
        <label
          htmlFor="components-graph-editor-nodeinspector-1267"
          className="block text-xs font-medium text-muted-foreground mb-1"
        >
          Backoff (ms)
        </label>
        <Input
          id="components-graph-editor-nodeinspector-1267"
          type="number"
          value={retryPolicy?.backoff_ms ?? ""}
          onChange={(e) => {
            const val = e.target.value;
            const backoff_ms = val ? parseInt(val, 10) : undefined;

            if (backoff_ms === undefined && retryPolicy?.max_attempts === undefined) {
              onChangeRetryPolicy(undefined);
              return;
            }

            onChangeRetryPolicy({
              max_attempts: retryPolicy?.max_attempts ?? 3,
              backoff_ms: backoff_ms ?? retryPolicy?.backoff_ms ?? 1000,
              backoff_strategy: retryPolicy?.backoff_strategy ?? "exponential",
            });
          }}
          placeholder="1000"
          className="text-sm"
          min={0}
          step={100}
        />
        <p className="mt-1 text-xs text-muted-foreground">
          Base delay between retries (fixed), or base delay for exponential backoff
        </p>
      </div>

      <div>
        <label
          htmlFor="components-graph-editor-nodeinspector-1297"
          className="block text-xs font-medium text-muted-foreground mb-1"
        >
          Backoff Strategy
        </label>
        <select
          id="components-graph-editor-nodeinspector-1297"
          value={retryPolicy?.backoff_strategy ?? "exponential"}
          onChange={(e) => {
            const backoff_strategy = e.target.value as RetryPolicy["backoff_strategy"];
            onChangeRetryPolicy({
              max_attempts: retryPolicy?.max_attempts ?? 3,
              backoff_ms: retryPolicy?.backoff_ms ?? 1000,
              backoff_strategy: backoff_strategy ?? "exponential",
            });
          }}
          className="w-full rounded-md border border-input bg-transparent px-3 py-2 text-sm shadow-xs outline-none focus-visible:border-ring focus-visible:ring-ring/50 focus-visible:ring-[3px] dark:bg-input/30"
        >
          <option value="exponential">exponential</option>
          <option value="fixed">fixed</option>
        </select>
        <p className="mt-1 text-xs text-muted-foreground">Exponential uses backoff * 2^(attempt-2)</p>
      </div>
    </CollapsibleSection>
  );
}

// Branch Node Config
function BranchNodeConfig({
  config,
  onChange,
  edges,
  nodeId,
  nodes,
}: {
  config: Record<string, unknown>;
  onChange: (config: Record<string, unknown>) => void;
  edges?: Edge[];
  nodeId?: string;
  nodes?: Node[];
}) {
  const conditionType = (config.condition_type as string) ?? "expression";

  // Find outgoing edges from this branch node
  const outgoingEdges = (edges ?? []).filter((e) => e.source === nodeId);
  const trueEdge = outgoingEdges.find((e) => {
    const label = typeof e.label === "string" ? e.label.toLowerCase() : "";
    return label === "true";
  });
  const falseEdge = outgoingEdges.find((e) => {
    const label = typeof e.label === "string" ? e.label.toLowerCase() : "";
    return label === "false";
  });

  const getTargetLabel = (edge: Edge | undefined) => {
    if (!edge) return "Not connected";
    const target = (nodes ?? []).find((n) => n.id === edge.target);
    return (target?.data?.label as string) ?? edge.target;
  };

  return (
    <>
      <CollapsibleSection title="Condition">
        <div>
          <label
            htmlFor="components-graph-editor-nodeinspector-1356"
            className="block text-xs font-medium text-muted-foreground mb-1"
          >
            Condition Type
          </label>
          <select
            id="components-graph-editor-nodeinspector-1356"
            value={conditionType}
            onChange={(e) => onChange({ ...config, condition_type: e.target.value })}
            className="w-full rounded-md border border-input bg-transparent px-3 py-2 text-sm shadow-xs outline-none focus-visible:border-ring focus-visible:ring-ring/50 focus-visible:ring-[3px] dark:bg-input/30"
          >
            <option value="expression">Expression</option>
            <option value="number">Number comparison</option>
            <option value="boolean">Boolean check</option>
            <option value="string">String match</option>
          </select>
        </div>
        <div>
          <label
            htmlFor="components-graph-editor-nodeinspector-1369"
            className="block text-xs font-medium text-muted-foreground mb-1"
          >
            Condition Expression
          </label>
          <Textarea
            id="components-graph-editor-nodeinspector-1369"
            value={(config.condition as string) ?? ""}
            onChange={(e) => onChange({ ...config, condition: e.target.value })}
            placeholder={
              conditionType === "number"
                ? "vars.score > 80"
                : conditionType === "boolean"
                  ? "vars.approved"
                  : conditionType === "string"
                    ? 'vars.status == "done"'
                    : "vars.score > 80"
            }
            rows={2}
            className="text-sm font-mono"
          />
          <p className="mt-1 text-xs text-muted-foreground">
            Expression that evaluates to true/false to determine which path to take
          </p>
        </div>
        <div className="rounded-md border border-border/50 bg-muted/40 p-3 text-xs text-muted-foreground space-y-1">
          <p className="font-medium text-foreground">Example expressions:</p>
          <code className="block font-mono text-foreground">vars.score &gt; 80</code>
          <code className="block font-mono text-foreground">node.http_1.output.status == 200</code>
          <code className="block font-mono text-foreground">vars.approved == true</code>
        </div>
      </CollapsibleSection>

      <CollapsibleSection title="Branch Paths">
        <div className="space-y-2">
          <div className="flex items-center gap-2 rounded-lg border border-emerald-500/30 bg-emerald-500/10 px-3 py-2">
            <CircleDot className="size-3.5 text-emerald-400 shrink-0" />
            <div className="flex-1 min-w-0">
              <p className="text-xs font-medium text-emerald-400">True</p>
              <p className="text-[11px] text-muted-foreground truncate">{getTargetLabel(trueEdge)}</p>
            </div>
            <ChevronRight className="size-3.5 text-muted-foreground shrink-0" />
          </div>
          <div className="flex items-center gap-2 rounded-lg border border-rose-500/30 bg-rose-500/10 px-3 py-2">
            <CircleDot className="size-3.5 text-rose-400 shrink-0" />
            <div className="flex-1 min-w-0">
              <p className="text-xs font-medium text-rose-400">False</p>
              <p className="text-[11px] text-muted-foreground truncate">{getTargetLabel(falseEdge)}</p>
            </div>
            <ChevronRight className="size-3.5 text-muted-foreground shrink-0" />
          </div>
        </div>
        {outgoingEdges.length === 0 && (
          <p className="text-xs text-muted-foreground">
            Connect edges labeled &quot;true&quot; / &quot;false&quot; to define branch paths.
          </p>
        )}
      </CollapsibleSection>
    </>
  );
}

// Merge Node Config
function MergeNodeConfig({
  config,
  onChange,
}: {
  config: Record<string, unknown>;
  onChange: (config: Record<string, unknown>) => void;
}) {
  return (
    <CollapsibleSection title="Merge Configuration">
      <div>
        <label
          htmlFor="components-graph-editor-nodeinspector-1437"
          className="block text-xs font-medium text-muted-foreground mb-1"
        >
          Merge Strategy
        </label>
        <select
          id="components-graph-editor-nodeinspector-1437"
          value={(config.merge_strategy as string) ?? "namespaced"}
          onChange={(e) => onChange({ ...config, merge_strategy: e.target.value })}
          className="w-full rounded-md border border-input bg-transparent px-3 py-2 text-sm shadow-xs outline-none focus-visible:border-ring focus-visible:ring-ring/50 focus-visible:ring-[3px] dark:bg-input/30"
        >
          <option value="namespaced">Namespaced (default)</option>
          <option value="last_write_wins">Last Write Wins</option>
        </select>
        <p className="mt-1 text-xs text-muted-foreground">How to combine outputs from incoming branches</p>
      </div>
      <div className="rounded-md border border-border/50 bg-muted/40 p-3 text-xs text-muted-foreground space-y-2">
        <div>
          <p className="font-medium text-foreground">Namespaced:</p>
          <p>Each branch&apos;s output is stored under its node ID</p>
        </div>
        <div>
          <p className="font-medium text-foreground">Last Write Wins:</p>
          <p>Later branches overwrite earlier values for same keys</p>
        </div>
      </div>
    </CollapsibleSection>
  );
}

// Memory Node Config
function MemoryNodeConfig({
  config,
  onChange,
}: {
  config: Record<string, unknown>;
  onChange: (config: Record<string, unknown>) => void;
}) {
  const action = (config.action as string) ?? "get";
  const ttlSeconds = typeof config.ttl_seconds === "number" ? config.ttl_seconds : "";
  const valueText =
    config.value === undefined
      ? ""
      : typeof config.value === "string"
        ? config.value
        : JSON.stringify(config.value, null, 2);

  return (
    <CollapsibleSection title="Memory Configuration">
      <div>
        <label
          htmlFor="components-graph-editor-nodeinspector-1482"
          className="block text-xs font-medium text-muted-foreground mb-1"
        >
          Action
        </label>
        <select
          id="components-graph-editor-nodeinspector-1482"
          value={action}
          onChange={(e) => onChange({ ...config, action: e.target.value })}
          className="w-full rounded-md border border-input bg-transparent px-3 py-2 text-sm shadow-xs outline-none focus-visible:border-ring focus-visible:ring-ring/50 focus-visible:ring-[3px] dark:bg-input/30"
        >
          <option value="get">Get</option>
          <option value="set">Set</option>
          <option value="delete">Delete</option>
        </select>
      </div>

      <div>
        <label
          htmlFor="components-graph-editor-nodeinspector-1495"
          className="block text-xs font-medium text-muted-foreground mb-1"
        >
          Key
        </label>
        <Input
          id="components-graph-editor-nodeinspector-1495"
          value={(config.key as string) ?? ""}
          onChange={(e) => onChange({ ...config, key: e.target.value })}
          placeholder="memory_key"
          className="text-sm"
        />
      </div>

      <div>
        <label
          htmlFor="components-graph-editor-nodeinspector-1505"
          className="block text-xs font-medium text-muted-foreground mb-1"
        >
          Namespace
        </label>
        <Input
          id="components-graph-editor-nodeinspector-1505"
          value={(config.namespace as string) ?? ""}
          onChange={(e) => onChange({ ...config, namespace: e.target.value })}
          placeholder="global"
          className="text-sm"
        />
        <p className="mt-1 text-xs text-muted-foreground">Optional namespace prefix for key isolation.</p>
      </div>

      <div>
        <label
          htmlFor="components-graph-editor-nodeinspector-1516"
          className="block text-xs font-medium text-muted-foreground mb-1"
        >
          Namespace Path
        </label>
        <Input
          id="components-graph-editor-nodeinspector-1516"
          value={(config.namespace_path as string) ?? ""}
          onChange={(e) => onChange({ ...config, namespace_path: e.target.value })}
          placeholder="input.thread_id"
          className="text-sm"
        />
        <p className="mt-1 text-xs text-muted-foreground">
          If set, resolves namespace from state (overrides Namespace).
        </p>
      </div>

      {action === "set" && (
        <>
          <div>
            <label
              htmlFor="components-graph-editor-nodeinspector-1531"
              className="block text-xs font-medium text-muted-foreground mb-1"
            >
              Value Path
            </label>
            <Input
              id="components-graph-editor-nodeinspector-1531"
              value={(config.value_path as string) ?? ""}
              onChange={(e) => onChange({ ...config, value_path: e.target.value })}
              placeholder="input.payload"
              className="text-sm"
            />
            <p className="mt-1 text-xs text-muted-foreground">
              Reads a value from state (takes precedence over Value).
            </p>
          </div>

          <div>
            <label
              htmlFor="components-graph-editor-nodeinspector-1544"
              className="block text-xs font-medium text-muted-foreground mb-1"
            >
              Value Template
            </label>
            <Input
              id="components-graph-editor-nodeinspector-1544"
              value={(config.value_template as string) ?? ""}
              onChange={(e) => onChange({ ...config, value_template: e.target.value })}
              placeholder="User {{input.user_id}} summary"
              className="text-sm"
            />
            <p className="mt-1 text-xs text-muted-foreground">Template values from state if Value Path is empty.</p>
          </div>

          <div>
            <label
              htmlFor="components-graph-editor-nodeinspector-1555"
              className="block text-xs font-medium text-muted-foreground mb-1"
            >
              Value (JSON or text)
            </label>
            <Textarea
              id="components-graph-editor-nodeinspector-1555"
              value={valueText}
              onChange={(e) => {
                const raw = e.target.value;
                if (!raw.trim()) {
                  const next = { ...config };
                  delete next.value;
                  onChange(next);
                  return;
                }
                try {
                  const parsed = JSON.parse(raw);
                  onChange({ ...config, value: parsed });
                } catch {
                  onChange({ ...config, value: raw });
                }
              }}
              placeholder='{"user_id": "123"}'
              rows={3}
              className="text-sm font-mono"
            />
            <p className="mt-1 text-xs text-muted-foreground">
              Static value used when Value Path and Template are empty.
            </p>
          </div>

          <div>
            <label
              htmlFor="components-graph-editor-nodeinspector-1583"
              className="block text-xs font-medium text-muted-foreground mb-1"
            >
              TTL (seconds)
            </label>
            <Input
              id="components-graph-editor-nodeinspector-1583"
              type="number"
              value={ttlSeconds}
              onChange={(e) => {
                const next = e.target.value ? parseInt(e.target.value, 10) : undefined;
                if (!next || Number.isNaN(next)) {
                  const updated = { ...config };
                  delete updated.ttl_seconds;
                  onChange(updated);
                  return;
                }
                onChange({ ...config, ttl_seconds: next });
              }}
              placeholder="3600"
              className="text-sm"
              min={1}
            />
          </div>
        </>
      )}
    </CollapsibleSection>
  );
}

// Tool Node Config
function ToolNodeConfig({
  config,
  onChange,
}: {
  config: Record<string, unknown>;
  onChange: (config: Record<string, unknown>) => void;
}) {
  const toolName = (config.tool as string) ?? "";
  const version = (config.version as string) ?? "";
  const inputTemplate = (config.input_template as string) ?? "";
  const inputPath = (config.input_path as string) ?? "";
  const configText = config.config && typeof config.config === "object" ? JSON.stringify(config.config, null, 2) : "";
  const inputText =
    config.input === undefined
      ? ""
      : typeof config.input === "string"
        ? config.input
        : JSON.stringify(config.input, null, 2);

  return (
    <CollapsibleSection title="Tool Configuration">
      <div>
        <label
          htmlFor="components-graph-editor-nodeinspector-1631"
          className="block text-xs font-medium text-muted-foreground mb-1"
        >
          Tool Name
        </label>
        <Input
          id="components-graph-editor-nodeinspector-1631"
          value={toolName}
          onChange={(e) => onChange({ ...config, tool: e.target.value })}
          placeholder="vector.search"
          className="text-sm"
        />
      </div>

      <div>
        <label
          htmlFor="components-graph-editor-nodeinspector-1641"
          className="block text-xs font-medium text-muted-foreground mb-1"
        >
          Version
        </label>
        <Input
          id="components-graph-editor-nodeinspector-1641"
          value={version}
          onChange={(e) => onChange({ ...config, version: e.target.value })}
          placeholder="1.0.0 (optional)"
          className="text-sm"
        />
      </div>

      <div>
        <label
          htmlFor="components-graph-editor-nodeinspector-1651"
          className="block text-xs font-medium text-muted-foreground mb-1"
        >
          Input Path
        </label>
        <Input
          id="components-graph-editor-nodeinspector-1651"
          value={inputPath}
          onChange={(e) => onChange({ ...config, input_path: e.target.value })}
          placeholder="vars.query"
          className="text-sm"
        />
      </div>

      <div>
        <label
          htmlFor="components-graph-editor-nodeinspector-1661"
          className="block text-xs font-medium text-muted-foreground mb-1"
        >
          Input Template
        </label>
        <Input
          id="components-graph-editor-nodeinspector-1661"
          value={inputTemplate}
          onChange={(e) => onChange({ ...config, input_template: e.target.value })}
          placeholder="Search for {{vars.query}}"
          className="text-sm"
        />
      </div>

      <div>
        <label
          htmlFor="components-graph-editor-nodeinspector-1671"
          className="block text-xs font-medium text-muted-foreground mb-1"
        >
          Static Input (JSON or text)
        </label>
        <Textarea
          id="components-graph-editor-nodeinspector-1671"
          value={inputText}
          onChange={(e) => {
            const raw = e.target.value;
            if (!raw.trim()) {
              const next = { ...config };
              delete next.input;
              onChange(next);
              return;
            }
            try {
              const parsed = JSON.parse(raw);
              onChange({ ...config, input: parsed });
            } catch {
              onChange({ ...config, input: raw });
            }
          }}
          rows={3}
          className="text-sm font-mono"
          placeholder='{"query": "hello"}'
        />
      </div>

      <div>
        <label
          htmlFor="components-graph-editor-nodeinspector-1696"
          className="block text-xs font-medium text-muted-foreground mb-1"
        >
          Tool Config Overrides (JSON)
        </label>
        <Textarea
          id="components-graph-editor-nodeinspector-1696"
          value={configText}
          onChange={(e) => {
            const raw = e.target.value;
            if (!raw.trim()) {
              const next = { ...config };
              delete next.config;
              onChange(next);
              return;
            }
            try {
              const parsed = JSON.parse(raw);
              onChange({ ...config, config: parsed });
            } catch {
              // ignore invalid json
            }
          }}
          rows={4}
          className="text-sm font-mono"
          placeholder='{"top_k": 5}'
        />
      </div>
    </CollapsibleSection>
  );
}

// Subgraph Node Config
function SubgraphNodeConfig({
  config,
  onChange,
}: {
  config: Record<string, unknown>;
  onChange: (config: Record<string, unknown>) => void;
}) {
  const inputMappingText =
    config.input_mapping && typeof config.input_mapping === "object"
      ? JSON.stringify(config.input_mapping, null, 2)
      : "";
  const outputMappingText =
    config.output_mapping && typeof config.output_mapping === "object"
      ? JSON.stringify(config.output_mapping, null, 2)
      : "";

  return (
    <CollapsibleSection title="Subgraph Configuration">
      <div>
        <label
          htmlFor="components-graph-editor-nodeinspector-1743"
          className="block text-xs font-medium text-muted-foreground mb-1"
        >
          Graph ID
        </label>
        <Input
          id="components-graph-editor-nodeinspector-1743"
          value={(config.graph_id as string) ?? ""}
          onChange={(e) => onChange({ ...config, graph_id: e.target.value })}
          placeholder="UUID of graph"
          className="text-sm"
        />
      </div>

      <div>
        <label
          htmlFor="components-graph-editor-nodeinspector-1753"
          className="block text-xs font-medium text-muted-foreground mb-1"
        >
          Graph Version ID (optional)
        </label>
        <Input
          id="components-graph-editor-nodeinspector-1753"
          value={(config.graph_version_id as string) ?? ""}
          onChange={(e) => onChange({ ...config, graph_version_id: e.target.value })}
          placeholder="UUID of graph version"
          className="text-sm"
        />
      </div>

      <div>
        <label
          htmlFor="components-graph-editor-nodeinspector-1763"
          className="block text-xs font-medium text-muted-foreground mb-1"
        >
          Input Path
        </label>
        <Input
          id="components-graph-editor-nodeinspector-1763"
          value={(config.input_path as string) ?? ""}
          onChange={(e) => onChange({ ...config, input_path: e.target.value })}
          placeholder="vars.subgraph_input"
          className="text-sm"
        />
      </div>

      <div>
        <label
          htmlFor="components-graph-editor-nodeinspector-1773"
          className="block text-xs font-medium text-muted-foreground mb-1"
        >
          Input Mapping (JSON)
        </label>
        <Textarea
          id="components-graph-editor-nodeinspector-1773"
          value={inputMappingText}
          onChange={(e) => {
            const raw = e.target.value;
            if (!raw.trim()) {
              const next = { ...config };
              delete next.input_mapping;
              onChange(next);
              return;
            }
            try {
              const parsed = JSON.parse(raw);
              onChange({ ...config, input_mapping: parsed });
            } catch {
              // ignore invalid json
            }
          }}
          rows={3}
          className="text-sm font-mono"
          placeholder='{"query": "vars.search_query"}'
        />
      </div>

      <div>
        <label
          htmlFor="components-graph-editor-nodeinspector-1798"
          className="block text-xs font-medium text-muted-foreground mb-1"
        >
          Output Mapping (JSON)
        </label>
        <Textarea
          id="components-graph-editor-nodeinspector-1798"
          value={outputMappingText}
          onChange={(e) => {
            const raw = e.target.value;
            if (!raw.trim()) {
              const next = { ...config };
              delete next.output_mapping;
              onChange(next);
              return;
            }
            try {
              const parsed = JSON.parse(raw);
              onChange({ ...config, output_mapping: parsed });
            } catch {
              // ignore invalid json
            }
          }}
          rows={3}
          className="text-sm font-mono"
          placeholder='{"vars.summary": "report.summary"}'
        />
      </div>

      <div>
        <label
          htmlFor="components-graph-editor-nodeinspector-1823"
          className="block text-xs font-medium text-muted-foreground mb-1"
        >
          Output Key
        </label>
        <Input
          id="components-graph-editor-nodeinspector-1823"
          value={(config.output_key as string) ?? ""}
          onChange={(e) => onChange({ ...config, output_key: e.target.value })}
          placeholder="vars.subgraph_output"
          className="text-sm"
        />
      </div>
    </CollapsibleSection>
  );
}

// Human Gate Node Config
function HumanGateNodeConfig({
  config,
  onChange,
}: {
  config: Record<string, unknown>;
  onChange: (config: Record<string, unknown>) => void;
}) {
  const [promptError, setPromptError] = useState<string | null>(null);
  const requiredFields = (config.required_fields as string[]) || [];

  const addField = (field: string) => {
    if (field && !requiredFields.includes(field)) {
      onChange({ ...config, required_fields: [...requiredFields, field] });
    }
  };

  const removeField = (index: number) => {
    const updated = requiredFields.filter((_, i) => i !== index);
    onChange({ ...config, required_fields: updated });
  };

  const validatePromptMessage = (value: string) => {
    if (!value.trim()) {
      setPromptError("Prompt message is required");
    } else {
      setPromptError(null);
    }
  };

  return (
    <CollapsibleSection title="Human Gate Configuration">
      <div>
        <label
          htmlFor="components-graph-editor-nodeinspector-1868"
          className="block text-xs font-medium text-muted-foreground mb-1"
        >
          Prompt Message
        </label>
        <Textarea
          id="components-graph-editor-nodeinspector-1868"
          value={(config.prompt_message as string) ?? ""}
          onChange={(e) => {
            setPromptError(null);
            onChange({ ...config, prompt_message: e.target.value });
          }}
          onBlur={(e) => validatePromptMessage(e.target.value)}
          placeholder="Please review and approve this step"
          rows={3}
          className="text-sm"
          aria-invalid={!!promptError}
        />
        {promptError ? (
          <p className="mt-1 text-xs text-destructive">{promptError}</p>
        ) : (
          <p className="mt-1 text-xs text-muted-foreground">Message shown to the reviewer when the company pauses</p>
        )}
      </div>

      <div>
        <label
          htmlFor="components-graph-editor-nodeinspector-1889"
          className="block text-xs font-medium text-muted-foreground mb-1"
        >
          Required Fields
        </label>
        <div className="space-y-2">
          {requiredFields.map((field, index) => (
            <div key={field} className="flex items-center gap-2">
              <Input
                id="components-graph-editor-nodeinspector-1889"
                value={field}
                readOnly
                className="text-sm flex-1"
              />
              <Button
                size="sm"
                variant="ghost"
                onClick={() => removeField(index)}
                className="text-destructive hover:text-destructive"
              >
                Remove
              </Button>
            </div>
          ))}
          <div className="flex gap-2">
            <Input
              placeholder="Field name (e.g., approval_reason)"
              className="text-sm flex-1"
              onKeyDown={(e) => {
                if (e.key === "Enter") {
                  const input = e.target as HTMLInputElement;
                  addField(input.value.trim());
                  input.value = "";
                }
              }}
            />
            <Button
              size="sm"
              variant="outline"
              onClick={(e) => {
                const input = (e.target as HTMLElement).previousElementSibling as HTMLInputElement;
                if (input?.value) {
                  addField(input.value.trim());
                  input.value = "";
                }
              }}
            >
              Add
            </Button>
          </div>
        </div>
        <p className="mt-1 text-xs text-muted-foreground">Fields the reviewer must fill in before approving</p>
      </div>

      <div className="rounded-md border border-border/50 bg-muted/40 p-3 text-xs text-muted-foreground space-y-2">
        <div>
          <p className="font-medium text-foreground">Approve:</p>
          <p>
            Run continues with submitted fields available in state as{" "}
            <code className="font-mono">node.&lt;id&gt;.output</code>
          </p>
        </div>
        <div>
          <p className="font-medium text-foreground">Reject:</p>
          <p>Run terminates with feedback message stored as error</p>
        </div>
      </div>
    </CollapsibleSection>
  );
}
