import { useCallback, useEffect, useMemo, useReducer } from "react";
import Link from "next/link";
import { useRouter } from "next/router";

import DashboardLayout from "../../components/DashboardLayout";
import ProtectedRoute from "../../components/ProtectedRoute";
import {
  analyticsApi,
  getApiErrorMessage,
  type MemoryAnalyticsCosts,
  type MemoryAnalyticsPerformance,
  type MemoryAnalyticsUsage,
} from "../../lib/api";
import {
  Alert,
  AlertDescription,
  Badge,
  Button,
  Card,
  CardContent,
  CardHeader,
  CardTitle,
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
  Spinner,
} from "@/components/ui";

const PERIOD_OPTIONS = [
  { value: "7d", label: "Last 7 days" },
  { value: "30d", label: "Last 30 days" },
  { value: "90d", label: "Last 90 days" },
  { value: "365d", label: "Last 12 months" },
];

const isPeriodOption = (value: unknown): value is string =>
  typeof value === "string" && PERIOD_OPTIONS.some((option) => option.value === value);

const NUMBER_FORMATTER = new Intl.NumberFormat();
const USD_FORMATTER = new Intl.NumberFormat("en-US", {
  style: "currency",
  currency: "USD",
  maximumFractionDigits: 2,
});

const formatNumber = (value: number | null | undefined) => {
  if (value === null || value === undefined) return "—";
  return NUMBER_FORMATTER.format(value);
};

const formatCurrency = (value: number | null | undefined) => {
  if (value === null || value === undefined) return "—";
  return USD_FORMATTER.format(value);
};

const formatPercent = (value: number | null | undefined) => {
  if (value === null || value === undefined) return "—";
  return `${Math.round(value * 100)}%`;
};

const formatDate = (value: string) => {
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return value;
  return date.toLocaleDateString();
};

const buildSparkline = (values: number[], width = 180, height = 48) => {
  if (!values.length) return "";
  const max = Math.max(...values, 1);
  const min = Math.min(...values, 0);
  const range = Math.max(max - min, 1);
  return values
    .map((value, index) => {
      const x = (index / Math.max(values.length - 1, 1)) * width;
      const y = height - ((value - min) / range) * height;
      return `${x},${y}`;
    })
    .join(" ");
};

const describeSparkline = (values: number[], label: string) => {
  if (!values.length) {
    return `${label}: no data available for the selected period.`;
  }
  const first = values[0] ?? 0;
  const latest = values[values.length - 1] ?? 0;
  const max = Math.max(...values);
  return `${label}: ${values.length} points, from ${formatNumber(first)} to ${formatNumber(latest)}, peak ${formatNumber(max)}.`;
};

function Sparkline({ values, className, label }: { values: number[]; className?: string; label: string }) {
  const points = buildSparkline(values);
  return (
    <svg viewBox="0 0 180 48" className={className} role="img" aria-label={describeSparkline(values, label)}>
      {points ? (
        <>
          <polyline
            points={points}
            fill="none"
            stroke="currentColor"
            strokeWidth="2"
            strokeLinejoin="round"
            strokeLinecap="round"
          />
          <polyline points={`0,48 ${points} 180,48`} fill="currentColor" opacity="0.15" />
        </>
      ) : (
        <rect width="180" height="48" fill="currentColor" opacity="0.08" />
      )}
    </svg>
  );
}

const downloadBlob = (blob: Blob, filename: string) => {
  const url = URL.createObjectURL(blob);
  const anchor = document.createElement("a");
  anchor.href = url;
  anchor.download = filename;
  anchor.click();
  URL.revokeObjectURL(url);
};

function MemoryAnalyticsHeader({
  period,
  loading,
  exportDisabled,
  onPeriodChange,
  onRefresh,
  onExport,
}: {
  period: string;
  loading: boolean;
  exportDisabled: boolean;
  onPeriodChange: (period: string) => void;
  onRefresh: () => void;
  onExport: (format: "json" | "csv") => void;
}) {
  return (
    <div className="relative overflow-hidden rounded-3xl border border-border/40 bg-card/70 p-6 shadow-lg backdrop-blur-sm">
      <div
        className="pointer-events-none absolute inset-0"
        style={{
          backgroundImage:
            "radial-gradient(circle at top left, rgba(14, 116, 144, 0.18), transparent 55%), radial-gradient(circle at 80% 20%, rgba(234, 179, 8, 0.15), transparent 50%), linear-gradient(120deg, rgba(15, 23, 42, 0.05), rgba(255, 255, 255, 0))",
        }}
      />
      <div className="relative flex flex-col gap-4 sm:flex-row sm:items-start sm:justify-between">
        <div>
          <Badge variant="outline" className="mb-3 border-cyan-400/40 text-cyan-700 dark:text-cyan-200">
            Memory Analytics
          </Badge>
          <h1 className="text-2xl sm:text-3xl font-semibold tracking-tight text-foreground">Signal, not noise.</h1>
          <p className="mt-2 max-w-xl text-sm text-muted-foreground">
            Monitor how memory tiers perform across operations, costs, and storage saturation. View refreshed on demand.
          </p>
        </div>
        <div className="flex flex-wrap items-center gap-3">
          <Select value={period} onValueChange={onPeriodChange}>
            <SelectTrigger className="w-[170px]">
              <SelectValue placeholder="Period" />
            </SelectTrigger>
            <SelectContent>
              {PERIOD_OPTIONS.map((option) => (
                <SelectItem key={option.value} value={option.value}>
                  {option.label}
                </SelectItem>
              ))}
            </SelectContent>
          </Select>
          <Button variant="outline" onClick={onRefresh} disabled={loading}>
            {loading ? <Spinner size="xs" /> : "Refresh"}
          </Button>
          <Button variant="outline" asChild>
            <Link href="/analytics/llm">LLM Analytics</Link>
          </Button>
          <Button variant="outline" onClick={() => onExport("json")} disabled={exportDisabled}>
            Export JSON
          </Button>
          <Button variant="outline" onClick={() => onExport("csv")} disabled={exportDisabled}>
            Export CSV
          </Button>
        </div>
      </div>
    </div>
  );
}

function MemoryTierCards({
  usage,
  performance,
  usageTokenSeries,
}: {
  usage: MemoryAnalyticsUsage | null;
  performance: MemoryAnalyticsPerformance | null;
  usageTokenSeries: number[];
}) {
  return (
    <div className="grid gap-4 lg:grid-cols-4">
      <Card className="border-border/50 bg-card/60">
        <CardHeader className="pb-3">
          <CardTitle className="text-base font-semibold">Tier 1 Buffer</CardTitle>
        </CardHeader>
        <CardContent className="flex flex-col gap-3">
          <div className="flex items-center justify-between">
            <span className="text-sm text-muted-foreground">Messages captured</span>
            <span className="text-xl font-semibold">{formatNumber(usage?.tier1.total_messages)}</span>
          </div>
          <div className="flex items-center justify-between text-sm">
            <span className="text-muted-foreground">Avg buffer size</span>
            <span className="font-medium">{formatNumber(usage?.tier1.avg_buffer_size)}</span>
          </div>
          <div className="flex items-center justify-between text-sm">
            <span className="text-muted-foreground">Peak buffer size</span>
            <span className="font-medium">{formatNumber(usage?.tier1.peak_buffer_size)}</span>
          </div>
          <Sparkline values={usageTokenSeries} className="text-cyan-500" label="Tier 1 token trend" />
        </CardContent>
      </Card>

      <Card className="border-border/50 bg-card/60">
        <CardHeader className="pb-3">
          <CardTitle className="text-base font-semibold">Tier 2 Redis</CardTitle>
        </CardHeader>
        <CardContent className="flex flex-col gap-3">
          <div className="flex items-center justify-between">
            <span className="text-sm text-muted-foreground">Keys stored</span>
            <span className="text-xl font-semibold">{formatNumber(usage?.tier2.redis_keys)}</span>
          </div>
          <div className="flex items-center justify-between text-sm">
            <span className="text-muted-foreground">Storage</span>
            <span className="font-medium">{usage ? `${usage.tier2.storage_mb} MB` : "—"}</span>
          </div>
          <div className="flex items-center justify-between text-sm">
            <span className="text-muted-foreground">Hit rate</span>
            <span className="font-medium">{formatPercent(usage?.tier2.hit_rate)}</span>
          </div>
          <div className="rounded-xl border border-border/40 bg-muted/40 px-3 py-2 text-xs text-muted-foreground">
            Redis analytics update as memory entries are written for this tenant.
          </div>
        </CardContent>
      </Card>

      <Card className="border-border/50 bg-card/60">
        <CardHeader className="pb-3">
          <CardTitle className="text-base font-semibold">Tier 3 Vector</CardTitle>
        </CardHeader>
        <CardContent className="flex flex-col gap-3">
          <div className="flex items-center justify-between">
            <span className="text-sm text-muted-foreground">Chunks stored</span>
            <span className="text-xl font-semibold">{formatNumber(usage?.tier3.chunks_stored)}</span>
          </div>
          <div className="flex items-center justify-between text-sm">
            <span className="text-muted-foreground">Embeddings generated</span>
            <span className="font-medium">{formatNumber(usage?.tier3.embeddings_generated)}</span>
          </div>
          <div className="flex items-center justify-between text-sm">
            <span className="text-muted-foreground">Avg search latency</span>
            <span className="font-medium">
              {usage?.tier3.avg_search_latency_ms ? `${usage.tier3.avg_search_latency_ms} ms` : "—"}
            </span>
          </div>
          <Sparkline
            values={usage?.usage_series.map((entry) => entry.summarization_cost_usd ?? 0) ?? []}
            className="text-amber-500"
            label="Tier 3 summarization cost trend"
          />
        </CardContent>
      </Card>

      <Card className="border-border/50 bg-card/60">
        <CardHeader className="pb-3">
          <CardTitle className="text-base font-semibold">Curated Memory</CardTitle>
        </CardHeader>
        <CardContent className="flex flex-col gap-3">
          <div className="flex items-center justify-between">
            <span className="text-sm text-muted-foreground">Observations</span>
            <span className="text-xl font-semibold">{formatNumber(usage?.curated_memory.observations_total)}</span>
          </div>
          <div className="flex items-center justify-between text-sm">
            <span className="text-muted-foreground">Indexed</span>
            <span className="font-medium">{formatNumber(usage?.curated_memory.indexed_observations_total)}</span>
          </div>
          <div className="flex items-center justify-between text-sm">
            <span className="text-muted-foreground">Pending index</span>
            <span className="font-medium">{formatNumber(usage?.curated_memory.pending_index_total)}</span>
          </div>
          <div className="rounded-xl border border-border/40 bg-muted/40 px-3 py-2 text-xs text-muted-foreground">
            Retrieval operations this period: {formatNumber(usage?.curated_memory.retrieval_runs_in_period)}
          </div>
          <div className="rounded-xl border border-border/40 bg-muted/40 px-3 py-2 text-xs text-muted-foreground">
            Search queries this period: {formatNumber(performance?.vector.search_queries)}
          </div>
        </CardContent>
      </Card>
    </div>
  );
}

type MemoryAnalyticsState = {
  usage: MemoryAnalyticsUsage | null;
  costs: MemoryAnalyticsCosts | null;
  performance: MemoryAnalyticsPerformance | null;
  loading: boolean;
  error: string | null;
};

type MemoryAnalyticsAction =
  | { type: "load-start" }
  | {
      type: "load-success";
      usage: MemoryAnalyticsUsage;
      costs: MemoryAnalyticsCosts;
      performance: MemoryAnalyticsPerformance;
    }
  | { type: "load-error"; error: string };

const initialMemoryAnalyticsState: MemoryAnalyticsState = {
  usage: null,
  costs: null,
  performance: null,
  loading: true,
  error: null,
};

function memoryAnalyticsReducer(state: MemoryAnalyticsState, action: MemoryAnalyticsAction): MemoryAnalyticsState {
  switch (action.type) {
    case "load-start":
      return { ...state, loading: true, error: null };
    case "load-success":
      return {
        usage: action.usage,
        costs: action.costs,
        performance: action.performance,
        loading: false,
        error: null,
      };
    case "load-error":
      return { ...state, loading: false, error: action.error };
    default:
      return state;
  }
}

export default function MemoryAnalyticsPage() {
  const router = useRouter();
  const { replace } = router;
  const [{ usage, costs, performance, loading, error }, dispatchPage] = useReducer(
    memoryAnalyticsReducer,
    initialMemoryAnalyticsState,
  );
  const period = isPeriodOption(router.query.period) ? router.query.period : "30d";

  const fetchAnalytics = useCallback(async (periodValue: string) => {
    dispatchPage({ type: "load-start" });

    try {
      const [usageData, costsData, performanceData] = await Promise.all([
        analyticsApi.getMemoryUsage(periodValue),
        analyticsApi.getMemoryCosts(periodValue),
        analyticsApi.getMemoryPerformance(periodValue),
      ]);

      dispatchPage({ type: "load-success", usage: usageData, costs: costsData, performance: performanceData });
    } catch (err: unknown) {
      dispatchPage({ type: "load-error", error: getApiErrorMessage(err, "Failed to load memory analytics.") });
    }
  }, []);

  useEffect(() => {
    void fetchAnalytics(period);
  }, [fetchAnalytics, period]);

  const handlePeriodChange = (nextPeriod: string) => {
    if (!router.isReady) {
      return;
    }
    void replace(
      {
        pathname: router.pathname,
        query: { ...router.query, period: nextPeriod },
      },
      undefined,
      { shallow: true, scroll: false },
    );
  };

  const costSparklineValues = useMemo(
    () => costs?.series.map((entry) => entry.summarization_cost_usd ?? 0) ?? [],
    [costs],
  );

  const usageTokenSeries = useMemo(
    () => usage?.usage_series.map((entry) => entry.summarization_total_tokens ?? 0) ?? [],
    [usage],
  );

  const handleExport = useCallback(
    async (format: "json" | "csv") => {
      try {
        const blob = await analyticsApi.exportMemoryReport({ format, period });
        downloadBlob(blob, `memory-analytics-${period}.${format}`);
      } catch (err: unknown) {
        dispatchPage({ type: "load-error", error: getApiErrorMessage(err, "Failed to export memory analytics.") });
      }
    },
    [period],
  );

  return (
    <ProtectedRoute>
      <DashboardLayout>
        <div className="flex flex-col gap-6">
          <MemoryAnalyticsHeader
            period={period}
            loading={loading}
            exportDisabled={!usage || !costs || !performance}
            onPeriodChange={handlePeriodChange}
            onRefresh={() => {
              void fetchAnalytics(period);
            }}
            onExport={(format) => {
              void handleExport(format);
            }}
          />

          {loading ? (
            <div className="flex items-center justify-center gap-3 rounded-2xl border border-border/40 bg-card/50 py-12">
              <Spinner size="md" />
              <span className="text-sm text-muted-foreground">Fetching memory telemetry…</span>
            </div>
          ) : (
            <>
              <MemoryTierCards usage={usage} performance={performance} usageTokenSeries={usageTokenSeries} />

              <div className="grid gap-4 lg:grid-cols-[1.3fr_1fr]">
                <Card className="border-border/50 bg-card/60">
                  <CardHeader>
                    <CardTitle className="flex flex-col gap-2 sm:flex-row sm:items-center sm:justify-between">
                      <span>Cost trajectory</span>
                      <span className="text-sm font-normal text-muted-foreground">
                        Total {formatCurrency(costs?.summarization_total_usd)}
                      </span>
                    </CardTitle>
                  </CardHeader>
                  <CardContent>
                    <div className="flex flex-col gap-4">
                      <div className="flex items-center justify-between rounded-xl border border-border/40 bg-muted/40 px-4 py-3">
                        <div>
                          <p className="text-xs uppercase tracking-widest text-muted-foreground">Summarization</p>
                          <p className="text-lg font-semibold">{formatCurrency(costs?.summarization_total_usd)}</p>
                        </div>
                        <div className="text-right">
                          <p className="text-xs uppercase tracking-widest text-muted-foreground">Tokens</p>
                          <p className="text-lg font-semibold">
                            {formatNumber(usage?.totals?.summarization_total_tokens)}
                          </p>
                        </div>
                      </div>
                      <div className="rounded-2xl border border-border/40 bg-gradient-to-br from-cyan-500/10 via-transparent to-amber-500/10 p-4">
                        <Sparkline
                          values={costSparklineValues}
                          className="h-16 w-full text-cyan-600"
                          label="Memory summarization cost trend"
                        />
                        <div className="mt-3 flex flex-wrap gap-3 text-xs text-muted-foreground">
                          {costs?.series.slice(-5).map((entry) => (
                            <div
                              key={entry.date}
                              className="rounded-full border border-border/40 bg-background/70 px-3 py-1"
                            >
                              {formatDate(entry.date)} · {formatCurrency(entry.summarization_cost_usd)}
                            </div>
                          ))}
                        </div>
                      </div>
                    </div>
                  </CardContent>
                </Card>

                <Card className="border-border/50 bg-card/60">
                  <CardHeader>
                    <CardTitle>Top agents</CardTitle>
                  </CardHeader>
                  <CardContent className="space-y-3">
                    {usage?.top_agents.length ? (
                      usage.top_agents.map((agent) => (
                        <div
                          key={agent.agent_id ?? "unknown"}
                          className="flex items-center justify-between rounded-xl border border-border/40 bg-muted/30 px-3 py-2 text-sm"
                        >
                          <span className="text-muted-foreground">
                            {agent.agent_id ? agent.agent_id.slice(0, 8) : "Unassigned"}
                          </span>
                          <span className="font-semibold">{formatNumber(agent.chunks)}</span>
                        </div>
                      ))
                    ) : (
                      <p className="text-sm text-muted-foreground">No agent activity recorded yet.</p>
                    )}
                  </CardContent>
                </Card>
              </div>

              <Card className="border-border/50 bg-card/60">
                <CardHeader>
                  <CardTitle>Performance summary</CardTitle>
                </CardHeader>
                <CardContent className="grid gap-4 md:grid-cols-2">
                  <div className="rounded-2xl border border-border/40 bg-muted/30 p-4">
                    <p className="text-xs uppercase tracking-widest text-muted-foreground">Vector</p>
                    <div className="mt-2 space-y-2 text-sm">
                      <div className="flex items-center justify-between">
                        <span className="text-muted-foreground">Chunks indexed</span>
                        <span className="font-semibold">{formatNumber(performance?.vector.chunks_indexed)}</span>
                      </div>
                      <div className="flex items-center justify-between">
                        <span className="text-muted-foreground">Search queries</span>
                        <span className="font-semibold">{formatNumber(performance?.vector.search_queries)}</span>
                      </div>
                      <div className="flex items-center justify-between">
                        <span className="text-muted-foreground">Avg latency</span>
                        <span className="font-semibold">
                          {performance?.vector.avg_search_latency_ms
                            ? `${performance.vector.avg_search_latency_ms} ms`
                            : "—"}
                        </span>
                      </div>
                    </div>
                  </div>

                  <div className="rounded-2xl border border-border/40 bg-muted/30 p-4">
                    <p className="text-xs uppercase tracking-widest text-muted-foreground">gRPC + Maintenance</p>
                    <div className="mt-2 space-y-2 text-sm">
                      <div className="flex items-center justify-between">
                        <span className="text-muted-foreground">gRPC requests</span>
                        <span className="font-semibold">{formatNumber(performance?.grpc.requests_total)}</span>
                      </div>
                      <div className="flex items-center justify-between">
                        <span className="text-muted-foreground">gRPC errors</span>
                        <span className="font-semibold">{formatNumber(performance?.grpc.errors_total)}</span>
                      </div>
                      <div className="flex items-center justify-between">
                        <span className="text-muted-foreground">Index queue errors</span>
                        <span className="font-semibold">
                          {formatNumber(performance?.indexing.enqueue_errors_total)}
                        </span>
                      </div>
                      <div className="flex items-center justify-between">
                        <span className="text-muted-foreground">Pending observations</span>
                        <span className="font-semibold">
                          {formatNumber(performance?.indexing.pending_observations_total)}
                        </span>
                      </div>
                      <div className="flex items-center justify-between">
                        <span className="text-muted-foreground">GC last operation</span>
                        <span className="font-semibold">
                          {performance?.maintenance.memory_gc_last_run_at
                            ? formatDate(performance.maintenance.memory_gc_last_run_at)
                            : "—"}
                        </span>
                      </div>
                    </div>
                  </div>
                </CardContent>
              </Card>

              <Card className="border-border/50 bg-card/60">
                <CardHeader>
                  <CardTitle>Retention posture</CardTitle>
                </CardHeader>
                <CardContent className="grid gap-4 md:grid-cols-[1.1fr_1fr]">
                  <div className="rounded-2xl border border-border/40 bg-muted/30 p-4">
                    <p className="text-xs uppercase tracking-widest text-muted-foreground">Policy summary</p>
                    <p className="mt-3 text-sm text-foreground">
                      {usage?.retention.summary ?? "No retention summary available."}
                    </p>
                    <div className="mt-4 flex flex-wrap gap-2 text-xs text-muted-foreground">
                      <span className="rounded-full border border-border/40 bg-background/70 px-3 py-1">
                        Observations: {usage?.retention.observations_retention_mode ?? "manual"}
                      </span>
                      <span className="rounded-full border border-border/40 bg-background/70 px-3 py-1">
                        Chunks: {usage?.retention.memory_chunks_retention_mode ?? "manual"}
                      </span>
                    </div>
                  </div>
                  <div className="rounded-2xl border border-border/40 bg-muted/30 p-4">
                    <p className="text-xs uppercase tracking-widest text-muted-foreground">Configured windows</p>
                    <div className="mt-2 space-y-2 text-sm">
                      <div className="flex items-center justify-between">
                        <span className="text-muted-foreground">Operations</span>
                        <span className="font-semibold">
                          {usage?.retention.runs_retention_days != null
                            ? `${usage.retention.runs_retention_days} days`
                            : "Not set"}
                        </span>
                      </div>
                      <div className="flex items-center justify-between">
                        <span className="text-muted-foreground">Operation logs</span>
                        <span className="font-semibold">
                          {usage?.retention.run_logs_retention_days != null
                            ? `${usage.retention.run_logs_retention_days} days`
                            : "Not set"}
                        </span>
                      </div>
                      <div className="flex items-center justify-between">
                        <span className="text-muted-foreground">Usage data</span>
                        <span className="font-semibold">
                          {usage?.retention.usage_retention_days != null
                            ? `${usage.retention.usage_retention_days} days`
                            : "Not set"}
                        </span>
                      </div>
                      <div className="flex items-center justify-between">
                        <span className="text-muted-foreground">Audit logs</span>
                        <span className="font-semibold">
                          {usage?.retention.audit_logs_retention_days != null
                            ? `${usage.retention.audit_logs_retention_days} days`
                            : "Not set"}
                        </span>
                      </div>
                    </div>
                  </div>
                </CardContent>
              </Card>
            </>
          )}

          {error && (
            <Alert variant="destructive">
              <AlertDescription>{error}</AlertDescription>
            </Alert>
          )}
        </div>
      </DashboardLayout>
    </ProtectedRoute>
  );
}
