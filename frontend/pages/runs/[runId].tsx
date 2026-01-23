import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import Link from "next/link";
import { useRouter } from "next/router";

import DashboardLayout from "../../components/DashboardLayout";
import ProtectedRoute from "../../components/ProtectedRoute";
import { getAccessToken, getApiErrorMessage, graphsApi, runsApi, type NodeRunItem, type RunDetail } from "../../lib/api";
import { formatJsonForDisplay } from "../../lib/json";
import { Badge, Button, Card, CardContent, CardHeader, CardTitle, Separator, Spinner } from "@/components/ui";

const formatDateTime = (isoString: string) => {
  const date = new Date(isoString);
  if (Number.isNaN(date.getTime())) {
    return isoString;
  }
  return date.toLocaleString();
};

const formatDuration = (durationMs: number | null) => {
  if (!durationMs && durationMs !== 0) return "-";
  if (durationMs < 1000) return `${durationMs}ms`;

  const totalSeconds = Math.floor(durationMs / 1000);
  const minutes = Math.floor(totalSeconds / 60);
  const seconds = totalSeconds % 60;
  if (minutes > 0) return `${minutes}m ${seconds}s`;
  return `${totalSeconds}s`;
};

const formatNodeStatusLabel = (status: string) => {
  if (status === "running") return "in progress";
  return status;
};

function StatusIcon({ status }: { status: string }) {
  switch (status) {
    case "succeeded":
    case "success":
      return (
        <svg viewBox="0 0 24 24" fill="none" aria-hidden="true">
          <path
            d="M9 12.5l2 2 4-5"
            stroke="currentColor"
            strokeWidth="2"
            strokeLinecap="round"
            strokeLinejoin="round"
          />
          <path
            d="M12 22c5.523 0 10-4.477 10-10S17.523 2 12 2 2 6.477 2 12s4.477 10 10 10z"
            stroke="currentColor"
            strokeWidth="2"
          />
        </svg>
      );
    case "failed":
    case "error":
      return (
        <svg viewBox="0 0 24 24" fill="none" aria-hidden="true">
          <path
            d="M15 9l-6 6M9 9l6 6"
            stroke="currentColor"
            strokeWidth="2"
            strokeLinecap="round"
          />
          <path
            d="M12 22c5.523 0 10-4.477 10-10S17.523 2 12 2 2 6.477 2 12s4.477 10 10 10z"
            stroke="currentColor"
            strokeWidth="2"
          />
        </svg>
      );
    case "running":
      return (
        <svg viewBox="0 0 24 24" fill="none" className="animate-spin" aria-hidden="true">
          <path
            d="M12 2a10 10 0 1 0 10 10"
            stroke="currentColor"
            strokeWidth="2"
            strokeLinecap="round"
          />
        </svg>
      );
    case "paused":
      return (
        <svg viewBox="0 0 24 24" fill="none" aria-hidden="true">
          <path
            d="M9 7v10M15 7v10"
            stroke="currentColor"
            strokeWidth="2"
            strokeLinecap="round"
          />
          <path
            d="M12 22c5.523 0 10-4.477 10-10S17.523 2 12 2 2 6.477 2 12s4.477 10 10 10z"
            stroke="currentColor"
            strokeWidth="2"
          />
        </svg>
      );
    case "canceled":
      return (
        <svg viewBox="0 0 24 24" fill="none" aria-hidden="true">
          <path
            d="M7 7l10 10"
            stroke="currentColor"
            strokeWidth="2"
            strokeLinecap="round"
          />
          <path
            d="M12 22c5.523 0 10-4.477 10-10S17.523 2 12 2 2 6.477 2 12s4.477 10 10 10z"
            stroke="currentColor"
            strokeWidth="2"
          />
        </svg>
      );
    case "skipped":
      return (
        <svg viewBox="0 0 24 24" fill="none" aria-hidden="true">
          <path
            d="M8 12h8"
            stroke="currentColor"
            strokeWidth="2"
            strokeLinecap="round"
          />
          <path
            d="M12 22c5.523 0 10-4.477 10-10S17.523 2 12 2 2 6.477 2 12s4.477 10 10 10z"
            stroke="currentColor"
            strokeWidth="2"
          />
        </svg>
      );
    case "pending":
    default:
      return (
        <svg viewBox="0 0 24 24" fill="none" aria-hidden="true">
          <path
            d="M12 6v6l4 2"
            stroke="currentColor"
            strokeWidth="2"
            strokeLinecap="round"
            strokeLinejoin="round"
          />
          <path
            d="M12 22c5.523 0 10-4.477 10-10S17.523 2 12 2 2 6.477 2 12s4.477 10 10 10z"
            stroke="currentColor"
            strokeWidth="2"
          />
        </svg>
      );
  }
}

const getStatusBadgeClass = (status: string) => {
  switch (status) {
    case "succeeded":
    case "success":
      return "border-emerald-500/25 bg-emerald-500/10 text-emerald-700 dark:text-emerald-300";
    case "failed":
    case "error":
      return "border-rose-500/25 bg-rose-500/10 text-rose-700 dark:text-rose-300";
    case "running":
      return "border-blue-500/25 bg-blue-500/10 text-blue-700 dark:text-blue-300";
    case "pending":
      return "border-muted-foreground/25 bg-muted/40 text-muted-foreground";
    case "paused":
      return "border-amber-500/25 bg-amber-500/10 text-amber-800 dark:text-amber-300";
    case "canceled":
      return "border-muted-foreground/20 bg-muted/40 text-muted-foreground";
    case "skipped":
      return "border-muted-foreground/20 bg-muted/40 text-muted-foreground";
    default:
      return "border-muted-foreground/25 bg-muted/40 text-muted-foreground";
  }
};

const escapeRegExp = (value: string) => value.replace(/[.*+?^${}()|[\]\\]/g, "\\$&");

type RunDeltaPayload = {
  id: string;
  status: string;
  started_at: string | null;
  ended_at: string | null;
  duration_ms: number | null;
  output_json: Record<string, unknown> | null;
  error_message: string;
};

type RunsWsMessage =
  | { type: "connected"; run_id: string }
  | { type: "run.updated"; run_id: string; run: RunDeltaPayload }
  | { type: "node_run.updated"; run_id: string; node_run: NodeRunItem }
  | { type: string; [key: string]: unknown };

const sortNodeRuns = (nodeRuns: NodeRunItem[]) => {
  return [...nodeRuns].sort((a, b) => {
    const aNull = !a.started_at;
    const bNull = !b.started_at;
    if (aNull && !bNull) return 1;
    if (!aNull && bNull) return -1;

    if (a.started_at && b.started_at) {
      const aTime = new Date(a.started_at).getTime();
      const bTime = new Date(b.started_at).getTime();
      if (!Number.isNaN(aTime) && !Number.isNaN(bTime) && aTime !== bTime) {
        return aTime - bTime;
      }
    }

    return a.attempt - b.attempt;
  });
};

const isTerminalRunStatus = (status: string) => {
  return status === "succeeded" || status === "failed" || status === "canceled";
};

export default function RunDetailPage() {
  const router = useRouter();
  const runId = typeof router.query.runId === "string" ? router.query.runId : null;

  const [run, setRun] = useState<RunDetail | null>(null);
  const [nodeNameById, setNodeNameById] = useState<Record<string, string>>({});

  const graphId = run?.graph_id;
  const graphVersionId = run?.graph_version_id;
  const runStatus = run?.status;

  const [loading, setLoading] = useState(true);
  const [isRefreshing, setIsRefreshing] = useState(false);
  const [isCanceling, setIsCanceling] = useState(false);
  const [isRerunning, setIsRerunning] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [lastUpdatedAt, setLastUpdatedAt] = useState<Date | null>(null);
  const [now, setNow] = useState<Date>(() => new Date());
  const [wsToken, setWsToken] = useState<string | null>(null);
  const [wsConnected, setWsConnected] = useState(false);
  const [wsError, setWsError] = useState<string | null>(null);

  const runStatusRef = useRef<string | null>(null);

  const [selectedNodeRunId, setSelectedNodeRunId] = useState<string | null>(null);

  const formatNodeLabel = useCallback(
    (nodeRun: NodeRunItem) => {
      const label = nodeNameById[nodeRun.node_id] ?? nodeRun.node_id;
      if (/\b(output|result)\b/i.test(label)) {
        return nodeRun.node_id;
      }
      return label;
    },
    [nodeNameById],
  );

  const fetchRun = useCallback(
    async (opts?: { silent?: boolean }) => {
      if (!runId) return;

      const silent = opts?.silent ?? false;
      if (!silent) {
        setLoading(true);
      } else {
        setIsRefreshing(true);
      }
      setError(null);

      try {
        const data = await runsApi.get(runId);
        runStatusRef.current = data?.status ? String(data.status) : null;
        setRun(data);
        setLastUpdatedAt(new Date());
        setWsToken(getAccessToken());
      } catch (err: unknown) {
        const statusCode =
          (err as { status?: number } | null)?.status ??
          (err as { response?: { status?: number } } | null)?.response?.status;

        if (statusCode === 404) {
          setError("Run not found (404).");
        } else {
          setError(getApiErrorMessage(err, "Failed to load run details."));
        }
      } finally {
        if (!silent) {
          setLoading(false);
        }
        setIsRefreshing(false);
      }
    },
    [runId],
  );

  const cancelRun = useCallback(async () => {
    if (!runId) return;

    setIsCanceling(true);
    setError(null);
    try {
      const data = await runsApi.cancel(runId);
      setRun(data);
      setLastUpdatedAt(new Date());
    } catch (err: unknown) {
      setError(getApiErrorMessage(err, "Failed to cancel run."));
    } finally {
      setIsCanceling(false);
    }
  }, [runId]);

  const rerun = useCallback(async () => {
    if (!run) return;

    setIsRerunning(true);
    setError(null);
    try {
      const newRun = await runsApi.start({
        graph_version_id: run.graph_version_id,
        input_json: run.input_json ?? {},
      });
      void router.push(`/runs/${newRun.id}`);
    } catch (err: unknown) {
      setError(getApiErrorMessage(err, "Failed to start a new run."));
    } finally {
      setIsRerunning(false);
    }
  }, [run, router]);

  useEffect(() => {
    if (!runId) return;
    void fetchRun();
  }, [runId, fetchRun]);

  useEffect(() => {
    if (!run || run.node_runs.length === 0) return;

    let isActive = true;
    const loadGraphVersion = async () => {
      try {
        const version = await graphsApi.getVersion(String(graphId ?? ""), String(graphVersionId ?? ""));
        const nameMap: Record<string, string> = {};
        for (const node of version.graph_json.nodes ?? []) {
          if (!node?.id) continue;
          nameMap[node.id] = node.name || node.id;
        }
        if (isActive) {
          setNodeNameById(nameMap);
        }
      } catch {
        if (isActive) {
          setNodeNameById({});
        }
      }
    };

    void loadGraphVersion();
    return () => {
      isActive = false;
    };
  }, [run, graphId, graphVersionId]);

  useEffect(() => {
    if (!run || run.node_runs.length === 0) {
      if (selectedNodeRunId !== null) {
        setSelectedNodeRunId(null);
      }
      return;
    }

    if (selectedNodeRunId && !run.node_runs.some((nodeRun) => nodeRun.id === selectedNodeRunId)) {
      setSelectedNodeRunId(null);
    }
  }, [run, selectedNodeRunId]);

  useEffect(() => {
    if (!run) return;
    if (selectedNodeRunId !== null) return;
    if (run.node_runs.length === 0) return;
    if (String(run.status) !== "succeeded") return;

    const preferred =
      run.node_runs.find((nodeRun) => nodeRun.output_json !== null) ??
      run.node_runs.find((nodeRun) => String(nodeRun.status) === "succeeded") ??
      run.node_runs[0];

    setSelectedNodeRunId(preferred.id);
  }, [run, selectedNodeRunId]);

  useEffect(() => {
    if (!runId || !wsToken) return;

    if (runStatus && isTerminalRunStatus(String(runStatus))) {
      setWsConnected(false);
      return;
    }

    const apiBaseUrl = (process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000").replace(/\/$/, "");
    const wsBaseUrl = apiBaseUrl.startsWith("https")
      ? apiBaseUrl.replace(/^https/, "wss")
      : apiBaseUrl.replace(/^http/, "ws");
    const wsUrl = `${wsBaseUrl}/ws/runs/${runId}/?token=${encodeURIComponent(wsToken)}`;

    let socket: WebSocket;
    try {
      socket = new WebSocket(wsUrl);
    } catch {
      setWsConnected(false);
      setWsError("Failed to open WebSocket.");
      return;
    }

    setWsError(null);
    setWsConnected(false);

    socket.onopen = () => {
      setWsConnected(true);
    };

    socket.onerror = () => {
      setWsConnected(false);
      setWsError("WebSocket error.");
    };

    socket.onclose = () => {
      setWsConnected(false);
    };

    socket.onmessage = (event) => {
      let message: RunsWsMessage | null = null;
      try {
        const parsed = JSON.parse(String(event.data)) as unknown;
        if (parsed && typeof parsed === "object") {
          message = parsed as RunsWsMessage;
        }
      } catch {
        return;
      }

      if (!message) return;

      if (message.type === "connected") {
        setWsConnected(true);
        return;
      }

      if (message.type === "run.updated" && "run" in message) {
        const runDelta = (message as { run: RunDeltaPayload }).run;
        setRun((prev) => {
          if (!prev) return prev;
          return {
            ...prev,
            ...runDelta,
          };
        });
        setLastUpdatedAt(new Date());
        return;
      }

      if (message.type === "node_run.updated" && "node_run" in message) {
        const updatedNodeRun = (message as { node_run: NodeRunItem }).node_run;
        setRun((prev) => {
          if (!prev) return prev;

          const existingById = prev.node_runs.findIndex((nodeRun) => nodeRun.id === updatedNodeRun.id);
          const existingByKey =
            existingById === -1
              ? prev.node_runs.findIndex(
                  (nodeRun) =>
                    nodeRun.node_id === updatedNodeRun.node_id && nodeRun.attempt === updatedNodeRun.attempt,
                )
              : existingById;

          const nextNodeRuns =
            existingByKey === -1
              ? [...prev.node_runs, updatedNodeRun]
              : prev.node_runs.map((nodeRun, index) => (index === existingByKey ? updatedNodeRun : nodeRun));

          return {
            ...prev,
            node_runs: sortNodeRuns(nextNodeRuns),
          };
        });
        setLastUpdatedAt(new Date());
        return;
      }
    };

    return () => {
      socket.close();
    };
  }, [runId, wsToken, runStatus]);

  useEffect(() => {
    if (wsConnected) return;
    if (!runId) return;

    const interval = window.setInterval(() => {
      const status = runStatusRef.current;
      if (status && isTerminalRunStatus(status)) return;
      void fetchRun({ silent: true });
    }, 3000);

    return () => {
      window.clearInterval(interval);
    };
  }, [runId, fetchRun, wsConnected]);

  useEffect(() => {
    if (!runId) return;

    const interval = window.setInterval(() => {
      setNow((previous) => new Date(previous.getTime() + 1000));
    }, 1000);

    return () => {
      window.clearInterval(interval);
    };
  }, [runId]);

  const selectedNodeRun: NodeRunItem | null = useMemo(() => {
    if (!run) return null;
    if (!selectedNodeRunId) return null;
    return run.node_runs.find((nodeRun) => nodeRun.id === selectedNodeRunId) ?? null;
  }, [run, selectedNodeRunId]);

  const displayedRunDurationMs = useMemo(() => {
    if (!run) return null;
    if (run.duration_ms !== null && run.duration_ms !== undefined) return run.duration_ms;
    if (!run.started_at) return null;

    const status = String(run.status);
    if (isTerminalRunStatus(status)) return null;

    const startedAt = new Date(run.started_at);
    if (Number.isNaN(startedAt.getTime())) return null;
    return Math.max(0, now.getTime() - startedAt.getTime());
  }, [run, now]);

  const displayedRunDurationLabel = useMemo(() => {
    return formatDuration(displayedRunDurationMs);
  }, [displayedRunDurationMs]);

  const hideRunStatusText = useMemo(() => {
    if (!run) return false;
    const statusLabel = String(run.status ?? "");
    const graphName = String(run.graph_name ?? "");
    if (!statusLabel || !graphName) return false;
    return new RegExp(`\\b${escapeRegExp(statusLabel)}\\b`, "i").test(graphName);
  }, [run]);

  return (
    <ProtectedRoute>
      <DashboardLayout>
        <div className="flex flex-col gap-6">
          <div className="relative overflow-hidden rounded-2xl border border-border/50 bg-card/60 backdrop-blur-sm p-6">
            <div className="pointer-events-none absolute inset-0 bg-linear-to-br from-primary/12 via-violet-500/8 to-fuchsia-500/8" />
            <div className="relative flex flex-col gap-4 lg:flex-row lg:items-start lg:justify-between">
              <div>
                <div className="flex items-center gap-3">
                  <Button variant="outline" size="sm" asChild>
                    <Link href="/runs">Back</Link>
                  </Button>
                  <h1 className="text-2xl sm:text-3xl font-bold tracking-tight text-foreground">Run</h1>
                </div>
                {lastUpdatedAt && (
                  <p className="mt-2 text-xs text-muted-foreground">
                    Last updated: {lastUpdatedAt.toLocaleTimeString()}
                  </p>
                )}
                {run && (
                  <p className="mt-1 text-xs text-muted-foreground">
                    Live updates: {wsConnected ? "websocket" : "polling"}
                    {wsError ? ` (${wsError})` : ""}
                  </p>
                )}
              </div>

              <div className="flex flex-wrap items-center gap-2">
                {run?.graph_id && (
                  <Button variant="outline" asChild disabled={loading || isRefreshing || isCanceling || isRerunning}>
                    <Link href={`/graphs/${run.graph_id}?runId=${run.id}`}>Open in editor</Link>
                  </Button>
                )}
                {run && (
                  <Button
                    variant="outline"
                    onClick={() => void rerun()}
                    disabled={loading || isRefreshing || isCanceling || isRerunning}
                  >
                    {isRerunning ? (
                      <>
                        <Spinner size="xs" className="mr-2" />
                        Starting...
                      </>
                    ) : (
                      "Re-run"
                    )}
                  </Button>
                )}
                {run && !isTerminalRunStatus(String(run.status)) && (
                  <Button
                    variant="destructive"
                    onClick={() => void cancelRun()}
                    disabled={loading || isRefreshing || isCanceling || isRerunning}
                  >
                    {isCanceling ? (
                      <>
                        <Spinner size="xs" className="mr-2" />
                        Canceling...
                      </>
                    ) : (
                      "Cancel"
                    )}
                  </Button>
                )}
                <Button
                  variant="outline"
                  onClick={() => void fetchRun()}
                  disabled={loading || isRefreshing || isCanceling || isRerunning}
                >
                  {loading || isRefreshing ? (
                    <>
                      <Spinner size="xs" className="mr-2" />
                      Refreshing...
                    </>
                  ) : (
                    "Refresh"
                  )}
                </Button>
              </div>
            </div>
          </div>

          {loading && !run ? (
            <div className="flex items-center justify-center py-12">
              <Spinner size="md" />
              <span className="ml-3 text-sm text-muted-foreground">Loading run...</span>
            </div>
          ) : !run ? (
            <Card className="border-border/50 bg-card/60 backdrop-blur-sm">
              <CardContent className="py-10">
                <p className="text-sm text-destructive">Error: {error ?? "Run not found."}</p>
              </CardContent>
            </Card>
          ) : (
            <>
              <Card className="border-border/50 bg-card/60 backdrop-blur-sm">
                <CardHeader>
                  <CardTitle className="flex items-center justify-between gap-4">
                    <span className="truncate">
                      {run.graph_name} <span className="text-muted-foreground">v{run.graph_version}</span>
                    </span>
                    <Badge variant="outline" className={getStatusBadgeClass(String(run.status))}>
                      <StatusIcon status={String(run.status)} />
                      {hideRunStatusText ? null : String(run.status)}
                    </Badge>
                  </CardTitle>
                </CardHeader>
                <CardContent>
                  <div className="grid gap-4 md:grid-cols-4">
                    <div className="bg-muted rounded-lg p-3">
                      <p className="text-xs font-medium text-muted-foreground uppercase">Started</p>
                      <p className="mt-1 text-sm">
                        {run.started_at ? formatDateTime(run.started_at) : "—"}
                      </p>
                    </div>
                    <div className="bg-muted rounded-lg p-3">
                      <p className="text-xs font-medium text-muted-foreground uppercase">Ended</p>
                      <p className="mt-1 text-sm">
                        {run.ended_at ? formatDateTime(run.ended_at) : "—"}
                      </p>
                    </div>
                    <div className="bg-muted rounded-lg p-3">
                      <p className="text-xs font-medium text-muted-foreground uppercase">Duration</p>
                      <p key={displayedRunDurationLabel} className="mt-1 text-sm">
                        {displayedRunDurationLabel}
                      </p>
                    </div>
                    <div className="bg-muted rounded-lg p-3">
                      <p className="text-xs font-medium text-muted-foreground uppercase">Run ID</p>
                      <p className="mt-1 text-sm font-mono">{run.id.slice(0, 8)}</p>
                    </div>
                  </div>

                  {run.error_message && (String(run.status) === "failed" || String(run.status) === "canceled") && (
                    <div className="mt-4 rounded-lg border border-destructive/20 bg-destructive/5 p-3">
                      <p className="text-xs font-medium text-destructive uppercase">Run message</p>
                      <p className="mt-1 text-sm text-destructive whitespace-pre-wrap">{run.error_message}</p>
                    </div>
                  )}

                  {error && <p className="mt-4 text-sm text-destructive">Error: {error}</p>}
                </CardContent>
              </Card>

              <Card className="border-border/50 bg-card/60 backdrop-blur-sm">
                <CardHeader>
                  <CardTitle>Run data</CardTitle>
                </CardHeader>
                <CardContent>
                  {run.output_json ? (
                    <pre className="p-4 bg-muted rounded-lg border border-border/50 overflow-auto max-h-[45vh] text-sm font-mono whitespace-pre-wrap">
                      {formatJsonForDisplay(run.output_json)}
                    </pre>
                  ) : (
                    <p className="text-sm text-muted-foreground">
                      {isTerminalRunStatus(String(run.status)) ? "No data recorded." : "No data yet."}
                    </p>
                  )}
                </CardContent>
              </Card>

              <div className="grid gap-6 lg:grid-cols-3">
                <Card className="lg:col-span-1 border-border/50 bg-card/60 backdrop-blur-sm">
                  <CardHeader>
                    <CardTitle>Nodes</CardTitle>
                  </CardHeader>
                  <CardContent>
                    {run.node_runs.length === 0 ? (
                      <p className="text-sm text-muted-foreground">No node runs recorded.</p>
                    ) : (
                      <div className="space-y-2 max-h-[65vh] overflow-auto pr-1">
                        {run.node_runs.map((nodeRun) => {
                          const isSelected = nodeRun.id === selectedNodeRunId;
                          const nodeName = formatNodeLabel(nodeRun);
                          const showNodeStatusText =
                            !(String(run.status) === "failed" && String(nodeRun.status) === "failed");

                          return (
                            <button
                              key={nodeRun.id}
                              type="button"
                              onClick={() => setSelectedNodeRunId(nodeRun.id)}
                              className={[
                                "w-full text-left rounded-lg border p-3 transition-colors",
                                isSelected ? "border-primary bg-primary/5" : "border-border hover:bg-muted/40",
                              ].join(" ")}
                            >
                              <div className="flex items-center justify-between gap-3">
                                <div className="min-w-0">
                                  <p className="text-sm font-medium truncate">{nodeName}</p>
                                  <p className="mt-0.5 text-xs text-muted-foreground">
                                    attempt {nodeRun.attempt}
                                  </p>
                                </div>
                                <div className="flex flex-col items-end gap-2">
                                  <Badge
                                    variant="outline"
                                    className={getStatusBadgeClass(String(nodeRun.status))}
                                  >
                                    <StatusIcon status={String(nodeRun.status)} />
                                    {showNodeStatusText ? formatNodeStatusLabel(String(nodeRun.status)) : null}
                                  </Badge>
                                  <span className="text-xs text-muted-foreground">
                                    {formatDuration(nodeRun.duration_ms)}
                                  </span>
                                </div>
                              </div>
                            </button>
                          );
                        })}
                      </div>
                    )}
                  </CardContent>
                </Card>

                <Card className="lg:col-span-2 lg:sticky lg:top-24 lg:self-start border-border/50 bg-card/60 backdrop-blur-sm">
                  <CardHeader>
                    <CardTitle>Node details</CardTitle>
                  </CardHeader>
                  <CardContent>
                    {!selectedNodeRun ? (
                      <p className="text-sm text-muted-foreground">Select a node to view details.</p>
                    ) : (
                      <div className="space-y-4">
                        <div className="flex flex-wrap items-center gap-2">
                          <Badge variant="outline" className={getStatusBadgeClass(String(selectedNodeRun.status))}>
                            <StatusIcon status={String(selectedNodeRun.status)} />
                            {formatNodeStatusLabel(String(selectedNodeRun.status))}
                          </Badge>
                          <span className="text-sm text-muted-foreground font-mono">{selectedNodeRun.node_id}</span>
                          <span className="text-sm text-muted-foreground">·</span>
                          <span className="text-sm text-muted-foreground">try {selectedNodeRun.attempt}</span>
                        </div>

                        <div className="grid gap-4 md:grid-cols-3">
                          <div className="bg-muted rounded-lg p-3">
                            <p className="text-xs font-medium text-muted-foreground uppercase">Started</p>
                            <p className="mt-1 text-sm">
                              {selectedNodeRun.started_at ? formatDateTime(selectedNodeRun.started_at) : "—"}
                            </p>
                          </div>
                          <div className="bg-muted rounded-lg p-3">
                            <p className="text-xs font-medium text-muted-foreground uppercase">Ended</p>
                            <p className="mt-1 text-sm">
                              {selectedNodeRun.ended_at ? formatDateTime(selectedNodeRun.ended_at) : "—"}
                            </p>
                          </div>
                          <div className="bg-muted rounded-lg p-3">
                            <p className="text-xs font-medium text-muted-foreground uppercase">Duration</p>
                            <p className="mt-1 text-sm">{formatDuration(selectedNodeRun.duration_ms)}</p>
                          </div>
                        </div>

                        <Separator />

                        <details open>
                          <summary className="cursor-pointer text-sm font-medium">Response</summary>
                          <pre className="mt-2 p-4 bg-muted rounded-lg border border-border/50 overflow-auto max-h-[45vh] text-sm font-mono whitespace-pre-wrap">
                            {formatJsonForDisplay(selectedNodeRun.output_json)}
                          </pre>
                        </details>

                        <details open={String(selectedNodeRun.status) === "failed"}>
                          <summary className="cursor-pointer text-sm font-medium">Failure</summary>
                          <pre className="mt-2 p-4 bg-muted rounded-lg overflow-auto max-h-[45vh] text-sm whitespace-pre-wrap">
                            {formatJsonForDisplay(selectedNodeRun.error_json)}
                          </pre>
                        </details>

                        <details open>
                          <summary className="cursor-pointer text-sm font-medium">Input</summary>
                          <pre className="mt-2 p-4 bg-muted rounded-lg overflow-auto max-h-[45vh] text-sm whitespace-pre-wrap">
                            {formatJsonForDisplay(selectedNodeRun.input_json)}
                          </pre>
                        </details>
                      </div>
                    )}
                  </CardContent>
                </Card>
              </div>
            </>
          )}
        </div>
      </DashboardLayout>
    </ProtectedRoute>
  );
}
