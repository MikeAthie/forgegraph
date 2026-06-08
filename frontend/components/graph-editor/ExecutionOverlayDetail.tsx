import Link from "next/link";

import { NodeRunActivityCard } from "./NodeRunActivityCard";
import type { GraphEditorController } from "./GraphEditor";

const isTerminalRunStatus = (status: string) => status === "succeeded" || status === "failed" || status === "canceled";

export function ExecutionOverlayDetail({ controller }: { controller: GraphEditorController }) {
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
