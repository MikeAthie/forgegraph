import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import Link from "next/link";
import { useRouter } from "next/router";

import DashboardLayout from "../../components/DashboardLayout";
import ProtectedRoute from "../../components/ProtectedRoute";
import { getAccessToken, getApiErrorMessage, graphsApi, runsApi, type NodeRunItem, type RunDetail, type ResumeRunInput } from "../../lib/api";
import { formatJsonForDisplay } from "../../lib/json";
import { showError, showSuccess, showWarning } from "../../lib/toast";
import { Badge, Button, Card, CardContent, CardHeader, CardTitle, ConfirmButton, Input, Separator, Spinner, Textarea } from "@/components/ui";

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
    case "waiting":
      return (
        <svg viewBox="0 0 24 24" fill="none" aria-hidden="true" className={status === "waiting" ? "animate-pulse" : ""}>
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
    case "waiting":
      return "border-amber-500/25 bg-amber-500/10 text-amber-800 dark:text-amber-300";
    case "canceled":
      return "border-muted-foreground/20 bg-muted/40 text-muted-foreground";
    case "skipped":
      return "border-muted-foreground/20 bg-muted/40 text-muted-foreground";
    default:
      return "border-muted-foreground/25 bg-muted/40 text-muted-foreground";
  }
};

const getRunStatusLabel = (run: RunDetail | null) => {
  if (!run) return "";
  if (String(run.status) === "pending" && run.queue_status) {
    return "queued";
  }
  return String(run.status);
};

const escapeRegExp = (value: string) => value.replace(/[.*+?^${}()|[\]\\]/g, "\\$&");

const getReconnectDelayMs = (attempt: number) => {
  if (attempt <= 0) return 0;
  const cappedAttempt = Math.min(attempt, 5);
  const baseDelayMs = 1000;
  const maxDelayMs = 10000;
  const delay = Math.min(maxDelayMs, baseDelayMs * 2 ** cappedAttempt);
  const jitter = Math.floor(Math.random() * 250);
  return delay + jitter;
};

type RunDeltaPayload = {
  id: string;
  status: string;
  started_at: string | null;
  ended_at: string | null;
  duration_ms: number | null;
  output_json: Record<string, unknown> | null;
  error_message: string;
};

type NodeStreamPayload = {
  node_id: string;
  node_type: string;
  attempt: number;
  chunk: string;
  chunk_index?: number;
};

type RunsWsMessage =
  | { type: "connected"; run_id: string }
  | { type: "run.updated"; run_id: string; run: RunDeltaPayload }
  | { type: "node_run.updated"; run_id: string; node_run: NodeRunItem }
  | { type: "node_stream.chunk"; run_id: string; node_stream: NodeStreamPayload }
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

const getNodeAttemptKey = (nodeId: string, attempt: number) => `${nodeId}:${attempt}`;
const isTerminalNodeStatus = (status: string) => {
  return status === "succeeded" || status === "failed" || status === "skipped";
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
  const [isReplaying, setIsReplaying] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [lastUpdatedAt, setLastUpdatedAt] = useState<Date | null>(null);
  const [now, setNow] = useState<Date>(() => new Date());
  const [wsToken, setWsToken] = useState<string | null>(null);
  const [wsConnected, setWsConnected] = useState(false);
  const [wsError, setWsError] = useState<string | null>(null);
  const [sseConnected, setSseConnected] = useState(false);
  const [sseError, setSseError] = useState<string | null>(null);
  const [lastStreamTimestamp, setLastStreamTimestamp] = useState<string | null>(null);
  const [streamReconnectCount, setStreamReconnectCount] = useState(0);
  const [lastReconnectFrom, setLastReconnectFrom] = useState<string | null>(null);
  const [nodeStreamText, setNodeStreamText] = useState<Record<string, string>>({});
  const lastStreamTimestampRef = useRef<string | null>(null);
  const pendingRunDeltaRef = useRef<RunDeltaPayload | null>(null);
  const pendingNodeRunsRef = useRef<Map<string, NodeRunItem>>(new Map());
  const pendingNodeStreamChunksRef = useRef<Map<string, string[]>>(new Map());
  const flushRafRef = useRef<number | null>(null);

  const runStatusRef = useRef<string | null>(null);

  const [selectedNodeRunId, setSelectedNodeRunId] = useState<string | null>(null);

  // Human Gate approval state
  const [approvalFields, setApprovalFields] = useState<Record<string, string>>({});
  const [approvalFeedback, setApprovalFeedback] = useState("");
  const [isApproving, setIsApproving] = useState(false);
  const [isRejecting, setIsRejecting] = useState(false);
  const hasPrefilledApprovalFieldsRef = useRef(false);

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

  const replayRun = useCallback(async () => {
    if (!runId) return;

    setIsReplaying(true);
    setError(null);
    try {
      const newRun = await runsApi.replay(runId);
      void router.push(`/runs/${newRun.id}`);
    } catch (err: unknown) {
      const message = getApiErrorMessage(err, "Failed to replay run from checkpoint.");
      setError(message);
      showError("Replay failed", message);
    } finally {
      setIsReplaying(false);
    }
  }, [runId, router]);

  const resumeRun = useCallback(async (approved: boolean) => {
    if (!runId || !run?.paused_node_id) return;

    const requiredFields = run.pause_payload?.required_fields ?? [];
    if (approved && requiredFields.length > 0) {
      const missing = requiredFields.filter((field) => !String(approvalFields[field] ?? "").trim());
      if (missing.length > 0) {
        const message = `Missing required field${missing.length === 1 ? "" : "s"}: ${missing.join(", ")}`;
        setError(message);
        showError("Cannot approve yet", message);
        return;
      }
    }

    if (approved) {
      setIsApproving(true);
    } else {
      setIsRejecting(true);
    }
    setError(null);

    try {
      const input: ResumeRunInput = {
        node_id: run.paused_node_id,
        input_json: {
          approved,
          fields: approved ? approvalFields : undefined,
          feedback: !approved ? approvalFeedback : undefined,
        },
      };
      await runsApi.resume(runId, input);
      if (approved) {
        showSuccess("Approved", "Run resumed and workflow continues.");
      } else {
        showWarning("Rejected", "Run was rejected and will not continue.");
      }
      // Clear the form
      setApprovalFields({});
      setApprovalFeedback("");
      // Refresh to get updated status
      await fetchRun({ silent: true });
    } catch (err: unknown) {
      const message = getApiErrorMessage(err, approved ? "Failed to approve run." : "Failed to reject run.");
      setError(message);
      showError(approved ? "Approval failed" : "Rejection failed", message);
    } finally {
      setIsApproving(false);
      setIsRejecting(false);
    }
  }, [runId, run, approvalFields, approvalFeedback, fetchRun]);

  const latestSucceededNodeRun = useMemo(() => {
    if (!run?.node_runs?.length) return null;
    const candidates = run.node_runs
      .filter((nodeRun) => (String(nodeRun.status) === "succeeded" || String(nodeRun.status) === "success") && nodeRun.output_json)
      .filter((nodeRun) => String(nodeRun.node_id) !== String(run.paused_node_id));
    return candidates.length > 0 ? candidates[candidates.length - 1] : null;
  }, [run]);

  const latestSucceededNodeOutputText = useMemo(() => {
    if (!latestSucceededNodeRun?.output_json) return "";
    return formatJsonForDisplay(latestSucceededNodeRun.output_json);
  }, [latestSucceededNodeRun]);

  const flushStreamUpdates = useCallback(() => {
    if (flushRafRef.current !== null) {
      return;
    }
    flushRafRef.current = window.requestAnimationFrame(() => {
      flushRafRef.current = null;
      const runDelta = pendingRunDeltaRef.current;
      const nodeRunUpdates = pendingNodeRunsRef.current;
      const streamChunkUpdates = pendingNodeStreamChunksRef.current;
      if (!runDelta && nodeRunUpdates.size === 0 && streamChunkUpdates.size === 0) return;

      pendingRunDeltaRef.current = null;
      pendingNodeRunsRef.current = new Map();
      pendingNodeStreamChunksRef.current = new Map();

      setRun((prev) => {
        if (!prev) return prev;
        let next = prev;
        if (runDelta) {
          next = { ...next, ...runDelta };
        }
        if (nodeRunUpdates.size > 0) {
          const nodeRunList = [...next.node_runs];
          for (const update of nodeRunUpdates.values()) {
            const existingById = nodeRunList.findIndex((nodeRun) => nodeRun.id === update.id);
            const existingByKey =
              existingById === -1
                ? nodeRunList.findIndex(
                    (nodeRun) =>
                      nodeRun.node_id === update.node_id && nodeRun.attempt === update.attempt,
                  )
                : existingById;

            if (existingByKey === -1) {
              nodeRunList.push(update);
            } else {
              nodeRunList[existingByKey] = update;
            }
          }
          next = { ...next, node_runs: sortNodeRuns(nodeRunList) };
        }
        return next;
      });
      setNodeStreamText((prev) => {
        if (streamChunkUpdates.size === 0 && nodeRunUpdates.size === 0) {
          return prev;
        }

        const next = { ...prev };
        let changed = false;

        for (const [streamKey, chunks] of streamChunkUpdates.entries()) {
          if (chunks.length === 0) continue;
          next[streamKey] = `${next[streamKey] ?? ""}${chunks.join("")}`;
          changed = true;
        }

        for (const updatedNodeRun of nodeRunUpdates.values()) {
          if (!isTerminalNodeStatus(String(updatedNodeRun.status))) {
            continue;
          }
          const streamKey = getNodeAttemptKey(updatedNodeRun.node_id, updatedNodeRun.attempt);
          if (streamKey in next) {
            delete next[streamKey];
            changed = true;
          }
        }

        return changed ? next : prev;
      });
      setLastUpdatedAt(new Date());
    });
  }, []);

  const handleStreamMessage = useCallback((message: RunsWsMessage | null) => {
    if (!message) return;

    const messageTimestamp =
      typeof (message as unknown as { timestamp?: string }).timestamp === "string"
        ? (message as unknown as { timestamp: string }).timestamp
        : null;
    if (messageTimestamp) {
      setLastStreamTimestamp(messageTimestamp);
      lastStreamTimestampRef.current = messageTimestamp;
    }

    if (message.type === "connected") {
      return;
    }

    if (message.type === "run.updated" && "run" in message) {
      const runDelta = (message as { run: RunDeltaPayload }).run;
      pendingRunDeltaRef.current = runDelta;
      flushStreamUpdates();
      return;
    }

    if (message.type === "node_run.updated" && "node_run" in message) {
      const updatedNodeRun = (message as { node_run: NodeRunItem }).node_run;
      const key = updatedNodeRun.id || `${updatedNodeRun.node_id}:${updatedNodeRun.attempt}`;
      pendingNodeRunsRef.current.set(key, updatedNodeRun);
      flushStreamUpdates();
      return;
    }

    if (message.type === "node_stream.chunk") {
      const rawPayload = ("node_stream" in message
        ? (message as { node_stream: unknown }).node_stream
        : (message as { payload?: unknown }).payload) as Record<string, unknown> | undefined;
      if (!rawPayload) return;

      const nodeId = String(rawPayload.node_id ?? "");
      const attempt = Number(rawPayload.attempt ?? 1);
      const chunk = String(rawPayload.chunk ?? "");
      if (!nodeId || !chunk) return;

      const streamKey = getNodeAttemptKey(nodeId, Number.isFinite(attempt) ? attempt : 1);
      const pendingChunks = pendingNodeStreamChunksRef.current.get(streamKey) ?? [];
      pendingChunks.push(chunk);
      pendingNodeStreamChunksRef.current.set(streamKey, pendingChunks);
      flushStreamUpdates();
    }
  }, [flushStreamUpdates]);

  useEffect(() => {
    if (!run || String(run.status) !== "paused") {
      hasPrefilledApprovalFieldsRef.current = false;
      return;
    }

    // Prefill likely long-form required fields (email draft / JSON review) with the most recent output,
    // but never overwrite user input and avoid obvious short fields like "ticket".
    const requiredFields = run.pause_payload?.required_fields ?? [];
    if (requiredFields.length === 0) return;
    if (hasPrefilledApprovalFieldsRef.current) return;

    const shouldPrefill = (field: string) => /\b(draft|email|body|message|json|data|content|output)\b/i.test(field);
    const next: Record<string, string> = { ...approvalFields };
    let changed = false;

    for (const field of requiredFields) {
      if (!shouldPrefill(field)) continue;
      if (String(next[field] ?? "").trim()) continue;
      if (!latestSucceededNodeOutputText) continue;
      next[field] = latestSucceededNodeOutputText;
      changed = true;
    }

    if (changed) {
      setApprovalFields(next);
      hasPrefilledApprovalFieldsRef.current = true;
    }
  }, [run, approvalFields, latestSucceededNodeOutputText]);

  useEffect(() => {
    if (!run || String(run.status) !== "paused") return;
    if (typeof window === "undefined") return;
    if (window.location.hash !== "#approval") return;
    const el = document.getElementById("approval");
    el?.scrollIntoView({ behavior: "smooth", block: "start" });
  }, [run]);

  useEffect(() => {
    if (!runId) return;
    setNodeStreamText({});
    pendingRunDeltaRef.current = null;
    pendingNodeRunsRef.current = new Map();
    pendingNodeStreamChunksRef.current = new Map();
    if (flushRafRef.current !== null) {
      window.cancelAnimationFrame(flushRafRef.current);
      flushRafRef.current = null;
    }
    void fetchRun();
  }, [runId, fetchRun]);

  useEffect(() => {
    return () => {
      if (flushRafRef.current !== null) {
        window.cancelAnimationFrame(flushRafRef.current);
        flushRafRef.current = null;
      }
    };
  }, []);

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
    if (wsConnected) return;

    if (runStatus && isTerminalRunStatus(String(runStatus))) {
      setWsConnected(false);
      return;
    }

    const apiBaseUrl = (process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000").replace(/\/$/, "");
    const wsBaseUrl = apiBaseUrl.startsWith("https")
      ? apiBaseUrl.replace(/^https/, "wss")
      : apiBaseUrl.replace(/^http/, "ws");
    const wsUrl = `${wsBaseUrl}/ws/runs/${runId}/?token=${encodeURIComponent(wsToken)}`;

    const reconnectDelayMs = getReconnectDelayMs(streamReconnectCount);
    let socket: WebSocket | null = null;
    let reconnectScheduled = false;
    let closed = false;
    let timeoutId: number | null = null;

    const scheduleReconnect = () => {
      if (reconnectScheduled) return;
      reconnectScheduled = true;
      setStreamReconnectCount((prev) => prev + 1);
    };

    const connect = () => {
      if (closed) return;

      try {
        socket = new WebSocket(wsUrl);
      } catch {
        setWsConnected(false);
        setWsError("Failed to open WebSocket.");
        scheduleReconnect();
        return;
      }

      setWsError(null);
      setWsConnected(false);

      socket.onopen = () => {
        setWsConnected(true);
        if (streamReconnectCount > 0 && lastStreamTimestampRef.current) {
          setLastReconnectFrom(lastStreamTimestampRef.current);
        }
      };

      socket.onerror = () => {
        setWsConnected(false);
        setWsError("WebSocket error.");
        scheduleReconnect();
        socket?.close();
      };

      socket.onclose = () => {
        setWsConnected(false);
        scheduleReconnect();
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

        handleStreamMessage(message);
      };
    };

    timeoutId = window.setTimeout(connect, reconnectDelayMs);

    return () => {
      closed = true;
      if (timeoutId) {
        window.clearTimeout(timeoutId);
      }
      socket?.close();
    };
  }, [runId, wsToken, runStatus, wsConnected, handleStreamMessage, streamReconnectCount]);

  useEffect(() => {
    if (wsConnected || sseConnected) return;
    if (!runId) return;

    const interval = window.setInterval(() => {
      const status = runStatusRef.current;
      if (status && isTerminalRunStatus(status)) return;
      void fetchRun({ silent: true });
    }, 3000);

    return () => {
      window.clearInterval(interval);
    };
  }, [runId, fetchRun, wsConnected, sseConnected]);

  useEffect(() => {
    if (!runId || !wsToken) return;
    if (wsConnected) return;
    if (sseConnected) return;

    if (runStatus && isTerminalRunStatus(String(runStatus))) {
      setSseConnected(false);
      return;
    }

    const apiBaseUrl = (process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000").replace(/\/$/, "");
    const sinceParam = lastStreamTimestampRef.current
      ? `&since=${encodeURIComponent(lastStreamTimestampRef.current)}`
      : "";
    const sseUrl = `${apiBaseUrl}/api/runs/${runId}/stream?token=${encodeURIComponent(wsToken)}${sinceParam}`;

    const reconnectDelayMs = getReconnectDelayMs(streamReconnectCount);
    let source: EventSource | null = null;
    let reconnectScheduled = false;
    let closed = false;
    let timeoutId: number | null = null;

    const scheduleReconnect = () => {
      if (reconnectScheduled) return;
      reconnectScheduled = true;
      setStreamReconnectCount((prev) => prev + 1);
    };

    const connect = () => {
      if (closed) return;

      try {
        source = new EventSource(sseUrl);
      } catch {
        setSseConnected(false);
        setSseError("Failed to open SSE stream.");
        scheduleReconnect();
        return;
      }

      setSseError(null);

      source.onopen = () => {
        setSseConnected(true);
        if (streamReconnectCount > 0 && lastStreamTimestampRef.current) {
          setLastReconnectFrom(lastStreamTimestampRef.current);
        }
      };

      source.onerror = () => {
        setSseConnected(false);
        setSseError("SSE error.");
        scheduleReconnect();
        source?.close();
      };

      const handleSseEvent = (event: MessageEvent<string>) => {
        try {
          const parsed = JSON.parse(event.data) as RunsWsMessage;
          handleStreamMessage(parsed);
        } catch {
          return;
        }
      };

      source.addEventListener("run.updated", handleSseEvent);
      source.addEventListener("node_run.updated", handleSseEvent);
      source.addEventListener("node_stream.chunk", handleSseEvent);
      source.addEventListener("connected", () => setSseConnected(true));
      source.onmessage = handleSseEvent;
    };

    timeoutId = window.setTimeout(connect, reconnectDelayMs);

    return () => {
      closed = true;
      if (timeoutId) {
        window.clearTimeout(timeoutId);
      }
      source?.close();
      setSseConnected(false);
    };
  }, [
    runId,
    wsToken,
    wsConnected,
    sseConnected,
    runStatus,
    handleStreamMessage,
    streamReconnectCount,
  ]);

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

  const selectedNodeStreamText = useMemo(() => {
    if (!selectedNodeRun) return "";
    return (
      nodeStreamText[getNodeAttemptKey(selectedNodeRun.node_id, selectedNodeRun.attempt)] ?? ""
    );
  }, [selectedNodeRun, nodeStreamText]);

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

  const canReplay = runStatus ? isTerminalRunStatus(String(runStatus)) : false;

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
                    Live updates: {wsConnected ? "websocket" : sseConnected ? "sse" : "polling"}
                    {wsError ? ` (${wsError})` : ""}
                    {lastReconnectFrom && (wsConnected || sseConnected) ? (
                      <span className="ml-2 text-xs text-muted-foreground">
                        Reconnected from {formatDateTime(lastReconnectFrom)}
                      </span>
                    ) : null}
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
                    disabled={loading || isRefreshing || isCanceling || isRerunning || isReplaying}
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
                {run && canReplay && (
                  <Button
                    variant="outline"
                    onClick={() => void replayRun()}
                    disabled={loading || isRefreshing || isCanceling || isRerunning || isReplaying}
                  >
                    {isReplaying ? (
                      <>
                        <Spinner size="xs" className="mr-2" />
                        Replaying...
                      </>
                    ) : (
                      "Replay from checkpoint"
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
                      {hideRunStatusText ? null : getRunStatusLabel(run)}
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
                  {String(run.status) === "pending" && run.queue_status && (
                    <div className="mt-4 rounded-lg border border-border/50 bg-muted/40 p-3">
                      <p className="text-xs font-medium text-muted-foreground uppercase">Queue status</p>
                      <div className="mt-1 flex flex-wrap items-center gap-3 text-sm text-muted-foreground">
                        <span className="capitalize">{run.queue_status}</span>
                        {typeof run.queue_attempts === "number" && (
                          <span>Attempts: {run.queue_attempts}</span>
                        )}
                        {run.queue_available_at && (
                          <span>Next check: {formatDateTime(run.queue_available_at)}</span>
                        )}
                      </div>
                    </div>
                  )}

                  {run.error_message && (String(run.status) === "failed" || String(run.status) === "canceled") && (
                    <div className="mt-4 rounded-lg border border-destructive/20 bg-destructive/5 p-3">
                      <p className="text-xs font-medium text-destructive uppercase">Run message</p>
                      <p className="mt-1 text-sm text-destructive whitespace-pre-wrap">{run.error_message}</p>
                    </div>
                  )}

                  {error && <p className="mt-4 text-sm text-destructive">Error: {error}</p>}
                </CardContent>
              </Card>

              {/* Human Gate Approval UI */}
              {String(run.status) === "paused" && run.paused_node_id && (
                <Card id="approval" className="border-amber-500/30 bg-amber-500/5 backdrop-blur-sm">
                  <CardHeader>
                    <CardTitle className="flex flex-wrap items-center justify-between gap-3">
                      <div className="flex items-center gap-2 text-amber-800 dark:text-amber-200">
                        <StatusIcon status="paused" />
                        <span>Waiting for Approval</span>
                      </div>
                      <Badge variant="outline" className="border-amber-500/30 bg-amber-500/10 text-amber-800 dark:text-amber-200">
                        Action required
                      </Badge>
                    </CardTitle>
                  </CardHeader>
                  <CardContent className="space-y-4">
                    {/* Prompt message */}
                    {run.pause_payload?.prompt_message && (
                      <div className="rounded-lg bg-background/50 p-4 border border-amber-500/20">
                        <p className="text-sm">{run.pause_payload.prompt_message}</p>
                      </div>
                    )}

                    {/* Node info */}
                    <div className="text-sm text-muted-foreground">
                      Paused at node: <span className="font-mono">{run.pause_payload?.node_name ?? run.paused_node_id}</span>
                    </div>

                    {/* Context */}
                    {latestSucceededNodeRun && latestSucceededNodeOutputText && (
                      <details className="rounded-lg border border-border/50 bg-background/50 p-3">
                        <summary className="cursor-pointer select-none text-sm font-medium text-foreground">
                          Show context (latest node output)
                        </summary>
                        <div className="mt-3 space-y-2">
                          <p className="text-xs text-muted-foreground">
                            From: <span className="font-mono">{formatNodeLabel(latestSucceededNodeRun)}</span>
                          </p>
                          <pre className="p-3 bg-muted rounded-md border border-border/50 overflow-auto max-h-[30vh] text-xs font-mono whitespace-pre-wrap">
                            {latestSucceededNodeOutputText}
                          </pre>
                        </div>
                      </details>
                    )}

                    {/* Required fields */}
                    {run.pause_payload?.required_fields && run.pause_payload.required_fields.length > 0 && (
                      <div className="space-y-3">
                        <p className="text-sm font-medium">Required fields</p>
                        {run.pause_payload.required_fields.map((field) => (
                          <div key={field}>
                            <label className="block text-xs font-medium text-muted-foreground mb-1">
                              {field}
                            </label>
                            {/\b(draft|email|body|message|json|data|content|output)\b/i.test(field) ? (
                              <Textarea
                                value={approvalFields[field] ?? ""}
                                onChange={(e) => setApprovalFields((prev) => ({ ...prev, [field]: e.target.value }))}
                                placeholder={`Enter ${field}...`}
                                rows={5}
                                className="text-sm"
                              />
                            ) : (
                              <Input
                                value={approvalFields[field] ?? ""}
                                onChange={(e) => setApprovalFields((prev) => ({ ...prev, [field]: e.target.value }))}
                                placeholder={`Enter ${field}...`}
                                className="text-sm"
                              />
                            )}
                          </div>
                        ))}
                      </div>
                    )}

                    {/* Feedback for rejection */}
                    <div>
                      <label className="block text-xs font-medium text-muted-foreground mb-1">
                        Feedback (optional for approval, recommended for rejection)
                      </label>
                      <Textarea
                        value={approvalFeedback}
                        onChange={(e) => setApprovalFeedback(e.target.value)}
                        placeholder="Add feedback or reason..."
                        rows={2}
                        className="text-sm"
                      />
                    </div>

                    {/* Action buttons */}
                    <div className="flex gap-3 pt-2">
                      <Button
                        onClick={() => void resumeRun(true)}
                        disabled={isApproving || isRejecting}
                        className="bg-emerald-600 hover:bg-emerald-700 text-white"
                        aria-label="Approve"
                      >
                        {isApproving ? (
                          <>
                            <Spinner size="xs" className="mr-2" />
                            Approving...
                          </>
                        ) : (
                          "Approve"
                        )}
                      </Button>
                      <ConfirmButton
                        variant="destructive"
                        title="Reject this approval?"
                        description="Rejecting will stop the workflow and mark the run as failed."
                        confirmText="Reject & Fail Run"
                        onConfirm={() => resumeRun(false)}
                        disabled={isApproving || isRejecting}
                      >
                        {isRejecting ? (
                          <>
                            <Spinner size="xs" className="mr-2" />
                            Rejecting...
                          </>
                        ) : (
                          "Reject"
                        )}
                      </ConfirmButton>
                    </div>
                  </CardContent>
                </Card>
              )}

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
                          {selectedNodeRun.node_type === "prompt" &&
                          !selectedNodeRun.output_json &&
                          selectedNodeStreamText ? (
                            <pre className="mt-2 p-4 bg-muted rounded-lg border border-border/50 overflow-auto max-h-[45vh] text-sm font-mono whitespace-pre-wrap">
                              {selectedNodeStreamText}
                              {String(selectedNodeRun.status) === "running" && (
                                <span className="inline-block animate-pulse">▍</span>
                              )}
                            </pre>
                          ) : (
                            <pre className="mt-2 p-4 bg-muted rounded-lg border border-border/50 overflow-auto max-h-[45vh] text-sm font-mono whitespace-pre-wrap">
                              {formatJsonForDisplay(selectedNodeRun.output_json)}
                            </pre>
                          )}
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
