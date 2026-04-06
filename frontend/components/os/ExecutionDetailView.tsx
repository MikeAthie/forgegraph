import { useEffect, useMemo, useRef, useState } from "react";
import { useRouter } from "next/router";
import Link from "next/link";

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

const summarizeStep = (step: NodeRunItem) => {
  if (step.agent_trace?.final_output) {
    return String(step.agent_trace.final_output).slice(0, 180);
  }
  if (step.agent_trace?.steps?.length) {
    const traceStep = step.agent_trace.steps[step.agent_trace.steps.length - 1];
    return String(
      traceStep.final_answer ?? traceStep.tool_output ?? traceStep.action ?? "Reasoning captured in detail panel.",
    ).slice(0, 180);
  }
  if (step.output_json) {
    return JSON.stringify(step.output_json).slice(0, 180);
  }
  if (step.error_json) {
    return JSON.stringify(step.error_json).slice(0, 180);
  }
  return "Step completed without a projected summary.";
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

const formatTracePayload = (value: unknown) => {
  if (value === null || value === undefined) {
    return "Unavailable";
  }
  if (typeof value === "string") {
    return value;
  }
  return JSON.stringify(value, null, 2);
};

type RunRealtimeMessage =
  | {
      type: "connection_established";
      timestamp: string;
      trace_id: string;
      run_id: string;
<<<<<<< Updated upstream
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
=======
      payload: {
        event_level?: string;
        organization_id?: string;
        user_id?: string;
        permissions?: string[];
      };
    }
  | {
      type: "heartbeat";
      timestamp: string;
      trace_id: string;
      run_id: string;
      payload: Record<string, never>;
    }
  | {
      type: "run_started" | "run_completed" | "run_failed" | "run_paused" | "run_resumed" | "run_canceled";
      timestamp: string;
      trace_id: string;
      run_id: string;
      payload: {
        status?: string;
        run?: Partial<RunDetail>;
      };
    }
  | {
      type: "node_started" | "node_completed" | "node_failed" | "node_skipped" | "node_updated";
      timestamp: string;
      trace_id: string;
      run_id: string;
      payload: {
        status?: string;
        node_run?: Partial<NodeRunItem> & {
          id: string;
          node_id: string;
          node_type: string;
          status: NodeRunItem["status"];
          attempt: number;
        };
      };
    }
  | {
      type: "node_stream_chunk" | "node_stream_end";
      timestamp: string;
      trace_id: string;
      run_id: string;
      payload: {
        node_id: string;
        attempt: number;
        text_preview?: string;
        final?: boolean;
      };
    }
  | {
      type: "decision_required" | "decision_resolved" | "cost_update" | "error";
      timestamp: string;
      trace_id: string;
      run_id: string;
      payload: Record<string, unknown>;
>>>>>>> Stashed changes
    };

const buildRunWebSocketUrl = (runId: string, ticket: string) => {
  const apiOrigin = (process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000").replace(/\/$/, "");
  const websocketOrigin = apiOrigin.replace(/^http/i, "ws");
<<<<<<< Updated upstream
  return `${websocketOrigin}/ws/runs/${runId}/?token=${encodeURIComponent(token)}`;
=======
  return `${websocketOrigin}/ws/runs/${runId}/?ticket=${encodeURIComponent(ticket)}&event_level=default`;
>>>>>>> Stashed changes
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

  if (
    message.type === "run_started" ||
    message.type === "run_completed" ||
    message.type === "run_failed" ||
    message.type === "run_paused" ||
    message.type === "run_resumed" ||
    message.type === "run_canceled"
  ) {
    return {
      ...current,
      ...(message.payload.run ?? {}),
    };
  }

  if (
    message.type === "node_started" ||
    message.type === "node_completed" ||
    message.type === "node_failed" ||
    message.type === "node_skipped" ||
    message.type === "node_updated"
  ) {
    const incoming = message.payload.node_run;
    if (!incoming) {
      return current;
    }
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
<<<<<<< Updated upstream
=======
  const [showAllSteps, setShowAllSteps] = useState(false);
  const [liveSummaries, setLiveSummaries] = useState<Record<string, string>>({});
  const reconnectAttemptRef = useRef(0);
  const hasConnectedOnceRef = useRef(false);
>>>>>>> Stashed changes

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

    if (!getAccessToken()) {
      setLiveStatus("offline");
      return;
    }

    let disposed = false;
    let socket: WebSocket | null = null;
    let reconnectTimer: number | null = null;
    let silenceMonitor: number | null = null;
    let lastActivityAt = Date.now();

    const refreshCanonicalState = async () => {
      try {
        const data =
          routeParam === "executionId" ? await executionsApi.get(executionId) : await runsApi.get(executionId);
        if (!disposed) {
          setRun(data);
          setSelectedStepId((current) =>
            current && data.node_runs.some((nodeRun) => nodeRun.id === current)
              ? current
              : (data.node_runs[0]?.id ?? null),
          );
          setLiveSummaries({});
        }
      } catch (err: unknown) {
        if (!disposed) {
          setError(getApiErrorMessage(err, "Failed to refresh execution detail."));
        }
      }
    };

    const clearReconnectTimer = () => {
      if (reconnectTimer !== null) {
        window.clearTimeout(reconnectTimer);
        reconnectTimer = null;
      }
    };

    const scheduleReconnect = () => {
      if (disposed || reconnectTimer !== null) {
        return;
      }
      const delayMs = Math.min(1000 * 2 ** reconnectAttemptRef.current, 10000);
      reconnectAttemptRef.current += 1;
      reconnectTimer = window.setTimeout(() => {
        reconnectTimer = null;
        void connect(true);
      }, delayMs);
    };

    const markActivity = () => {
      lastActivityAt = Date.now();
    };

    const handleMessage = (message: RunRealtimeMessage, reconnected: boolean) => {
      if (message.run_id !== executionId) {
        return;
      }

      if (message.type === "connection_established") {
        reconnectAttemptRef.current = 0;
        setLiveStatus("active");
        markActivity();
        const shouldRefresh = hasConnectedOnceRef.current || reconnected;
        hasConnectedOnceRef.current = true;
        if (shouldRefresh) {
          void refreshCanonicalState();
        }
        return;
      }

      if (message.type === "heartbeat") {
        markActivity();
        return;
      }

      if (message.type === "node_stream_chunk" || message.type === "node_stream_end") {
        const summaryKey = `${message.payload.node_id}:${message.payload.attempt}`;
        setLiveSummaries((current) => ({
          ...current,
          [summaryKey]: message.payload.text_preview ?? current[summaryKey] ?? "",
        }));
        markActivity();
        return;
      }

      if (message.type === "decision_required" || message.type === "decision_resolved") {
        markActivity();
        void refreshCanonicalState();
        return;
      }

      if (message.type === "cost_update") {
        markActivity();
        return;
      }

      if (message.type === "error") {
        markActivity();
        void refreshCanonicalState();
        return;
      }

      markActivity();
      setRun((current) => applyRealtimeMessage(current, message));
      if (
        message.type === "run_completed" ||
        message.type === "run_failed" ||
        message.type === "run_canceled"
      ) {
        void refreshCanonicalState();
      }
    };

    const connect = async (isReconnect: boolean) => {
      if (disposed) {
        return;
      }

      setLiveStatus("pending");
      if (isReconnect) {
        await refreshCanonicalState();
      }

      let ticket: string;
      try {
<<<<<<< Updated upstream
        const message = JSON.parse(String(event.data)) as RunRealtimeMessage;
        if (message.type === "connected") {
          return;
        }
        setRun((current) => applyRealtimeMessage(current, message));
=======
        const ticketResponse = await authApi.issueWsTicket();
        ticket = ticketResponse.ticket;
>>>>>>> Stashed changes
      } catch {
        if (!disposed) {
          setLiveStatus("offline");
          scheduleReconnect();
        }
        return;
      }

      if (disposed) {
        return;
      }

      socket = new WebSocket(buildRunWebSocketUrl(executionId, ticket));
      socket.addEventListener("open", markActivity);
      socket.addEventListener("message", (event) => {
        if (disposed) {
          return;
        }

        try {
          const message = JSON.parse(String(event.data)) as RunRealtimeMessage;
          handleMessage(message, isReconnect);
        } catch {
          void refreshCanonicalState();
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
          scheduleReconnect();
        }
      });
    };

    silenceMonitor = window.setInterval(() => {
      if (disposed) {
        return;
      }
      if (Date.now() - lastActivityAt > 30000) {
        socket?.close();
      }
    }, 5000);

    void connect(false);

    return () => {
      disposed = true;
      clearReconnectTimer();
      if (silenceMonitor !== null) {
        window.clearInterval(silenceMonitor);
      }
      socket?.close();
    };
  }, [executionId, routeParam]);

  useEffect(() => {
    if (!selectedStepId && run?.node_runs.length) {
      setSelectedStepId(run.node_runs[0].id);
    }
  }, [run?.node_runs, selectedStepId]);

  const selectedStep = useMemo(
    () => run?.node_runs.find((step) => step.id === selectedStepId) ?? run?.node_runs[0] ?? null,
    [run?.node_runs, selectedStepId],
  );

  const totalCost = estimateExecutionCost(run);
  const failedStep = run?.node_runs.find((step) => step.status === "failed" || step.status === "error") ?? null;

  const inspector = selectedStep ? (
    <InspectorPanel
      title={selectedStep.node_id}
      subtitle="The inspector keeps canonical step input and output adjacent to a concise human-readable summary."
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
            title="Structured execution trace"
            description="A readable sequence of agents, tools, and steps with summaries first. Each step opens into the inspector for canonical input, output, and reasoning context."
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

          {loading || !run ? (
            <div className="flex min-h-[320px] items-center justify-center rounded-[1.75rem] border border-slate-900/10 bg-white/70 dark:border-white/10 dark:bg-slate-950/50">
              <Spinner size="lg" />
            </div>
          ) : (
            <>
              <Panel
                title={run.graph_name}
                description="Top summary of the execution before you inspect individual steps."
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
                      Total cost
                    </p>
                    <p className="mt-2 text-2xl font-semibold text-slate-950 dark:text-slate-50">
                      {formatCurrency(totalCost)}
                    </p>
                  </div>
                  <div className="rounded-[1.2rem] border border-slate-900/8 bg-[var(--panel-muted)] px-4 py-4 dark:border-white/8">
                    <p className="text-[11px] uppercase tracking-[0.18em] text-slate-500 dark:text-slate-400">Result</p>
                    <div className="mt-2">
                      <StatusBadge status={String(run.status)} label={String(run.status)} />
                    </div>
                  </div>
                  <div className="rounded-[1.2rem] border border-slate-900/8 bg-[var(--panel-muted)] px-4 py-4 dark:border-white/8">
                    <p className="text-[11px] uppercase tracking-[0.18em] text-slate-500 dark:text-slate-400">
                      Failure point
                    </p>
                    <p className="mt-2 text-sm font-semibold text-slate-950 dark:text-slate-50">
                      {failedStep ? failedStep.node_id : "No failure detected"}
                    </p>
                  </div>
                </div>
              </Panel>

              <div className="grid gap-6">
                <Panel title="Execution flow" description="Ordered steps across agents, tools, and workflow nodes.">
                  {run.node_runs.length ? (
                    <div className="space-y-4">
                      {run.node_runs.map((step, index) => {
                        const tone = statusTone(step.status);
                        const traceStep = step.agent_trace?.steps?.[step.agent_trace.steps.length - 1] as
                          | AgentTraceStep
                          | undefined;

                        return (
                          <button
                            key={step.id}
                            type="button"
                            onClick={() => setSelectedStepId(step.id)}
                            className="w-full rounded-[1.3rem] border border-slate-900/8 bg-white/75 px-5 py-5 text-left transition-colors hover:bg-[var(--panel-muted)] dark:border-white/8 dark:bg-white/4 dark:hover:bg-white/8"
                          >
                            <div className="grid gap-4 xl:grid-cols-[3.5rem_minmax(0,1fr)_12rem]">
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
                                </div>
                                <p className="mt-3 text-sm leading-7 text-slate-600 dark:text-slate-300">
                                  {summarizeStep(step)}
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
                  <Panel title="Execution state" description="Canonical execution timing and queue status.">
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

                  <Panel
                    title="Human gate"
                    description="If the run is paused for approval, the prompt context stays visible here."
                  >
                    {run.paused_node_id ? (
                      <div className="rounded-[1.2rem] border border-slate-900/8 bg-[var(--panel-muted)] px-4 py-4 dark:border-white/8">
                        <p className="text-sm font-semibold text-slate-950 dark:text-slate-50">
                          {run.pause_payload?.node_name ?? run.paused_node_id}
                        </p>
                        <p className="mt-2 text-sm leading-7 text-slate-600 dark:text-slate-300">
                          {run.pause_payload?.prompt_message ?? "Execution is waiting on human approval."}
                        </p>
                      </div>
                    ) : (
                      <EmptyBlock
                        title="No active human gate"
                        description="This execution is not currently paused for approval."
                      />
                    )}
                  </Panel>
                </div>
              </div>
            </>
          )}
        </div>
      </DashboardLayout>
    </ProtectedRoute>
  );
}
