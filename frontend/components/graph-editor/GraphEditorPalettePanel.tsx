import { NodePalette } from "./NodePalette";
import type { GraphEditorController } from "./GraphEditor";

export function GraphEditorPalettePanel({ controller }: { controller: GraphEditorController }) {
  return (
    <aside
      ref={controller.palettePanelRef}
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
    </aside>
  );
}
