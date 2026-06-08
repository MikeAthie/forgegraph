import { ValidationStatusBar } from "./validation/ValidationStatusBar";
import { QuickToolBar } from "./QuickToolBar";
import { GraphEditorDialogs } from "./GraphEditorDialogs";
import { GraphEditorPalettePanel } from "./GraphEditorPalettePanel";
import { GraphCanvasPanel } from "./GraphCanvasPanel";
import { GraphInspectorPanel } from "./GraphInspectorPanel";
import { ValidationTrigger } from "./ValidationTrigger";
import type { GraphEditorController } from "./GraphEditor";

export function GraphEditorShell({ controller }: { controller: GraphEditorController }) {
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
