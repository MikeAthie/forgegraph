import {
  Background,
  BackgroundVariant,
  Controls,
  MarkerType,
  MiniMap,
  Panel,
  ReactFlow,
  SelectionMode,
  type EdgeTypes,
  type NodeTypes,
} from "@xyflow/react";
import { Plus } from "lucide-react";

import { NODE_TYPES } from "../../lib/graph-types";
import { GRAPH_EDITOR_SNAP_GRID } from "../../lib/graph-editor-interactions";
import { GraphNode as GraphNodeComponent } from "./nodes/GraphNode";
import { NoteNode as NoteNodeComponent } from "./nodes/NoteNode";
import { TypedEdge } from "./TypedEdge";
import { ValidationOverlay } from "./validation/ValidationOverlay";
import { GraphCanvasToolbar } from "./GraphCanvasToolbar";
import type { GraphEditorController } from "./GraphEditor";

const NOTE_NODE_TYPE = "note";

const edgeTypes: EdgeTypes = {
  typed: TypedEdge,
};

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

export function GraphCanvasPanel({ controller }: { controller: GraphEditorController }) {
  return (
    <section
      ref={controller.canvasPanelRef}
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
      <ValidationOverlay
        onAddStartNode={controller.handleAddStartNode}
        onAddOutputNode={controller.handleAddOutputNode}
      />
    </section>
  );
}
