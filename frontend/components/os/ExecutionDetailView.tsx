import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { useRouter } from "next/router";
import Link from "next/link";
import {
  AlertTriangle,
  ArrowRight,
  ChevronDown,
  ChevronUp,
  Clock3,
  Filter,
  Inbox,
  RotateCcw,
  Square,
} from "lucide-react";

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
import { getDepartmentTaskLabel, translateRunStatus } from "@/lib/company-workspace";
import { showError, showSuccess } from "@/lib/toast";

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
      type: "connection_established";
      timestamp: string;
      trace_id: string;
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
      type: "node_stream.summary";
      run_id: string;
      node_stream: {
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
    };

const buildRunWebSocketUrl = (runId: string, ticket: string) => {
  const apiOrigin = (process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000").replace(/\/$/, "");
  const websocketOrigin = apiOrigin.replace(/^http/i, "ws");
  return `${websocketOrigin}/ws/runs/${runId}/?ticket=${encodeURIComponent(ticket)}&event_level=default`;
};

const primaryActionButtonClass =
  "rounded-full bg-white text-slate-950 shadow-[0_18px_38px_-24px_rgba(255,255,255,0.85)] hover:bg-slate-100 dark:bg-slate-950 dark:text-white dark:hover:bg-slate-800";
const secondaryActionButtonClass =
  "rounded-full border-white/25 bg-white/10 text-white hover:bg-white/18 hover:text-white dark:border-slate-950/15 dark:bg-slate-950/8 dark:text-slate-950 dark:hover:bg-slate-950/12";
const destructiveActionButtonClass =
  "rounded-full bg-rose-500 text-white shadow-[0_18px_38px_-24px_rgba(244,63,94,0.85)] hover:bg-rose-400 dark:bg-rose-600 dark:hover:bg-rose-500";

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
  const [showAllSteps, setShowAllSteps] = useState(false);
  const [liveSummaries, setLiveSummaries] = useState<Record<string, string>>({});
  const [actionLoading, setActionLoading] = useState<"cancel" | "replay" | null>(null);
  const reconnectAttemptRef = useRef(0);
  const hasConnectedOnceRef = useRef(false);

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
      if (message.type === "run_completed" || message.type === "run_failed" || message.type === "run_canceled") {
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
        const ticketResponse = await authApi.issueWsTicket();
        ticket = ticketResponse.ticket;
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

  const handleCancelOperation = useCallback(async () => {
    if (!run || actionLoading) {
      return;
    }

    setActionLoading("cancel");
    try {
      const updated = await runsApi.cancel(run.id);
      setRun(updated);
      showSuccess("Operation stopped", "The operation was canceled by the backend control plane.");
    } catch (err: unknown) {
      showError("Stop failed", getApiErrorMessage(err, "Unable to stop this operation."));
    } finally {
      setActionLoading(null);
    }
  }, [actionLoading, run]);

  const handleReplayOperation = useCallback(async () => {
    if (!run || actionLoading) {
      return;
    }

    setActionLoading("replay");
    try {
      const replayed = await runsApi.replay(run.id);
      showSuccess("Replay started", "A fresh operation has been queued from the saved input.");
      await router.push(`/executions/${replayed.id}`);
    } catch (err: unknown) {
      showError("Replay failed", getApiErrorMessage(err, "Unable to replay this operation."));
    } finally {
      setActionLoading(null);
    }
  }, [actionLoading, router, run]);

  const handleInspectStep = useCallback((stepId: string) => {
    setSelectedStepId(stepId);
    if (typeof document !== "undefined") {
      document.getElementById("department-activity")?.scrollIntoView({ behavior: "smooth", block: "start" });
    }
  }, []);

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
  const normalizedRunStatus = String(run?.status ?? "").toLowerCase();
  const hasFailedRun = normalizedRunStatus === "failed";
  const canStopOperation = ["pending", "queued", "running", "resume_requested"].includes(normalizedRunStatus);
  const isWaitingForApproval = normalizedRunStatus === "paused" || Boolean(run?.paused_node_id);
  const canReplayOperation = Boolean(run) && !canStopOperation && !isWaitingForApproval;
  const replayButtonLabel =
    actionLoading === "replay"
      ? "Replaying..."
      : normalizedRunStatus === "succeeded"
        ? "Run again"
        : "Replay operation";
  const actionTitle =
    failedStep || hasFailedRun
      ? "Failure needs review"
      : isWaitingForApproval
        ? "Approval needed"
        : canStopOperation
          ? "Operation is active"
          : normalizedRunStatus === "succeeded"
            ? "Operation completed"
            : "Operation actions";
  const actionDescription = failedStep
    ? `${getDepartmentTaskLabel(failedStep, null)} failed. Inspect the failure first, then replay once the issue is understood.`
    : hasFailedRun
      ? "The operation failed without a highlighted department step. Review the trace, then replay once the issue is understood."
      : isWaitingForApproval
        ? "This operation is paused at an approval gate. Open the approval queue to decide the next step."
        : canStopOperation
          ? "Live work is in progress. Keep watching the trace or stop the operation if it is no longer valid."
          : normalizedRunStatus === "succeeded"
            ? "The run finished cleanly. Review the trace or replay it when you need the same operation again."
            : "Use these controls before drilling into logs, timing, or department-level diagnostics.";

  const inspector = selectedStep ? (
    <InspectorPanel
      title={getDepartmentTaskLabel(selectedStep, null)}
      subtitle="The inspector keeps canonical input and output adjacent to a short summary so the operator can inspect only when needed."
      sections={[
        {
          title: "Department activity metadata",
          content: (
            <div className="space-y-2">
              <div className="flex items-center justify-between">
                <span>Status</span>
                <StatusBadge status={translateRunStatus(String(selectedStep.status))} />
              </div>
              <div className="flex items-center justify-between">
                <span>Activity</span>
                <span>{getDepartmentTaskLabel(selectedStep, null)}</span>
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
            eyebrow="Operation detail"
            title="Operation trace"
            description="Failures, decisions, and bottlenecks come first. Routine department activity stays collapsed until the operator explicitly expands it."
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
              <div className="rounded-[2rem] border border-slate-950/12 bg-slate-950 px-6 py-5 text-white shadow-[0_34px_90px_-58px_rgba(15,23,42,0.95)] dark:border-white/12 dark:bg-slate-100 dark:text-slate-950">
                <div className="flex flex-col gap-5 xl:flex-row xl:items-center xl:justify-between">
                  <div className="min-w-0">
                    <div className="flex flex-wrap items-center gap-2">
                      <p className="text-[11px] uppercase tracking-[0.24em] text-white/60 dark:text-slate-500">
                        Operator action
                      </p>
                      <StatusBadge status={String(run.status)} />
                      <StatusBadge
                        status={liveStatus}
                        label={
                          liveStatus === "active" ? "Live updates" : liveStatus === "pending" ? "Connecting" : "Offline"
                        }
                      />
                    </div>
                    <h3
                      className="mt-3 text-2xl font-semibold tracking-tight"
                      style={{ fontFamily: "var(--font-serif)" }}
                    >
                      {actionTitle}
                    </h3>
                    <p className="mt-2 max-w-3xl text-sm leading-7 text-white/68 dark:text-slate-600">
                      {actionDescription}
                    </p>
                  </div>

                  <div className="flex flex-wrap items-center gap-2 xl:justify-end">
                    {failedStep ? (
                      <Button
                        type="button"
                        className={primaryActionButtonClass}
                        onClick={() => handleInspectStep(failedStep.id)}
                      >
                        Inspect failure
                        <ArrowRight className="h-4 w-4" />
                      </Button>
                    ) : null}

                    {isWaitingForApproval ? (
                      <Button asChild className={primaryActionButtonClass}>
                        <Link href="/inbox">
                          <Inbox className="h-4 w-4" />
                          Open approvals
                        </Link>
                      </Button>
                    ) : null}

                    {canStopOperation ? (
                      <Button
                        type="button"
                        className={destructiveActionButtonClass}
                        onClick={() => void handleCancelOperation()}
                        disabled={actionLoading !== null}
                      >
                        <Square className="h-4 w-4" />
                        {actionLoading === "cancel" ? "Stopping..." : "Stop operation"}
                      </Button>
                    ) : null}

                    {canReplayOperation ? (
                      <Button
                        type="button"
                        className={failedStep ? secondaryActionButtonClass : primaryActionButtonClass}
                        onClick={() => void handleReplayOperation()}
                        disabled={actionLoading !== null}
                      >
                        <RotateCcw className="h-4 w-4" />
                        {replayButtonLabel}
                      </Button>
                    ) : null}

                    <Button asChild variant="outline" className={secondaryActionButtonClass}>
                      <Link href="/executions">Back to operations</Link>
                    </Button>
                  </div>
                </div>
              </div>

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
                      Attention point
                    </p>
                    <p className="mt-2 text-sm font-semibold text-slate-950 dark:text-slate-50">
                      {failedStep ? getDepartmentTaskLabel(failedStep, null) : "No failure detected"}
                    </p>
                  </div>
                  <div className="rounded-[1.2rem] border border-slate-900/8 bg-[var(--panel-muted)] px-4 py-4 dark:border-white/8">
                    <p className="text-[11px] uppercase tracking-[0.18em] text-slate-500 dark:text-slate-400">
                      Bottleneck
                    </p>
                    <p className="mt-2 text-sm font-semibold text-slate-950 dark:text-slate-50">
                      {bottleneckStep
                        ? `${getDepartmentTaskLabel(bottleneckStep, null)} · ${formatDuration(bottleneckStep.duration_ms)}`
                        : "No bottleneck flagged"}
                    </p>
                  </div>
                </div>
              </Panel>

              <div className="grid gap-6 2xl:grid-cols-[0.92fr_1.08fr]">
                <Panel
                  title="Attention points"
                  description="The department activity that matters most to an operator right now."
                >
                  {failedStep || decisionStep || bottleneckStep ? (
                    <div className="space-y-3">
                      {failedStep ? (
                        <div className="rounded-[1.2rem] border border-rose-800/12 bg-rose-50 px-4 py-4 text-rose-950 dark:border-rose-200/15 dark:bg-rose-500/10 dark:text-rose-100">
                          <div className="flex items-start justify-between gap-3">
                            <div>
                              <p className="text-sm font-semibold">Needs attention</p>
                              <p className="mt-2 text-sm leading-7">
                                {getDepartmentTaskLabel(failedStep, null)} needs attention. Inspect this activity before
                                replaying the operation.
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
                            {getDepartmentTaskLabel(decisionStep, null)} is waiting on a human decision or approval
                            boundary.
                          </p>
                        </div>
                      ) : null}
                      {bottleneckStep ? (
                        <div className="rounded-[1.2rem] border border-slate-900/8 bg-[var(--panel-muted)] px-4 py-4 dark:border-white/8">
                          <div className="flex items-start justify-between gap-3">
                            <div>
                              <p className="text-sm font-semibold text-slate-950 dark:text-slate-50">Bottleneck</p>
                              <p className="mt-2 text-sm leading-7 text-slate-700 dark:text-slate-200">
                                {getDepartmentTaskLabel(bottleneckStep, null)} consumed{" "}
                                {formatDuration(bottleneckStep.duration_ms)} and is materially slower than the rest of
                                the operation.
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

                <Panel
                  title="Operation posture"
                  description="Operator-oriented summary of the current operation state."
                >
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

              <div id="department-activity" className="scroll-mt-32">
                <Panel
                  title="Department activity"
                  description="Routine activity is collapsed by default so the operator can focus on failures, decisions, and bottlenecks first."
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
                            Collapse routine activity
                            <ChevronUp className="h-4 w-4" />
                          </>
                        ) : (
                          <>
                            Show all activity
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
                          {traceState.hiddenRoutineCount} routine activit
                          {traceState.hiddenRoutineCount === 1 ? "y" : "ies"} collapsed.
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
                                    {getDepartmentTaskLabel(step, null)}
                                  </p>
                                  <StatusBadge status={translateRunStatus(String(step.status))} />
                                  <StatusBadge status="pending" label="department activity" />
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
                                    <p className="mt-1 text-xs">This activity requires intervention here.</p>
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
                      title="No activity available"
                      description="This operation has not emitted any department activity yet."
                    />
                  )}
                </Panel>
              </div>

              <div className="grid gap-6 2xl:grid-cols-2">
                <Panel title="Operation state" description="Canonical timing, queue status, and memory posture.">
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
                  title="Approval gate"
                  description="Decision context stays readable and close to the main operation trace."
                >
                  {run.paused_node_id ? (
                    <div className="rounded-[1.2rem] border border-slate-900/8 bg-[var(--panel-muted)] px-4 py-4 dark:border-white/8">
                      <p className="text-sm font-semibold text-slate-950 dark:text-slate-50">
                        {run.pause_payload?.node_name ?? run.paused_node_id}
                      </p>
                      <p className="mt-2 text-sm leading-7 text-slate-600 dark:text-slate-300">
                        {run.pause_payload?.prompt_message ?? "This operation is waiting on human approval."}
                      </p>
                      <div className="mt-4">
                        <Button asChild size="sm" className="rounded-full">
                          <Link href="/inbox">
                            Open approvals
                            <ArrowRight className="h-4 w-4" />
                          </Link>
                        </Button>
                      </div>
                    </div>
                  ) : (
                    <EmptyBlock
                      title="No active approval gate"
                      description="This operation is not currently paused for approval."
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
