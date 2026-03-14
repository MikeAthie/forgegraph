import { useCallback, useEffect, useMemo, useState } from "react";
import Link from "next/link";

import DashboardLayout from "../../components/DashboardLayout";
import ProtectedRoute from "../../components/ProtectedRoute";
import {
  analyticsApi,
  getApiErrorMessage,
  type LLMBudgetStatus,
  type LLMAnalyticsCosts,
  type LLMQuotaStatus,
  type LLMAnalyticsUsage,
} from "../../lib/api";
import { showError, showSuccess } from "../../lib/toast";
import { ERROR_FALLBACKS } from "../../lib/error-messages";
import {
  Alert,
  AlertDescription,
  Badge,
  Button,
  Card,
  CardContent,
  CardHeader,
  CardTitle,
  Input,
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

const formatNumber = (value: number | null | undefined) => {
  if (value === null || value === undefined) return "—";
  return new Intl.NumberFormat().format(value);
};

const formatCurrency = (value: number | null | undefined) => {
  if (value === null || value === undefined) return "—";
  return new Intl.NumberFormat("en-US", {
    style: "currency",
    currency: "USD",
    maximumFractionDigits: 2,
  }).format(value);
};

const formatPercent = (value: number | null | undefined) => {
  if (value === null || value === undefined) return "—";
  return `${Math.round(value * 100)}%`;
};

const buildSparkline = (values: number[], width = 200, height = 60) => {
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

function Sparkline({ values, className }: { values: number[]; className?: string }) {
  const points = buildSparkline(values);
  return (
    <svg viewBox="0 0 200 60" className={className} aria-hidden="true">
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
          <polyline points={`0,60 ${points} 200,60`} fill="currentColor" opacity="0.15" />
        </>
      ) : (
        <rect width="200" height="60" fill="currentColor" opacity="0.08" />
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

export default function LLMAnalyticsPage() {
  const [period, setPeriod] = useState("30d");
  const [usage, setUsage] = useState<LLMAnalyticsUsage | null>(null);
  const [costs, setCosts] = useState<LLMAnalyticsCosts | null>(null);
  const [budget, setBudget] = useState<LLMBudgetStatus | null>(null);
  const [quota, setQuota] = useState<LLMQuotaStatus | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  const [budgetLimit, setBudgetLimit] = useState("");
  const [budgetThreshold, setBudgetThreshold] = useState("80");
  const [isSavingBudget, setIsSavingBudget] = useState(false);

  const fetchAnalytics = useCallback(async (periodValue: string) => {
    setLoading(true);
    setError(null);

    try {
      const [usageData, costsData, budgetData, quotaData] = await Promise.all([
        analyticsApi.getLLMUsage(periodValue),
        analyticsApi.getLLMCosts(periodValue),
        analyticsApi.getLLMBudget(),
        analyticsApi.getLLMQuota(),
      ]);

      setUsage(usageData);
      setCosts(costsData);
      setBudget(budgetData);
      setQuota(quotaData);
    } catch (err: unknown) {
      setError(getApiErrorMessage(err, "Failed to load LLM analytics."));
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    void fetchAnalytics(period);
  }, [fetchAnalytics, period]);

  useEffect(() => {
    if (budget?.budget?.monthly_limit_usd != null) {
      setBudgetLimit(String(budget.budget.monthly_limit_usd));
    }
    if (budget?.budget?.warning_threshold_pct != null) {
      setBudgetThreshold(String(Math.round(budget.budget.warning_threshold_pct * 100)));
    }
  }, [budget]);

  const costSparklineValues = useMemo(() => costs?.series.map((entry) => entry.cost_usd ?? 0) ?? [], [costs]);

  const budgetUsed = budget?.usage.month_cost_usd ?? 0;
  const budgetLimitValue = budget?.budget?.monthly_limit_usd ?? null;
  const budgetProgress = budgetLimitValue ? Math.min(budgetUsed / budgetLimitValue, 1) : 0;

  const saveBudget = async () => {
    if (!budgetLimit) return;
    setIsSavingBudget(true);
    try {
      const updated = await analyticsApi.setLLMBudget({
        monthly_limit_usd: Number(budgetLimit),
        warning_threshold_pct: Number(budgetThreshold),
      });
      setBudget(updated);
      showSuccess("Budget updated");
    } catch (err: unknown) {
      showError("Budget update failed", getApiErrorMessage(err, ERROR_FALLBACKS.analytics.update));
    } finally {
      setIsSavingBudget(false);
    }
  };

  const handleExport = useCallback(
    async (dataset: "usage" | "costs" | "budget" | "quota", format: "json" | "csv") => {
      try {
        const blob = await analyticsApi.exportLLMReport({ dataset, format, period });
        downloadBlob(blob, `llm-${dataset}-${period}.${format}`);
      } catch (err: unknown) {
        showError("Export failed", getApiErrorMessage(err, ERROR_FALLBACKS.analytics.load));
      }
    },
    [period],
  );

  return (
    <ProtectedRoute>
      <DashboardLayout>
        <div className="flex flex-col gap-6">
          <div className="relative overflow-hidden rounded-3xl border border-border/40 bg-card/70 p-6 shadow-lg backdrop-blur-sm">
            <div
              className="pointer-events-none absolute inset-0"
              style={{
                backgroundImage:
                  "radial-gradient(circle at top left, rgba(15, 118, 110, 0.15), transparent 55%), radial-gradient(circle at 80% 20%, rgba(59, 130, 246, 0.12), transparent 50%), linear-gradient(120deg, rgba(15, 23, 42, 0.04), rgba(255, 255, 255, 0))",
              }}
            />
            <div className="relative flex flex-col gap-4 sm:flex-row sm:items-start sm:justify-between">
              <div>
                <Badge variant="outline" className="mb-3 border-emerald-400/40 text-emerald-700 dark:text-emerald-200">
                  LLM Analytics
                </Badge>
                <h1 className="text-2xl sm:text-3xl font-semibold tracking-tight text-foreground">
                  Cost control, visible.
                </h1>
                <p className="mt-2 max-w-xl text-sm text-muted-foreground">
                  Track spend, usage, and provider mix in real time. Budget alerts fire before you blow the month.
                </p>
              </div>
              <div className="flex flex-wrap items-center gap-2">
                <Select value={period} onValueChange={setPeriod}>
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
                <Button variant="outline" onClick={() => void fetchAnalytics(period)} disabled={loading}>
                  {loading ? <Spinner size="xs" /> : "Refresh"}
                </Button>
                <Button variant="outline" asChild>
                  <Link href="/analytics/memory">Memory Analytics</Link>
                </Button>
                <Button variant="outline" onClick={() => void handleExport("usage", "csv")}>
                  Export usage CSV
                </Button>
                <Button variant="outline" onClick={() => void handleExport("costs", "json")}>
                  Export cost JSON
                </Button>
              </div>
            </div>
          </div>

          {budget?.over_budget ? (
            <Alert variant="destructive">
              <AlertDescription>
                Monthly LLM budget exceeded. Runs will be blocked until the next cycle or budget update.
              </AlertDescription>
            </Alert>
          ) : budget?.warning ? (
            <Alert>
              <AlertDescription>
                Budget warning: usage has crossed {formatCurrency(budget.warning_threshold_usd)} this month.
              </AlertDescription>
            </Alert>
          ) : null}

          {loading ? (
            <div className="flex items-center justify-center gap-3 rounded-2xl border border-border/40 bg-card/50 py-12">
              <Spinner size="md" />
              <span className="text-sm text-muted-foreground">Loading LLM telemetry…</span>
            </div>
          ) : (
            <>
              <div className="grid gap-4 lg:grid-cols-3">
                <Card className="border-border/50 bg-card/60">
                  <CardHeader className="pb-3">
                    <CardTitle className="text-base font-semibold">Total Cost</CardTitle>
                  </CardHeader>
                  <CardContent className="flex flex-col gap-3">
                    <div className="text-2xl font-semibold">{formatCurrency(costs?.total_usd)}</div>
                    <div className="text-sm text-muted-foreground">
                      {formatNumber(usage?.totals.total_tokens)} tokens across all providers.
                    </div>
                    <Sparkline values={costSparklineValues} className="text-emerald-500" />
                  </CardContent>
                </Card>

                <Card className="border-border/50 bg-card/60">
                  <CardHeader className="pb-3">
                    <CardTitle className="text-base font-semibold">Provider Mix</CardTitle>
                  </CardHeader>
                  <CardContent className="space-y-3">
                    {usage?.by_provider.length ? (
                      usage.by_provider.map((row) => (
                        <div key={row.provider} className="flex items-center justify-between text-sm">
                          <span className="capitalize text-muted-foreground">{row.provider}</span>
                          <span className="font-semibold">{formatCurrency(row.cost_usd)}</span>
                        </div>
                      ))
                    ) : (
                      <p className="text-sm text-muted-foreground">No provider usage yet.</p>
                    )}
                  </CardContent>
                </Card>

                <Card className="border-border/50 bg-card/60">
                  <CardHeader className="pb-3">
                    <CardTitle className="text-base font-semibold">Top Models</CardTitle>
                  </CardHeader>
                  <CardContent className="space-y-3">
                    {usage?.by_model.length ? (
                      usage.by_model.map((row) => (
                        <div key={`${row.provider}-${row.model}`} className="flex items-center justify-between text-sm">
                          <span className="text-muted-foreground">
                            {row.provider}:{row.model}
                          </span>
                          <span className="font-semibold">{formatCurrency(row.cost_usd)}</span>
                        </div>
                      ))
                    ) : (
                      <p className="text-sm text-muted-foreground">No model usage recorded yet.</p>
                    )}
                  </CardContent>
                </Card>
              </div>

              <div className="grid gap-4 lg:grid-cols-[1.3fr_1fr]">
                <Card className="border-border/50 bg-card/60">
                  <CardHeader>
                    <CardTitle>Budget Control</CardTitle>
                  </CardHeader>
                  <CardContent className="space-y-4">
                    {budget?.budget ? (
                      <>
                        <div className="flex items-center justify-between text-sm">
                          <span className="text-muted-foreground">Spent this month</span>
                          <span className="font-semibold">{formatCurrency(budgetUsed)}</span>
                        </div>
                        <div className="flex items-center justify-between text-sm">
                          <span className="text-muted-foreground">Monthly limit</span>
                          <span className="font-semibold">{formatCurrency(budgetLimitValue)}</span>
                        </div>
                        <div className="h-2 rounded-full bg-muted/60 overflow-hidden">
                          <div
                            className="h-full bg-emerald-500 transition-all"
                            style={{ width: `${Math.round(budgetProgress * 100)}%` }}
                          />
                        </div>
                        <div className="text-xs text-muted-foreground">
                          Warning at {formatPercent(budget?.budget?.warning_threshold_pct)}
                        </div>
                      </>
                    ) : (
                      <p className="text-sm text-muted-foreground">
                        No budget configured yet. Set one to unlock alerts.
                      </p>
                    )}

                    <div className="grid gap-3 sm:grid-cols-2">
                      <div>
                        <label className="text-xs text-muted-foreground">Monthly limit (USD)</label>
                        <Input value={budgetLimit} onChange={(e) => setBudgetLimit(e.target.value)} placeholder="200" />
                      </div>
                      <div>
                        <label className="text-xs text-muted-foreground">Warning threshold (%)</label>
                        <Input
                          value={budgetThreshold}
                          onChange={(e) => setBudgetThreshold(e.target.value)}
                          placeholder="80"
                        />
                      </div>
                    </div>
                    <Button onClick={saveBudget} disabled={isSavingBudget || !budgetLimit}>
                      {isSavingBudget ? <Spinner size="xs" className="mr-2" /> : null}
                      Save budget
                    </Button>
                  </CardContent>
                </Card>

                <Card className="border-border/50 bg-card/60">
                  <CardHeader>
                    <CardTitle>Usage and Quota</CardTitle>
                  </CardHeader>
                  <CardContent className="space-y-3">
                    <div className="flex items-center justify-between text-sm">
                      <span className="text-muted-foreground">Prompt tokens</span>
                      <span className="font-semibold">{formatNumber(usage?.totals.prompt_tokens)}</span>
                    </div>
                    <div className="flex items-center justify-between text-sm">
                      <span className="text-muted-foreground">Completion tokens</span>
                      <span className="font-semibold">{formatNumber(usage?.totals.completion_tokens)}</span>
                    </div>
                    <div className="flex items-center justify-between text-sm">
                      <span className="text-muted-foreground">Total tokens</span>
                      <span className="font-semibold">{formatNumber(usage?.totals.total_tokens)}</span>
                    </div>
                    <div className="mt-4 rounded-xl border border-border/40 bg-muted/30 px-3 py-3">
                      <div className="flex items-center justify-between text-sm">
                        <span className="text-muted-foreground">Monthly token quota</span>
                        <span className="font-semibold">
                          {quota?.quota?.monthly_token_limit != null
                            ? formatNumber(quota.quota.monthly_token_limit)
                            : "Not set"}
                        </span>
                      </div>
                      <div className="mt-2 flex items-center justify-between text-sm">
                        <span className="text-muted-foreground">Monthly cost quota</span>
                        <span className="font-semibold">
                          {quota?.quota?.monthly_cost_limit_usd != null
                            ? formatCurrency(quota.quota.monthly_cost_limit_usd)
                            : "Not set"}
                        </span>
                      </div>
                      <div className="mt-2 flex items-center justify-between text-sm">
                        <span className="text-muted-foreground">Usage this month</span>
                        <span className="font-semibold">{formatNumber(quota?.usage.month_total_tokens)} tokens</span>
                      </div>
                    </div>
                  </CardContent>
                </Card>
              </div>
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
