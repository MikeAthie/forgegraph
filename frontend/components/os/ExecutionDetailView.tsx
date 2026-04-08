import { useEffect, useMemo, useState } from "react";
import { useRouter } from "next/router";
import Link from "next/link";
import { AlertTriangle, ArrowRight, ChevronDown, ChevronUp, Clock3, Filter } from "lucide-react";

import DashboardLayout from "@/components/DashboardLayout";
import {
  EmptyBlock,
  InspectorPanel,
  KeyValueGrid,
  Panel,
  SectionHeader,
  StatusBadge,
  formatCurrency,
  formatDateTime,
  formatDuration,
  statusTone,
} from "@/components/os/operations-ui";
import ProtectedRoute from "@/components/ProtectedRoute";
import { Alert, AlertDescription, Button, Spinner } from "@/components/ui";
import {
  authApi,
  executionsApi,
  getAccessToken,
  getApiErrorMessage,
  runsApi,
  type AgentTraceStep,
  type NodeRunItem,
  type RunDetail,
} from "@/lib/api";

const formatTracePayload = (value: unknown) => {
  if (value === null || value === undefined) {
    return "Unavailable";
  }
  if (typeof value === "string") {
    return value;
  }
  return JSON.stringify(value, null, 2);
};

const estimateExecutionCost = (run: RunDetail | null) => {
  if (!run) {
    return 0;
  }

  const totalTokens = run.node_runs.reduce((sum, node) => {
    const usage = node.agent_trace?.usage?.total_tokens;
    return sum + (typeof usage === "number" ? usage : 0);
  }, 0);

  return Math.round((totalTokens * 0.000004 + run.node_runs.length * 0.021) * 100) / 100;
};

const buildStepNarrative = (step: NodeRunItem, liveSummary?: string | null) => {
  if (liveSummary) {
    return liveSummary;
  }
  if (step.agent_trace?.final_output) {
    return String(step.agent_trace.final_output).slice(0, 220);
  }
  if (step.agent_trace?.steps?.length) {
    const traceStep = step.agent_trace.steps[step.agent_trace.steps.length - 1];
    return String(
      traceStep.final_answer ??
        traceStep.tool_output ??
        traceStep.action ??
        "Reasoning was captured, but the projected summary is limited.",
    ).slice(0, 220);
  }
  if (step.output_json) {
    return JSON.stringify(step.output_json).slice(0, 220);
  }
  if (step.error_json) {
    return JSON.stringify(step.error_json).slice(0, 220);
  }
  return "No projected summary is available for this step yet.";
};

type RunRealtimeMessage =
  | {
      type: "connected";
      run_id: string;
      level?: string;
    }
  | {
      type: "run.updated";
      run_id: string;
      run: Partial<RunDetail>;
    }
  | {
      type: "node_run.updated";
      run_id: string;
      node_run: Partial<NodeRunItem> & {
        id: string;
        node_id: string;
        node_type: string;
        status: NodeRunItem["status"];
        attempt: number;
      };
    }
  | {
      type: "node_stream.summary";
      run_id: string;
      node_stream: {
        node_id: string;
        attempt: number;
        text_preview?: string;
        final?: boolean;
      };
    };

const buildRunWebSocketUrl = (runId: string, ticket: string) => {
  const apiOrigin = (process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000").replace(/\/$/, "");
  const websocketOrigin = apiOrigin.replace(/^http/i, "ws");
  return `${websocketOrigin}/ws/runs/${runId}/?ticket=${encodeURIComponent(ticket)}&event_level=default`;
};

const sortNodeRuns = (nodeRuns: NodeRunItem[]) =>
  [...nodeRuns].sort((left, right) => {
    const leftTime = left.started_at ? new Date(left.started_at).getTime() : Number.MAX_SAFE_INTEGER;
    const rightTime = right.started_at ? new Date(right.started_at).getTime() : Number.MAX_SAFE_INTEGER;
    if (leftTime !== rightTime) {
      return leftTime - rightTime;
    }
    if (left.attempt !== right.attempt) {
      return left.attempt - right.attempt;
    }
    return left.id.localeCompare(right.id);
  });

const applyRealtimeMessage = (current: RunDetail | null, message: RunRealtimeMessage): RunDetail | null => {
  if (!current || message.run_id !== current.id) {
    return current;
  }

  if (message.type === "run.updated") {
    return {
      ...current,
      ...message.run,
    };
  }

  if (message.type === "node_run.updated") {
    const incoming = message.node_run;
    const existingIndex = current.node_runs.findIndex(
      (nodeRun) =>
        nodeRun.id === incoming.id || (nodeRun.node_id === incoming.node_id && nodeRun.attempt === incoming.attempt),
    );
    const nextNodeRun: NodeRunItem =
      existingIndex >= 0
        ? {
            ...current.node_runs[existingIndex],
            ...incoming,
          }
        : {
            id: incoming.id,
            node_id: incoming.node_id,
            node_type: incoming.node_type,
            status: incoming.status,
            attempt: incoming.attempt,
            started_at: incoming.started_at ?? null,
            ended_at: incoming.ended_at ?? null,
            duration_ms: incoming.duration_ms ?? null,
            input_json: (incoming.input_json as Record<string, unknown> | undefined) ?? {},
            output_json: (incoming.output_json as Record<string, unknown> | null | undefined) ?? null,
            error_json: (incoming.error_json as Record<string, unknown> | null | undefined) ?? null,
            agent_trace: null,
            memory_activity: null,
          };

    const nodeRuns =
      existingIndex >= 0
        ? current.node_runs.map((nodeRun, index) => (index === existingIndex ? nextNodeRun : nodeRun))
        : [...current.node_runs, nextNodeRun];

    return {
      ...current,
      node_runs: sortNodeRuns(nodeRuns),
    };
  }

  return current;
};

type ExecutionDetailViewProps = {
  routeParam: "runId" | "executionId";
};

export default function ExecutionDetailView({ routeParam }: ExecutionDetailViewProps) {
  const router = useRouter();
  const executionId = typeof router.query[routeParam] === "string" ? router.query[routeParam] : null;
  const [run, setRun] = useState<RunDetail | null>(null);
  const [selectedStepId, setSelectedStepId] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [liveStatus, setLiveStatus] = useState<"pending" | "active" | "offline">("pending");
  const [showAllSteps, setShowAllSteps] = useState(false);
  const [liveSummaries, setLiveSummaries] = useState<Record<string, string>>({});

  useEffect(() => {
    if (!executionId) {
      return;
    }

    let cancelled = false;

    const load = async () => {
      try {
        const data =
          routeParam === "executionId" ? await executionsApi.get(executionId) : await runsApi.get(executionId);
        if (!cancelled) {
          setRun(data);
          setSelectedStepId(data.node_runs[0]?.id ?? null);
          setLiveSummaries({});
        }
      } catch (err: unknown) {
        if (!cancelled) {
          setError(getApiErrorMessage(err, "Failed to load execution detail."));
        }
      } finally {
        if (!cancelled) {
          setLoading(false);
        }
      }
    };

    void load();

    return () => {
      cancelled = true;
    };
  }, [executionId, routeParam]);

  useEffect(() => {
    if (!executionId || typeof window === "undefined") {
      return;
    }

    const token = getAccessToken();
    if (!token) {
      setLiveStatus("offline");
      return;
    }

    let disposed = false;
    let socket: WebSocket | null = null;
    setLiveStatus("pending");
    void (async () => {
      try {
        const { ticket } = await authApi.createWsTicket();
        if (disposed) {
          return;
        }

        socket = new WebSocket(buildRunWebSocketUrl(executionId, ticket));

        socket.addEventListener("open", () => {
          if (!disposed) {
            setLiveStatus("active");
          }
        });

        socket.addEventListener("message", (event) => {
          if (disposed) {
            return;
          }

          try {
            const message = JSON.parse(String(event.data)) as RunRealtimeMessage;
            if (message.type === "connected") {
              return;
            }
            if (message.type === "node_stream.summary") {
              const summaryKey = `${message.node_stream.node_id}:${message.node_stream.attempt}`;
              setLiveSummaries((current) => ({
                ...current,
                [summaryKey]: message.node_stream.text_preview ?? current[summaryKey] ?? "",
              }));
              return;
            }
            setRun((current) => applyRealtimeMessage(current, message));
          } catch {
            // Ignore malformed messages and keep the last known canonical state.
          }
        });

        socket.addEventListener("error", () => {
          if (!disposed) {
            setLiveStatus("offline");
          }
        });

        socket.addEventListener("close", () => {
          if (!disposed) {
            setLiveStatus("offline");
          }
        });
      } catch {
        if (!disposed) {
          setLiveStatus("offline");
        }
      }
    })();

    return () => {
      disposed = true;
      socket?.close();
    };
  }, [executionId]);

  useEffect(() => {
    if (!selectedStepId && run?.node_runs.length) {
      setSelectedStepId(run.node_runs[0].id);
    }
  }, [run?.node_runs, selectedStepId]);

  const selectedStep = useMemo(
    () => run?.node_runs.find((step) => step.id === selectedStepId) ?? run?.node_runs[0] ?? null,
    [run?.node_runs, selectedStepId],
  );

  const traceState = useMemo(() => {
    if (!run) {
      return null;
    }

    const timedSteps = run.node_runs.filter((step) => typeof step.duration_ms === "number");
    const averageDuration =
      timedSteps.length > 0
        ? timedSteps.reduce((sum, step) => sum + (step.duration_ms ?? 0), 0) / timedSteps.length
        : 0;
    const bottleneckSteps = timedSteps
      .filter((step) => (step.duration_ms ?? 0) >= Math.max(averageDuration * 1.5, 4_000))
      .sort((left, right) => (right.duration_ms ?? 0) - (left.duration_ms ?? 0))
      .slice(0, 2);
    const bottleneckIds = new Set(bottleneckSteps.map((step) => step.id));
    const decisionSteps = run.node_runs.filter(
      (step) => step.status === "waiting" || step.node_type === "human_gate" || step.agent_trace?.approval_pending,
    );
    const failedSteps = run.node_runs.filter((step) => step.status === "failed" || step.status === "error");
    const highlightIds = new Set([
      ...bottleneckIds,
      ...decisionSteps.map((step) => step.id),
      ...failedSteps.map((step) => step.id),
    ]);
    const routineSteps = run.node_runs.filter((step) => !highlightIds.has(step.id));
    const visibleRoutineIds = new Set(routineSteps.slice(0, 3).map((step) => step.id));

    const visibleSteps = showAllSteps
      ? run.node_runs
      : run.node_runs.filter(
          (step) => highlightIds.has(step.id) || visibleRoutineIds.has(step.id) || step.id === selectedStepId,
        );

    return {
      failedSteps,
      decisionSteps,
      bottleneckSteps,
      bottleneckIds,
      hiddenRoutineCount: Math.max(routineSteps.length - visibleRoutineIds.size, 0),
      visibleSteps,
    };
  }, [run, selectedStepId, showAllSteps]);

  const totalCost = estimateExecutionCost(run);
  const failedStep = traceState?.failedSteps[0] ?? null;
  const decisionStep = traceState?.decisionSteps[0] ?? null;
  const bottleneckStep = traceState?.bottleneckSteps[0] ?? null;

  const inspector = selectedStep ? (
    <InspectorPanel
      title={selectedStep.node_id}
      subtitle="The inspector keeps canonical input and output adjacent to a short summary so the operator can inspect only when needed."
      sections={[
        {
          title: "Step metadata",
          content: (
            <div className="space-y-2">
              <div className="flex items-center justify-between">
                <span>Status</span>
                <StatusBadge status={selectedStep.status} />
              </div>
              <div className="flex items-center justify-between">
                <span>Type</span>
                <span>{selectedStep.node_type}</span>
              </div>
              <div className="flex items-center justify-between">
                <span>Duration</span>
                <span>{formatDuration(selectedStep.duration_ms)}</span>
              </div>
            </div>
          ),
        },
        {
          title: "Readable summary",
          content: buildStepNarrative(selectedStep, liveSummaries[`${selectedStep.node_id}:${selectedStep.attempt}`]),
        },
        {
          title: "Input",
          content: (
            <pre className="overflow-x-auto whitespace-pre-wrap text-xs leading-6">
              {formatTracePayload(selectedStep.input_json)}
            </pre>
          ),
        },
        {
          title: "Output",
          content: (
            <pre className="overflow-x-auto whitespace-pre-wrap text-xs leading-6">
              {formatTracePayload(selectedStep.output_json ?? selectedStep.error_json)}
            </pre>
          ),
        },
      ]}
    />
  ) : null;

  return (
    <ProtectedRoute>
      <DashboardLayout inspector={inspector}>
        <div className="space-y-6">
          <SectionHeader
            eyebrow="Workflow execution"
            title="Execution trace"
            description="Failures, decisions, and bottlenecks come first. Routine step noise stays collapsed until the operator explicitly expands it."
            action={
              <div className="flex items-center gap-2">
                <StatusBadge
                  status={liveStatus}
                  label={liveStatus === "active" ? "Live updates" : liveStatus === "pending" ? "Connecting" : "Offline"}
                />
                <Button asChild variant="outline" className="rounded-full">
                  <Link href="/executions">Back to executions</Link>
                </Button>
              </div>
            }
          />

          {error ? (
            <Alert variant="destructive">
              <AlertDescription>{error}</AlertDescription>
            </Alert>
          ) : null}

          {loading || !run || !traceState ? (
            <div className="flex min-h-[320px] items-center justify-center rounded-[1.75rem] border border-slate-900/10 bg-white/70 dark:border-white/10 dark:bg-slate-950/50">
              <Spinner size="lg" />
            </div>
          ) : (
            <>
              <Panel
                title={run.graph_name}
                description="One-screen summary of what happened, what needs attention, and where the run slowed down."
                action={<StatusBadge status={String(run.status)} />}
              >
                <div className="grid gap-4 xl:grid-cols-4">
                  <div className="rounded-[1.2rem] border border-slate-900/8 bg-[var(--panel-muted)] px-4 py-4 dark:border-white/8">
                    <p className="text-[11px] uppercase tracking-[0.18em] text-slate-500 dark:text-slate-400">
                      Total duration
                    </p>
                    <p className="mt-2 text-2xl font-semibold text-slate-950 dark:text-slate-50">
                      {formatDuration(run.duration_ms)}
                    </p>
                  </div>
                  <div className="rounded-[1.2rem] border border-slate-900/8 bg-[var(--panel-muted)] px-4 py-4 dark:border-white/8">
                    <p className="text-[11px] uppercase tracking-[0.18em] text-slate-500 dark:text-slate-400">
                      Estimated cost
                    </p>
                    <p className="mt-2 text-2xl font-semibold text-slate-950 dark:text-slate-50">
                      {formatCurrency(totalCost)}
                    </p>
                  </div>
                  <div className="rounded-[1.2rem] border border-slate-900/8 bg-[var(--panel-muted)] px-4 py-4 dark:border-white/8">
                    <p className="text-[11px] uppercase tracking-[0.18em] text-slate-500 dark:text-slate-400">
                      Failure point
                    </p>
                    <p className="mt-2 text-sm font-semibold text-slate-950 dark:text-slate-50">
                      {failedStep ? failedStep.node_id : "No failure detected"}
                    </p>
                  </div>
                  <div className="rounded-[1.2rem] border border-slate-900/8 bg-[var(--panel-muted)] px-4 py-4 dark:border-white/8">
                    <p className="text-[11px] uppercase tracking-[0.18em] text-slate-500 dark:text-slate-400">
                      Bottleneck
                    </p>
                    <p className="mt-2 text-sm font-semibold text-slate-950 dark:text-slate-50">
                      {bottleneckStep
                        ? `${bottleneckStep.node_id} · ${formatDuration(bottleneckStep.duration_ms)}`
                        : "No bottleneck flagged"}
                    </p>
                  </div>
                </div>
              </Panel>

              <div className="grid gap-6 2xl:grid-cols-[0.92fr_1.08fr]">
                <Panel title="Attention points" description="The steps that matter most to an operator right now.">
                  {failedStep || decisionStep || bottleneckStep ? (
                    <div className="space-y-3">
                      {failedStep ? (
                        <div className="rounded-[1.2rem] border border-rose-800/12 bg-rose-50 px-4 py-4 text-rose-950 dark:border-rose-200/15 dark:bg-rose-500/10 dark:text-rose-100">
                          <div className="flex items-start justify-between gap-3">
                            <div>
                              <p className="text-sm font-semibold">Failure</p>
                              <p className="mt-2 text-sm leading-7">
                                {failedStep.node_id} failed. Inspect this step first before replaying the run.
                              </p>
                            </div>
                            <AlertTriangle className="h-4 w-4 shrink-0" />
                          </div>
                        </div>
                      ) : null}
                      {decisionStep ? (
                        <div className="rounded-[1.2rem] border border-amber-800/12 bg-amber-50 px-4 py-4 text-amber-950 dark:border-amber-200/15 dark:bg-amber-500/10 dark:text-amber-100">
                          <p className="text-sm font-semibold">Decision boundary</p>
                          <p className="mt-2 text-sm leading-7">
                            {decisionStep.node_id} is waiting on a human decision or approval boundary.
                          </p>
                        </div>
                      ) : null}
                      {bottleneckStep ? (
                        <div className="rounded-[1.2rem] border border-slate-900/8 bg-[var(--panel-muted)] px-4 py-4 dark:border-white/8">
                          <div className="flex items-start justify-between gap-3">
                            <div>
                              <p className="text-sm font-semibold text-slate-950 dark:text-slate-50">Bottleneck</p>
                              <p className="mt-2 text-sm leading-7 text-slate-700 dark:text-slate-200">
                                {bottleneckStep.node_id} consumed {formatDuration(bottleneckStep.duration_ms)} and is
                                materially slower than the rest of the trace.
                              </p>
                            </div>
                            <Clock3 className="h-4 w-4 shrink-0 text-slate-500 dark:text-slate-400" />
                          </div>
                        </div>
                      ) : null}
                    </div>
                  ) : (
                    <EmptyBlock
                      title="No attention point surfaced"
                      description="The visible trace completed without a failure, decision boundary, or obvious bottleneck."
                    />
                  )}
                </Panel>

                <Panel title="Execution posture" description="Operator-oriented summary of the current run state.">
                  <KeyValueGrid
                    columns={2}
                    items={[
                      {
                        label: "Current status",
                        value: <StatusBadge status={String(run.status)} label={String(run.status)} />,
                      },
                      {
                        label: "Decision boundaries",
                        value: traceState.decisionSteps.length,
                      },
                      {
                        label: "Flagged bottlenecks",
                        value: traceState.bottleneckSteps.length,
                      },
                      {
                        label: "Routine steps hidden",
                        value: showAllSteps ? 0 : traceState.hiddenRoutineCount,
                      },
                    ]}
                  />
                </Panel>
              </div>

              <Panel
                title="Trace sequence"
                description="Routine steps are collapsed by default so the operator can focus on failures, decisions, and bottlenecks first."
                action={
                  run.node_runs.length > 3 ? (
                    <Button
                      type="button"
                      variant="outline"
                      className="rounded-full"
                      onClick={() => setShowAllSteps((current) => !current)}
                    >
                      {showAllSteps ? (
                        <>
                          Collapse noise
                          <ChevronUp className="h-4 w-4" />
                        </>
                      ) : (
                        <>
                          Show all steps
                          <ChevronDown className="h-4 w-4" />
                        </>
                      )}
                    </Button>
                  ) : null
                }
              >
                {run.node_runs.length ? (
                  <div className="space-y-4">
                    {!showAllSteps && traceState.hiddenRoutineCount > 0 ? (
                      <div className="flex items-center gap-2 rounded-[1.2rem] border border-slate-900/8 bg-[var(--panel-muted)] px-4 py-3 text-sm text-slate-600 dark:border-white/8 dark:text-slate-300">
                        <Filter className="h-4 w-4" />
                        {traceState.hiddenRoutineCount} routine step{traceState.hiddenRoutineCount === 1 ? "" : "s"}{" "}
                        collapsed.
                      </div>
                    ) : null}

                    {traceState.visibleSteps.map((step, index) => {
                      const tone = statusTone(step.status);
                      const traceStep = step.agent_trace?.steps?.[step.agent_trace.steps.length - 1] as
                        | AgentTraceStep
                        | undefined;
                      const isBottleneck = traceState.bottleneckIds.has(step.id);
                      const isDecision =
                        step.status === "waiting" ||
                        step.node_type === "human_gate" ||
                        step.agent_trace?.approval_pending;
                      const summaryKey = `${step.node_id}:${step.attempt}`;

                      return (
                        <button
                          key={step.id}
                          type="button"
                          onClick={() => setSelectedStepId(step.id)}
                          className="w-full rounded-[1.3rem] border border-slate-900/8 bg-white/75 px-5 py-5 text-left transition-colors hover:bg-[var(--panel-muted)] dark:border-white/8 dark:bg-white/4 dark:hover:bg-white/8"
                        >
                          <div className="grid gap-4 xl:grid-cols-[3.5rem_minmax(0,1fr)_13rem]">
                            <div className="flex items-start gap-3 xl:block">
                              <div className="flex h-10 w-10 items-center justify-center rounded-2xl border border-slate-900/10 bg-[var(--panel-muted)] text-sm font-semibold dark:border-white/10">
                                {index + 1}
                              </div>
                            </div>
                            <div className="min-w-0">
                              <div className="flex flex-wrap items-center gap-2">
                                <p className="text-sm font-semibold text-slate-950 dark:text-slate-50">
                                  {step.node_id}
                                </p>
                                <StatusBadge status={step.status} />
                                <StatusBadge status="pending" label={step.node_type} />
                                {isDecision ? <StatusBadge status="paused" label="decision" /> : null}
                                {isBottleneck ? <StatusBadge status="pending" label="bottleneck" /> : null}
                              </div>
                              <p className="mt-3 text-sm leading-7 text-slate-600 dark:text-slate-300">
                                {buildStepNarrative(step, liveSummaries[summaryKey])}
                              </p>
                              {traceStep ? (
                                <p className="mt-3 text-xs text-slate-500 dark:text-slate-400">
                                  {traceStep.tool ? `Tool ${traceStep.tool}` : "Reasoning step"} ·{" "}
                                  {traceStep.finish_reason ?? traceStep.action ?? "Completed"}
                                </p>
                              ) : null}
                            </div>
                            <div className="grid gap-2 text-sm">
                              <div className="rounded-2xl border border-slate-900/8 bg-[var(--panel-muted)] px-3 py-2 dark:border-white/8">
                                <p className="text-[11px] uppercase tracking-[0.16em] text-slate-500 dark:text-slate-400">
                                  Duration
                                </p>
                                <p className="mt-1 font-medium text-slate-900 dark:text-slate-100">
                                  {formatDuration(step.duration_ms)}
                                </p>
                              </div>
                              <div className="rounded-2xl border border-slate-900/8 bg-[var(--panel-muted)] px-3 py-2 dark:border-white/8">
                                <p className="text-[11px] uppercase tracking-[0.16em] text-slate-500 dark:text-slate-400">
                                  Started
                                </p>
                                <p className="mt-1 font-medium text-slate-900 dark:text-slate-100">
                                  {formatDateTime(step.started_at)}
                                </p>
                              </div>
                              {tone === "rose" ? (
                                <div className="rounded-2xl border border-rose-800/15 bg-rose-50 px-3 py-2 text-rose-900 dark:border-rose-200/20 dark:bg-rose-500/10 dark:text-rose-100">
                                  <p className="text-[11px] uppercase tracking-[0.16em]">Failure</p>
                                  <p className="mt-1 text-xs">Execution requires intervention here.</p>
                                </div>
                              ) : null}
                            </div>
                          </div>
                        </button>
                      );
                    })}
                  </div>
                ) : (
                  <EmptyBlock
                    title="No steps available"
                    description="This execution has not emitted any node-level steps yet."
                  />
                )}
              </Panel>

              <div className="grid gap-6 2xl:grid-cols-2">
                <Panel title="Execution state" description="Canonical timing, queue status, and memory posture.">
                  <KeyValueGrid
                    columns={2}
                    items={[
                      { label: "Started", value: formatDateTime(run.started_at) },
                      { label: "Ended", value: formatDateTime(run.ended_at) },
                      { label: "Queue status", value: run.queue_status ?? "Not queued" },
                      { label: "Attempts", value: run.queue_attempts ?? 0 },
                    ]}
                  />
                </Panel>

                <Panel title="Human gate" description="Decision context stays readable and close to the main trace.">
                  {run.paused_node_id ? (
                    <div className="rounded-[1.2rem] border border-slate-900/8 bg-[var(--panel-muted)] px-4 py-4 dark:border-white/8">
                      <p className="text-sm font-semibold text-slate-950 dark:text-slate-50">
                        {run.pause_payload?.node_name ?? run.paused_node_id}
                      </p>
                      <p className="mt-2 text-sm leading-7 text-slate-600 dark:text-slate-300">
                        {run.pause_payload?.prompt_message ?? "Execution is waiting on human approval."}
                      </p>
                      <div className="mt-4">
                        <Button asChild size="sm" className="rounded-full">
                          <Link href="/inbox">
                            Open inbox
                            <ArrowRight className="h-4 w-4" />
                          </Link>
                        </Button>
                      </div>
                    </div>
                  ) : (
                    <EmptyBlock
                      title="No active human gate"
                      description="This execution is not currently paused for approval."
                    />
                  )}
                </Panel>
              </div>
            </>
          )}
        </div>
      </DashboardLayout>
    </ProtectedRoute>
  );
}
