"use client";

import {
  useCallback,
  useEffect,
  useEffectEvent,
  useReducer,
  useRef,
  useState,
  type Ref,
  type SetStateAction,
} from "react";
import Link from "next/link";
import { useRouter } from "next/router";
import {
  ReactFlow,
  Controls,
  Background,
  MiniMap,
  useNodesState,
  useEdgesState,
  addEdge,
  SelectionMode,
  MarkerType,
  type OnNodeDrag,
  type Connection,
  type Node,
  type Edge,
  type NodeTypes,
  type EdgeTypes,
  BackgroundVariant,
  Panel,
} from "@xyflow/react";
import { Brain, Play, Plus, Save as SaveIcon, LayoutGrid, Redo2, Undo2, Wand2 } from "lucide-react";

import { WizardProvider, useWizard } from "@/contexts/WizardContext";
import { ValidationProvider, useValidation } from "@/contexts/ValidationContext";
import { AgentWizard, type AgentWizardCompletePayload } from "./wizard";
import { ValidationOverlay, ValidationStatusBar } from "./validation";

import type { GraphJson, NodeType, NodeConfig } from "../../lib/graph-types";
import { NODE_TYPES, PHASE2_NODE_TYPES, createEmptyGraphJson, isValidNodeType } from "../../lib/graph-types";
import { graphJsonToReactFlow, reactFlowToGraphJson } from "../../lib/graph-conversion";
import { getLayoutedElements } from "../../lib/graph-layout";
import {
  getApiErrorMessage,
  graphsApi,
  marketplaceApi,
  runsApi,
  type AgentTrace,
  type MarketplacePackage,
  type NodeRunItem,
  type RunDetail,
} from "../../lib/api";
import { formatJsonForDisplay } from "../../lib/json";
import { canAddMarketplacePackageToEditor, getMarketplacePackageReason } from "../../lib/marketplace-runtime";
import { showError, showInfo, showSuccess } from "../../lib/toast";
import { ERROR_FALLBACKS } from "../../lib/error-messages";
import { newClientCommandId, stableClientCommandId } from "../../lib/idempotency";
import {
  GRAPH_EDITOR_SNAP_GRID,
  getConnectionFeedback,
  snapPositionToGrid,
  validateGraphConnection,
} from "../../lib/graph-editor-interactions";
import {
  AGENT_OUTPUT_PLACEHOLDER,
  OBSERVATION_CONTEXT_PLACEHOLDER,
  type AgentWizardBlueprint,
} from "../../lib/agent-wizard-presets";
import { NodePalette } from "./NodePalette";
import { NodeInspector } from "./NodeInspector";
import { GraphNode as GraphNodeComponent } from "./nodes/GraphNode";
import { NoteNode as NoteNodeComponent } from "./nodes/NoteNode";
import { PromptNodeWizardDialog } from "./PromptNodeWizardDialog";
import { NodeConfigDialog } from "./NodeConfigDialog";
import { MemoryConfigDialog } from "./dialogs/MemoryConfigDialog";
import { getNodeFormComponent, getNodeTypeInfo } from "./forms/node-form-registry";
import { TypedEdge } from "./TypedEdge";
import { QuickToolBar } from "./QuickToolBar";
import { useEdgeTypes } from "@/hooks/useEdgeTypes";
import { AgentTracePanel } from "../runs/AgentTracePanel";

const NOTE_NODE_TYPE = "note";

const getNodeRunAgentTrace = (nodeRun: NodeRunItem | null): AgentTrace | null => {
  if (!nodeRun || String(nodeRun.node_type) !== "agent") {
    return null;
  }
  if (nodeRun.agent_trace && typeof nodeRun.agent_trace === "object") {
    return nodeRun.agent_trace;
  }
  const nestedOutput = nodeRun.output_json?.output;
  if (nestedOutput && typeof nestedOutput === "object") {
    return nestedOutput as AgentTrace;
  }
  return null;
};

// Custom edge types for React Flow
const edgeTypes: EdgeTypes = {
  typed: TypedEdge,
};

// Custom node types for React Flow
const nodeTypes: NodeTypes = {
  [NODE_TYPES.AGENT]: GraphNodeComponent,
  [NODE_TYPES.PROMPT]: GraphNodeComponent,
  [NODE_TYPES.HTTP]: GraphNodeComponent,
  [NODE_TYPES.TRANSFORM]: GraphNodeComponent,
  [NODE_TYPES.OUTPUT]: GraphNodeComponent,
  [NODE_TYPES.BRANCH]: GraphNodeComponent,
  [NODE_TYPES.MERGE]: GraphNodeComponent,
  [NODE_TYPES.HUMAN_GATE]: GraphNodeComponent,
  [NODE_TYPES.MEMORY]: GraphNodeComponent,
  [NODE_TYPES.OBSERVATION_SAVE]: GraphNodeComponent,
  [NODE_TYPES.OBSERVATION_SEARCH]: GraphNodeComponent,
  [NODE_TYPES.OBSERVATION_CONTEXT]: GraphNodeComponent,
  [NODE_TYPES.OBSERVATION_TIMELINE]: GraphNodeComponent,
  [NODE_TYPES.TOOL]: GraphNodeComponent,
  [NODE_TYPES.SUBGRAPH]: GraphNodeComponent,
  [NOTE_NODE_TYPE]: NoteNodeComponent,
};

interface GraphEditorProps {
  graphId: string;
  graphName: string;
  graphDescription: string;
  initialGraphJson: GraphJson | null;
  currentVersion: number | null;
  currentVersionId: string | null;
  availableVersions: Array<{ id: string; version: number }>;
  onSelectVersion: (versionId: string) => Promise<void>;
  loadingVersion?: boolean;
  onSave: (graphJson: GraphJson) => Promise<void>;
  onUpdateMetadata: (name: string, description: string) => Promise<void>;
  saving: boolean;
}

type GraphEditorViewport = { x: number; y: number; zoom: number } | undefined;

type GraphEditorUiState = {
  selectedNodeId: string | null;
  selectedEdgeId: string | null;
  isDirty: boolean;
  isEditingMetadata: boolean;
  startingRun: boolean;
  overlayRun: RunDetail | null;
  overlayRunLoading: boolean;
  overlayRunRefreshing: boolean;
  overlayRunError: string | null;
  overlayCanceling: boolean;
  promptWizardOpen: boolean;
  promptWizardSourceNodeId: string | null;
  configDialogOpen: boolean;
  configDialogNodeType: NodeType | null;
  configDialogSourceNodeId: string | null;
  configDialogInitialConfig: NodeConfig;
  configDialogInitialLabel: string | null;
  memoryConfigOpen: boolean;
  marketplaceNodes: MarketplacePackage[];
  currentViewport: GraphEditorViewport;
};

type GraphEditorUiAction = {
  patch: Partial<GraphEditorUiState> | ((state: GraphEditorUiState) => Partial<GraphEditorUiState>);
};

function graphEditorUiReducer(state: GraphEditorUiState, action: GraphEditorUiAction): GraphEditorUiState {
  const patch = typeof action.patch === "function" ? action.patch(state) : action.patch;
  return { ...state, ...patch };
}

function createInitialGraphEditorUiState(currentViewport: GraphEditorViewport): GraphEditorUiState {
  return {
    selectedNodeId: null,
    selectedEdgeId: null,
    isDirty: false,
    isEditingMetadata: false,
    startingRun: false,
    overlayRun: null,
    overlayRunLoading: false,
    overlayRunRefreshing: false,
    overlayRunError: null,
    overlayCanceling: false,
    promptWizardOpen: false,
    promptWizardSourceNodeId: null,
    configDialogOpen: false,
    configDialogNodeType: null,
    configDialogSourceNodeId: null,
    configDialogInitialConfig: {},
    configDialogInitialLabel: null,
    memoryConfigOpen: false,
    marketplaceNodes: [],
    currentViewport,
  };
}

function resolveStateAction<T>(value: SetStateAction<T>, current: T): T {
  return typeof value === "function" ? (value as (current: T) => T)(current) : value;
}

// Generate unique ID for new nodes/edges
function generateId(): string {
  return `${Date.now()}-${Math.random().toString(36).substr(2, 9)}`;
}

type EditorSnapshot = {
  nodes: Node[];
  edges: Edge[];
};

type ClipboardNode = Pick<Node, "id" | "type" | "position" | "data" | "connectable" | "draggable">;
type ClipboardEdge = Pick<Edge, "source" | "target" | "label" | "data">;
type ClipboardSnapshot = {
  nodes: ClipboardNode[];
  edges: ClipboardEdge[];
};

type MaterializedBlueprint = {
  nodes: Node[];
  edges: Edge[];
  createdNodeIds: string[];
};

function deepClone<T>(value: T): T {
  const cloneFn = (globalThis as any).structuredClone as ((input: T) => T) | undefined;
  if (typeof cloneFn === "function") {
    return cloneFn(value);
  }
  return JSON.parse(JSON.stringify(value)) as T;
}

function replaceBlueprintPlaceholders(value: unknown, replacements: Record<string, string>): unknown {
  if (typeof value === "string") {
    let next = value;
    for (const [token, replacement] of Object.entries(replacements)) {
      next = next.split(token).join(replacement);
    }
    return next;
  }

  if (Array.isArray(value)) {
    return value.map((item) => replaceBlueprintPlaceholders(item, replacements));
  }

  if (value && typeof value === "object") {
    return Object.fromEntries(
      Object.entries(value).map(([key, child]) => [key, replaceBlueprintPlaceholders(child, replacements)]),
    );
  }

  return value;
}

function isEditableTarget(target: EventTarget | null): boolean {
  if (!target || !(target instanceof HTMLElement)) {
    return false;
  }

  const tagName = target.tagName;
  if (tagName === "INPUT" || tagName === "TEXTAREA" || tagName === "SELECT") {
    return true;
  }

  return target.isContentEditable;
}

const isTerminalRunStatus = (status: string) => {
  return status === "succeeded" || status === "failed" || status === "canceled";
};

const formatDuration = (durationMs: number | null | undefined) => {
  if (durationMs === null || durationMs === undefined) return "-";
  if (durationMs < 1000) return `${durationMs}ms`;
  const totalSeconds = Math.floor(durationMs / 1000);
  const minutes = Math.floor(totalSeconds / 60);
  const seconds = totalSeconds % 60;
  if (minutes > 0) return `${minutes}m ${seconds}s`;
  return `${totalSeconds}s`;
};

// Wizard button component - uses wizard context
interface WizardButtonProps {
  buttonRef?: Ref<HTMLButtonElement>;
  onBeforeStart?: () => void;
}

function WizardButton({ buttonRef, onBeforeStart }: WizardButtonProps) {
  const { startWizard, state } = useWizard();

  return (
    <button
      ref={buttonRef}
      type="button"
      aria-label="Operating Model Wizard"
      onClick={() => {
        onBeforeStart?.();
        startWizard(false);
      }}
      disabled={state.isActive}
      title="Open Operating Model Wizard (Ctrl+W / Ctrl+Shift+W)"
      className="bg-violet-600 text-white px-3 py-1.5 rounded-lg text-sm font-medium hover:bg-violet-700 disabled:opacity-50 disabled:cursor-not-allowed transition-colors shadow-sm flex items-center gap-1.5"
    >
      <Wand2 aria-hidden="true" className="size-4" />
      <span className="hidden sm:inline">Wizard</span>
    </button>
  );
}

// Validation trigger component - triggers validation on node/edge changes
function ValidationTrigger({ nodes, edges }: { nodes: Node[]; edges: Edge[] }) {
  const { validate } = useValidation();

  useEffect(() => {
    validate(nodes, edges);
  }, [nodes, edges, validate]);

  return null;
}

function useGraphEditorController({
  graphId,
  graphName,
  graphDescription,
  initialGraphJson,
  currentVersion,
  currentVersionId,
  availableVersions,
  onSelectVersion,
  loadingVersion = false,
  onSave,
  onUpdateMetadata,
  saving,
}: GraphEditorProps) {
  const router = useRouter();

  const { push } = router;
  const runIdParam = router.query.runId;
  const runIdValue = Array.isArray(runIdParam) ? runIdParam[0] : runIdParam;
  const overlayRunId = typeof runIdValue === "string" ? runIdValue : null;

  const initial = initialGraphJson
    ? graphJsonToReactFlow(initialGraphJson)
    : graphJsonToReactFlow(
        createEmptyGraphJson({
          name: graphName,
          description: graphDescription,
        }),
      );

  const [nodes, setNodes, onNodesChange] = useNodesState(initial.nodes);
  const [edges, setEdges, onEdgesChange] = useEdgesState(initial.edges);

  // Handle inserting a node on an edge (splitting the edge)
  const handleInsertNodeOnEdge = useCallback(
    (edgeId: string, position: { x: number; y: number }) => {
      const edge = edges.find((e) => e.id === edgeId);
      if (!edge) return;

      // Focus the palette search to let the user pick a node type
      // The position is stored so the next added node can be placed there
      paletteSearchRef.current?.focus();
    },
    [edges],
  );

  // Enrich edges with type information for visual display
  const typedEdges = useEdgeTypes(nodes, edges, handleInsertNodeOnEdge);

  const [uiState, dispatchUiState] = useReducer(
    graphEditorUiReducer,
    initialGraphJson?.editor_state?.viewport,
    createInitialGraphEditorUiState,
  );
  const {
    selectedNodeId,
    selectedEdgeId,
    isDirty,
    isEditingMetadata,
    startingRun,
    overlayRun,
    overlayRunLoading,
    overlayRunRefreshing,
    overlayRunError,
    overlayCanceling,
    promptWizardOpen,
    promptWizardSourceNodeId,
    configDialogOpen,
    configDialogNodeType,
    configDialogSourceNodeId,
    configDialogInitialConfig,
    configDialogInitialLabel,
    memoryConfigOpen,
    marketplaceNodes,
    currentViewport,
  } = uiState;

  const setUiField = useCallback(
    <K extends keyof GraphEditorUiState>(key: K, value: SetStateAction<GraphEditorUiState[K]>) => {
      dispatchUiState({
        patch: (state) =>
          ({
            [key]: resolveStateAction(value, state[key]),
          }) as Partial<GraphEditorUiState>,
      });
    },
    [],
  );
  const setSelectedNodeId = useCallback(
    (value: SetStateAction<string | null>) => setUiField("selectedNodeId", value),
    [setUiField],
  );
  const setSelectedEdgeId = useCallback(
    (value: SetStateAction<string | null>) => setUiField("selectedEdgeId", value),
    [setUiField],
  );
  const setIsDirty = useCallback((value: SetStateAction<boolean>) => setUiField("isDirty", value), [setUiField]);
  const setIsEditingMetadata = useCallback(
    (value: SetStateAction<boolean>) => setUiField("isEditingMetadata", value),
    [setUiField],
  );
  const setStartingRun = useCallback((value: SetStateAction<boolean>) => setUiField("startingRun", value), [setUiField]);
  const setOverlayRun = useCallback(
    (value: SetStateAction<RunDetail | null>) => setUiField("overlayRun", value),
    [setUiField],
  );
  const setOverlayRunLoading = useCallback(
    (value: SetStateAction<boolean>) => setUiField("overlayRunLoading", value),
    [setUiField],
  );
  const setOverlayRunRefreshing = useCallback(
    (value: SetStateAction<boolean>) => setUiField("overlayRunRefreshing", value),
    [setUiField],
  );
  const setOverlayRunError = useCallback(
    (value: SetStateAction<string | null>) => setUiField("overlayRunError", value),
    [setUiField],
  );
  const setOverlayCanceling = useCallback(
    (value: SetStateAction<boolean>) => setUiField("overlayCanceling", value),
    [setUiField],
  );
  const setPromptWizardOpen = useCallback(
    (value: SetStateAction<boolean>) => setUiField("promptWizardOpen", value),
    [setUiField],
  );
  const setPromptWizardSourceNodeId = useCallback(
    (value: SetStateAction<string | null>) => setUiField("promptWizardSourceNodeId", value),
    [setUiField],
  );
  const setConfigDialogOpen = useCallback(
    (value: SetStateAction<boolean>) => setUiField("configDialogOpen", value),
    [setUiField],
  );
  const setConfigDialogNodeType = useCallback(
    (value: SetStateAction<NodeType | null>) => setUiField("configDialogNodeType", value),
    [setUiField],
  );
  const setConfigDialogSourceNodeId = useCallback(
    (value: SetStateAction<string | null>) => setUiField("configDialogSourceNodeId", value),
    [setUiField],
  );
  const setConfigDialogInitialConfig = useCallback(
    (value: SetStateAction<NodeConfig>) => setUiField("configDialogInitialConfig", value),
    [setUiField],
  );
  const setConfigDialogInitialLabel = useCallback(
    (value: SetStateAction<string | null>) => setUiField("configDialogInitialLabel", value),
    [setUiField],
  );
  const setMemoryConfigOpen = useCallback(
    (value: SetStateAction<boolean>) => setUiField("memoryConfigOpen", value),
    [setUiField],
  );
  const setMarketplaceNodes = useCallback(
    (value: SetStateAction<MarketplacePackage[]>) => setUiField("marketplaceNodes", value),
    [setUiField],
  );
  const setCurrentViewport = useCallback(
    (value: SetStateAction<GraphEditorViewport>) => setUiField("currentViewport", value),
    [setUiField],
  );

  const paletteSearchRef = useRef<HTMLInputElement>(null);
  const wizardButtonRef = useRef<HTMLButtonElement>(null);
  const memoryButtonRef = useRef<HTMLButtonElement>(null);
  const palettePanelRef = useRef<HTMLDivElement>(null);
  const canvasPanelRef = useRef<HTMLDivElement>(null);
  const inspectorPanelRef = useRef<HTMLDivElement>(null);
  const focusRestoreRef = useRef<HTMLElement | null>(null);

  const clipboardRef = useRef<ClipboardSnapshot | null>(null);
  const pasteOffsetRef = useRef(0);

  const undoStackRef = useRef<EditorSnapshot[]>([]);
  const redoStackRef = useRef<EditorSnapshot[]>([]);
  const [canUndo, setCanUndo] = useState(false);
  const [canRedo, setCanRedo] = useState(false);
  const editHistoryArmedRef = useRef(false);
  const editHistoryTimerRef = useRef<ReturnType<typeof setTimeout> | null>(null);
  const dragHistoryPushedRef = useRef(false);

  const captureFocusableTarget = useCallback(() => {
    if (typeof document === "undefined") return;
    const active = document.activeElement;
    focusRestoreRef.current = active instanceof HTMLElement ? active : null;
  }, []);

  const restoreFocusableTarget = useCallback(() => {
    const target = focusRestoreRef.current;
    focusRestoreRef.current = null;
    target?.focus();
  }, []);

  const takeSnapshot = useCallback((): EditorSnapshot => {
    return { nodes: deepClone(nodes), edges: deepClone(edges) };
  }, [nodes, edges]);

  const resetHistory = useCallback(() => {
    undoStackRef.current = [];
    redoStackRef.current = [];
    setCanUndo(false);
    setCanRedo(false);
    editHistoryArmedRef.current = false;
    if (editHistoryTimerRef.current) {
      clearTimeout(editHistoryTimerRef.current);
      editHistoryTimerRef.current = null;
    }
    clipboardRef.current = null;
    pasteOffsetRef.current = 0;
    dragHistoryPushedRef.current = false;
  }, []);

  const pushHistory = useCallback(() => {
    undoStackRef.current.push(takeSnapshot());
    if (undoStackRef.current.length > 50) {
      undoStackRef.current.shift();
    }
    redoStackRef.current = [];
    setCanUndo(true);
    setCanRedo(false);
  }, [takeSnapshot]);

  const pushHistoryForEdit = useCallback(() => {
    if (!editHistoryArmedRef.current) {
      pushHistory();
      editHistoryArmedRef.current = true;
    }

    if (editHistoryTimerRef.current) {
      clearTimeout(editHistoryTimerRef.current);
    }
    editHistoryTimerRef.current = setTimeout(() => {
      editHistoryArmedRef.current = false;
    }, 800);
  }, [pushHistory]);

  const handleUndo = useCallback(() => {
    const previous = undoStackRef.current.pop();
    if (!previous) return;

    redoStackRef.current.push(takeSnapshot());
    setNodes(previous.nodes);
    setEdges(previous.edges);
    setSelectedNodeId(null);
    setSelectedEdgeId(null);
    setIsDirty(true);

    setCanUndo(undoStackRef.current.length > 0);
    setCanRedo(true);
  }, [setEdges, setIsDirty, setNodes, setSelectedEdgeId, setSelectedNodeId, takeSnapshot]);

  const handleRedo = useCallback(() => {
    const next = redoStackRef.current.pop();
    if (!next) return;

    undoStackRef.current.push(takeSnapshot());
    setNodes(next.nodes);
    setEdges(next.edges);
    setSelectedNodeId(null);
    setSelectedEdgeId(null);
    setIsDirty(true);

    setCanUndo(true);
    setCanRedo(redoStackRef.current.length > 0);
  }, [setEdges, setIsDirty, setNodes, setSelectedEdgeId, setSelectedNodeId, takeSnapshot]);

  const getSelectedNodes = useCallback((): Node[] => {
    const selected = nodes.filter((n) => n.selected);
    if (selected.length > 0) return selected;

    if (selectedNodeId) {
      const selectedNode = nodes.find((n) => n.id === selectedNodeId);
      return selectedNode ? [selectedNode] : [];
    }

    return [];
  }, [nodes, selectedNodeId]);

  const getSelectedEdges = useCallback((): Edge[] => {
    const selected = edges.filter((e) => e.selected);
    if (selected.length > 0) return selected;

    if (selectedEdgeId) {
      const selectedEdge = edges.find((e) => e.id === selectedEdgeId);
      return selectedEdge ? [selectedEdge] : [];
    }

    return [];
  }, [edges, selectedEdgeId]);

  const handleCopy = useCallback(() => {
    const selectedNodes = getSelectedNodes();
    if (selectedNodes.length === 0) return;

    const selectedIds = new Set(selectedNodes.map((n) => n.id));
    const selectedEdges = edges.filter((edge) => selectedIds.has(edge.source) && selectedIds.has(edge.target));

    clipboardRef.current = deepClone({
      nodes: selectedNodes.map((node) => ({
        id: node.id,
        type: node.type,
        position: node.position,
        data: node.data,
        connectable: node.connectable,
        draggable: node.draggable,
      })),
      edges: selectedEdges.map((edge) => ({
        source: edge.source,
        target: edge.target,
        label: edge.label,
        data: edge.data,
      })),
    } satisfies ClipboardSnapshot);

    pasteOffsetRef.current = 0;
  }, [edges, getSelectedNodes]);

  const applyClipboard = useCallback(
    (clipboard: ClipboardSnapshot, options?: { incrementOffset?: boolean }) => {
      if (clipboard.nodes.length === 0) return;

      pushHistory();

      const offsetBase = 40;
      const offset = offsetBase + pasteOffsetRef.current;
      if (options?.incrementOffset !== false) {
        pasteOffsetRef.current += 20;
      }

      const idMap = new Map<string, string>();
      const newNodes: Node[] = clipboard.nodes.map((node) => {
        const newId = generateId();
        idMap.set(node.id, newId);

        const label = typeof (node.data as any)?.label === "string" ? String((node.data as any).label) : "";

        return {
          ...deepClone(node),
          id: newId,
          position: {
            x: node.position.x + offset,
            y: node.position.y + offset,
          },
          data: {
            ...(deepClone(node.data) as any),
            label: label ? `${label} (copy)` : label,
          },
          selected: true,
        } satisfies Node;
      });

      const newEdges: Edge[] = clipboard.edges.flatMap((edge): Edge[] => {
          const source = idMap.get(edge.source);
          const target = idMap.get(edge.target);
          if (!source || !target) return [];

          return [
            {
              id: generateId(),
              source,
              target,
              label: edge.label,
              data: deepClone(edge.data),
            } as Edge,
          ];
        });

      setNodes((nds) => [...nds.map((n) => ({ ...n, selected: false })), ...newNodes]);
      setEdges((eds) => [...eds.map((e) => ({ ...e, selected: false })), ...newEdges]);
      setSelectedNodeId(newNodes[0]?.id ?? null);
      setSelectedEdgeId(null);
      setIsDirty(true);
    },
    [pushHistory, setEdges, setIsDirty, setNodes, setSelectedEdgeId, setSelectedNodeId],
  );

  const handlePaste = useCallback(() => {
    const clipboard = clipboardRef.current;
    if (!clipboard) return;
    applyClipboard(clipboard);
  }, [applyClipboard]);

  const handleDuplicateSelection = useCallback(() => {
    const selectedNodes = getSelectedNodes();
    if (selectedNodes.length === 0) return;

    const selectedIds = new Set(selectedNodes.map((n) => n.id));
    const selectedEdges = edges.filter((edge) => selectedIds.has(edge.source) && selectedIds.has(edge.target));

    applyClipboard(
      {
        nodes: selectedNodes.map((node) => ({
          id: node.id,
          type: node.type,
          position: node.position,
          data: node.data,
          connectable: node.connectable,
          draggable: node.draggable,
        })),
        edges: selectedEdges.map((edge) => ({
          source: edge.source,
          target: edge.target,
          label: edge.label,
          data: edge.data,
        })),
      },
      { incrementOffset: false },
    );
  }, [applyClipboard, edges, getSelectedNodes]);

  const handleDeleteSelection = useCallback(() => {
    const selectedNodes = getSelectedNodes();
    const selectedEdges = getSelectedEdges();

    if (selectedNodes.length === 0 && selectedEdges.length === 0) {
      return;
    }

    pushHistory();

    const nodeIdSet = new Set(selectedNodes.map((n) => n.id));
    const edgeIdSet = new Set(selectedEdges.map((e) => e.id));

    setNodes((nds) => nds.filter((n) => !nodeIdSet.has(n.id)));
    setEdges((eds) =>
      eds.filter((e) => {
        if (edgeIdSet.has(e.id)) return false;
        if (nodeIdSet.has(e.source) || nodeIdSet.has(e.target)) return false;
        return true;
      }),
    );

    setSelectedNodeId(null);
    setSelectedEdgeId(null);
    setIsDirty(true);
  }, [getSelectedEdges, getSelectedNodes, pushHistory, setEdges, setIsDirty, setNodes, setSelectedEdgeId, setSelectedNodeId]);

  // Sync editor state when the loaded version changes (save or version switch).
  useEffect(() => {
    resetHistory();

    if (!initialGraphJson) {
      dispatchUiState({ patch: { isDirty: false } });
      return;
    }

    const next = graphJsonToReactFlow(initialGraphJson);
    setNodes(next.nodes);
    setEdges(next.edges);
    dispatchUiState({ patch: { selectedNodeId: null, selectedEdgeId: null, isDirty: false } });
  }, [initialGraphJson, resetHistory, setNodes, setEdges]);

  useEffect(() => {
    let active = true;
    const loadMarketplaceNodes = async () => {
      try {
        const installed = await marketplaceApi.listInstalled();
        if (!active) return;
        setMarketplaceNodes(installed);
      } catch {
        if (!active) return;
        setMarketplaceNodes([]);
      }
    };
    void loadMarketplaceNodes();
    return () => {
      active = false;
    };
  }, [setMarketplaceNodes]);

  const applyExecutionOverlay = useCallback(
    (run: RunDetail | null) => {
      setNodes((currentNodes) => {
        const latestByNodeId: Record<string, NodeRunItem> = {};

        for (const nodeRun of run?.node_runs ?? []) {
          const key = nodeRun.node_id;
          const existing = latestByNodeId[key];
          if (!existing || nodeRun.attempt >= existing.attempt) {
            latestByNodeId[key] = nodeRun;
          }
        }

        return currentNodes.map((node) => {
          if (node.type === NOTE_NODE_TYPE) return node;

          const data = { ...(node.data as Record<string, unknown>) };
          delete data.executionStatus;
          delete data.executionAttempt;
          delete data.executionDurationMs;

          const latest = latestByNodeId[node.id];
          if (latest) {
            data.executionStatus = String(latest.status);
            data.executionAttempt = latest.attempt;
            data.executionDurationMs = latest.duration_ms ?? null;
          }

          return { ...node, data };
        });
      });
    },
    [setNodes],
  );

  const fetchOverlayRun = useCallback(
    async (opts?: { silent?: boolean }) => {
      if (!overlayRunId) return;

      const silent = opts?.silent ?? false;
      if (!silent) {
        setOverlayRunLoading(true);
      } else {
        setOverlayRunRefreshing(true);
      }
      setOverlayRunError(null);

      try {
        const run = await runsApi.get(overlayRunId);

        if (String(run.graph_id ?? "") !== String(graphId)) {
          setOverlayRun(null);
          setOverlayRunError("This run does not belong to the current graph.");
          applyExecutionOverlay(null);
          return;
        }

        setOverlayRun(run);
      } catch (err: unknown) {
        setOverlayRun(null);
        setOverlayRunError(getApiErrorMessage(err, "Failed to load execution trace."));
        applyExecutionOverlay(null);
      } finally {
        setOverlayRunLoading(false);
        setOverlayRunRefreshing(false);
      }
    },
    [applyExecutionOverlay, graphId, overlayRunId, setOverlayRun, setOverlayRunError, setOverlayRunLoading, setOverlayRunRefreshing],
  );

  useEffect(() => {
    if (!overlayRunId) {
      setOverlayRun(null);
      setOverlayRunError(null);
      applyExecutionOverlay(null);
      return;
    }

    void fetchOverlayRun();
  }, [applyExecutionOverlay, fetchOverlayRun, overlayRunId, setOverlayRun, setOverlayRunError]);

  useEffect(() => {
    applyExecutionOverlay(overlayRun);
  }, [applyExecutionOverlay, initialGraphJson, overlayRun]);

  useEffect(() => {
    if (!overlayRunId) return;
    if (!overlayRun) return;
    if (isTerminalRunStatus(String(overlayRun.status))) return;

    const interval = window.setInterval(() => {
      void fetchOverlayRun({ silent: true });
    }, 3000);

    return () => {
      window.clearInterval(interval);
    };
  }, [fetchOverlayRun, overlayRun, overlayRunId]);

  const selectedNode = selectedNodeId ? nodes.find((n) => n.id === selectedNodeId) : null;
  const selectedEdge = selectedEdgeId ? edges.find((e) => e.id === selectedEdgeId) : null;
  const canQuickAddConnect = !!selectedNode && selectedNode.type !== NOTE_NODE_TYPE;

  const handleSelectVersion = useCallback(
    async (versionId: string) => {
      if (!versionId || versionId === currentVersionId) return;

      if (isDirty) {
        const confirmed = window.confirm("You have unsaved changes. Discard them and switch versions?");
        if (!confirmed) return;
      }

      try {
        await onSelectVersion(versionId);
      } catch {
        // Errors are surfaced by the parent (toast).
      }
    },
    [currentVersionId, isDirty, onSelectVersion],
  );

  const onConnect = useCallback(
    (connection: Connection) => {
      const validation = validateGraphConnection(connection, edges);
      if (!validation.valid) {
        const feedback = getConnectionFeedback(validation.reason);
        showInfo(feedback.title, feedback.description);
        return;
      }

      pushHistory();

      // Determine edge label based on source node type and handle
      let edgeLabel: string | undefined;
      const sourceNode = nodes.find((n) => n.id === connection.source);
      if (sourceNode?.type === NODE_TYPES.BRANCH && connection.sourceHandle) {
        // Branch node: label edge with "true" or "false" based on handle
        edgeLabel = connection.sourceHandle;
      }

      const newEdge: Edge = {
        ...connection,
        id: generateId(),
        label: edgeLabel,
      } as Edge;

      setEdges((eds) => addEdge(newEdge, eds));
      setIsDirty(true);
    },
    [edges, nodes, pushHistory, setEdges, setIsDirty],
  );

  const onNodeClick = useCallback((_: React.MouseEvent, node: Node) => {
    setSelectedNodeId(node.id);
    setSelectedEdgeId(null);
  }, [setSelectedEdgeId, setSelectedNodeId]);

  const onEdgeClick = useCallback((_: React.MouseEvent, edge: Edge) => {
    setSelectedEdgeId(edge.id);
    setSelectedNodeId(null);
  }, [setSelectedEdgeId, setSelectedNodeId]);

  const onNodeDragStop = useCallback<OnNodeDrag>(
    (_, node, draggingNodes) => {
      dragHistoryPushedRef.current = false;

      const movedNodes = (draggingNodes && draggingNodes.length > 0 ? draggingNodes : [node]).filter(
        (draggedNode): draggedNode is Node => Boolean(draggedNode),
      );

      const snappedPositions = new Map<string, { x: number; y: number }>();
      for (const movedNode of movedNodes) {
        snappedPositions.set(movedNode.id, snapPositionToGrid(movedNode.position, GRAPH_EDITOR_SNAP_GRID));
      }

      setNodes((currentNodes) => {
        let hasChanges = false;
        const nextNodes = currentNodes.map((currentNode) => {
          const snapped = snappedPositions.get(currentNode.id);
          if (!snapped) {
            return currentNode;
          }

          if (currentNode.position.x === snapped.x && currentNode.position.y === snapped.y) {
            return currentNode;
          }

          hasChanges = true;
          return {
            ...currentNode,
            position: snapped,
          };
        });

        return hasChanges ? nextNodes : currentNodes;
      });

      setIsDirty(true);
    },
    [setIsDirty, setNodes],
  );

  const onNodeDragStart = useCallback<OnNodeDrag>(() => {
    if (dragHistoryPushedRef.current) return;
    dragHistoryPushedRef.current = true;
    pushHistory();
  }, [pushHistory]);

  const onPaneClick = useCallback(() => {
    setSelectedNodeId(null);
    setSelectedEdgeId(null);
  }, [setSelectedEdgeId, setSelectedNodeId]);

  const addExecutableNode = useCallback(
    (
      nodeType: NodeType,
      options?: {
        sourceNodeId?: string | null;
        config?: Record<string, unknown>;
        label?: string;
      },
    ) => {
      const typeInfo = PHASE2_NODE_TYPES.find((t) => t.type === nodeType);
      if (!typeInfo) return;

      // Human Gate is implemented; keep it enabled even if a stale config marks it otherwise.
      if (!typeInfo.enabled && nodeType !== NODE_TYPES.HUMAN_GATE) return;

      pushHistory();
      const newNodeId = generateId();

      const sourceNodeId = options?.sourceNodeId ?? null;
      const sourceNode = sourceNodeId ? nodes.find((n) => n.id === sourceNodeId && n.type !== NOTE_NODE_TYPE) : null;

      setNodes((nds) => {
        const hasTrigger = nds.some((node) => node.type !== NOTE_NODE_TYPE && (node.data as any)?.isTrigger === true);
        const nodeConfig = deepClone(options?.config ?? {});
        let position: { x: number; y: number };

        if (sourceNode) {
          // Position below the selected node
          position = {
            x: sourceNode.position.x,
            y: sourceNode.position.y + 150,
          };
        } else {
          // Default grid positioning
          const index = nds.length;
          const col = index % 2;
          const row = Math.floor(index / 2);
          position = { x: 50 + col * 220, y: 80 + row * 190 };
        }

        const newNode: Node = {
          id: newNodeId,
          type: nodeType,
          position,
          data: {
            label: options?.label || `${typeInfo.label} Node`,
            nodeType: nodeType,
            config: nodeConfig,
            ...(hasTrigger ? {} : { isTrigger: true }),
          },
        };

        return [...nds, newNode];
      });

      // Create edge from selected node to new node
      if (sourceNode) {
        const newEdge: Edge = {
          id: generateId(),
          source: sourceNode.id,
          target: newNodeId,
        };
        setEdges((eds) => [...eds, newEdge]);
      }

      setSelectedNodeId(newNodeId);
      setIsDirty(true);
    },
    [nodes, pushHistory, setEdges, setIsDirty, setNodes, setSelectedNodeId],
  );

  const handleAddNode = useCallback(
    (nodeType: NodeType, connectToSelected = false) => {
      const typeInfo = PHASE2_NODE_TYPES.find((t) => t.type === nodeType);
      if (!typeInfo) return;

      // Human Gate is implemented; keep it enabled even if a stale config marks it otherwise.
      if (!typeInfo.enabled && nodeType !== NODE_TYPES.HUMAN_GATE) return;

      const sourceNodeId =
        connectToSelected && selectedNodeId && nodes.some((n) => n.id === selectedNodeId && n.type !== NOTE_NODE_TYPE)
          ? selectedNodeId
          : null;

      // For prompt nodes, use the special wizard
      if (nodeType === NODE_TYPES.PROMPT) {
        captureFocusableTarget();
        setPromptWizardSourceNodeId(sourceNodeId);
        setPromptWizardOpen(true);
        return;
      }

      // For other nodes, open the config dialog
      const formInfo = getNodeTypeInfo(nodeType);
      if (formInfo) {
        captureFocusableTarget();
        setConfigDialogNodeType(nodeType);
        setConfigDialogSourceNodeId(sourceNodeId);
        setConfigDialogInitialConfig({});
        setConfigDialogInitialLabel(null);
        setConfigDialogOpen(true);
        return;
      }

      // Fallback: add node directly without config dialog
      addExecutableNode(nodeType, { sourceNodeId, config: {} });
    },
    [addExecutableNode, captureFocusableTarget, nodes, selectedNodeId, setConfigDialogInitialConfig, setConfigDialogInitialLabel, setConfigDialogNodeType, setConfigDialogOpen, setConfigDialogSourceNodeId, setPromptWizardOpen, setPromptWizardSourceNodeId],
  );

  const handleAddMarketplaceNode = useCallback(
    (pkg: MarketplacePackage, connectToSelected = false) => {
      if (!canAddMarketplacePackageToEditor(pkg)) {
        showError(
          "Package unavailable",
          getMarketplacePackageReason(pkg) ?? "This marketplace package cannot be added in the current product mode.",
        );
        return;
      }

      const release = pkg.installed_release ?? pkg.latest_release;
      if (!release) {
        return;
      }
      const executionType = String(release.execution_node_type);
      if (!isValidNodeType(executionType)) {
        showError("Unsupported package", "This marketplace package uses an unsupported node type.");
        return;
      }
      const sourceNodeId =
        connectToSelected && selectedNodeId && nodes.some((n) => n.id === selectedNodeId && n.type !== NOTE_NODE_TYPE)
          ? selectedNodeId
          : null;

      const label =
        typeof release.ui_schema?.label === "string" && release.ui_schema.label ? release.ui_schema.label : pkg.name;
      const config =
        release.config_defaults && typeof release.config_defaults === "object" ? release.config_defaults : {};

      captureFocusableTarget();
      setConfigDialogNodeType(executionType);
      setConfigDialogSourceNodeId(sourceNodeId);
      setConfigDialogInitialConfig(deepClone(config));
      setConfigDialogInitialLabel(label);
      setConfigDialogOpen(true);

      const provider =
        config && typeof config === "object" && "provider" in config
          ? String((config as Record<string, unknown>).provider || "").trim()
          : "";
      if (provider) {
        showInfo("Credential setup", `Configure ${provider} credentials in this dialog before adding the node.`);
      }
    },
    [captureFocusableTarget, nodes, selectedNodeId, setConfigDialogInitialConfig, setConfigDialogInitialLabel, setConfigDialogNodeType, setConfigDialogOpen, setConfigDialogSourceNodeId],
  );

  const handleConfigDialogComplete = useCallback(
    (config: NodeConfig, label: string) => {
      if (!configDialogNodeType) return;
      addExecutableNode(configDialogNodeType, {
        sourceNodeId: configDialogSourceNodeId,
        config,
        label,
      });
      setConfigDialogOpen(false);
      setConfigDialogNodeType(null);
      setConfigDialogSourceNodeId(null);
      setConfigDialogInitialConfig({});
      setConfigDialogInitialLabel(null);
    },
    [addExecutableNode, configDialogNodeType, configDialogSourceNodeId, setConfigDialogInitialConfig, setConfigDialogInitialLabel, setConfigDialogNodeType, setConfigDialogOpen, setConfigDialogSourceNodeId],
  );

  const handleOpenMemoryConfig = useCallback(() => {
    captureFocusableTarget();
    setMemoryConfigOpen(true);
  }, [captureFocusableTarget, setMemoryConfigOpen]);

  const handleMemoryConfigOpenChange = useCallback(
    (open: boolean) => {
      setMemoryConfigOpen(open);
      if (!open) {
        restoreFocusableTarget();
      }
    },
    [restoreFocusableTarget, setMemoryConfigOpen],
  );

  const handleAddNote = useCallback(() => {
    pushHistory();
    const newNodeId = generateId();

    setNodes((nds) => {
      const noteCount = nds.filter((n) => n.type === NOTE_NODE_TYPE).length;
      const col = noteCount % 2;
      const row = Math.floor(noteCount / 2);

      const position = { x: 350 + col * 240, y: 80 + row * 190 };

      const newNode: Node = {
        id: newNodeId,
        type: NOTE_NODE_TYPE,
        position,
        data: {
          label: "Note",
          text: "",
        },
        connectable: false,
      };

      return [...nds, newNode];
    });

    setSelectedNodeId(newNodeId);
    setSelectedEdgeId(null);
    setIsDirty(true);
  }, [pushHistory, setIsDirty, setNodes, setSelectedEdgeId, setSelectedNodeId]);

  const handleUpdateNode = useCallback(
    (nodeId: string, updates: Partial<Node["data"]>) => {
      pushHistoryForEdit();
      setNodes((nds) =>
        nds.map((node) => (node.id === nodeId ? { ...node, data: { ...node.data, ...updates } } : node)),
      );
      setIsDirty(true);
    },
    [pushHistoryForEdit, setIsDirty, setNodes],
  );

  const handleUpdateEdge = useCallback(
    (edgeId: string, updates: Partial<Edge>) => {
      pushHistoryForEdit();
      setEdges((eds) =>
        eds.map((edge) => {
          if (edge.id !== edgeId) return edge;
          return {
            ...edge,
            ...updates,
            data: {
              ...(edge.data ?? {}),
              ...(updates.data ?? {}),
            },
          };
        }),
      );
      setIsDirty(true);
    },
    [pushHistoryForEdit, setEdges, setIsDirty],
  );

  const handleDeleteNode = useCallback(
    (nodeId: string) => {
      if (!nodes.some((n) => n.id === nodeId)) return;
      pushHistory();
      setNodes((nds) => nds.filter((n) => n.id !== nodeId));
      setEdges((eds) => eds.filter((e) => e.source !== nodeId && e.target !== nodeId));
      if (selectedNodeId === nodeId) {
        setSelectedNodeId(null);
      }
      setIsDirty(true);
    },
    [nodes, pushHistory, setNodes, setEdges, selectedNodeId, setIsDirty, setSelectedNodeId],
  );

  const handleDuplicateNode = useCallback(
    (nodeId: string) => {
      const nodeToDuplicate = nodes.find((n) => n.id === nodeId);
      if (!nodeToDuplicate) return;

      pushHistory();
      const newNodeId = generateId();
      const newNode: Node = {
        ...nodeToDuplicate,
        id: newNodeId,
        position: {
          x: nodeToDuplicate.position.x + 50,
          y: nodeToDuplicate.position.y + 50,
        },
        data: {
          ...nodeToDuplicate.data,
          label: `${nodeToDuplicate.data.label} (copy)`,
        },
        selected: false,
      };

      setNodes((nds) => [...nds, newNode]);
      setSelectedNodeId(newNodeId);
      setIsDirty(true);
    },
    [nodes, pushHistory, setIsDirty, setNodes, setSelectedNodeId],
  );

  const handleDeleteEdge = useCallback(
    (edgeId: string) => {
      if (!edges.some((e) => e.id === edgeId)) return;
      pushHistory();
      setEdges((eds) => eds.filter((e) => e.id !== edgeId));
      if (selectedEdgeId === edgeId) {
        setSelectedEdgeId(null);
      }
      setIsDirty(true);
    },
    [edges, pushHistory, setEdges, selectedEdgeId, setIsDirty, setSelectedEdgeId],
  );

  const materializeAgentBlueprint = useCallback(
    (
      blueprint: AgentWizardBlueprint,
      options?: {
        nodes?: Node[];
        edges?: Edge[];
        sourceNodeId?: string | null;
      },
    ): MaterializedBlueprint => {
      const currentNodes = options?.nodes ?? nodes;
      const currentEdges = options?.edges ?? edges;
      const sourceNodeId = options?.sourceNodeId ?? selectedNodeId;
      const selectedSourceNode =
        sourceNodeId && currentNodes.some((node) => node.id === sourceNodeId && node.type !== NOTE_NODE_TYPE)
          ? (currentNodes.find((node) => node.id === sourceNodeId) ?? null)
          : null;

      const maxX = currentNodes.reduce((max, node) => Math.max(max, node.position.x), 0);
      const baseX = selectedSourceNode ? selectedSourceNode.position.x + 260 : maxX + 140;
      const baseY = selectedSourceNode ? selectedSourceNode.position.y : 120;
      const hasTriggerNode = currentNodes.some(
        (node) => node.type !== NOTE_NODE_TYPE && (node.data as Record<string, unknown>)?.isTrigger === true,
      );

      const createdNodeIds: string[] = [];
      const agentNodeTemplateIndex = blueprint.nodes.findIndex((template) => template.nodeType === NODE_TYPES.AGENT);

      const draftNodes: Node[] = blueprint.nodes.map((template, index) => {
        const newNodeId = generateId();
        createdNodeIds.push(newNodeId);
        const rawConfig = deepClone(template.config);
        return {
          id: newNodeId,
          type: template.nodeType,
          position: {
            x: baseX,
            y: baseY + index * 170,
          },
          data: {
            label: template.label,
            nodeType: template.nodeType,
            config: rawConfig,
            ...(!hasTriggerNode && index === 0 ? { isTrigger: true } : {}),
            ...(template.nodeType === NODE_TYPES.OUTPUT ? { isEnd: true } : {}),
          },
          selected: false,
        } satisfies Node;
      });

      const agentNodeId = agentNodeTemplateIndex >= 0 ? createdNodeIds[agentNodeTemplateIndex] : "";
      const observationContextTemplateIndex = blueprint.nodes.findIndex(
        (template) => template.nodeType === NODE_TYPES.OBSERVATION_CONTEXT,
      );
      const observationContextNodeId =
        observationContextTemplateIndex >= 0 ? createdNodeIds[observationContextTemplateIndex] : "";
      const replacements: Record<string, string> = {};
      if (agentNodeId) {
        replacements[AGENT_OUTPUT_PLACEHOLDER] = agentNodeId;
      }
      if (observationContextNodeId) {
        replacements[OBSERVATION_CONTEXT_PLACEHOLDER] = observationContextNodeId;
      }

      const newNodes = draftNodes.map((node) => ({
        ...node,
        data: {
          ...(node.data as Record<string, unknown>),
          config: replaceBlueprintPlaceholders((node.data as Record<string, unknown>).config, replacements),
        },
      }));

      const newEdges: Edge[] = [];
      const appendEdge = (source: string, target: string) => {
        const exists =
          currentEdges.some((edge) => edge.source === source && edge.target === target) ||
          newEdges.some((edge) => edge.source === source && edge.target === target);
        if (exists) {
          return;
        }
        newEdges.push({
          id: generateId(),
          source,
          target,
        } as Edge);
      };

      if (selectedSourceNode && newNodes[0]) {
        appendEdge(selectedSourceNode.id, newNodes[0].id);
      }

      for (let index = 0; index < newNodes.length - 1; index += 1) {
        appendEdge(newNodes[index].id, newNodes[index + 1].id);
      }

      return {
        nodes: [...currentNodes.map((node) => ({ ...node, selected: false })), ...newNodes],
        edges: [...currentEdges.map((edge) => ({ ...edge, selected: false })), ...newEdges],
        createdNodeIds,
      };
    },
    [edges, nodes, selectedNodeId],
  );

  const applyAgentBlueprint = useCallback(
    (blueprint: AgentWizardBlueprint): MaterializedBlueprint => {
      pushHistory();
      const materialized = materializeAgentBlueprint(blueprint);
      setNodes(materialized.nodes);
      setEdges(materialized.edges);
      setSelectedNodeId(materialized.createdNodeIds[materialized.createdNodeIds.length - 1] ?? null);
      setSelectedEdgeId(null);
      setIsDirty(true);
      return materialized;
    },
    [materializeAgentBlueprint, pushHistory, setEdges, setIsDirty, setNodes, setSelectedEdgeId, setSelectedNodeId],
  );

  const saveGraphSnapshot = useCallback(
    async (draftNodes: Node[], draftEdges: Edge[]) => {
      let normalizedNodes = draftNodes;
      let addedTrigger = false;
      let addedEnds = 0;

      const executableNodes = draftNodes.filter((node) => node.type !== NOTE_NODE_TYPE);

      // Validation: Cannot save empty operating model
      if (executableNodes.length === 0) {
        showError("Cannot save empty operating model", "Add at least one step to the operating model");
        return false;
      }

      // Validation: Must have at least one deliverable step
      const hasOutputNode = executableNodes.some((node) => node.type === NODE_TYPES.OUTPUT);
      if (!hasOutputNode) {
        showError("Operating model needs a deliverable step", "Add a Final Deliverable step to define the result");
        return false;
      }
      if (executableNodes.length > 0) {
        const hasTrigger = executableNodes.some((node) => (node.data as any)?.isTrigger === true);
        if (!hasTrigger) {
          const firstExecutableIndex = draftNodes.findIndex((node) => node.type !== NOTE_NODE_TYPE);
          if (firstExecutableIndex >= 0) {
            normalizedNodes = draftNodes.map((node, index) =>
              index === firstExecutableIndex ? { ...node, data: { ...node.data, isTrigger: true } } : node,
            );
            addedTrigger = true;
          }
        }

        const hasEnd = executableNodes.some((node) => (node.data as any)?.isEnd === true);
        if (!hasEnd) {
          const executableIds = new Set(executableNodes.map((node) => node.id));
          const outdegree = new Map<string, number>();
          for (const id of executableIds) {
            outdegree.set(id, 0);
          }
          for (const edge of draftEdges) {
            if (executableIds.has(edge.source) && executableIds.has(edge.target)) {
              outdegree.set(edge.source, (outdegree.get(edge.source) ?? 0) + 1);
            }
          }

          const sinkIds = [...executableIds].filter((id) => (outdegree.get(id) ?? 0) === 0);
          if (sinkIds.length > 0) {
            const sinkSet = new Set(sinkIds);
            normalizedNodes = normalizedNodes.map((node) =>
              sinkSet.has(node.id) ? { ...node, data: { ...node.data, isEnd: true } } : node,
            );
            addedEnds = sinkIds.length;
          }
        }
      }

      if (normalizedNodes !== draftNodes) {
        setNodes(normalizedNodes);
      }

      if (addedTrigger || addedEnds > 0) {
        const parts: string[] = [];
        if (addedTrigger) parts.push("added START entry");
        if (addedEnds > 0) parts.push(`added ${addedEnds} END exit${addedEnds === 1 ? "" : "s"}`);
        showInfo("Graph structure updated", parts.join(" and "));
      }

      const graphJson = reactFlowToGraphJson(
        normalizedNodes,
        draftEdges,
        { name: graphName, description: graphDescription },
        graphId,
        undefined,
        currentViewport,
      );
      await onSave(graphJson);
      setIsDirty(false);
      return true;
    },
    [currentViewport, graphDescription, graphId, graphName, onSave, setIsDirty, setNodes],
  );

  const handleSave = useCallback(async () => {
    return saveGraphSnapshot(nodes, edges);
  }, [edges, nodes, saveGraphSnapshot]);

  const runDisabledReason = startingRun
    ? "Starting run"
    : saving
      ? "Save in progress"
      : loadingVersion
        ? "Loading version"
        : !currentVersionId
          ? "Save the graph to create a version first"
          : isDirty
            ? "Save changes before running"
            : null;

  const handleRunWorkflow = useCallback(async () => {
    if (runDisabledReason) {
      showError(runDisabledReason);
      return;
    }
    if (!currentVersionId) return;

    setStartingRun(true);
    try {
      const run = await runsApi.start(
        {
          graph_version_id: currentVersionId,
          llm_mode: "managed",
          input_json: {},
        },
        {
          idempotencyKey: newClientCommandId("graph.run"),
        },
      );
      showSuccess("Run created");
      void push(`/runs/${run.id}`);
    } catch (err: unknown) {
      showError("Run failed", getApiErrorMessage(err, ERROR_FALLBACKS.run.start));
    } finally {
      setStartingRun(false);
    }
  }, [currentVersionId, push, runDisabledReason, setStartingRun]);

  const handleExitExecutionView = useCallback(() => {
    void push(`/graphs/${graphId}`);
  }, [graphId, push]);

  const handleCancelExecution = useCallback(async () => {
    if (!overlayRun) return;
    if (isTerminalRunStatus(String(overlayRun.status))) return;

    setOverlayCanceling(true);
    try {
      const updated = await runsApi.cancel(overlayRun.id, {
        idempotencyKey: stableClientCommandId("graph.cancel", overlayRun.id),
      });
      setOverlayRun(updated);
      showSuccess("Run canceled");
    } catch (err: unknown) {
      showError("Cancel failed", getApiErrorMessage(err, ERROR_FALLBACKS.run.cancel));
    } finally {
      setOverlayCanceling(false);
    }
  }, [overlayRun, setOverlayCanceling, setOverlayRun]);

  const handleAutoLayout = useCallback(() => {
    if (nodes.length === 0) return;
    pushHistory();
    const executableNodes = nodes.filter((node) => node.type !== NOTE_NODE_TYPE);
    const noteNodes = nodes.filter((node) => node.type === NOTE_NODE_TYPE);
    const executableIds = new Set(executableNodes.map((node) => node.id));
    const executableEdges = edges.filter((edge) => executableIds.has(edge.source) && executableIds.has(edge.target));

    const { nodes: layoutedNodes, edges: layoutedEdges } = getLayoutedElements(executableNodes, executableEdges, {
      direction: "TB",
      nodeSpacing: 50,
      rankSpacing: 100,
    });
    setNodes([...layoutedNodes, ...noteNodes]);
    setEdges(layoutedEdges);
    setIsDirty(true);
  }, [nodes, pushHistory, edges, setNodes, setEdges, setIsDirty]);

  const handleSaveShortcut = useEffectEvent(handleSave);
  const handleUndoShortcut = useEffectEvent(handleUndo);
  const handleRedoShortcut = useEffectEvent(handleRedo);
  const handleCopyShortcut = useEffectEvent(handleCopy);
  const handlePasteShortcut = useEffectEvent(handlePaste);
  const handleDuplicateShortcut = useEffectEvent(handleDuplicateSelection);
  const handleDeleteShortcut = useEffectEvent(handleDeleteSelection);

  // Keyboard shortcuts
  useEffect(() => {
    const handleKeyDown = (e: KeyboardEvent) => {
      const key = e.key.toLowerCase();

      // Cmd/Ctrl + W (and Cmd/Ctrl + Shift + W) to open Agent Wizard.
      if ((e.metaKey || e.ctrlKey) && key === "w") {
        if (!isEditableTarget(e.target)) {
          e.preventDefault();
          wizardButtonRef.current?.click();
        }
      }

      // Cmd/Ctrl + S to save
      if ((e.metaKey || e.ctrlKey) && key === "s") {
        if (!isEditableTarget(e.target)) {
          e.preventDefault();
          if (!saving) {
            void handleSaveShortcut();
          }
        }
      }

      // Cmd/Ctrl + A to select all nodes
      if ((e.metaKey || e.ctrlKey) && key === "a") {
        if (!isEditableTarget(e.target)) {
          e.preventDefault();
          setNodes((nds) => nds.map((n) => ({ ...n, selected: true })));
        }
      }

      // Cmd/Ctrl + Z (undo) and Cmd/Ctrl + Shift + Z (redo)
      if ((e.metaKey || e.ctrlKey) && key === "z") {
        if (!isEditableTarget(e.target)) {
          e.preventDefault();
          if (e.shiftKey) {
            handleRedoShortcut();
          } else {
            handleUndoShortcut();
          }
        }
      }

      // Cmd/Ctrl + Y to redo (Windows convention)
      if ((e.metaKey || e.ctrlKey) && key === "y") {
        if (!isEditableTarget(e.target)) {
          e.preventDefault();
          handleRedoShortcut();
        }
      }

      // Cmd/Ctrl + Shift + F to focus node search
      if ((e.metaKey || e.ctrlKey) && e.shiftKey && key === "f") {
        if (!isEditableTarget(e.target)) {
          e.preventDefault();
          palettePanelRef.current?.focus();
          paletteSearchRef.current?.focus();
          paletteSearchRef.current?.select();
        }
      }

      // Cmd/Ctrl + C to copy selected nodes
      if ((e.metaKey || e.ctrlKey) && key === "c") {
        if (!isEditableTarget(e.target)) {
          e.preventDefault();
          handleCopyShortcut();
        }
      }

      // Cmd/Ctrl + V to paste copied nodes
      if ((e.metaKey || e.ctrlKey) && key === "v") {
        if (!isEditableTarget(e.target)) {
          e.preventDefault();
          handlePasteShortcut();
        }
      }

      // Cmd/Ctrl + D to duplicate selection
      if ((e.metaKey || e.ctrlKey) && key === "d") {
        if (!isEditableTarget(e.target)) {
          e.preventDefault();
          handleDuplicateShortcut();
        }
      }

      // Delete/Backspace to delete selected node
      if (e.key === "Delete" || e.key === "Backspace") {
        // Only delete if not focused on an input
        if (!isEditableTarget(e.target)) {
          handleDeleteShortcut();
        }
      }
    };

    window.addEventListener("keydown", handleKeyDown);
    return () => window.removeEventListener("keydown", handleKeyDown);
  }, [handleCopyShortcut, handleDeleteShortcut, handleDuplicateShortcut, handlePasteShortcut, handleRedoShortcut, handleSaveShortcut, handleUndoShortcut, saving, setNodes]);

  const overlaySelectedNodeRuns: NodeRunItem[] =
    overlayRun && selectedNodeId
      ? overlayRun.node_runs
          .filter((nodeRun) => nodeRun.node_id === selectedNodeId)
          .toSorted((a, b) => a.attempt - b.attempt)
      : [];

  // Handlers for validation quick fixes
  const handleAddStartNode = useCallback(() => {
    // Mark the first executable node as trigger if one exists
    const executableNodes = nodes.filter((n) => n.type !== NOTE_NODE_TYPE);
    if (executableNodes.length > 0) {
      const firstNode = executableNodes[0];
      handleUpdateNode(firstNode.id, { isTrigger: true });
      showSuccess("Start node added", `"${(firstNode.data as Record<string, unknown>).label}" is now the entry point`);
    } else {
      // Open the prompt wizard to add a new prompt node as start
      setPromptWizardSourceNodeId(null);
      setPromptWizardOpen(true);
    }
  }, [nodes, handleUpdateNode, setPromptWizardSourceNodeId, setPromptWizardOpen]);

  const handleAddOutputNode = useCallback(() => {
    addExecutableNode(NODE_TYPES.OUTPUT, {
      sourceNodeId: selectedNodeId,
      config: {},
    });
  }, [addExecutableNode, selectedNodeId]);

  const handleFocusNode = useCallback((nodeId: string) => {
    setSelectedNodeId(nodeId);
    setSelectedEdgeId(null);
  }, [setSelectedEdgeId, setSelectedNodeId]);

  const handleFocusEdge = useCallback((edgeId: string) => {
    setSelectedEdgeId(edgeId);
    setSelectedNodeId(null);
  }, [setSelectedEdgeId, setSelectedNodeId]);

  const handleQuickFix = useCallback(
    (error: import("@/lib/graph-validator").ValidationError, fixLabel: string) => {
      if (error.code === "NO_START_NODE" && fixLabel === "Add Start") {
        handleAddStartNode();
      } else if (error.code === "NO_OUTPUT_NODE" && fixLabel === "Add Output") {
        handleAddOutputNode();
      } else if (error.code === "DISCONNECTED_NODE" && fixLabel === "Remove" && error.nodeId) {
        handleDeleteNode(error.nodeId);
      }
    },
    [handleAddStartNode, handleAddOutputNode, handleDeleteNode],
  );

  const handleWizardComplete = useCallback(
    async (payload: AgentWizardCompletePayload) => {
      const materialized = applyAgentBlueprint(payload.blueprint);
      showSuccess("AI worker flow added", `${payload.blueprint.name} was added as a real operating-model flow.`);

      if (!payload.runTest) {
        return;
      }

      if (saving || loadingVersion) {
        showError("Cannot run test now", "Please wait for current save/version operations to finish.");
        return;
      }

      showInfo("Starting test operation", "Saving the operating model and launching a test operation");

      let versionId = currentVersionId;

      try {
        if (isDirty || !versionId || materialized.createdNodeIds.length > 0) {
          const saveOk = await saveGraphSnapshot(materialized.nodes, materialized.edges);
          if (!saveOk) {
            return;
          }

          const latestVersion = await graphsApi.getLatestVersion(graphId);
          versionId = latestVersion?.id ?? versionId;
        }

        if (!versionId) {
          showError("Run failed", "Save the graph to create a version first.");
          return;
        }

        setStartingRun(true);
        const run = await runsApi.start(
          {
            graph_version_id: versionId,
            llm_mode: "managed",
            input_json: { mode: "wizard_test" },
          },
          {
            idempotencyKey: newClientCommandId("graph.run"),
          },
        );
        showSuccess("Test run started");
        void push(`/runs/${run.id}`);
      } catch (err: unknown) {
        showError("Run failed", getApiErrorMessage(err, ERROR_FALLBACKS.run.start));
      } finally {
        setStartingRun(false);
      }
    },
    [applyAgentBlueprint, currentVersionId, graphId, isDirty, loadingVersion, push, saveGraphSnapshot, saving, setStartingRun],
  );

  return {
    graphId,
    graphName,
    graphDescription,
    currentVersionId,
    availableVersions,
    loadingVersion,
    onUpdateMetadata,
    saving,
    nodes,
    edges,
    typedEdges,
    onNodesChange,
    onEdgesChange,
    selectedNode,
    selectedEdge,
    selectedNodeId,
    isDirty,
    isEditingMetadata,
    startingRun,
    overlayRun,
    overlayRunLoading,
    overlayRunRefreshing,
    overlayRunError,
    overlayCanceling,
    promptWizardOpen,
    promptWizardSourceNodeId,
    configDialogOpen,
    configDialogNodeType,
    configDialogInitialConfig,
    configDialogInitialLabel,
    memoryConfigOpen,
    marketplaceNodes,
    currentViewport,
    paletteSearchRef,
    wizardButtonRef,
    memoryButtonRef,
    palettePanelRef,
    canvasPanelRef,
    inspectorPanelRef,
    canUndo,
    canRedo,
    canQuickAddConnect,
    runDisabledReason,
    overlayRunId,
    overlaySelectedNodeRuns,
    captureFocusableTarget,
    restoreFocusableTarget,
    setPromptWizardOpen,
    setPromptWizardSourceNodeId,
    setConfigDialogOpen,
    setConfigDialogNodeType,
    setConfigDialogSourceNodeId,
    setConfigDialogInitialConfig,
    setConfigDialogInitialLabel,
    setIsEditingMetadata,
    setCurrentViewport,
    addExecutableNode,
    handleAddNode,
    handleAddNote,
    handleAddMarketplaceNode,
    handleConfigDialogComplete,
    handleMemoryConfigOpenChange,
    handleOpenMemoryConfig,
    handleWizardComplete,
    onConnect,
    onNodeClick,
    onEdgeClick,
    onNodeDragStart,
    onNodeDragStop,
    onPaneClick,
    handleUndo,
    handleRedo,
    handleAutoLayout,
    handleSelectVersion,
    handleRunWorkflow,
    handleSave,
    handleAddStartNode,
    handleAddOutputNode,
    handleExitExecutionView,
    handleCancelExecution,
    fetchOverlayRun,
    handleUpdateNode,
    handleUpdateEdge,
    handleDeleteNode,
    handleDeleteEdge,
    handleDuplicateNode,
    handleFocusNode,
    handleFocusEdge,
    handleQuickFix,
  };
}

type GraphEditorController = ReturnType<typeof useGraphEditorController>;

export function GraphEditor(props: GraphEditorProps) {
  const controller = useGraphEditorController(props);

  return (
    <ValidationProvider>
      <WizardProvider>
        <GraphEditorShell controller={controller} />
      </WizardProvider>
    </ValidationProvider>
  );
}

function GraphEditorShell({ controller }: { controller: GraphEditorController }) {
  return (
    <>
      <ValidationTrigger nodes={controller.nodes} edges={controller.edges} />
      <div className="flex h-full flex-col">
        <QuickToolBar
          marketplaceNodes={controller.marketplaceNodes}
          onSelectPackage={(pkg) => controller.handleAddMarketplaceNode(pkg, controller.canQuickAddConnect)}
          hasSelectedNode={controller.canQuickAddConnect}
        />
        <div className="flex flex-1 overflow-hidden">
          <GraphEditorDialogs controller={controller} />
          <GraphEditorPalettePanel controller={controller} />
          <GraphCanvasPanel controller={controller} />
          <GraphInspectorPanel controller={controller} />
        </div>
        <ValidationStatusBar
          onFocusNode={controller.handleFocusNode}
          onFocusEdge={controller.handleFocusEdge}
          onQuickFix={controller.handleQuickFix}
        />
      </div>
    </>
  );
}

function GraphEditorDialogs({ controller }: { controller: GraphEditorController }) {
  return (
    <>
      <AgentWizard
        onComplete={(payload) => {
          void controller.handleWizardComplete(payload);
          controller.restoreFocusableTarget();
        }}
        onExit={controller.restoreFocusableTarget}
      />
      <PromptNodeWizardDialog
        open={controller.promptWizardOpen}
        onOpenChange={(nextOpen) => {
          controller.setPromptWizardOpen(nextOpen);
          if (!nextOpen) {
            controller.setPromptWizardSourceNodeId(null);
            controller.restoreFocusableTarget();
          }
        }}
        onComplete={(config) => {
          controller.addExecutableNode(NODE_TYPES.PROMPT, {
            sourceNodeId: controller.promptWizardSourceNodeId,
            config,
          });
          controller.setPromptWizardSourceNodeId(null);
        }}
      />
      <NodeConfigDialog
        isOpen={controller.configDialogOpen}
        onClose={() => {
          controller.setConfigDialogOpen(false);
          controller.setConfigDialogNodeType(null);
          controller.setConfigDialogSourceNodeId(null);
          controller.setConfigDialogInitialConfig({});
          controller.setConfigDialogInitialLabel(null);
          controller.restoreFocusableTarget();
        }}
        nodeType={controller.configDialogNodeType}
        initialConfig={controller.configDialogInitialConfig}
        initialLabel={controller.configDialogInitialLabel ?? undefined}
        onSave={controller.handleConfigDialogComplete}
        FormComponent={
          controller.configDialogNodeType
            ? (getNodeFormComponent(controller.configDialogNodeType) ?? undefined)
            : undefined
        }
      />
      <MemoryConfigDialog
        graphId={controller.graphId ?? null}
        open={controller.memoryConfigOpen}
        onOpenChange={controller.handleMemoryConfigOpenChange}
      />
    </>
  );
}

function GraphEditorPalettePanel({ controller }: { controller: GraphEditorController }) {
  return (
    <div
      ref={controller.palettePanelRef}
      role="complementary"
      aria-label="Step palette panel"
      tabIndex={-1}
      className="w-64 border-r border-border bg-card/50 backdrop-blur-sm overflow-y-auto focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-primary/70"
    >
      <NodePalette
        onAddNode={controller.handleAddNode}
        onAddNote={controller.handleAddNote}
        onAddMarketplaceNode={controller.handleAddMarketplaceNode}
        marketplaceNodes={controller.marketplaceNodes}
        hasSelectedNode={controller.canQuickAddConnect}
        searchInputRef={controller.paletteSearchRef}
      />
    </div>
  );
}

function GraphCanvasPanel({ controller }: { controller: GraphEditorController }) {
  return (
    <div
      ref={controller.canvasPanelRef}
      role="region"
      aria-label="Canvas panel"
      data-testid="graph-canvas-panel"
      tabIndex={-1}
      className="flex-1 relative overflow-hidden focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-primary/70"
    >
      <ReactFlow
        className="bg-background"
        aria-label="Operating model canvas"
        nodes={controller.nodes}
        edges={controller.typedEdges}
        onNodesChange={controller.onNodesChange}
        onEdgesChange={controller.onEdgesChange}
        onConnect={controller.onConnect}
        connectOnClick
        onNodeClick={controller.onNodeClick}
        onEdgeClick={controller.onEdgeClick}
        onNodeDragStart={controller.onNodeDragStart}
        onNodeDragStop={controller.onNodeDragStop}
        onPaneClick={controller.onPaneClick}
        onMoveEnd={(_, viewport) => controller.setCurrentViewport(viewport)}
        nodeTypes={nodeTypes}
        edgeTypes={edgeTypes}
        defaultViewport={controller.currentViewport}
        fitView={!controller.currentViewport}
        onlyRenderVisibleElements
        snapToGrid
        snapGrid={GRAPH_EDITOR_SNAP_GRID}
        selectionOnDrag
        selectionMode={SelectionMode.Partial}
        selectNodesOnDrag={false}
        panOnDrag={[1, 2]}
        defaultEdgeOptions={{
          type: "typed",
          style: { strokeWidth: 2 },
          markerEnd: {
            type: MarkerType.ArrowClosed,
            width: 14,
            height: 14,
          },
        }}
      >
        <Background variant={BackgroundVariant.Dots} gap={24} size={0.8} color="rgba(255,255,255,0.06)" />
        <Controls />
        <MiniMap
          nodeStrokeWidth={3}
          zoomable
          pannable
          className="bg-background/60 backdrop-blur-sm border border-border rounded-lg"
        />
        <GraphCanvasToolbar controller={controller} />
        <Panel position="bottom-center">
          <button
            type="button"
            onClick={() => controller.paletteSearchRef.current?.focus()}
            className="bg-primary/90 text-white px-5 py-2.5 rounded-full text-sm font-medium shadow-lg hover:bg-primary transition-colors flex items-center gap-2 backdrop-blur-sm"
          >
            <Plus className="size-4" />
            Add Step
          </button>
        </Panel>
      </ReactFlow>
      <ValidationOverlay onAddStartNode={controller.handleAddStartNode} onAddOutputNode={controller.handleAddOutputNode} />
    </div>
  );
}

function GraphCanvasToolbar({ controller }: { controller: GraphEditorController }) {
  return (
    <Panel position="top-right" className="flex items-center gap-2">
      <div className="bg-background/60 backdrop-blur-sm border border-border rounded-lg overflow-hidden shadow-sm flex">
        <button
          type="button"
          aria-label="Undo"
          onClick={controller.handleUndo}
          disabled={!controller.canUndo}
          title="Undo (Ctrl+Z)"
          className="px-2.5 py-1.5 text-muted-foreground hover:bg-accent/50 hover:text-foreground disabled:opacity-40 disabled:cursor-not-allowed transition-colors"
        >
          <Undo2 aria-hidden="true" className="size-4" />
        </button>
        <div className="w-px bg-border" />
        <button
          type="button"
          aria-label="Redo"
          onClick={controller.handleRedo}
          disabled={!controller.canRedo}
          title="Redo (Ctrl+Y)"
          className="px-2.5 py-1.5 text-muted-foreground hover:bg-accent/50 hover:text-foreground disabled:opacity-40 disabled:cursor-not-allowed transition-colors"
        >
          <Redo2 aria-hidden="true" className="size-4" />
        </button>
      </div>
      <button
        type="button"
        aria-label="Auto-layout"
        onClick={controller.handleAutoLayout}
        disabled={controller.nodes.length === 0}
        className="bg-background/60 backdrop-blur-sm border border-border text-muted-foreground px-3 py-1.5 rounded-lg text-sm font-medium hover:bg-accent/50 hover:text-foreground disabled:opacity-50 disabled:cursor-not-allowed transition-colors shadow-sm flex items-center gap-1.5"
        title="Tidy up layout"
      >
        <LayoutGrid aria-hidden="true" className="size-4" />
        <span className="hidden sm:inline">Tidy</span>
      </button>
      <GraphVersionSelect controller={controller} />
      {!controller.isEditingMetadata ? <GraphPrimaryActions controller={controller} /> : null}
    </Panel>
  );
}

function GraphVersionSelect({ controller }: { controller: GraphEditorController }) {
  return (
    <div className="bg-background/60 backdrop-blur-sm border border-border rounded-lg px-3 py-1.5 text-sm text-muted-foreground shadow-sm flex items-center gap-2">
      <select
        aria-label="Saved version"
        value={controller.currentVersionId ?? ""}
        disabled={controller.loadingVersion || controller.saving || controller.availableVersions.length === 0}
        onChange={(event) => void controller.handleSelectVersion(event.target.value)}
        className="bg-transparent text-sm text-muted-foreground outline-none"
      >
        {controller.availableVersions.length === 0 ? (
          <option value="">No version</option>
        ) : (
          controller.availableVersions.toSorted((left, right) => right.version - left.version).map((version) => (
            <option key={version.id} value={version.id}>
              v{version.version}
            </option>
          ))
        )}
      </select>
      {controller.isDirty ? <span className="text-amber-500 ml-1">*</span> : null}
    </div>
  );
}

function GraphPrimaryActions({ controller }: { controller: GraphEditorController }) {
  return (
    <>
      <WizardButton buttonRef={controller.wizardButtonRef} onBeforeStart={controller.captureFocusableTarget} />
      <button
        ref={controller.memoryButtonRef}
        type="button"
        aria-label="Memory settings"
        onClick={controller.handleOpenMemoryConfig}
        className="bg-background/60 backdrop-blur-sm border border-border text-muted-foreground px-3 py-1.5 rounded-lg text-sm font-medium hover:bg-accent/50 hover:text-foreground transition-colors shadow-sm flex items-center gap-1.5"
      >
        <Brain aria-hidden="true" className="size-4" />
        <span className="hidden sm:inline">Memory</span>
      </button>
      <button
        type="button"
        aria-label={controller.runDisabledReason ?? "Launch test operation"}
        onClick={() => void controller.handleRunWorkflow()}
        disabled={Boolean(controller.runDisabledReason)}
        title={controller.runDisabledReason ?? "Launch test operation"}
        className="bg-emerald-600 text-white px-4 py-1.5 rounded-lg text-sm font-medium hover:bg-emerald-700 disabled:opacity-50 disabled:cursor-not-allowed transition-colors shadow-sm"
      >
        {controller.startingRun ? "Starting" : <Play aria-hidden="true" className="size-4" />}
      </button>
      <button
        type="button"
        aria-label={controller.saving ? "Saving" : "Save"}
        onClick={() => void controller.handleSave()}
        disabled={controller.saving || !controller.isDirty}
        className="bg-primary text-white px-4 py-1.5 rounded-lg text-sm font-medium hover:bg-primary/90 disabled:opacity-50 disabled:cursor-not-allowed transition-colors shadow-sm"
      >
        {controller.saving ? "Saving" : <SaveIcon aria-hidden="true" className="size-4" />}
      </button>
    </>
  );
}

function GraphInspectorPanel({ controller }: { controller: GraphEditorController }) {
  return (
    <div
      ref={controller.inspectorPanelRef}
      role="complementary"
      aria-label="Inspector panel"
      tabIndex={-1}
      className="w-80 border-l border-border bg-card/50 backdrop-blur-sm overflow-y-auto focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-primary/70"
    >
      {controller.overlayRunId ? <ExecutionOverlayPanel controller={controller} /> : null}
      <NodeInspector
        selectedNode={controller.selectedNode}
        selectedEdge={controller.selectedEdge}
        nodes={controller.nodes}
        edges={controller.edges}
        graphName={controller.graphName}
        graphDescription={controller.graphDescription}
        onUpdateNode={controller.handleUpdateNode}
        onUpdateEdge={controller.handleUpdateEdge}
        onDeleteNode={controller.handleDeleteNode}
        onDeleteEdge={controller.handleDeleteEdge}
        onDuplicateNode={controller.handleDuplicateNode}
        onUpdateMetadata={controller.onUpdateMetadata}
        onEditingMetadataChange={controller.setIsEditingMetadata}
      />
    </div>
  );
}

function ExecutionOverlayPanel({ controller }: { controller: GraphEditorController }) {
  return (
    <div className="border-b border-border bg-muted/30 p-4 space-y-3">
      <div className="flex items-center justify-between gap-2">
        <h3 className="text-sm font-semibold text-foreground">Operation</h3>
        <button
          type="button"
          onClick={controller.handleExitExecutionView}
          className="text-xs font-medium text-muted-foreground hover:text-foreground transition-colors"
        >
          Exit
        </button>
      </div>
      {controller.overlayRunLoading && !controller.overlayRun ? (
        <p className="text-xs text-muted-foreground">Loading operation detail&hellip;</p>
      ) : null}
      {controller.overlayRunError ? (
        <p className="text-xs text-destructive whitespace-pre-wrap">{controller.overlayRunError}</p>
      ) : null}
      {controller.overlayRun ? <ExecutionOverlayDetail controller={controller} /> : null}
    </div>
  );
}

function ExecutionOverlayDetail({ controller }: { controller: GraphEditorController }) {
  const run = controller.overlayRun;
  if (!run) {
    return null;
  }

  return (
    <>
      <div className="flex items-center justify-between gap-2 text-xs text-muted-foreground">
        <span>
          Status: <span className="font-medium text-foreground">{String(run.status)}</span>
        </span>
        <Link href={`/runs/${run.id}`} className="text-primary hover:underline">
          Open operation
        </Link>
      </div>
      <div className="flex items-center gap-2">
        {!isTerminalRunStatus(String(run.status)) ? (
          <button
            type="button"
            onClick={() => void controller.handleCancelExecution()}
            disabled={controller.overlayCanceling}
            className="flex-1 bg-red-600 text-white px-3 py-1.5 rounded-md text-xs font-medium hover:bg-red-700 disabled:opacity-50 disabled:cursor-not-allowed transition-colors"
          >
            {controller.overlayCanceling ? "Stopping" : "Stop"}
          </button>
        ) : null}
        <button
          type="button"
          onClick={() => void controller.fetchOverlayRun()}
          disabled={controller.overlayRunLoading || controller.overlayRunRefreshing}
          className="flex-1 bg-background/60 backdrop-blur-sm border border-border text-foreground px-3 py-1.5 rounded-md text-xs font-medium hover:bg-accent/50 disabled:opacity-50 disabled:cursor-not-allowed transition-colors"
        >
          {controller.overlayRunLoading || controller.overlayRunRefreshing ? "Refreshing" : "Refresh"}
        </button>
      </div>
      <div className="pt-3 border-t border-border space-y-2">
        <p className="text-xs font-semibold text-muted-foreground uppercase">Department activity</p>
        <NodeRunActivityList controller={controller} />
      </div>
    </>
  );
}

function NodeRunActivityList({ controller }: { controller: GraphEditorController }) {
  if (!controller.selectedNodeId) {
    return <p className="text-xs text-muted-foreground">Select a step to inspect its activity.</p>;
  }
  if (controller.overlaySelectedNodeRuns.length === 0) {
    return <p className="text-xs text-muted-foreground">No activity records for this step.</p>;
  }

  return (
    <div className="space-y-2">
      {controller.overlaySelectedNodeRuns.map((nodeRun) => (
        <NodeRunActivityCard key={nodeRun.id} nodeRun={nodeRun} />
      ))}
    </div>
  );
}

function NodeRunActivityCard({ nodeRun }: { nodeRun: NodeRunItem }) {
  const agentTrace = getNodeRunAgentTrace(nodeRun);

  return (
    <div className="rounded-lg border border-border bg-background/40 p-2 space-y-2">
      <div className="flex items-center justify-between gap-2 text-xs">
        <span className="font-medium text-foreground">attempt {nodeRun.attempt}</span>
        <span className="text-muted-foreground">{String(nodeRun.status)}</span>
        <span className="text-muted-foreground">{formatDuration(nodeRun.duration_ms)}</span>
      </div>
      {agentTrace ? <AgentTracePanel trace={agentTrace} compact /> : null}
      <NodeRunJsonBlock title="Deliverable / response" value={nodeRun.output_json} open />
      <NodeRunJsonBlock title="Needs attention" value={nodeRun.error_json} open={String(nodeRun.status) === "failed"} />
      <NodeRunJsonBlock title="Input" value={nodeRun.input_json} />
    </div>
  );
}

function NodeRunJsonBlock({ open, title, value }: { open?: boolean; title: string; value: unknown }) {
  return (
    <details open={open}>
      <summary className="cursor-pointer text-xs font-medium text-muted-foreground">{title}</summary>
      <pre className="mt-1 max-h-40 overflow-auto rounded border border-border/50 bg-muted p-2 text-[11px] text-foreground font-mono whitespace-pre-wrap">
        {formatJsonForDisplay(value)}
      </pre>
    </details>
  );
}
