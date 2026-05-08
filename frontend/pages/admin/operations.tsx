import { useCallback, useEffect, useMemo, useState } from "react";
import Link from "next/link";
import { AlertTriangle, ArrowRight, BrainCircuit, Download, FileJson, HardDriveDownload } from "lucide-react";

import DashboardLayout from "../../components/DashboardLayout";
import ProtectedRoute from "../../components/ProtectedRoute";
import { useAuth } from "../../contexts/AuthContext";
import {
  analyticsApi,
  getApiErrorMessage,
  healthApi,
  metricsApi,
  operatorApi,
  policiesApi,
  retentionApi,
  type MemoryAnalyticsPerformance,
  type MemoryAnalyticsUsage,
  type MemoryHealthResponse,
  type MetricsSummary,
  type OperatorDeadLetters,
  type OperatorOrgLoad,
  type OperatorRunState,
  type OperatorRuntimeIntentBacklog,
  type OperatorWebSocketSubscribers,
  type RetentionCleanupPreview,
  type RetentionExportType,
  type TenantGuardrailPolicy,
  type TenantRetentionPolicyResponse,
} from "../../lib/api";
import {
  Alert,
  AlertDescription,
  Badge,
  Button,
  Card,
  CardContent,
  CardDescription,
  CardHeader,
  CardTitle,
  Spinner,
} from "@/components/ui";

type OperationsData = {
  policy: TenantGuardrailPolicy;
  retention: TenantRetentionPolicyResponse;
  memoryUsage: MemoryAnalyticsUsage;
  memoryPerformance: MemoryAnalyticsPerformance;
  memoryHealth: MemoryHealthResponse;
  metricsSummary: MetricsSummary;
};

type RecoveryData = {
  backlog: OperatorRuntimeIntentBacklog;
  deadLetters: OperatorDeadLetters;
  orgLoad: OperatorOrgLoad;
  wsSubscribers: OperatorWebSocketSubscribers;
};

type ExportAction = {
  key: string;
  label: string;
  description: string;
  type?: RetentionExportType;
  kind: "retention" | "memory_report";
};

const EXPORT_ACTIONS: ExportAction[] = [
  {
    key: "runs",
    label: "Operation traces",
    description: "Redacted operation-level payloads for support review.",
    type: "runs",
    kind: "retention",
  },
  {
    key: "node-runs",
    label: "Node responses",
    description: "Per-node inputs, outputs, and failures.",
    type: "node_runs",
    kind: "retention",
  },
  {
    key: "audit",
    label: "Audit trail",
    description: "Governance trail for tenant actions and retention changes.",
    type: "audit_logs",
    kind: "retention",
  },
  {
    key: "usage",
    label: "Usage rows",
    description: "LLM usage rows scoped to the current tenant.",
    type: "usage",
    kind: "retention",
  },
  {
    key: "memory-usage",
    label: "Memory usage rows",
    description: "Curated-memory summarization and memory usage rows.",
    type: "memory_usage",
    kind: "retention",
  },
  {
    key: "memory-report",
    label: "Memory report",
    description: "Observation counts, indexing posture, and retention summary.",
    kind: "memory_report",
  },
];

const formatDateTime = (value: string | null | undefined) => {
  if (!value) {
    return "Not recorded";
  }
  const parsed = new Date(value);
  if (Number.isNaN(parsed.getTime())) {
    return value;
  }
  return parsed.toLocaleString();
};

const formatDays = (value: number | null) => {
  if (value == null) {
    return "Manual / not set";
  }
  return `${value} days`;
};

const formatSreValue = (value: unknown, unit: string) => {
  if (value === null || value === undefined) {
    return "No data";
  }
  if (Array.isArray(value)) {
    if (unit === "usd") {
      const total = value.reduce(
        (sum, item) => sum + Number((item as { total_cost_usd?: number }).total_cost_usd ?? 0),
        0,
      );
      return new Intl.NumberFormat("en-US", { style: "currency", currency: "USD", maximumFractionDigits: 2 }).format(
        total,
      );
    }
    return `${value.length} rows`;
  }
  if (typeof value === "object") {
    const entries = Object.entries(value as Record<string, unknown>);
    if (entries.length === 0) {
      return "None";
    }
    return entries
      .slice(0, 3)
      .map(([key, item]) => `${key}: ${String(item)}`)
      .join(" · ");
  }
  if (typeof value === "number") {
    if (unit === "ratio") {
      return `${Math.round(value * 1000) / 10}%`;
    }
    if (unit === "ms") {
      return `${Math.round(value)} ms`;
    }
    if (unit === "seconds") {
      return `${Math.round(value)}s`;
    }
    if (unit === "per_minute") {
      return `${Math.round(value * 10) / 10}/min`;
    }
    if (unit === "usd") {
      return new Intl.NumberFormat("en-US", { style: "currency", currency: "USD", maximumFractionDigits: 2 }).format(
        value,
      );
    }
    return new Intl.NumberFormat("en-US").format(value);
  }
  return String(value);
};

const downloadBlob = (blob: Blob, filename: string) => {
  const url = URL.createObjectURL(blob);
  const link = document.createElement("a");
  link.href = url;
  link.download = filename;
  link.click();
  URL.revokeObjectURL(url);
};

export default function AdminOperationsPage() {
  const { user } = useAuth();
  const canManage = user?.organization_role === "owner" || user?.organization_role === "admin";

  const [data, setData] = useState<OperationsData | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [cleanupPreview, setCleanupPreview] = useState<RetentionCleanupPreview | null>(null);
  const [previewLoading, setPreviewLoading] = useState(false);
  const [exportingKey, setExportingKey] = useState<string | null>(null);
  const [recoveryData, setRecoveryData] = useState<RecoveryData | null>(null);
  const [recoveryLoading, setRecoveryLoading] = useState(false);
  const [operatorError, setOperatorError] = useState<string | null>(null);
  const [runLookupId, setRunLookupId] = useState("");
  const [inspectedRun, setInspectedRun] = useState<OperatorRunState | null>(null);
  const [operatorReason, setOperatorReason] = useState("");
  const [operatorAction, setOperatorAction] = useState<string | null>(null);

  const loadData = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const [policy, retention, memoryUsage, memoryPerformance, memoryHealth, metricsSummary] = await Promise.all([
        policiesApi.getGuardrails(),
        retentionApi.getPolicy(),
        analyticsApi.getMemoryUsage("30d"),
        analyticsApi.getMemoryPerformance("30d"),
        healthApi.getMemory(),
        metricsApi.getSummary(),
      ]);
      setData({
        policy,
        retention,
        memoryUsage,
        memoryPerformance,
        memoryHealth,
        metricsSummary,
      });
    } catch (err: unknown) {
      setError(getApiErrorMessage(err, "Failed to load operator controls."));
    } finally {
      setLoading(false);
    }
  }, []);

  const loadRecoveryData = useCallback(async () => {
    setRecoveryLoading(true);
    setOperatorError(null);
    try {
      const [backlog, deadLetters, orgLoad, wsSubscribers] = await Promise.all([
        operatorApi.getRuntimeIntentBacklog(),
        operatorApi.getDeadLetters(),
        operatorApi.getOrgLoad(),
        operatorApi.getWebSocketSubscribers(),
      ]);
      setRecoveryData({ backlog, deadLetters, orgLoad, wsSubscribers });
    } catch (err: unknown) {
      setOperatorError(getApiErrorMessage(err, "Failed to load recovery diagnostics."));
    } finally {
      setRecoveryLoading(false);
    }
  }, []);

  useEffect(() => {
    if (!canManage) {
      setLoading(false);
      return;
    }
    void loadData();
    void loadRecoveryData();
  }, [canManage, loadData, loadRecoveryData]);

  const handlePreviewCleanup = useCallback(async () => {
    setPreviewLoading(true);
    try {
      const preview = await retentionApi.previewCleanup();
      setCleanupPreview(preview);
    } catch (err: unknown) {
      setError(getApiErrorMessage(err, "Failed to preview retention cleanup."));
    } finally {
      setPreviewLoading(false);
    }
  }, []);

  const handleExport = useCallback(async (action: ExportAction) => {
    setExportingKey(action.key);
    try {
      const blob =
        action.kind === "memory_report"
          ? await analyticsApi.exportMemoryReport({ format: "json", period: "30d" })
          : await retentionApi.exportData({ type: action.type!, limit: 250 });
      downloadBlob(blob, `forgegraph-${action.key}-${new Date().toISOString().slice(0, 10)}.json`);
    } catch (err: unknown) {
      setError(getApiErrorMessage(err, `Failed to export ${action.label.toLowerCase()}.`));
    } finally {
      setExportingKey(null);
    }
  }, []);

  const handleInspectRun = useCallback(async () => {
    const runId = runLookupId.trim();
    if (!runId) {
      setOperatorError("Enter a run ID to inspect.");
      return;
    }
    setOperatorAction("inspect-run");
    setOperatorError(null);
    try {
      setInspectedRun(await operatorApi.getRunState(runId));
    } catch (err: unknown) {
      setOperatorError(getApiErrorMessage(err, "Failed to inspect run state."));
    } finally {
      setOperatorAction(null);
    }
  }, [runLookupId]);

  const requireOperatorReason = useCallback(() => {
    const reason = operatorReason.trim();
    if (!reason) {
      setOperatorError("Operator recovery actions require a reason.");
      return null;
    }
    return reason;
  }, [operatorReason]);

  const handleRunRecoveryAction = useCallback(
    async (action: "force-fail" | "force-cancel" | "force-rehydrate") => {
      if (!inspectedRun) {
        return;
      }
      const reason = requireOperatorReason();
      if (!reason) {
        return;
      }
      setOperatorAction(action);
      setOperatorError(null);
      try {
        const updated =
          action === "force-fail"
            ? await operatorApi.forceFailRun(inspectedRun.run.id, reason)
            : action === "force-cancel"
              ? await operatorApi.forceCancelRun(inspectedRun.run.id, reason)
              : await operatorApi.forceRehydrateRun(inspectedRun.run.id, reason);
        setInspectedRun(updated);
        await loadRecoveryData();
      } catch (err: unknown) {
        setOperatorError(getApiErrorMessage(err, "Operator recovery action failed."));
      } finally {
        setOperatorAction(null);
      }
    },
    [inspectedRun, loadRecoveryData, requireOperatorReason],
  );

  const handleIntentAction = useCallback(
    async (intentId: string, action: "replay" | "acknowledge") => {
      const reason = requireOperatorReason();
      if (!reason) {
        return;
      }
      setOperatorAction(`${action}:${intentId}`);
      setOperatorError(null);
      try {
        if (action === "replay") {
          await operatorApi.replayIntent(intentId, reason);
        } else {
          await operatorApi.acknowledgeIntent(intentId, reason);
        }
        await loadRecoveryData();
      } catch (err: unknown) {
        setOperatorError(getApiErrorMessage(err, "Runtime intent recovery action failed."));
      } finally {
        setOperatorAction(null);
      }
    },
    [loadRecoveryData, requireOperatorReason],
  );

  const handleEventDeadLetterAction = useCallback(
    async (deadLetterId: string, action: "replay" | "acknowledge") => {
      const reason = requireOperatorReason();
      if (!reason) {
        return;
      }
      setOperatorAction(`event-${action}:${deadLetterId}`);
      setOperatorError(null);
      try {
        if (action === "replay") {
          await operatorApi.replayEventDeadLetter(deadLetterId, reason);
        } else {
          await operatorApi.acknowledgeEventDeadLetter(deadLetterId, reason);
        }
        await loadRecoveryData();
      } catch (err: unknown) {
        setOperatorError(getApiErrorMessage(err, "Event dead-letter recovery action failed."));
      } finally {
        setOperatorAction(null);
      }
    },
    [loadRecoveryData, requireOperatorReason],
  );

  const healthItems = useMemo(() => {
    if (!data) {
      return [];
    }

    const items = [
      {
        label: "Redis cache",
        state: data.memoryHealth.redis.healthy ? "healthy" : "degraded",
        detail: `${data.memoryHealth.redis.latency_ms} ms latency`,
      },
      {
        label: "Memory gRPC",
        state: data.memoryHealth.grpc?.configured
          ? data.memoryHealth.grpc.healthy
            ? "healthy"
            : "degraded"
          : "unconfigured",
        detail: data.memoryHealth.grpc?.configured
          ? data.memoryHealth.grpc.healthy
            ? "Serving"
            : (data.memoryHealth.grpc.error ?? "Unavailable")
          : "Not configured in this environment",
      },
      {
        label: "Indexing backlog",
        state: data.memoryPerformance.indexing.pending_observations_total > 0 ? "attention" : "healthy",
        detail: `${data.memoryPerformance.indexing.pending_observations_total} observations pending`,
      },
      {
        label: "Queue depth",
        state: data.metricsSummary.violations.queue_depth ? "attention" : "healthy",
        detail: `${data.metricsSummary.queue.total_depth} queued runs`,
      },
    ];

    return items;
  }, [data]);

  const riskNotices = useMemo(() => {
    if (!data) {
      return [];
    }

    const notices: string[] = [];
    if (data.policy.summary.runtime_mode === "cloud") {
      notices.push("Cloud mode can still deny exec-tool behavior even when a graph requests it.");
    }
    if (data.policy.summary.http_access_mode === "default_deny") {
      notices.push("HTTP egress is default-deny. External calls must match the tenant allowlist.");
    }
    if (!data.policy.summary.curated_memory_vector_indexing_enabled) {
      notices.push("Vector indexing is disabled. Curated-memory retrieval will rely on non-vector paths.");
    }
    if (data.memoryPerformance.indexing.pending_observations_total > 0) {
      notices.push("Observation indexing is backlogged. Memory-backed runs can degrade until indexing catches up.");
    }
    if (data.metricsSummary.violations.queue_depth) {
      notices.push("Queue depth is above the target. Operators should expect slower operation starts.");
    }
    if (data.metricsSummary.sre?.alerts.active_total) {
      notices.push(`${data.metricsSummary.sre.alerts.active_total} SRE alert(s) are active in the current SLO window.`);
    }
    const missingSloData =
      data.metricsSummary.sre?.objectives.filter((objective) => objective.missing_data).length ?? 0;
    if (missingSloData > 0) {
      notices.push(`${missingSloData} SLO signal(s) have no data yet; do not treat them as passing.`);
    }
    return notices;
  }, [data]);

  const sreSummary = data?.metricsSummary.sre ?? null;
  const breachingSloCount = sreSummary?.objectives.filter((objective) => objective.status === "breaching").length ?? 0;
  const missingSloCount = sreSummary?.objectives.filter((objective) => objective.missing_data).length ?? 0;
  const eventDeadLetters = recoveryData?.deadLetters.event_dead_letters ?? [];
  const runtimeIntentDeadLetters = recoveryData?.deadLetters.runtime_intent_outcomes ?? [];
  const activeEventDeadLetterCount = eventDeadLetters.filter(
    (item) => item.status === "active" || item.status === "replay_requested",
  ).length;
  const taskDeadLetterCount = recoveryData?.orgLoad.dead_letters ?? 0;
  const runtimeIntentDeadLetterCount = recoveryData?.backlog.dead_letter_count ?? 0;
  const eventDeadLetterCount = recoveryData?.orgLoad.event_dead_letters ?? activeEventDeadLetterCount;
  const totalDeadLetterCount = taskDeadLetterCount + runtimeIntentDeadLetterCount + eventDeadLetterCount;

  if (!canManage) {
    return (
      <ProtectedRoute>
        <DashboardLayout>
          <div className="mx-auto max-w-3xl py-8">
            <Alert variant="destructive">
              <AlertDescription>
                You do not have access to manage policies, retention, or support exports.
              </AlertDescription>
            </Alert>
          </div>
        </DashboardLayout>
      </ProtectedRoute>
    );
  }

  return (
    <ProtectedRoute>
      <DashboardLayout>
        <div className="flex flex-col gap-6">
          <section className="relative overflow-hidden rounded-[2rem] border border-border/50 bg-card/80 p-6 shadow-lg backdrop-blur-sm sm:p-8">
            <div
              className="pointer-events-none absolute inset-0 opacity-90"
              style={{
                backgroundImage:
                  "radial-gradient(circle at 0% 0%, rgba(56, 189, 248, 0.18), transparent 36%), radial-gradient(circle at 100% 10%, rgba(245, 158, 11, 0.14), transparent 34%), linear-gradient(135deg, rgba(15, 23, 42, 0.08), rgba(255, 255, 255, 0))",
              }}
            />
            <div className="relative flex flex-col gap-5">
              <div className="flex flex-col gap-4 lg:flex-row lg:items-start lg:justify-between">
                <div className="max-w-3xl">
                  <Badge variant="outline" className="mb-4 border-sky-500/30 text-sky-700 dark:text-sky-300">
                    Policies & Operations
                  </Badge>
                  <h1 className="text-3xl font-semibold tracking-tight text-foreground sm:text-4xl">
                    Guardrails, retention, and support exports in one place.
                  </h1>
                  <p className="mt-3 text-sm leading-7 text-muted-foreground sm:text-base">
                    This page is the operator control plane for what gets blocked, what gets retained, and what can be
                    exported safely when a tenant needs support.
                  </p>
                </div>
                <div className="flex flex-wrap gap-2">
                  <Button asChild variant="outline">
                    <Link href="/admin/help">
                      Operator help
                      <ArrowRight className="ml-2 h-4 w-4" aria-hidden="true" />
                    </Link>
                  </Button>
                  <Button asChild variant="outline">
                    <Link href="/admin/audit-logs">
                      Audit trail
                      <ArrowRight className="ml-2 h-4 w-4" aria-hidden="true" />
                    </Link>
                  </Button>
                  <Button asChild variant="outline">
                    <Link href="/analytics/memory">
                      Memory analytics
                      <ArrowRight className="ml-2 h-4 w-4" aria-hidden="true" />
                    </Link>
                  </Button>
                  <Button asChild variant="outline">
                    <Link href="/memory">
                      Memory browser
                      <ArrowRight className="ml-2 h-4 w-4" aria-hidden="true" />
                    </Link>
                  </Button>
                </div>
              </div>

              {data && (
                <div className="flex flex-wrap gap-2">
                  <Badge variant="outline">Runtime: {data.policy.summary.runtime_mode}</Badge>
                  <Badge variant="outline">HTTP: {data.policy.summary.http_access_mode.replace(/_/g, " ")}</Badge>
                  <Badge variant="outline">
                    Indexing: {data.policy.summary.curated_memory_vector_indexing_enabled ? "enabled" : "disabled"}
                  </Badge>
                  <Badge variant="outline">Queue: {data.metricsSummary.queue.total_depth} waiting</Badge>
                </div>
              )}
            </div>
          </section>

          {error && (
            <Alert variant="destructive">
              <AlertDescription>{error}</AlertDescription>
            </Alert>
          )}

          {loading ? (
            <div className="flex items-center gap-2 text-muted-foreground">
              <Spinner className="h-5 w-5" />
              Loading operator controls…
            </div>
          ) : data ? (
            <>
              {riskNotices.length > 0 && (
                <Alert className="border-amber-500/30 bg-amber-500/10 text-amber-900 dark:text-amber-100">
                  <AlertTriangle className="h-4 w-4" />
                  <AlertDescription className="space-y-2">
                    {riskNotices.map((notice) => (
                      <p key={notice}>{notice}</p>
                    ))}
                  </AlertDescription>
                </Alert>
              )}

              {operatorError && (
                <Alert variant="destructive">
                  <AlertDescription>{operatorError}</AlertDescription>
                </Alert>
              )}

              {sreSummary && (
                <Card className="border-border/60 bg-card/70 backdrop-blur-sm">
                  <CardHeader>
                    <CardTitle>Production SLOs and SRE alerts</CardTitle>
                    <CardDescription>
                      Backend-owned SLO evidence, dashboard signals, and alert state from the current evaluation window.
                    </CardDescription>
                  </CardHeader>
                  <CardContent className="space-y-5">
                    <div className="grid gap-3 md:grid-cols-4">
                      <div className="rounded-xl border border-border/50 bg-background/70 p-4">
                        <p className="text-xs uppercase tracking-[0.2em] text-muted-foreground">Release tier</p>
                        <p className="mt-2 text-2xl font-semibold text-foreground">{sreSummary.release_tier}</p>
                        <p className="mt-2 text-sm text-muted-foreground">
                          {Math.round(sreSummary.window_seconds / 60)} minute window
                        </p>
                      </div>
                      <div className="rounded-xl border border-border/50 bg-background/70 p-4">
                        <p className="text-xs uppercase tracking-[0.2em] text-muted-foreground">Breaching SLOs</p>
                        <p className="mt-2 text-2xl font-semibold text-foreground">{breachingSloCount}</p>
                        <p className="mt-2 text-sm text-muted-foreground">Targets come from production-slos.yaml.</p>
                      </div>
                      <div className="rounded-xl border border-border/50 bg-background/70 p-4">
                        <p className="text-xs uppercase tracking-[0.2em] text-muted-foreground">Active alerts</p>
                        <p className="mt-2 text-2xl font-semibold text-foreground">{sreSummary.alerts.active_total}</p>
                        <p className="mt-2 text-sm text-muted-foreground">Repo-native alert evaluation.</p>
                      </div>
                      <div className="rounded-xl border border-border/50 bg-background/70 p-4">
                        <p className="text-xs uppercase tracking-[0.2em] text-muted-foreground">Missing signals</p>
                        <p className="mt-2 text-2xl font-semibold text-foreground">{missingSloCount}</p>
                        <p className="mt-2 text-sm text-muted-foreground">Missing data is never treated as healthy.</p>
                      </div>
                    </div>

                    <div className="grid gap-4 xl:grid-cols-[1fr_0.9fr]">
                      <div className="rounded-xl border border-border/50 bg-background/70 p-4">
                        <div className="flex items-center justify-between gap-3">
                          <div>
                            <p className="font-medium text-foreground">SLO objectives</p>
                            <p className="text-sm text-muted-foreground">
                              Production readiness targets and current state.
                            </p>
                          </div>
                          <Badge variant="outline">{sreSummary.objectives.length} objectives</Badge>
                        </div>
                        <div className="mt-4 grid gap-3 md:grid-cols-2">
                          {sreSummary.objectives.map((objective) => (
                            <div key={objective.id} className="rounded-lg border border-border/50 bg-card/70 p-3">
                              <div className="flex items-start justify-between gap-3">
                                <div>
                                  <p className="text-sm font-medium">{objective.title}</p>
                                  <p className="mt-1 text-xs text-muted-foreground">
                                    {formatSreValue(objective.actual, objective.unit)} / target{" "}
                                    {formatSreValue(objective.target, objective.unit)}
                                  </p>
                                </div>
                                <Badge
                                  variant="outline"
                                  className={
                                    objective.status === "passing"
                                      ? "border-emerald-500/30 text-emerald-700 dark:text-emerald-300"
                                      : objective.status === "breaching"
                                        ? "border-destructive/30 text-destructive"
                                        : "border-amber-500/30 text-amber-800 dark:text-amber-200"
                                  }
                                >
                                  {objective.status.replace(/_/g, " ")}
                                </Badge>
                              </div>
                              <p className="mt-2 text-xs text-muted-foreground">
                                Source: {objective.source} · samples {objective.observed_count}
                              </p>
                            </div>
                          ))}
                        </div>
                      </div>

                      <div className="rounded-xl border border-border/50 bg-background/70 p-4">
                        <p className="font-medium text-foreground">Active alert state</p>
                        <div className="mt-4 space-y-3">
                          {sreSummary.alerts.items
                            .filter((alert) => alert.state !== "ok")
                            .map((alert) => (
                              <div key={alert.id} className="rounded-lg border border-border/50 bg-card/70 p-3">
                                <div className="flex items-center justify-between gap-3">
                                  <p className="text-sm font-medium">{alert.title}</p>
                                  <Badge
                                    variant="outline"
                                    className={
                                      alert.state === "active"
                                        ? "border-destructive/30 text-destructive"
                                        : "border-amber-500/30 text-amber-800 dark:text-amber-200"
                                    }
                                  >
                                    {alert.state.replace(/_/g, " ")}
                                  </Badge>
                                </div>
                                <p className="mt-2 text-xs text-muted-foreground">{alert.runbook}</p>
                              </div>
                            ))}
                          {sreSummary.alerts.items.every((alert) => alert.state === "ok") ? (
                            <p className="rounded-lg border border-border/50 bg-card/70 p-4 text-sm text-muted-foreground">
                              No SRE alerts are active in the current window.
                            </p>
                          ) : null}
                        </div>
                      </div>
                    </div>

                    <div className="rounded-xl border border-border/50 bg-background/70 p-4">
                      <p className="font-medium text-foreground">Dashboard signals</p>
                      <div className="mt-4 grid gap-3 md:grid-cols-3 xl:grid-cols-4">
                        {sreSummary.dashboard_panels.map((panel) => (
                          <div key={panel.id} className="rounded-lg border border-border/50 bg-card/70 p-3">
                            <p className="text-xs uppercase tracking-[0.16em] text-muted-foreground">{panel.title}</p>
                            <p className="mt-2 text-sm font-semibold text-foreground">
                              {formatSreValue(panel.value, panel.unit)}
                            </p>
                            {panel.missing_data ? (
                              <p className="mt-1 text-xs text-amber-700 dark:text-amber-200">No data configured</p>
                            ) : null}
                          </div>
                        ))}
                      </div>
                    </div>
                  </CardContent>
                </Card>
              )}

              <Card className="border-border/60 bg-card/70 backdrop-blur-sm">
                <CardHeader>
                  <CardTitle role="heading" aria-level={2}>
                    Recovery controls
                  </CardTitle>
                  <CardDescription>
                    Backend-owned state, retry backlog, dead letters, and live connection counts for stuck-company
                    inspection.
                  </CardDescription>
                </CardHeader>
                <CardContent className="space-y-5">
                  <div className="grid gap-3 md:grid-cols-4">
                    <div className="rounded-xl border border-border/50 bg-background/70 p-4">
                      <p className="text-xs uppercase tracking-[0.2em] text-muted-foreground">Intent backlog</p>
                      <p className="mt-2 text-2xl font-semibold text-foreground">
                        {recoveryData?.backlog.backlog ?? 0}
                      </p>
                      <p className="mt-2 text-sm text-muted-foreground">
                        Pending {recoveryData?.backlog.pending ?? 0} · lag {recoveryData?.backlog.lag ?? 0}
                      </p>
                    </div>
                    <div className="rounded-xl border border-border/50 bg-background/70 p-4">
                      <p className="text-xs uppercase tracking-[0.2em] text-muted-foreground">Dead letters</p>
                      <p className="mt-2 text-2xl font-semibold text-foreground">{totalDeadLetterCount}</p>
                      <p className="mt-2 text-sm text-muted-foreground">
                        {eventDeadLetterCount} event · {runtimeIntentDeadLetterCount} runtime intent
                      </p>
                    </div>
                    <div className="rounded-xl border border-border/50 bg-background/70 p-4">
                      <p className="text-xs uppercase tracking-[0.2em] text-muted-foreground">WebSocket clients</p>
                      <p className="mt-2 text-2xl font-semibold text-foreground">
                        {recoveryData?.wsSubscribers.total ?? 0}
                      </p>
                      <p className="mt-2 text-sm text-muted-foreground">
                        {Object.keys(recoveryData?.wsSubscribers.by_run ?? {}).length} runs subscribed
                      </p>
                    </div>
                    <div className="rounded-xl border border-border/50 bg-background/70 p-4">
                      <p className="text-xs uppercase tracking-[0.2em] text-muted-foreground">Retry operations</p>
                      <p className="mt-2 text-2xl font-semibold text-foreground">
                        {(recoveryData?.orgLoad.retry_operations ?? []).reduce((sum, item) => sum + item.count, 0)}
                      </p>
                      <p className="mt-2 text-sm text-muted-foreground">Bounded and inspectable.</p>
                    </div>
                  </div>

                  <div className="grid gap-4 xl:grid-cols-[0.95fr_1.05fr]">
                    <div className="rounded-xl border border-border/50 bg-background/70 p-4">
                      <div className="flex flex-col gap-3 sm:flex-row">
                        <input
                          value={runLookupId}
                          onChange={(event) => setRunLookupId(event.target.value)}
                          placeholder="Run ID"
                          className="min-h-10 flex-1 rounded-md border border-border bg-background px-3 text-sm outline-none focus:ring-2 focus:ring-ring"
                        />
                        <Button
                          variant="outline"
                          onClick={() => void handleInspectRun()}
                          disabled={operatorAction === "inspect-run"}
                        >
                          {operatorAction === "inspect-run" ? <Spinner size="xs" className="mr-2" /> : null}
                          Inspect run
                        </Button>
                      </div>
                      <textarea
                        value={operatorReason}
                        onChange={(event) => setOperatorReason(event.target.value)}
                        placeholder="Operator reason required for replay, acknowledgement, force fail, force cancel, and rehydrate."
                        className="mt-3 min-h-20 w-full rounded-md border border-border bg-background px-3 py-2 text-sm outline-none focus:ring-2 focus:ring-ring"
                      />

                      {inspectedRun ? (
                        <div className="mt-4 space-y-3">
                          <div className="grid gap-3 md:grid-cols-2">
                            <div className="rounded-lg border border-border/50 bg-card/70 p-3">
                              <p className="text-xs uppercase tracking-[0.2em] text-muted-foreground">Status</p>
                              <p className="mt-2 font-semibold">{inspectedRun.run.status}</p>
                              <p className="mt-1 text-sm text-muted-foreground">
                                Attempt {inspectedRun.run.current_attempt ?? "unknown"}
                              </p>
                            </div>
                            <div className="rounded-lg border border-border/50 bg-card/70 p-3">
                              <p className="text-xs uppercase tracking-[0.2em] text-muted-foreground">Blocked work</p>
                              <p className="mt-2 font-semibold">
                                {inspectedRun.active_tasks.length} active · {inspectedRun.dead_letter_count} dead
                              </p>
                              <p className="mt-1 text-sm text-muted-foreground">
                                {inspectedRun.pending_decisions.length} pending decisions
                              </p>
                            </div>
                          </div>
                          <div className="grid gap-2 sm:grid-cols-3">
                            <Button
                              variant="outline"
                              onClick={() => void handleRunRecoveryAction("force-fail")}
                              disabled={operatorAction === "force-fail"}
                            >
                              Force fail
                            </Button>
                            <Button
                              variant="outline"
                              onClick={() => void handleRunRecoveryAction("force-cancel")}
                              disabled={operatorAction === "force-cancel"}
                            >
                              Force cancel
                            </Button>
                            <Button
                              variant="outline"
                              onClick={() => void handleRunRecoveryAction("force-rehydrate")}
                              disabled={operatorAction === "force-rehydrate"}
                            >
                              Rehydrate
                            </Button>
                          </div>
                          <div className="max-h-56 overflow-auto rounded-lg border border-border/50">
                            {inspectedRun.tasks.map((task) => (
                              <div
                                key={task.id}
                                className="flex items-start justify-between gap-3 border-b border-border/40 px-3 py-2 last:border-b-0"
                              >
                                <div>
                                  <p className="text-sm font-medium">{task.title}</p>
                                  <p className="text-xs text-muted-foreground">
                                    {task.status} · attempt {task.current_attempt}
                                    {task.unresolved_error ? ` · ${task.unresolved_error}` : ""}
                                  </p>
                                </div>
                                <Badge variant="outline">{task.priority}</Badge>
                              </div>
                            ))}
                          </div>
                        </div>
                      ) : null}
                    </div>

                    <div className="rounded-xl border border-border/50 bg-background/70 p-4">
                      <div className="mb-3 flex items-center justify-between gap-3">
                        <div>
                          <p className="font-medium text-foreground">Dead-letter recovery</p>
                          <p className="text-sm text-muted-foreground">
                            Event ingestion failures, runtime intent poison messages, and audited operator recovery.
                          </p>
                        </div>
                        <Button variant="outline" onClick={() => void loadRecoveryData()} disabled={recoveryLoading}>
                          {recoveryLoading ? <Spinner size="xs" className="mr-2" /> : null}
                          Refresh
                        </Button>
                      </div>
                      <div className="max-h-80 space-y-3 overflow-auto pr-1">
                        {eventDeadLetters.slice(0, 8).map((deadLetter) => (
                          <div key={deadLetter.id} className="rounded-lg border border-border/50 bg-card/70 p-3">
                            <div className="flex items-start justify-between gap-3">
                              <div className="min-w-0">
                                <p className="truncate text-sm font-medium">
                                  {deadLetter.event_type || "unknown event"}
                                </p>
                                <p className="mt-1 text-xs text-muted-foreground">
                                  {deadLetter.reason || deadLetter.error_class || "No reason recorded"}
                                </p>
                                <p className="mt-1 text-xs text-muted-foreground">
                                  Seen {deadLetter.retry_count} time(s) · last {formatDateTime(deadLetter.last_seen_at)}
                                </p>
                              </div>
                              <Badge variant="outline">{deadLetter.status.replace(/_/g, " ")}</Badge>
                            </div>
                            <div className="mt-3 flex flex-wrap gap-2">
                              <Button
                                size="sm"
                                variant="outline"
                                onClick={() => void handleEventDeadLetterAction(deadLetter.id, "replay")}
                                disabled={operatorAction === `event-replay:${deadLetter.id}`}
                              >
                                Request replay
                              </Button>
                              <Button
                                size="sm"
                                variant="outline"
                                onClick={() => void handleEventDeadLetterAction(deadLetter.id, "acknowledge")}
                                disabled={
                                  Boolean(deadLetter.acknowledged_at) ||
                                  operatorAction === `event-acknowledge:${deadLetter.id}`
                                }
                              >
                                Acknowledge
                              </Button>
                            </div>
                          </div>
                        ))}
                        {eventDeadLetters.length === 0 ? (
                          <p className="rounded-lg border border-border/50 bg-card/70 p-4 text-sm text-muted-foreground">
                            No event ingestion dead letters are visible for this organization.
                          </p>
                        ) : null}

                        {runtimeIntentDeadLetters.slice(0, 8).map((outcome) => (
                          <div key={outcome.intent_id} className="rounded-lg border border-border/50 bg-card/70 p-3">
                            <div className="flex items-start justify-between gap-3">
                              <div className="min-w-0">
                                <p className="truncate text-sm font-medium">{outcome.intent_type}</p>
                                <p className="mt-1 text-xs text-muted-foreground">
                                  {outcome.reason || outcome.error_class || "No reason recorded"}
                                </p>
                                <p className="mt-1 text-xs text-muted-foreground">
                                  {outcome.acknowledged_at
                                    ? `Acknowledged ${formatDateTime(outcome.acknowledged_at)}`
                                    : "Unacknowledged"}
                                </p>
                              </div>
                              <Badge variant="outline">{outcome.attempt_id || "no attempt"}</Badge>
                            </div>
                            <div className="mt-3 flex flex-wrap gap-2">
                              <Button
                                size="sm"
                                variant="outline"
                                onClick={() => void handleIntentAction(outcome.intent_id, "replay")}
                                disabled={operatorAction === `replay:${outcome.intent_id}`}
                              >
                                Replay
                              </Button>
                              <Button
                                size="sm"
                                variant="outline"
                                onClick={() => void handleIntentAction(outcome.intent_id, "acknowledge")}
                                disabled={
                                  Boolean(outcome.acknowledged_at) ||
                                  operatorAction === `acknowledge:${outcome.intent_id}`
                                }
                              >
                                Acknowledge
                              </Button>
                            </div>
                          </div>
                        ))}
                        {runtimeIntentDeadLetters.length === 0 ? (
                          <p className="rounded-lg border border-border/50 bg-card/70 p-4 text-sm text-muted-foreground">
                            No runtime intent dead letters are visible for this organization.
                          </p>
                        ) : null}
                      </div>
                    </div>
                  </div>
                </CardContent>
              </Card>

              <div className="grid gap-4 xl:grid-cols-2">
                <Card className="border-border/60 bg-card/70 backdrop-blur-sm">
                  <CardHeader>
                    <CardTitle>Guardrail summary</CardTitle>
                    <CardDescription>
                      These summaries are derived from the actual tenant policy plus the current runtime mode.
                    </CardDescription>
                  </CardHeader>
                  <CardContent className="grid gap-3 md:grid-cols-2">
                    <div className="rounded-xl border border-border/50 bg-background/70 p-4">
                      <p className="text-xs uppercase tracking-[0.2em] text-muted-foreground">HTTP egress</p>
                      <p className="mt-2 text-lg font-semibold text-foreground">
                        {data.policy.summary.http_access_mode === "default_deny"
                          ? "Default deny"
                          : data.policy.summary.http_access_mode === "allowlist_first"
                            ? "Allowlist first"
                            : "Open"}
                      </p>
                      <p className="mt-2 text-sm text-muted-foreground">
                        Allowlist: {data.policy.summary.egress_allowlist_count} · Denylist:{" "}
                        {data.policy.summary.egress_denylist_count}
                      </p>
                    </div>
                    <div className="rounded-xl border border-border/50 bg-background/70 p-4">
                      <p className="text-xs uppercase tracking-[0.2em] text-muted-foreground">Runtime mode</p>
                      <p className="mt-2 text-lg font-semibold text-foreground">{data.policy.summary.runtime_mode}</p>
                      <p className="mt-2 text-sm text-muted-foreground">
                        Exec tools are {data.policy.summary.exec_tools_policy.replace(/_/g, " ")}.
                      </p>
                    </div>
                    <div className="rounded-xl border border-border/50 bg-background/70 p-4">
                      <p className="text-xs uppercase tracking-[0.2em] text-muted-foreground">Allowed providers</p>
                      <p className="mt-2 text-lg font-semibold text-foreground">
                        {data.policy.summary.provider_allowlist_count}
                      </p>
                      <p className="mt-2 text-sm text-muted-foreground">
                        {data.policy.allowed_providers.length > 0
                          ? data.policy.allowed_providers.join(", ")
                          : "All configured providers are currently allowed."}
                      </p>
                    </div>
                    <div className="rounded-xl border border-border/50 bg-background/70 p-4">
                      <p className="text-xs uppercase tracking-[0.2em] text-muted-foreground">Allowed models</p>
                      <p className="mt-2 text-lg font-semibold text-foreground">
                        {data.policy.summary.model_allowlist_count}
                      </p>
                      <p className="mt-2 text-sm text-muted-foreground">
                        {data.policy.allowed_models.length > 0
                          ? data.policy.allowed_models.join(", ")
                          : "No model-specific allowlist is set."}
                      </p>
                    </div>
                  </CardContent>
                </Card>

                <Card className="border-border/60 bg-card/70 backdrop-blur-sm">
                  <CardHeader>
                    <CardTitle>Retention and lifecycle</CardTitle>
                    <CardDescription>
                      Operators should be able to explain what data lasts, what is manual, and what a cleanup would
                      remove.
                    </CardDescription>
                  </CardHeader>
                  <CardContent className="space-y-4">
                    <div className="grid gap-3 md:grid-cols-2">
                      <div className="rounded-xl border border-border/50 bg-background/70 p-4">
                        <p className="text-xs uppercase tracking-[0.2em] text-muted-foreground">Runs</p>
                        <p className="mt-2 text-lg font-semibold text-foreground">
                          {formatDays(data.retention.runs_retention_days)}
                        </p>
                      </div>
                      <div className="rounded-xl border border-border/50 bg-background/70 p-4">
                        <p className="text-xs uppercase tracking-[0.2em] text-muted-foreground">Operation logs</p>
                        <p className="mt-2 text-lg font-semibold text-foreground">
                          {formatDays(data.retention.run_logs_retention_days)}
                        </p>
                      </div>
                      <div className="rounded-xl border border-border/50 bg-background/70 p-4">
                        <p className="text-xs uppercase tracking-[0.2em] text-muted-foreground">Audit logs</p>
                        <p className="mt-2 text-lg font-semibold text-foreground">
                          {formatDays(data.retention.audit_logs_retention_days)}
                        </p>
                      </div>
                      <div className="rounded-xl border border-border/50 bg-background/70 p-4">
                        <p className="text-xs uppercase tracking-[0.2em] text-muted-foreground">Usage rows</p>
                        <p className="mt-2 text-lg font-semibold text-foreground">
                          {formatDays(data.retention.usage_retention_days)}
                        </p>
                      </div>
                    </div>

                    <Alert className="border-sky-500/30 bg-sky-500/10 text-sky-800 dark:text-sky-100">
                      <BrainCircuit className="h-4 w-4" />
                      <AlertDescription>{data.memoryUsage.retention.summary}</AlertDescription>
                    </Alert>

                    <div className="flex flex-wrap items-center gap-3">
                      <Button variant="outline" onClick={() => void handlePreviewCleanup()} disabled={previewLoading}>
                        {previewLoading ? (
                          <>
                            <Spinner size="xs" className="mr-2" />
                            Previewing…
                          </>
                        ) : (
                          "Preview cleanup impact"
                        )}
                      </Button>
                      <p className="text-sm text-muted-foreground">
                        Preview only. No data is deleted from this screen.
                      </p>
                    </div>

                    {cleanupPreview && (
                      <div className="grid gap-3 md:grid-cols-3">
                        <div className="rounded-xl border border-border/50 bg-background/70 p-4">
                          <p className="text-xs uppercase tracking-[0.2em] text-muted-foreground">Would delete</p>
                          <p className="mt-2 text-lg font-semibold text-foreground">{cleanupPreview.total_deleted}</p>
                          <p className="mt-2 text-sm text-muted-foreground">Total rows across the current policy.</p>
                        </div>
                        <div className="rounded-xl border border-border/50 bg-background/70 p-4">
                          <p className="text-xs uppercase tracking-[0.2em] text-muted-foreground">Run artifacts</p>
                          <p className="mt-2 text-lg font-semibold text-foreground">
                            {cleanupPreview.runs_deleted + cleanupPreview.run_logs_deleted}
                          </p>
                          <p className="mt-2 text-sm text-muted-foreground">
                            Operations plus operation logs that are past retention.
                          </p>
                        </div>
                        <div className="rounded-xl border border-border/50 bg-background/70 p-4">
                          <p className="text-xs uppercase tracking-[0.2em] text-muted-foreground">Usage & audit</p>
                          <p className="mt-2 text-lg font-semibold text-foreground">
                            {cleanupPreview.audit_logs_deleted +
                              cleanupPreview.llm_usage_deleted +
                              cleanupPreview.memory_usage_deleted}
                          </p>
                          <p className="mt-2 text-sm text-muted-foreground">
                            Audit logs and usage rows that exceed retention.
                          </p>
                        </div>
                      </div>
                    )}
                  </CardContent>
                </Card>
              </div>

              <div className="grid gap-4 xl:grid-cols-[1.05fr_0.95fr]">
                <Card className="border-border/60 bg-card/70 backdrop-blur-sm">
                  <CardHeader>
                    <CardTitle>Support-safe exports</CardTitle>
                    <CardDescription>
                      These exports stay tenant-scoped and use the API’s existing redaction behavior.
                    </CardDescription>
                  </CardHeader>
                  <CardContent className="grid gap-3 md:grid-cols-2">
                    {EXPORT_ACTIONS.map((action) => (
                      <div key={action.key} className="rounded-xl border border-border/50 bg-background/70 p-4">
                        <div className="flex items-start justify-between gap-3">
                          <div>
                            <p className="font-medium text-foreground">{action.label}</p>
                            <p className="mt-1 text-sm text-muted-foreground">{action.description}</p>
                          </div>
                          <FileJson className="h-5 w-5 text-muted-foreground" aria-hidden="true" />
                        </div>
                        <Button
                          variant="outline"
                          className="mt-4 w-full justify-between"
                          onClick={() => void handleExport(action)}
                          disabled={exportingKey === action.key}
                        >
                          {exportingKey === action.key ? (
                            <>
                              <span className="inline-flex items-center">
                                <Spinner size="xs" className="mr-2" />
                                Exporting…
                              </span>
                              <HardDriveDownload className="h-4 w-4" aria-hidden="true" />
                            </>
                          ) : (
                            <>
                              <span>Download JSON</span>
                              <Download className="h-4 w-4" aria-hidden="true" />
                            </>
                          )}
                        </Button>
                      </div>
                    ))}
                  </CardContent>
                </Card>

                <Card className="border-border/60 bg-card/70 backdrop-blur-sm">
                  <CardHeader>
                    <CardTitle>Health and diagnostics</CardTitle>
                    <CardDescription>
                      Use these signals before explaining degraded memory-backed runs to a tenant.
                    </CardDescription>
                  </CardHeader>
                  <CardContent className="space-y-3">
                    {healthItems.map((item) => (
                      <div key={item.label} className="rounded-xl border border-border/50 bg-background/70 p-4">
                        <div className="flex items-center justify-between gap-3">
                          <p className="font-medium text-foreground">{item.label}</p>
                          <Badge
                            variant="outline"
                            className={
                              item.state === "healthy"
                                ? "border-emerald-500/30 text-emerald-700 dark:text-emerald-300"
                                : item.state === "attention"
                                  ? "border-amber-500/30 text-amber-800 dark:text-amber-200"
                                  : "border-destructive/30 text-destructive"
                            }
                          >
                            {item.state}
                          </Badge>
                        </div>
                        <p className="mt-2 text-sm text-muted-foreground">{item.detail}</p>
                      </div>
                    ))}

                    <div className="rounded-xl border border-border/50 bg-background/70 p-4">
                      <p className="font-medium text-foreground">Latest maintenance markers</p>
                      <div className="mt-3 grid gap-3 text-sm text-muted-foreground md:grid-cols-2">
                        <p>GC last run: {formatDateTime(data.memoryHealth.metrics?.memory_gc_last_run_at)}</p>
                        <p>Reindex marker: {formatDateTime(data.memoryHealth.metrics?.memory_gc_last_reindex)}</p>
                        <p>
                          Index jobs: {data.memoryPerformance.indexing.jobs_total} · success{" "}
                          {data.memoryPerformance.indexing.success_total}
                        </p>
                        <p>
                          gRPC calls: {data.memoryPerformance.grpc.requests_total} · errors{" "}
                          {data.memoryPerformance.grpc.errors_total}
                        </p>
                      </div>
                    </div>
                  </CardContent>
                </Card>
              </div>

              <Card className="border-border/60 bg-card/70 backdrop-blur-sm">
                <CardHeader>
                  <CardTitle>Operator next steps</CardTitle>
                  <CardDescription>
                    The admin experience should make the next troubleshooting hop obvious instead of forcing source-code
                    spelunking.
                  </CardDescription>
                </CardHeader>
                <CardContent className="grid gap-3 md:grid-cols-3">
                  <Link
                    href="/admin/billing"
                    className="rounded-xl border border-border/50 bg-background/70 p-4 transition-colors hover:bg-background"
                  >
                    <p className="font-medium text-foreground">Blocked by budget or quota</p>
                    <p className="mt-2 text-sm text-muted-foreground">
                      Use Billing to compare plan entitlements, tenant quota, and spend budget.
                    </p>
                  </Link>
                  <Link
                    href="/admin/audit-logs"
                    className="rounded-xl border border-border/50 bg-background/70 p-4 transition-colors hover:bg-background"
                  >
                    <p className="font-medium text-foreground">Need an action trail</p>
                    <p className="mt-2 text-sm text-muted-foreground">
                      Audit explains who changed retention, identity, or curated-memory state.
                    </p>
                  </Link>
                  <Link
                    href="/memory"
                    className="rounded-xl border border-border/50 bg-background/70 p-4 transition-colors hover:bg-background"
                  >
                    <p className="font-medium text-foreground">Need observation context</p>
                    <p className="mt-2 text-sm text-muted-foreground">
                      The Memory Browser shows the actual curated observations backing retrieval.
                    </p>
                  </Link>
                </CardContent>
              </Card>
            </>
          ) : null}
        </div>
      </DashboardLayout>
    </ProtectedRoute>
  );
}
