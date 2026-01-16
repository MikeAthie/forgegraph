"use client";

import { useCallback, useEffect, useRef, useState } from "react";
import {
  ReactFlow,
  Controls,
  Background,
  MiniMap,
  useNodesState,
  useEdgesState,
  addEdge,
  SelectionMode,
  type OnNodeDrag,
  type Connection,
  type Node,
  type Edge,
  type NodeTypes,
  BackgroundVariant,
  Panel,
} from "@xyflow/react";
import { Save as SaveIcon, LayoutGrid, Redo2, Undo2 } from "lucide-react";

import type { GraphJson, NodeType } from "../../lib/graph-types";
import { NODE_TYPES, PHASE2_NODE_TYPES, createEmptyGraphJson } from "../../lib/graph-types";
import { graphJsonToReactFlow, reactFlowToGraphJson } from "../../lib/graph-conversion";
import { getLayoutedElements } from "../../lib/graph-layout";
import { NodePalette } from "./NodePalette";
import { NodeInspector } from "./NodeInspector";
import { GraphNode as GraphNodeComponent } from "./nodes/GraphNode";
import { NoteNode as NoteNodeComponent } from "./nodes/NoteNode";

const NOTE_NODE_TYPE = "note";

// Custom node types for React Flow
const nodeTypes: NodeTypes = {
  [NODE_TYPES.PROMPT]: GraphNodeComponent,
  [NODE_TYPES.HTTP]: GraphNodeComponent,
  [NODE_TYPES.TRANSFORM]: GraphNodeComponent,
  [NODE_TYPES.OUTPUT]: GraphNodeComponent,
  [NODE_TYPES.BRANCH]: GraphNodeComponent,
  [NODE_TYPES.MERGE]: GraphNodeComponent,
  [NODE_TYPES.HUMAN_GATE]: GraphNodeComponent,
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

function deepClone<T>(value: T): T {
  const cloneFn = (globalThis as any).structuredClone as ((input: T) => T) | undefined;
  if (typeof cloneFn === "function") {
    return cloneFn(value);
  }
  return JSON.parse(JSON.stringify(value)) as T;
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

export function GraphEditor({
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
  const initial = initialGraphJson
    ? graphJsonToReactFlow(initialGraphJson)
    : graphJsonToReactFlow(createEmptyGraphJson({ name: graphName, description: graphDescription }));

  const [nodes, setNodes, onNodesChange] = useNodesState(initial.nodes);
  const [edges, setEdges, onEdgesChange] = useEdgesState(initial.edges);
  const [selectedNodeId, setSelectedNodeId] = useState<string | null>(null);
  const [selectedEdgeId, setSelectedEdgeId] = useState<string | null>(null);
  const [isDirty, setIsDirty] = useState(false);
  const [isEditingMetadata, setIsEditingMetadata] = useState(false);

  const paletteSearchRef = useRef<HTMLInputElement>(null);

  const clipboardRef = useRef<ClipboardSnapshot | null>(null);
  const pasteOffsetRef = useRef(0);

  const undoStackRef = useRef<EditorSnapshot[]>([]);
  const redoStackRef = useRef<EditorSnapshot[]>([]);
  const [canUndo, setCanUndo] = useState(false);
  const [canRedo, setCanRedo] = useState(false);
  const editHistoryArmedRef = useRef(false);
  const editHistoryTimerRef = useRef<ReturnType<typeof setTimeout> | null>(null);
  const dragHistoryPushedRef = useRef(false);

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
  }, [setEdges, setNodes, takeSnapshot]);

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
  }, [setEdges, setNodes, takeSnapshot]);

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
    const selectedEdges = edges.filter(
      (edge) => selectedIds.has(edge.source) && selectedIds.has(edge.target),
    );

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

        const label =
          typeof (node.data as any)?.label === "string" ? String((node.data as any).label) : "";

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

      const newEdges: Edge[] = clipboard.edges
        .map((edge): Edge | null => {
          const source = idMap.get(edge.source);
          const target = idMap.get(edge.target);
          if (!source || !target) return null;

          return {
            id: generateId(),
            source,
            target,
            label: edge.label,
            data: deepClone(edge.data),
          } as Edge;
        })
        .filter((edge): edge is Edge => edge !== null);

      setNodes((nds) => [...nds.map((n) => ({ ...n, selected: false })), ...newNodes]);
      setEdges((eds) => [...eds.map((e) => ({ ...e, selected: false })), ...newEdges]);
      setSelectedNodeId(newNodes[0]?.id ?? null);
      setSelectedEdgeId(null);
      setIsDirty(true);
    },
    [pushHistory, setEdges, setNodes],
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
    const selectedEdges = edges.filter(
      (edge) => selectedIds.has(edge.source) && selectedIds.has(edge.target),
    );

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
  }, [getSelectedEdges, getSelectedNodes, pushHistory, setEdges, setNodes]);

  // Sync editor state when the loaded version changes (save or version switch).
  useEffect(() => {
    resetHistory();

    if (!initialGraphJson) {
      setIsDirty(false);
      return;
    }

    const next = graphJsonToReactFlow(initialGraphJson);
    setNodes(next.nodes);
    setEdges(next.edges);
    setSelectedNodeId(null);
    setSelectedEdgeId(null);
    setIsDirty(false);
  }, [initialGraphJson, resetHistory, setNodes, setEdges]);

  const selectedNode = selectedNodeId
    ? nodes.find((n) => n.id === selectedNodeId)
    : null;
  const canQuickAddConnect = !!selectedNode && selectedNode.type !== NOTE_NODE_TYPE;

  const handleSelectVersion = useCallback(
    async (versionId: string) => {
      if (!versionId || versionId === currentVersionId) return;

      if (isDirty) {
        const confirmed = window.confirm(
          "You have unsaved changes. Discard them and switch versions?"
        );
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
      // Prevent self-connections
      if (connection.source === connection.target) {
        return;
      }

      // Prevent duplicate edges
      const exists = edges.some(
        (e) => e.source === connection.source && e.target === connection.target
      );
      if (exists) {
        return;
      }

      pushHistory();
      const newEdge: Edge = {
        ...connection,
        id: generateId(),
      } as Edge;

      setEdges((eds) => addEdge(newEdge, eds));
      setIsDirty(true);
    },
    [edges, pushHistory, setEdges]
  );

  const onNodeClick = useCallback((_: React.MouseEvent, node: Node) => {
    setSelectedNodeId(node.id);
    setSelectedEdgeId(null);
  }, []);

  const onEdgeClick = useCallback((_: React.MouseEvent, edge: Edge) => {
    setSelectedEdgeId(edge.id);
    setSelectedNodeId(null);
  }, []);

  const onNodeDragStop = useCallback<OnNodeDrag>((_, __, ___) => {
    dragHistoryPushedRef.current = false;
    setIsDirty(true);
  }, []);

  const onNodeDragStart = useCallback<OnNodeDrag>(() => {
    if (dragHistoryPushedRef.current) return;
    dragHistoryPushedRef.current = true;
    pushHistory();
  }, [pushHistory]);

  const onPaneClick = useCallback(() => {
    setSelectedNodeId(null);
    setSelectedEdgeId(null);
  }, []);

  const handleAddNode = useCallback(
    (nodeType: NodeType, connectToSelected = false) => {
      const typeInfo = PHASE2_NODE_TYPES.find((t) => t.type === nodeType);
      if (!typeInfo?.enabled) return;

      pushHistory();
      const newNodeId = generateId();
      const sourceNode =
        connectToSelected && selectedNodeId
          ? nodes.find((n) => n.id === selectedNodeId && n.type !== NOTE_NODE_TYPE)
          : null;

      setNodes((nds) => {
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
            label: `${typeInfo.label} Node`,
            nodeType: nodeType,
            config: {},
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
    [nodes, pushHistory, selectedNodeId, setEdges, setNodes]
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
  }, [pushHistory, setNodes]);

  const handleUpdateNode = useCallback(
    (nodeId: string, updates: Partial<Node["data"]>) => {
      pushHistoryForEdit();
      setNodes((nds) =>
        nds.map((node) =>
          node.id === nodeId
            ? { ...node, data: { ...node.data, ...updates } }
            : node
        )
      );
      setIsDirty(true);
    },
    [pushHistoryForEdit, setNodes]
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
    [nodes, pushHistory, setNodes, setEdges, selectedNodeId]
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
    [nodes, pushHistory, setNodes]
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
    [edges, pushHistory, setEdges, selectedEdgeId],
  );

  const handleSave = useCallback(async () => {
    const graphJson = reactFlowToGraphJson(
      nodes,
      edges,
      { name: graphName, description: graphDescription },
      graphId
    );
    await onSave(graphJson);
    setIsDirty(false);
  }, [nodes, edges, graphName, graphDescription, graphId, onSave]);

  const handleAutoLayout = useCallback(() => {
    if (nodes.length === 0) return;
    pushHistory();
    const executableNodes = nodes.filter((node) => node.type !== NOTE_NODE_TYPE);
    const noteNodes = nodes.filter((node) => node.type === NOTE_NODE_TYPE);
    const executableIds = new Set(executableNodes.map((node) => node.id));
    const executableEdges = edges.filter(
      (edge) => executableIds.has(edge.source) && executableIds.has(edge.target)
    );

    const { nodes: layoutedNodes, edges: layoutedEdges } = getLayoutedElements(
      executableNodes,
      executableEdges,
      { direction: "TB", nodeSpacing: 50, rankSpacing: 100 }
    );
    setNodes([...layoutedNodes, ...noteNodes]);
    setEdges(layoutedEdges);
    setIsDirty(true);
  }, [nodes, edges, pushHistory, setNodes, setEdges]);

  // Keyboard shortcuts
  useEffect(() => {
    const handleKeyDown = (e: KeyboardEvent) => {
      // Cmd/Ctrl + S to save
      if ((e.metaKey || e.ctrlKey) && e.key.toLowerCase() === "s") {
        if (!isEditableTarget(e.target)) {
          e.preventDefault();
          if (!saving) {
            void handleSave();
          }
        }
      }

      // Cmd/Ctrl + A to select all nodes
      if ((e.metaKey || e.ctrlKey) && e.key.toLowerCase() === "a") {
        if (!isEditableTarget(e.target)) {
          e.preventDefault();
          setNodes((nds) => nds.map((n) => ({ ...n, selected: true })));
        }
      }

      // Cmd/Ctrl + Z (undo) and Cmd/Ctrl + Shift + Z (redo)
      if ((e.metaKey || e.ctrlKey) && e.key.toLowerCase() === "z") {
        if (!isEditableTarget(e.target)) {
          e.preventDefault();
          if (e.shiftKey) {
            handleRedo();
          } else {
            handleUndo();
          }
        }
      }

      // Cmd/Ctrl + Y to redo (Windows convention)
      if ((e.metaKey || e.ctrlKey) && e.key.toLowerCase() === "y") {
        if (!isEditableTarget(e.target)) {
          e.preventDefault();
          handleRedo();
        }
      }

      // Cmd/Ctrl + Shift + F to focus node search
      if ((e.metaKey || e.ctrlKey) && e.shiftKey && e.key.toLowerCase() === "f") {
        if (!isEditableTarget(e.target)) {
          e.preventDefault();
          paletteSearchRef.current?.focus();
          paletteSearchRef.current?.select();
        }
      }

      // Cmd/Ctrl + C to copy selected nodes
      if ((e.metaKey || e.ctrlKey) && e.key.toLowerCase() === "c") {
        if (!isEditableTarget(e.target)) {
          e.preventDefault();
          handleCopy();
        }
      }

      // Cmd/Ctrl + V to paste copied nodes
      if ((e.metaKey || e.ctrlKey) && e.key.toLowerCase() === "v") {
        if (!isEditableTarget(e.target)) {
          e.preventDefault();
          handlePaste();
        }
      }

      // Cmd/Ctrl + D to duplicate selection
      if ((e.metaKey || e.ctrlKey) && e.key.toLowerCase() === "d") {
        if (!isEditableTarget(e.target)) {
          e.preventDefault();
          handleDuplicateSelection();
        }
      }

      // Delete/Backspace to delete selected node
      if (e.key === "Delete" || e.key === "Backspace") {
        // Only delete if not focused on an input
        if (!isEditableTarget(e.target)) {
          handleDeleteSelection();
        }
      }
    };

    window.addEventListener("keydown", handleKeyDown);
    return () => window.removeEventListener("keydown", handleKeyDown);
  }, [handleSave, saving, setNodes, handleUndo, handleRedo, handleCopy, handlePaste, handleDuplicateSelection, handleDeleteSelection]);

  return (
    <div className="flex h-full">
      {/* Left Panel - Node Palette */}
      <div className="w-64 border-r border-gray-200 bg-white overflow-y-auto">
        <NodePalette
          onAddNode={handleAddNode}
          onAddNote={handleAddNote}
          hasSelectedNode={canQuickAddConnect}
          searchInputRef={paletteSearchRef}
        />
      </div>

      {/* Center - Canvas */}
      <div className="flex-1 relative overflow-hidden">
        <ReactFlow
          nodes={nodes}
          edges={edges}
          onNodesChange={onNodesChange}
          onEdgesChange={onEdgesChange}
          onConnect={onConnect}
          connectOnClick
          onNodeClick={onNodeClick}
          onEdgeClick={onEdgeClick}
          onNodeDragStart={onNodeDragStart}
          onNodeDragStop={onNodeDragStop}
          onPaneClick={onPaneClick}
          nodeTypes={nodeTypes}
          fitView
          snapToGrid
          snapGrid={[15, 15]}
          selectionOnDrag
          selectionMode={SelectionMode.Partial}
          selectNodesOnDrag={false}
          panOnDrag={[1, 2]}
          defaultEdgeOptions={{
            type: "smoothstep",
            style: { strokeWidth: 2 },
          }}
        >
          <Background variant={BackgroundVariant.Dots} gap={20} size={1} />
          <Controls />
          <MiniMap
            nodeStrokeWidth={3}
            zoomable
            pannable
            className="bg-white border border-gray-200 rounded-lg"
          />
          <Panel position="top-right" className="flex items-center gap-2">
            <div className="bg-white border border-gray-200 rounded-lg overflow-hidden shadow-sm flex">
              <button
                type="button"
                aria-label="Undo"
                onClick={handleUndo}
                disabled={!canUndo}
                title="Undo (Ctrl+Z)"
                className="px-2.5 py-1.5 text-gray-600 hover:bg-gray-50 disabled:opacity-40 disabled:cursor-not-allowed transition-colors"
              >
                <Undo2 aria-hidden="true" className="h-4 w-4" />
              </button>
              <div className="w-px bg-gray-200" />
              <button
                type="button"
                aria-label="Redo"
                onClick={handleRedo}
                disabled={!canRedo}
                title="Redo (Ctrl+Y)"
                className="px-2.5 py-1.5 text-gray-600 hover:bg-gray-50 disabled:opacity-40 disabled:cursor-not-allowed transition-colors"
              >
                <Redo2 aria-hidden="true" className="h-4 w-4" />
              </button>
            </div>
            <button
              type="button"
              aria-label="Auto-layout"
              onClick={handleAutoLayout}
              disabled={nodes.length === 0}
              className="bg-white border border-gray-200 text-gray-600 px-3 py-1.5 rounded-lg text-sm font-medium hover:bg-gray-50 disabled:opacity-50 disabled:cursor-not-allowed transition-colors shadow-sm flex items-center gap-1.5"
              title="Tidy up layout"
            >
              <LayoutGrid aria-hidden="true" className="h-4 w-4" />
              <span className="hidden sm:inline">Tidy</span>
            </button>
            <div className="bg-white border border-gray-200 rounded-lg px-3 py-1.5 text-sm text-gray-600 shadow-sm flex items-center gap-2">
              <select
                aria-label="Version"
                value={currentVersionId ?? ""}
                disabled={loadingVersion || saving || availableVersions.length === 0}
                onChange={(e) => void handleSelectVersion(e.target.value)}
                className="bg-transparent text-sm text-gray-600 outline-none"
              >
                {availableVersions.length === 0 ? (
                  <option value="">No version</option>
                ) : (
                  [...availableVersions]
                    .sort((a, b) => b.version - a.version)
                    .map((v) => (
                      <option key={v.id} value={v.id}>
                        v{v.version}
                      </option>
                    ))
                )}
              </select>
              {isDirty && <span className="text-amber-500 ml-1">*</span>}
            </div>
            {!isEditingMetadata && (
              <button
                type="button"
                aria-label={saving ? "Saving..." : "Save"}
                onClick={() => void handleSave()}
                disabled={saving || !isDirty}
                className="bg-primary text-white px-4 py-1.5 rounded-lg text-sm font-medium hover:bg-primary/90 disabled:opacity-50 disabled:cursor-not-allowed transition-colors shadow-sm"
              >
                {saving ? "Saving..." : <SaveIcon aria-hidden="true" className="h-4 w-4" />}
              </button>
            )}
          </Panel>
        </ReactFlow>
      </div>

      {/* Right Panel - Inspector */}
      <div className="w-80 border-l border-gray-200 bg-white overflow-y-auto">
        <NodeInspector
          selectedNode={selectedNode}
          graphName={graphName}
          graphDescription={graphDescription}
          onUpdateNode={handleUpdateNode}
          onDeleteNode={handleDeleteNode}
          onDuplicateNode={handleDuplicateNode}
          onUpdateMetadata={onUpdateMetadata}
          onEditingMetadataChange={setIsEditingMetadata}
        />
      </div>
    </div>
  );
}
