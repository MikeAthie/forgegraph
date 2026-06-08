import { Panel } from "@xyflow/react";
import { LayoutGrid, Redo2, Undo2 } from "lucide-react";

import { GraphPrimaryActions } from "./GraphPrimaryActions";
import type { GraphEditorController } from "./GraphEditor";

export function GraphCanvasToolbar({ controller }: { controller: GraphEditorController }) {
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
          controller.availableVersions
            .toSorted((left, right) => right.version - left.version)
            .map((version) => (
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
