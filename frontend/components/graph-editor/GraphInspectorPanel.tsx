import { NodeInspector } from "./NodeInspector";
import { ExecutionOverlayDetail } from "./ExecutionOverlayDetail";
import type { GraphEditorController } from "./GraphEditor";

export function GraphInspectorPanel({ controller }: { controller: GraphEditorController }) {
  return (
    <aside
      ref={controller.inspectorPanelRef}
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
    </aside>
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
