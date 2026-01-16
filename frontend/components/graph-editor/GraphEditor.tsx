"use client";

import { useCallback, useState, useEffect } from "react";
import {
  ReactFlow,
  Controls,
  Background,
  MiniMap,
  useNodesState,
  useEdgesState,
  addEdge,
  type Connection,
  type Node,
  type Edge,
  type NodeTypes,
  BackgroundVariant,
  Panel,
} from "@xyflow/react";
import { Save as SaveIcon } from "lucide-react";

import type { GraphJson, NodeType } from "../../lib/graph-types";
import { NODE_TYPES, PHASE2_NODE_TYPES, createEmptyGraphJson } from "../../lib/graph-types";
import { graphJsonToReactFlow, reactFlowToGraphJson } from "../../lib/graph-conversion";
import { NodePalette } from "./NodePalette";
import { NodeInspector } from "./NodeInspector";
import { GraphNode as GraphNodeComponent } from "./nodes/GraphNode";

// Custom node types for React Flow
const nodeTypes: NodeTypes = {
  [NODE_TYPES.PROMPT]: GraphNodeComponent,
  [NODE_TYPES.HTTP]: GraphNodeComponent,
  [NODE_TYPES.TRANSFORM]: GraphNodeComponent,
  [NODE_TYPES.OUTPUT]: GraphNodeComponent,
  [NODE_TYPES.BRANCH]: GraphNodeComponent,
  [NODE_TYPES.MERGE]: GraphNodeComponent,
  [NODE_TYPES.HUMAN_GATE]: GraphNodeComponent,
};

interface GraphEditorProps {
  graphId: string;
  graphName: string;
  graphDescription: string;
  initialGraphJson: GraphJson | null;
  currentVersion: number | null;
  onSave: (graphJson: GraphJson) => Promise<void>;
  onUpdateMetadata: (name: string, description: string) => Promise<void>;
  saving: boolean;
}

// Generate unique ID for new nodes/edges
function generateId(): string {
  return `${Date.now()}-${Math.random().toString(36).substr(2, 9)}`;
}

export function GraphEditor({
  graphId,
  graphName,
  graphDescription,
  initialGraphJson,
  currentVersion,
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
  const [isDirty, setIsDirty] = useState(false);
  const [isEditingMetadata, setIsEditingMetadata] = useState(false);

  // Track changes
  useEffect(() => {
    setIsDirty(true);
  }, [nodes, edges]);

  // Reset dirty state when initialGraphJson changes (after save)
  useEffect(() => {
    setIsDirty(false);
  }, [initialGraphJson]);

  const selectedNode = selectedNodeId
    ? nodes.find((n) => n.id === selectedNodeId)
    : null;

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

      const newEdge: Edge = {
        ...connection,
        id: generateId(),
      } as Edge;

      setEdges((eds) => addEdge(newEdge, eds));
    },
    [edges, setEdges]
  );

  const onNodeClick = useCallback((_: React.MouseEvent, node: Node) => {
    setSelectedNodeId(node.id);
  }, []);

  const onPaneClick = useCallback(() => {
    setSelectedNodeId(null);
  }, []);

  const handleAddNode = useCallback(
    (nodeType: NodeType) => {
      const typeInfo = PHASE2_NODE_TYPES.find((t) => t.type === nodeType);
      if (!typeInfo?.enabled) return;

      const newNode: Node = {
        id: generateId(),
        type: nodeType,
        position: { x: 250, y: 150 },
        data: {
          label: `${typeInfo.label} Node`,
          nodeType: nodeType,
          config: {},
        },
      };

      setNodes((nds) => [...nds, newNode]);
      setSelectedNodeId(newNode.id);
    },
    [setNodes]
  );

  const handleUpdateNode = useCallback(
    (nodeId: string, updates: Partial<Node["data"]>) => {
      setNodes((nds) =>
        nds.map((node) =>
          node.id === nodeId
            ? { ...node, data: { ...node.data, ...updates } }
            : node
        )
      );
    },
    [setNodes]
  );

  const handleDeleteNode = useCallback(
    (nodeId: string) => {
      setNodes((nds) => nds.filter((n) => n.id !== nodeId));
      setEdges((eds) => eds.filter((e) => e.source !== nodeId && e.target !== nodeId));
      if (selectedNodeId === nodeId) {
        setSelectedNodeId(null);
      }
    },
    [setNodes, setEdges, selectedNodeId]
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

  // Keyboard shortcuts
  useEffect(() => {
    const handleKeyDown = (e: KeyboardEvent) => {
      // Cmd/Ctrl + S to save
      if ((e.metaKey || e.ctrlKey) && e.key === "s") {
        e.preventDefault();
        if (!saving) {
          void handleSave();
        }
      }

      // Delete/Backspace to delete selected node
      if ((e.key === "Delete" || e.key === "Backspace") && selectedNodeId) {
        // Only delete if not focused on an input
        const target = e.target as HTMLElement;
        if (target.tagName !== "INPUT" && target.tagName !== "TEXTAREA") {
          handleDeleteNode(selectedNodeId);
        }
      }
    };

    window.addEventListener("keydown", handleKeyDown);
    return () => window.removeEventListener("keydown", handleKeyDown);
  }, [handleSave, saving, selectedNodeId, handleDeleteNode]);

  return (
    <div className="flex h-full">
      {/* Left Panel - Node Palette */}
      <div className="w-64 border-r border-gray-200 bg-white overflow-y-auto">
        <NodePalette onAddNode={handleAddNode} />
      </div>

      {/* Center - Canvas */}
      <div className="flex-1 relative">
        <ReactFlow
          nodes={nodes}
          edges={edges}
          onNodesChange={onNodesChange}
          onEdgesChange={onEdgesChange}
          onConnect={onConnect}
          onNodeClick={onNodeClick}
          onPaneClick={onPaneClick}
          nodeTypes={nodeTypes}
          fitView
          snapToGrid
          snapGrid={[15, 15]}
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
            <div className="bg-white border border-gray-200 rounded-lg px-3 py-1.5 text-sm text-gray-600 shadow-sm">
              {currentVersion ? `v${currentVersion}` : "No version"}
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
          onUpdateMetadata={onUpdateMetadata}
          onEditingMetadataChange={setIsEditingMetadata}
        />
      </div>
    </div>
  );
}
