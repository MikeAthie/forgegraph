import { Badge, Separator } from "@/components/ui";
import { formatJsonForDisplay } from "@/lib/json";
import type { AgentEventItem, AgentTrace, AgentTraceStep } from "@/lib/api";

const STOP_REASON_LABELS: Record<string, string> = {
  final_answer: "Final answer",
  max_steps_reached: "Max steps reached",
  max_tool_calls_reached: "Max tool calls reached",
  tool_policy_denied: "Tool denied",
  approval_required: "Approval required",
};

const formatStopReason = (stopReason: unknown): string => {
  if (typeof stopReason !== "string" || !stopReason.trim()) {
    return "Unknown";
  }
  return STOP_REASON_LABELS[stopReason] ?? stopReason.replace(/_/g, " ");
};

const formatUsageLabel = (usage: AgentTrace["usage"]): string | null => {
  if (!usage || typeof usage !== "object") {
    return null;
  }
  const totalTokens = Number(usage.total_tokens);
  if (!Number.isFinite(totalTokens)) {
    return null;
  }
  return `${totalTokens} tokens`;
};

const getEventLabel = (event: AgentEventItem): string => {
  if (typeof event.event !== "string" || !event.event.trim()) {
    return "agent event";
  }
  return event.event.replace(/^agent\./, "").replace(/\./g, " ");
};

const renderStepBody = (step: AgentTraceStep) => {
  if (step.action === "tool_call") {
    return (
      <div className="space-y-2">
        <div className="text-xs text-muted-foreground">
          Tool: <span className="font-medium text-foreground">{String(step.tool ?? "-")}</span>
        </div>
        {step.approval_required ? (
          <div className="rounded-md border border-amber-500/30 bg-amber-500/10 px-3 py-2 text-xs text-amber-900 dark:text-amber-100">
            This tool call requires approval before execution can continue.
          </div>
        ) : null}
        {step.tool_input !== undefined ? (
          <details open>
            <summary className="cursor-pointer text-xs font-medium text-muted-foreground">
              Tool input
            </summary>
            <pre className="mt-1 max-h-36 overflow-auto rounded border border-border/50 bg-muted p-2 text-[11px] font-mono whitespace-pre-wrap">
              {formatJsonForDisplay(step.tool_input)}
            </pre>
          </details>
        ) : null}
        {step.tool_output !== undefined ? (
          <details open>
            <summary className="cursor-pointer text-xs font-medium text-muted-foreground">
              Tool output
            </summary>
            <pre className="mt-1 max-h-36 overflow-auto rounded border border-border/50 bg-muted p-2 text-[11px] font-mono whitespace-pre-wrap">
              {formatJsonForDisplay(step.tool_output)}
            </pre>
          </details>
        ) : null}
      </div>
    );
  }

  return (
    <div className="space-y-2">
      {step.final_answer ? (
        <div className="rounded-md border border-emerald-500/20 bg-emerald-500/5 px-3 py-2 text-xs text-foreground whitespace-pre-wrap">
          {step.final_answer}
        </div>
      ) : null}
      {step.error ? (
        <div className="rounded-md border border-destructive/20 bg-destructive/5 px-3 py-2 text-xs text-destructive whitespace-pre-wrap">
          {step.error}
        </div>
      ) : null}
    </div>
  );
};

type AgentTracePanelProps = {
  trace: AgentTrace;
  compact?: boolean;
  showApprovalHint?: boolean;
};

export function AgentTracePanel({
  trace,
  compact = false,
  showApprovalHint = false,
}: AgentTracePanelProps) {
  const steps = Array.isArray(trace.steps) ? trace.steps : [];
  const events = Array.isArray(trace.events) ? trace.events : [];
  const usageLabel = formatUsageLabel(trace.usage);

  return (
    <div className="space-y-3">
      <div className="grid gap-2 md:grid-cols-4">
        <div className="rounded-lg border border-border/50 bg-muted/40 p-3">
          <p className="text-[11px] font-medium uppercase text-muted-foreground">Stop reason</p>
          <p className="mt-1 text-sm text-foreground">{formatStopReason(trace.stop_reason)}</p>
        </div>
        <div className="rounded-lg border border-border/50 bg-muted/40 p-3">
          <p className="text-[11px] font-medium uppercase text-muted-foreground">Steps</p>
          <p className="mt-1 text-sm text-foreground">{String(trace.step_count ?? steps.length ?? 0)}</p>
        </div>
        <div className="rounded-lg border border-border/50 bg-muted/40 p-3">
          <p className="text-[11px] font-medium uppercase text-muted-foreground">Tool calls</p>
          <p className="mt-1 text-sm text-foreground">
            {String(trace.tool_call_count ?? steps.filter((step) => step.action === "tool_call").length)}
          </p>
        </div>
        <div className="rounded-lg border border-border/50 bg-muted/40 p-3">
          <p className="text-[11px] font-medium uppercase text-muted-foreground">Model usage</p>
          <p className="mt-1 text-sm text-foreground">{usageLabel ?? "-"}</p>
        </div>
      </div>

      {trace.approval_pending || trace.stop_reason === "approval_required" ? (
        <div className="rounded-lg border border-amber-500/30 bg-amber-500/10 px-3 py-3 text-sm text-amber-900 dark:text-amber-100">
          <p className="font-medium">Approval required</p>
          <p className="mt-1 text-xs text-amber-900/80 dark:text-amber-100/80">
            The agent stopped before executing a gated tool.
            {showApprovalHint ? " Review the approval panel to continue this run." : ""}
          </p>
        </div>
      ) : null}

      {trace.final_output ? (
        <div className="rounded-lg border border-emerald-500/20 bg-emerald-500/5 p-3">
          <p className="text-[11px] font-medium uppercase text-emerald-700 dark:text-emerald-300">
            Final output
          </p>
          <p className="mt-1 text-sm whitespace-pre-wrap text-foreground">{trace.final_output}</p>
        </div>
      ) : null}

      {steps.length > 0 ? (
        <div className="space-y-2">
          <p className="text-xs font-semibold uppercase text-muted-foreground">Agent steps</p>
          <div className="space-y-2">
            {steps.map((step, index) => (
              <div
                key={`${String(step.step_index ?? index)}-${String(step.action ?? "step")}`}
                className="rounded-lg border border-border/50 bg-background/50 p-3"
              >
                <div className="flex flex-wrap items-center gap-2">
                  <Badge variant="outline">Step {String(step.step_index ?? index + 1)}</Badge>
                  <Badge variant="secondary">{String(step.action ?? "unknown")}</Badge>
                  {step.response_model ? (
                    <span className="text-xs text-muted-foreground">{step.response_model}</span>
                  ) : null}
                </div>
                <div className="mt-3">{renderStepBody(step)}</div>
              </div>
            ))}
          </div>
        </div>
      ) : null}

      {!compact && events.length > 0 ? (
        <>
          <Separator />
          <details>
            <summary className="cursor-pointer text-xs font-semibold uppercase text-muted-foreground">
              Agent events
            </summary>
            <div className="mt-2 space-y-2">
              {events.map((event, index) => (
                <div
                  key={`${String(event.event ?? "event")}-${String(event.chunk_index ?? index)}`}
                  className="rounded-md border border-border/50 bg-muted/30 px-3 py-2"
                >
                  <div className="flex flex-wrap items-center gap-2">
                    <Badge variant="outline">{getEventLabel(event)}</Badge>
                    {typeof event.step_index === "number" ? (
                      <span className="text-xs text-muted-foreground">
                        step {event.step_index}
                      </span>
                    ) : null}
                    {typeof event.tool === "string" && event.tool ? (
                      <span className="text-xs text-muted-foreground">
                        tool {event.tool}
                      </span>
                    ) : null}
                  </div>
                  <pre className="mt-2 max-h-36 overflow-auto rounded border border-border/50 bg-background/70 p-2 text-[11px] font-mono whitespace-pre-wrap">
                    {formatJsonForDisplay(event)}
                  </pre>
                </div>
              ))}
            </div>
          </details>
        </>
      ) : null}
    </div>
  );
}
