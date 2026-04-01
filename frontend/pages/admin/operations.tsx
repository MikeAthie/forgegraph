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
  policiesApi,
  retentionApi,
  type MemoryAnalyticsPerformance,
  type MemoryAnalyticsUsage,
  type MemoryHealthResponse,
  type MetricsSummary,
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
    label: "Run traces",
    description: "Redacted run-level payloads for support review.",
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

  useEffect(() => {
    if (!canManage) {
      setLoading(false);
      return;
    }
    void loadData();
  }, [canManage, loadData]);

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
      notices.push("Queue depth is above the target. Operators should expect slower run starts.");
    }
    return notices;
  }, [data]);

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
              Loading operator controls...
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
                        <p className="text-xs uppercase tracking-[0.2em] text-muted-foreground">Run logs</p>
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
                            Previewing...
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
                            Runs plus run logs that are past retention.
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
                                Exporting...
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
