import type { AgentTrace, NodeRunItem } from "../../lib/api";
import { formatJsonForDisplay } from "../../lib/json";
import { AgentTracePanel } from "../runs/AgentTracePanel";

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

const formatDuration = (durationMs: number | null | undefined) => {
  if (durationMs === null || durationMs === undefined) return "-";
  if (durationMs < 1000) return `${durationMs}ms`;
  const totalSeconds = Math.floor(durationMs / 1000);
  const minutes = Math.floor(totalSeconds / 60);
  const seconds = totalSeconds % 60;
  if (minutes > 0) return `${minutes}m ${seconds}s`;
  return `${totalSeconds}s`;
};

export function NodeRunActivityCard({ nodeRun }: { nodeRun: NodeRunItem }) {
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
