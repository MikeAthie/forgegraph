import { useCallback, useEffect, useMemo, useReducer, type SetStateAction } from "react";
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

type AdminOperationsState = {
  data: OperationsData | null;
  loading: boolean;
  error: string | null;
  cleanupPreview: RetentionCleanupPreview | null;
  previewLoading: boolean;
  exportingKey: string | null;
  recoveryData: RecoveryData | null;
  recoveryLoading: boolean;
  operatorError: string | null;
  runLookupId: string;
  inspectedRun: OperatorRunState | null;
  operatorReason: string;
  operatorAction: string | null;
};

type AdminOperationsAction = {
  patch: Partial<AdminOperationsState> | ((state: AdminOperationsState) => Partial<AdminOperationsState>);
};

const initialAdminOperationsState: AdminOperationsState = {
  data: null,
  loading: true,
  error: null,
  cleanupPreview: null,
  previewLoading: false,
  exportingKey: null,
  recoveryData: null,
  recoveryLoading: false,
  operatorError: null,
  runLookupId: "",
  inspectedRun: null,
  operatorReason: "",
  operatorAction: null,
};

function adminOperationsReducer(state: AdminOperationsState, action: AdminOperationsAction): AdminOperationsState {
  const patch = typeof action.patch === "function" ? action.patch(state) : action.patch;
  return { ...state, ...patch };
}

function resolveStateAction<T>(value: SetStateAction<T>, current: T): T {
  return typeof value === "function" ? (value as (current: T) => T)(current) : value;
}

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

const USD_FORMATTER = new Intl.NumberFormat("en-US", {
  style: "currency",
  currency: "USD",
  maximumFractionDigits: 2,
});
const NUMBER_FORMATTER = new Intl.NumberFormat("en-US");

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
      return USD_FORMATTER.format(total);
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
      return USD_FORMATTER.format(value);
    }
    return NUMBER_FORMATTER.format(value);
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

function useAdminOperationsController() {
  const { user } = useAuth();
  const canManage = user?.organization_role === "owner" || user?.organization_role === "admin";

  const [pageState, dispatchPageState] = useReducer(adminOperationsReducer, initialAdminOperationsState);
  const {
    data,
    loading,
    error,
    cleanupPreview,
    previewLoading,
    exportingKey,
    recoveryData,
    recoveryLoading,
    operatorError,
    runLookupId,
    inspectedRun,
    operatorReason,
    operatorAction,
  } = pageState;
  const setPageField = useCallback(
    <K extends keyof AdminOperationsState>(key: K, value: SetStateAction<AdminOperationsState[K]>) => {
      dispatchPageState({
        patch: (current) => ({ [key]: resolveStateAction(value, current[key]) }) as Partial<AdminOperationsState>,
      });
    },
    [],
  );
  const setData = useCallback(
    (value: SetStateAction<OperationsData | null>) => setPageField("data", value),
    [setPageField],
  );
  const setLoading = useCallback((value: SetStateAction<boolean>) => setPageField("loading", value), [setPageField]);
  const setError = useCallback((value: SetStateAction<string | null>) => setPageField("error", value), [setPageField]);
  const setCleanupPreview = useCallback(
    (value: SetStateAction<RetentionCleanupPreview | null>) => setPageField("cleanupPreview", value),
    [setPageField],
  );
  const setPreviewLoading = useCallback(
    (value: SetStateAction<boolean>) => setPageField("previewLoading", value),
    [setPageField],
  );
  const setExportingKey = useCallback(
    (value: SetStateAction<string | null>) => setPageField("exportingKey", value),
    [setPageField],
  );
  const setRecoveryData = useCallback(
    (value: SetStateAction<RecoveryData | null>) => setPageField("recoveryData", value),
    [setPageField],
  );
  const setRecoveryLoading = useCallback(
    (value: SetStateAction<boolean>) => setPageField("recoveryLoading", value),
    [setPageField],
  );
  const setOperatorError = useCallback(
    (value: SetStateAction<string | null>) => setPageField("operatorError", value),
    [setPageField],
  );
  const setRunLookupId = useCallback(
    (value: SetStateAction<string>) => setPageField("runLookupId", value),
    [setPageField],
  );
  const setInspectedRun = useCallback(
    (value: SetStateAction<OperatorRunState | null>) => setPageField("inspectedRun", value),
    [setPageField],
  );
  const setOperatorReason = useCallback(
    (value: SetStateAction<string>) => setPageField("operatorReason", value),
    [setPageField],
  );
  const setOperatorAction = useCallback(
    (value: SetStateAction<string | null>) => setPageField("operatorAction", value),
    [setPageField],
  );

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
  }, [setData, setError, setLoading]);

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
  }, [setOperatorError, setRecoveryData, setRecoveryLoading]);

  useEffect(() => {
    if (!canManage) {
      setLoading(false);
      return;
    }
    void loadData();
    void loadRecoveryData();
  }, [canManage, loadData, loadRecoveryData, setLoading]);

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
  }, [setCleanupPreview, setError, setPreviewLoading]);

  const handleExport = useCallback(
    async (action: ExportAction) => {
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
    },
    [setError, setExportingKey],
  );

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
  }, [runLookupId, setInspectedRun, setOperatorAction, setOperatorError]);

  const requireOperatorReason = useCallback(() => {
    const reason = operatorReason.trim();
    if (!reason) {
      setOperatorError("Operator recovery actions require a reason.");
      return null;
    }
    return reason;
  }, [operatorReason, setOperatorError]);

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
    [inspectedRun, loadRecoveryData, requireOperatorReason, setInspectedRun, setOperatorAction, setOperatorError],
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
    [loadRecoveryData, requireOperatorReason, setOperatorAction, setOperatorError],
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
    [loadRecoveryData, requireOperatorReason, setOperatorAction, setOperatorError],
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

  return {
    canManage,
    data,
    loading,
    error,
    cleanupPreview,
    previewLoading,
    exportingKey,
    recoveryData,
    recoveryLoading,
    operatorError,
    runLookupId,
    inspectedRun,
    operatorReason,
    operatorAction,
    healthItems,
    riskNotices,
    sreSummary,
    breachingSloCount,
    missingSloCount,
    eventDeadLetters,
    runtimeIntentDeadLetters,
    taskDeadLetterCount,
    runtimeIntentDeadLetterCount,
    eventDeadLetterCount,
    totalDeadLetterCount,
    loadData,
    loadRecoveryData,
    handlePreviewCleanup,
    handleExport,
    handleInspectRun,
    handleRunRecoveryAction,
    handleIntentAction,
    handleEventDeadLetterAction,
    setRunLookupId,
    setOperatorReason,
  };
}
type AdminOperationsController = ReturnType<typeof useAdminOperationsController>;

function AdminOperationsNoAccess() {
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

function AdminOperationsHero({ controller }: { controller: AdminOperationsController }) {
  const { data } = controller;

  return (
    <section className="relative overflow-hidden rounded-[2rem] border border-border/50 bg-card/80 p-6 shadow-lg backdrop-blur-sm sm:p-8">
      <div className="relative flex flex-col gap-5 md:flex-row md:items-start md:justify-between">
        <div>
          <p className="text-xs uppercase tracking-[0.24em] text-muted-foreground">Operator controls</p>
          <h1 className="mt-2 text-3xl font-semibold tracking-tight text-foreground">Operations administration</h1>
          <p className="mt-3 max-w-3xl text-sm leading-6 text-muted-foreground">
            Tenant-scoped guardrails, retention, diagnostics, and operator export workflows.
          </p>
        </div>
        <div className="flex flex-wrap gap-2">
          <Button asChild variant="outline" className="rounded-full">
            <Link href="/admin/help">
              Operator help
              <ArrowRight className="size-4" />
            </Link>
          </Button>
          <Button asChild variant="outline" className="rounded-full">
            <Link href="/ops">
              Recovery console
              <ArrowRight className="size-4" />
            </Link>
          </Button>
        </div>
      </div>
      {data ? (
        <div className="mt-5 flex flex-wrap gap-2">
          <Badge variant="outline">Runtime: {data.policy.summary.runtime_mode}</Badge>
          <Badge variant="outline">HTTP: {data.policy.summary.http_access_mode.replace(/_/g, " ")}</Badge>
          <Badge variant="outline">
            Indexing: {data.policy.summary.curated_memory_vector_indexing_enabled ? "enabled" : "disabled"}
          </Badge>
          <Badge variant="outline">Queue: {data.metricsSummary.queue.total_depth} waiting</Badge>
        </div>
      ) : null}
    </section>
  );
}

function AdminOperationsLoadedContent({ controller }: { controller: AdminOperationsController }) {
  if (controller.loading) {
    return (
      <div className="flex items-center gap-2 text-muted-foreground">
        <Spinner className="size-5" />
        Loading operator controls&hellip;
      </div>
    );
  }

  if (!controller.data) {
    return null;
  }

  return (
    <>
      <RiskNoticeAlert notices={controller.riskNotices} />
      {controller.operatorError ? (
        <Alert variant="destructive">
          <AlertDescription>{controller.operatorError}</AlertDescription>
        </Alert>
      ) : null}
      {controller.sreSummary ? <SreSummaryCard controller={controller} /> : null}
      <RecoveryControlsCard controller={controller} />
      <div className="grid gap-4 xl:grid-cols-2">
        <GuardrailSummaryCard data={controller.data} />
        <RetentionLifecycleCard controller={controller} />
      </div>
      <div className="grid gap-4 xl:grid-cols-[1.05fr_0.95fr]">
        <SupportExportsCard controller={controller} />
        <HealthDiagnosticsCard controller={controller} />
      </div>
      <OperatorNextStepsCard />
    </>
  );
}

function RiskNoticeAlert({ notices }: { notices: string[] }) {
  if (notices.length === 0) {
    return null;
  }

  return (
    <Alert className="border-amber-500/30 bg-amber-500/10 text-amber-900 dark:text-amber-100">
      <AlertTriangle className="size-4" />
      <AlertDescription className="space-y-2">
        {notices.map((notice) => (
          <p key={notice}>{notice}</p>
        ))}
      </AlertDescription>
    </Alert>
  );
}

function SummaryMetric({ label, value, detail }: { label: string; value: string | number; detail: string }) {
  return (
    <div className="rounded-xl border border-border/50 bg-background/70 p-4">
      <p className="text-xs uppercase tracking-[0.2em] text-muted-foreground">{label}</p>
      <p className="mt-2 text-2xl font-semibold text-foreground">{value}</p>
      <p className="mt-2 text-sm text-muted-foreground">{detail}</p>
    </div>
  );
}

function SreSummaryCard({ controller }: { controller: AdminOperationsController }) {
  const sre = controller.sreSummary;
  if (!sre) {
    return null;
  }

  return (
    <Card className="border-border/60 bg-card/70 backdrop-blur-sm">
      <CardHeader>
        <CardTitle>Production SLOs and SRE alerts</CardTitle>
        <CardDescription>
          Backend-owned SLO evidence, dashboard signals, and alert state from the current evaluation window.
        </CardDescription>
      </CardHeader>
      <CardContent className="space-y-5">
        <div className="grid gap-3 md:grid-cols-4">
          <SummaryMetric
            label="Release tier"
            value={sre.release_tier}
            detail={`${Math.round(sre.window_seconds / 60)} minute window`}
          />
          <SummaryMetric
            label="Breaching SLOs"
            value={controller.breachingSloCount}
            detail="Targets come from production-slos.yaml."
          />
          <SummaryMetric label="Active alerts" value={sre.alerts.active_total} detail="Repo-native alert evaluation." />
          <SummaryMetric
            label="Missing signals"
            value={controller.missingSloCount}
            detail="Missing data is never treated as healthy."
          />
        </div>
        <div className="grid gap-4 xl:grid-cols-[1fr_0.9fr]">
          <SloObjectivesPanel controller={controller} />
          <SreAlertsPanel controller={controller} />
        </div>
        <DashboardSignalsPanel controller={controller} />
      </CardContent>
    </Card>
  );
}

function SloObjectivesPanel({ controller }: { controller: AdminOperationsController }) {
  const sre = controller.sreSummary;
  if (!sre) {
    return null;
  }

  return (
    <div className="rounded-xl border border-border/50 bg-background/70 p-4">
      <div className="flex items-center justify-between gap-3">
        <div>
          <p className="font-medium text-foreground">SLO objectives</p>
          <p className="text-sm text-muted-foreground">Production readiness targets and current state.</p>
        </div>
        <Badge variant="outline">{sre.objectives.length} objectives</Badge>
      </div>
      <div className="mt-4 grid gap-3 md:grid-cols-2">
        {sre.objectives.map((objective) => (
          <SloObjectiveCard key={objective.id} objective={objective} />
        ))}
      </div>
    </div>
  );
}

function SloObjectiveCard({
  objective,
}: {
  objective: NonNullable<AdminOperationsController["sreSummary"]>["objectives"][number];
}) {
  return (
    <div className="rounded-lg border border-border/50 bg-card/70 p-3">
      <div className="flex items-start justify-between gap-3">
        <div>
          <p className="text-sm font-medium">{objective.title}</p>
          <p className="mt-1 text-xs text-muted-foreground">
            {formatSreValue(objective.actual, objective.unit)} / target{" "}
            {formatSreValue(objective.target, objective.unit)}
          </p>
        </div>
        <SloStatusBadge status={objective.status} />
      </div>
      <p className="mt-2 text-xs text-muted-foreground">
        Source: {objective.source} · samples {objective.observed_count}
      </p>
    </div>
  );
}

function SloStatusBadge({ status }: { status: string }) {
  return (
    <Badge
      variant="outline"
      className={
        status === "passing"
          ? "border-emerald-500/30 text-emerald-700 dark:text-emerald-300"
          : status === "breaching"
            ? "border-destructive/30 text-destructive"
            : "border-amber-500/30 text-amber-800 dark:text-amber-200"
      }
    >
      {status.replace(/_/g, " ")}
    </Badge>
  );
}

function SreAlertsPanel({ controller }: { controller: AdminOperationsController }) {
  const visibleAlerts = (controller.sreSummary?.alerts.items ?? []).filter((alert) => alert.state !== "ok");

  return (
    <div className="rounded-xl border border-border/50 bg-background/70 p-4">
      <p className="font-medium text-foreground">Active alert state</p>
      <div className="mt-4 space-y-3">
        {visibleAlerts.map((alert) => (
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
        {visibleAlerts.length === 0 ? (
          <p className="rounded-lg border border-border/50 bg-card/70 p-4 text-sm text-muted-foreground">
            No SRE alerts are active in the current window.
          </p>
        ) : null}
      </div>
    </div>
  );
}

function DashboardSignalsPanel({ controller }: { controller: AdminOperationsController }) {
  const panels = controller.sreSummary?.dashboard_panels ?? [];
  return (
    <div className="rounded-xl border border-border/50 bg-background/70 p-4">
      <p className="font-medium text-foreground">Dashboard signals</p>
      <div className="mt-4 grid gap-3 md:grid-cols-3 xl:grid-cols-4">
        {panels.map((panel) => (
          <div key={panel.id} className="rounded-lg border border-border/50 bg-card/70 p-3">
            <p className="text-xs uppercase tracking-[0.16em] text-muted-foreground">{panel.title}</p>
            <p className="mt-2 text-sm font-semibold text-foreground">{formatSreValue(panel.value, panel.unit)}</p>
            {panel.missing_data ? (
              <p className="mt-1 text-xs text-amber-700 dark:text-amber-200">No data configured</p>
            ) : null}
          </div>
        ))}
      </div>
    </div>
  );
}

function RecoveryControlsCard({ controller }: { controller: AdminOperationsController }) {
  return (
    <Card className="border-border/60 bg-card/70 backdrop-blur-sm">
      <CardHeader>
        <CardTitle role="heading" aria-level={2}>
          Recovery controls
        </CardTitle>
        <CardDescription>
          Backend-owned state, retry backlog, dead letters, and live connection counts for stuck-company inspection.
        </CardDescription>
      </CardHeader>
      <CardContent className="space-y-5">
        <RecoveryMetricsGrid controller={controller} />
        <div className="grid gap-4 xl:grid-cols-[0.95fr_1.05fr]">
          <RunInspectionPanel controller={controller} />
          <DeadLetterRecoveryPanel controller={controller} />
        </div>
      </CardContent>
    </Card>
  );
}

function RecoveryMetricsGrid({ controller }: { controller: AdminOperationsController }) {
  const retryCount = (controller.recoveryData?.orgLoad.retry_operations ?? []).reduce(
    (sum, item) => sum + item.count,
    0,
  );
  return (
    <div className="grid gap-3 md:grid-cols-4">
      <SummaryMetric
        label="Intent backlog"
        value={controller.recoveryData?.backlog.backlog ?? 0}
        detail={`Pending ${controller.recoveryData?.backlog.pending ?? 0} · lag ${controller.recoveryData?.backlog.lag ?? 0}`}
      />
      <SummaryMetric
        label="Dead letters"
        value={controller.totalDeadLetterCount}
        detail={`${controller.eventDeadLetterCount} event · ${controller.runtimeIntentDeadLetterCount} runtime intent`}
      />
      <SummaryMetric
        label="WebSocket clients"
        value={controller.recoveryData?.wsSubscribers.total ?? 0}
        detail={`${Object.keys(controller.recoveryData?.wsSubscribers.by_run ?? {}).length} runs subscribed`}
      />
      <SummaryMetric label="Retry operations" value={retryCount} detail="Bounded and inspectable." />
    </div>
  );
}

function RunInspectionPanel({ controller }: { controller: AdminOperationsController }) {
  return (
    <div className="rounded-xl border border-border/50 bg-background/70 p-4">
      <div className="flex flex-col gap-3 sm:flex-row">
        <input
          value={controller.runLookupId}
          onChange={(event) => controller.setRunLookupId(event.target.value)}
          placeholder="Run ID"
          className="min-h-10 flex-1 rounded-md border border-border bg-background px-3 text-sm outline-none focus:ring-2 focus:ring-ring"
        />
        <Button
          variant="outline"
          onClick={() => void controller.handleInspectRun()}
          disabled={controller.operatorAction === "inspect-run"}
        >
          {controller.operatorAction === "inspect-run" ? <Spinner size="xs" className="mr-2" /> : null}
          Inspect run
        </Button>
      </div>
      <textarea
        value={controller.operatorReason}
        onChange={(event) => controller.setOperatorReason(event.target.value)}
        placeholder="Operator reason required for replay, acknowledgement, force fail, force cancel, and rehydrate."
        className="mt-3 min-h-20 w-full rounded-md border border-border bg-background px-3 py-2 text-sm outline-none focus:ring-2 focus:ring-ring"
      />
      {controller.inspectedRun ? <InspectedRunPanel controller={controller} /> : null}
    </div>
  );
}

function InspectedRunPanel({ controller }: { controller: AdminOperationsController }) {
  const run = controller.inspectedRun;
  if (!run) return null;
  return (
    <div className="mt-4 space-y-3">
      <div className="grid gap-3 md:grid-cols-2">
        <SummaryMetric
          label="Status"
          value={run.run.status}
          detail={`Attempt ${run.run.current_attempt ?? "unknown"}`}
        />
        <SummaryMetric
          label="Blocked work"
          value={`${run.active_tasks.length} active · ${run.dead_letter_count} dead`}
          detail={`${run.pending_decisions.length} pending decisions`}
        />
      </div>
      <div className="grid gap-2 sm:grid-cols-3">
        <Button
          variant="outline"
          onClick={() => void controller.handleRunRecoveryAction("force-fail")}
          disabled={controller.operatorAction === "force-fail"}
        >
          Force fail
        </Button>
        <Button
          variant="outline"
          onClick={() => void controller.handleRunRecoveryAction("force-cancel")}
          disabled={controller.operatorAction === "force-cancel"}
        >
          Force cancel
        </Button>
        <Button
          variant="outline"
          onClick={() => void controller.handleRunRecoveryAction("force-rehydrate")}
          disabled={controller.operatorAction === "force-rehydrate"}
        >
          Rehydrate
        </Button>
      </div>
      <div className="max-h-56 overflow-auto rounded-lg border border-border/50">
        {run.tasks.map((task) => (
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
  );
}

function DeadLetterRecoveryPanel({ controller }: { controller: AdminOperationsController }) {
  return (
    <div className="rounded-xl border border-border/50 bg-background/70 p-4">
      <div className="mb-3 flex items-center justify-between gap-3">
        <div>
          <p className="font-medium text-foreground">Dead-letter recovery</p>
          <p className="text-sm text-muted-foreground">
            Event ingestion failures, runtime intent poison messages, and audited operator recovery.
          </p>
        </div>
        <Button
          variant="outline"
          onClick={() => void controller.loadRecoveryData()}
          disabled={controller.recoveryLoading}
        >
          {controller.recoveryLoading ? <Spinner size="xs" className="mr-2" /> : null}
          Refresh
        </Button>
      </div>
      <div className="max-h-80 space-y-3 overflow-auto pr-1">
        <EventDeadLettersList controller={controller} />
        <RuntimeIntentDeadLettersList controller={controller} />
      </div>
    </div>
  );
}

function EventDeadLettersList({ controller }: { controller: AdminOperationsController }) {
  return (
    <>
      {controller.eventDeadLetters.slice(0, 8).map((deadLetter) => (
        <div key={deadLetter.id} className="rounded-lg border border-border/50 bg-card/70 p-3">
          <div className="flex items-start justify-between gap-3">
            <div className="min-w-0">
              <p className="truncate text-sm font-medium">{deadLetter.event_type || "unknown event"}</p>
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
              onClick={() => void controller.handleEventDeadLetterAction(deadLetter.id, "replay")}
              disabled={controller.operatorAction === `event-replay:${deadLetter.id}`}
            >
              Request replay
            </Button>
            <Button
              size="sm"
              variant="outline"
              onClick={() => void controller.handleEventDeadLetterAction(deadLetter.id, "acknowledge")}
              disabled={
                Boolean(deadLetter.acknowledged_at) ||
                controller.operatorAction === `event-acknowledge:${deadLetter.id}`
              }
            >
              Acknowledge
            </Button>
          </div>
        </div>
      ))}
      {controller.eventDeadLetters.length === 0 ? (
        <p className="rounded-lg border border-border/50 bg-card/70 p-4 text-sm text-muted-foreground">
          No event ingestion dead letters are visible for this organization.
        </p>
      ) : null}
    </>
  );
}

function RuntimeIntentDeadLettersList({ controller }: { controller: AdminOperationsController }) {
  return (
    <>
      {controller.runtimeIntentDeadLetters.slice(0, 8).map((outcome) => (
        <div key={outcome.intent_id} className="rounded-lg border border-border/50 bg-card/70 p-3">
          <div className="flex items-start justify-between gap-3">
            <div className="min-w-0">
              <p className="truncate text-sm font-medium">{outcome.intent_type}</p>
              <p className="mt-1 text-xs text-muted-foreground">
                {outcome.reason || outcome.error_class || "No reason recorded"}
              </p>
              <p className="mt-1 text-xs text-muted-foreground">
                {outcome.acknowledged_at ? `Acknowledged ${formatDateTime(outcome.acknowledged_at)}` : "Unacknowledged"}
              </p>
            </div>
            <Badge variant="outline">{outcome.attempt_id || "no attempt"}</Badge>
          </div>
          <div className="mt-3 flex flex-wrap gap-2">
            <Button
              size="sm"
              variant="outline"
              onClick={() => void controller.handleIntentAction(outcome.intent_id, "replay")}
              disabled={controller.operatorAction === `replay:${outcome.intent_id}`}
            >
              Replay
            </Button>
            <Button
              size="sm"
              variant="outline"
              onClick={() => void controller.handleIntentAction(outcome.intent_id, "acknowledge")}
              disabled={
                Boolean(outcome.acknowledged_at) || controller.operatorAction === `acknowledge:${outcome.intent_id}`
              }
            >
              Acknowledge
            </Button>
          </div>
        </div>
      ))}
      {controller.runtimeIntentDeadLetters.length === 0 ? (
        <p className="rounded-lg border border-border/50 bg-card/70 p-4 text-sm text-muted-foreground">
          No runtime intent dead letters are visible for this organization.
        </p>
      ) : null}
    </>
  );
}

function InfoTile({ label, value, detail }: { label: string; value: string | number; detail: string }) {
  return (
    <div className="rounded-xl border border-border/50 bg-background/70 p-4">
      <p className="text-xs uppercase tracking-[0.2em] text-muted-foreground">{label}</p>
      <p className="mt-2 text-lg font-semibold text-foreground">{value}</p>
      <p className="mt-2 text-sm text-muted-foreground">{detail}</p>
    </div>
  );
}

function GuardrailSummaryCard({ data }: { data: OperationsData }) {
  const httpLabel =
    data.policy.summary.http_access_mode === "default_deny"
      ? "Default deny"
      : data.policy.summary.http_access_mode === "allowlist_first"
        ? "Allowlist first"
        : "Open";

  return (
    <Card className="border-border/60 bg-card/70 backdrop-blur-sm">
      <CardHeader>
        <CardTitle>Guardrail summary</CardTitle>
        <CardDescription>
          These summaries are derived from the actual tenant policy plus the current runtime mode.
        </CardDescription>
      </CardHeader>
      <CardContent className="grid gap-3 md:grid-cols-2">
        <InfoTile
          label="HTTP egress"
          value={httpLabel}
          detail={`Allowlist: ${data.policy.summary.egress_allowlist_count} · Denylist: ${data.policy.summary.egress_denylist_count}`}
        />
        <InfoTile
          label="Runtime mode"
          value={data.policy.summary.runtime_mode}
          detail={`Exec tools are ${data.policy.summary.exec_tools_policy.replace(/_/g, " ")}.`}
        />
        <InfoTile
          label="Allowed providers"
          value={data.policy.summary.provider_allowlist_count}
          detail={
            data.policy.allowed_providers.length > 0
              ? data.policy.allowed_providers.join(", ")
              : "All configured providers are currently allowed."
          }
        />
        <InfoTile
          label="Allowed models"
          value={data.policy.summary.model_allowlist_count}
          detail={
            data.policy.allowed_models.length > 0
              ? data.policy.allowed_models.join(", ")
              : "No model-specific allowlist is set."
          }
        />
      </CardContent>
    </Card>
  );
}

function RetentionLifecycleCard({ controller }: { controller: AdminOperationsController }) {
  const data = controller.data;
  if (!data) return null;
  return (
    <Card className="border-border/60 bg-card/70 backdrop-blur-sm">
      <CardHeader>
        <CardTitle>Retention and lifecycle</CardTitle>
        <CardDescription>
          Operators should be able to explain what data lasts, what is manual, and what a cleanup would remove.
        </CardDescription>
      </CardHeader>
      <CardContent className="space-y-4">
        <div className="grid gap-3 md:grid-cols-2">
          <InfoTile label="Runs" value={formatDays(data.retention.runs_retention_days)} detail="Operation records" />
          <InfoTile
            label="Operation logs"
            value={formatDays(data.retention.run_logs_retention_days)}
            detail="Execution logs"
          />
          <InfoTile
            label="Audit logs"
            value={formatDays(data.retention.audit_logs_retention_days)}
            detail="Governance actions"
          />
          <InfoTile
            label="Usage rows"
            value={formatDays(data.retention.usage_retention_days)}
            detail="Usage accounting"
          />
        </div>
        <Alert className="border-sky-500/30 bg-sky-500/10 text-sky-800 dark:text-sky-100">
          <BrainCircuit className="size-4" />
          <AlertDescription>{data.memoryUsage.retention.summary}</AlertDescription>
        </Alert>
        <div className="flex flex-wrap items-center gap-3">
          <Button
            variant="outline"
            onClick={() => void controller.handlePreviewCleanup()}
            disabled={controller.previewLoading}
          >
            {controller.previewLoading ? (
              <>
                <Spinner size="xs" className="mr-2" />
                Previewing&hellip;
              </>
            ) : (
              "Preview cleanup impact"
            )}
          </Button>
          <p className="text-sm text-muted-foreground">Preview only. No data is deleted from this screen.</p>
        </div>
        {controller.cleanupPreview ? <CleanupPreviewGrid preview={controller.cleanupPreview} /> : null}
      </CardContent>
    </Card>
  );
}

function CleanupPreviewGrid({ preview }: { preview: RetentionCleanupPreview }) {
  return (
    <div className="grid gap-3 md:grid-cols-3">
      <InfoTile label="Would delete" value={preview.total_deleted} detail="Total rows across the current policy." />
      <InfoTile
        label="Run artifacts"
        value={preview.runs_deleted + preview.run_logs_deleted}
        detail="Operations plus operation logs that are past retention."
      />
      <InfoTile
        label="Usage and audit"
        value={preview.audit_logs_deleted + preview.llm_usage_deleted + preview.memory_usage_deleted}
        detail="Audit logs and usage rows that exceed retention."
      />
    </div>
  );
}

function SupportExportsCard({ controller }: { controller: AdminOperationsController }) {
  return (
    <Card className="border-border/60 bg-card/70 backdrop-blur-sm">
      <CardHeader>
        <CardTitle>Support-safe exports</CardTitle>
        <CardDescription>
          These exports stay tenant-scoped and use the API&apos;s existing redaction behavior.
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
              <FileJson className="size-5 text-muted-foreground" aria-hidden="true" />
            </div>
            <Button
              variant="outline"
              className="mt-4 w-full justify-between"
              onClick={() => void controller.handleExport(action)}
              disabled={controller.exportingKey === action.key}
            >
              {controller.exportingKey === action.key ? (
                <>
                  <span className="inline-flex items-center">
                    <Spinner size="xs" className="mr-2" />
                    Exporting&hellip;
                  </span>
                  <HardDriveDownload className="size-4" aria-hidden="true" />
                </>
              ) : (
                <>
                  <span>Download JSON</span>
                  <Download className="size-4" aria-hidden="true" />
                </>
              )}
            </Button>
          </div>
        ))}
      </CardContent>
    </Card>
  );
}

function HealthDiagnosticsCard({ controller }: { controller: AdminOperationsController }) {
  const data = controller.data;
  if (!data) return null;
  return (
    <Card className="border-border/60 bg-card/70 backdrop-blur-sm">
      <CardHeader>
        <CardTitle>Health and diagnostics</CardTitle>
        <CardDescription>Use these signals before explaining degraded memory-backed runs to a tenant.</CardDescription>
      </CardHeader>
      <CardContent className="space-y-3">
        {controller.healthItems.map((item) => (
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
  );
}

function OperatorNextStepsCard() {
  return (
    <Card className="border-border/60 bg-card/70 backdrop-blur-sm">
      <CardHeader>
        <CardTitle>Operator next steps</CardTitle>
        <CardDescription>
          The admin experience should make the next troubleshooting hop obvious instead of forcing source-code
          spelunking.
        </CardDescription>
      </CardHeader>
      <CardContent className="grid gap-3 md:grid-cols-3">
        <NextStepLink
          href="/admin/billing"
          title="Blocked by budget or quota"
          detail="Use Billing to compare plan entitlements, tenant quota, and spend budget."
        />
        <NextStepLink
          href="/admin/audit-logs"
          title="Need an action trail"
          detail="Audit explains who changed retention, identity, or curated-memory state."
        />
        <NextStepLink
          href="/memory"
          title="Need observation context"
          detail="The Memory Browser shows the actual curated observations backing retrieval."
        />
      </CardContent>
    </Card>
  );
}

function NextStepLink({ href, title, detail }: { href: string; title: string; detail: string }) {
  return (
    <Link
      href={href}
      className="rounded-xl border border-border/50 bg-background/70 p-4 transition-colors hover:bg-background"
    >
      <p className="font-medium text-foreground">{title}</p>
      <p className="mt-2 text-sm text-muted-foreground">{detail}</p>
    </Link>
  );
}

export default function AdminOperationsPage() {
  const controller = useAdminOperationsController();

  if (!controller.canManage) {
    return <AdminOperationsNoAccess />;
  }

  return (
    <ProtectedRoute>
      <DashboardLayout>
        <div className="flex flex-col gap-6">
          <AdminOperationsHero controller={controller} />
          {controller.error ? (
            <Alert variant="destructive">
              <AlertDescription>{controller.error}</AlertDescription>
            </Alert>
          ) : null}
          <AdminOperationsLoadedContent controller={controller} />
        </div>
      </DashboardLayout>
    </ProtectedRoute>
  );
}
