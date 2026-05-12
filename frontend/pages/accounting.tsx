import { useEffect, useMemo, useReducer } from "react";
import { Building2, CircleDollarSign, CircleOff, ReceiptText, Wallet } from "lucide-react";

import DashboardLayout from "@/components/DashboardLayout";
import {
  EmptyBlock,
  InspectorPanel,
  MetricCard,
  Panel,
  SectionHeader,
  StatusBadge,
  TrendBar,
  formatCurrency,
  formatDateTime,
} from "@/components/os/operations-ui";
import ProtectedRoute from "@/components/ProtectedRoute";
import { Alert, AlertDescription, Spinner } from "@/components/ui";
import { translateProductError } from "@/domain/errors";
import { accountingRepository } from "@/domain/repositories";
import type {
  AccountingLedgerEntryVM,
  AccountingOverviewVM,
  MetricProvenanceVM,
} from "@/domain/translation/viewModels";

const notInstrumentedLabel = "Not yet instrumented";

function metricProvenanceLine(metric: MetricProvenanceVM): string {
  const computedAt = metric.computedAt ? `Computed ${formatDateTime(metric.computedAt)}` : "computed_at unavailable";
  const freshness = typeof metric.freshnessMs === "number" ? ` · freshness ${Math.round(metric.freshnessMs)}ms` : "";

  return `${metric.source} · ${computedAt}${freshness}`;
}

function financialMetricLabel(metric: MetricProvenanceVM): string {
  if (metric.status === "available" && typeof metric.value === "number") {
    return formatCurrency(metric.value);
  }

  return notInstrumentedLabel;
}

type AccountingState = {
  overview: AccountingOverviewVM | null;
  ledger: AccountingLedgerEntryVM[];
  loading: boolean;
  error: string | null;
};

type AccountingAction =
  | { type: "loaded"; overview: AccountingOverviewVM; ledger: AccountingLedgerEntryVM[] }
  | { type: "failed"; error: string };

function accountingReducer(state: AccountingState, action: AccountingAction): AccountingState {
  switch (action.type) {
    case "loaded":
      return { ...state, overview: action.overview, ledger: action.ledger, loading: false, error: null };
    case "failed":
      return { ...state, loading: false, error: action.error };
    default:
      return state;
  }
}

export default function AccountingPage() {
  const [{ overview, ledger, loading, error }, dispatch] = useReducer(accountingReducer, {
    overview: null,
    ledger: [],
    loading: true,
    error: null,
  });

  useEffect(() => {
    let cancelled = false;

    const load = async () => {
      try {
        const [overviewData, ledgerData] = await Promise.all([
          accountingRepository.getOverview(),
          accountingRepository.listLedger(),
        ]);
        if (!cancelled) {
          dispatch({ type: "loaded", overview: overviewData, ledger: ledgerData.slice(0, 12) });
        }
      } catch (err: unknown) {
        if (!cancelled) {
          dispatch({ type: "failed", error: translateProductError(err, "accounting") });
        }
      }
    };

    void load();

    return () => {
      cancelled = true;
    };
  }, []);

  const accountingState = useMemo(() => {
    if (!overview) {
      return null;
    }

    return {
      trackedCost: overview.totalCostUsd,
      maxTypeCost: Math.max(...overview.costByType.map((entry) => entry.totalCostUsd), 1),
      maxDepartmentCost: Math.max(...overview.topDepartments.map((department) => department.totalCostUsd), 1),
    };
  }, [overview]);

  const inspector =
    overview && accountingState ? (
      <InspectorPanel
        title="Accounting posture"
        subtitle="Costs stay append-only and canonical. Revenue and profit remain unavailable until backend accounting instruments them."
        sections={[
          {
            title: "Backend metrics",
            content: (
              <div className="space-y-2">
                <div className="flex items-center justify-between">
                  <span>Spend</span>
                  <span>{financialMetricLabel(overview.metricProvenance.totalCostUsd)}</span>
                </div>
                <div className="flex items-center justify-between">
                  <span>Revenue</span>
                  <span>{notInstrumentedLabel}</span>
                </div>
                <div className="flex items-center justify-between">
                  <span>Profit</span>
                  <span>{notInstrumentedLabel}</span>
                </div>
                <p className="pt-2 text-xs leading-5 text-zinc-500 dark:text-zinc-400">
                  {metricProvenanceLine(overview.metricProvenance.totalCostUsd)}
                </p>
              </div>
            ),
          },
          {
            title: "Instrumentation",
            content: (
              <div className="space-y-2">
                <div className="flex items-center justify-between">
                  <span>Revenue source</span>
                  <span>{overview.metricProvenance.revenue.source}</span>
                </div>
                <div className="flex items-center justify-between">
                  <span>Revenue status</span>
                  <StatusBadge status="pending" label={notInstrumentedLabel} />
                </div>
              </div>
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
            eyebrow="Accounting"
            title="Economic state of the AI organization"
            description="This surface shows backend-owned cost records. Revenue and profit stay unavailable until backend instrumentation exists."
          />

          {error ? (
            <Alert variant="destructive">
              <AlertDescription>{error}</AlertDescription>
            </Alert>
          ) : null}

          {loading || !overview || !accountingState ? (
            <div className="flex min-h-[320px] items-center justify-center rounded-[1.75rem] border border-zinc-900/10 bg-white/70 dark:border-white/10 dark:bg-zinc-950/50">
              <Spinner size="lg" />
            </div>
          ) : (
            <>
              <div className="grid gap-4 xl:grid-cols-5">
                <MetricCard
                  eyebrow="Cost today"
                  value={financialMetricLabel(overview.metricProvenance.totalCostUsd)}
                  delta={metricProvenanceLine(overview.metricProvenance.totalCostUsd)}
                  tone="rose"
                  icon={<Wallet className="size-4" />}
                />
                <MetricCard
                  eyebrow="Cost sources"
                  value={overview.costByType.length.toLocaleString()}
                  delta="Backend ledger cost types"
                  icon={<ReceiptText className="size-4" />}
                />
                <MetricCard
                  eyebrow="Departments"
                  value={overview.topDepartments.length.toLocaleString()}
                  delta="Backend departments with spend"
                  icon={<Building2 className="size-4" />}
                />
                <MetricCard
                  eyebrow="Revenue"
                  value={notInstrumentedLabel}
                  delta={metricProvenanceLine(overview.metricProvenance.revenue)}
                  tone="slate"
                  icon={<CircleDollarSign className="size-4" />}
                />
                <MetricCard
                  eyebrow="Profit / loss"
                  value={notInstrumentedLabel}
                  delta={metricProvenanceLine(overview.metricProvenance.profit)}
                  tone="slate"
                  icon={<CircleOff className="size-4" />}
                />
              </div>

              <div className="grid gap-6 2xl:grid-cols-[0.92fr_1.08fr]">
                <Panel title="Cost breakdown" description="Cost by source type with a small trend indication.">
                  <div className="space-y-4">
                    {overview.costByType.length ? (
                      overview.costByType.map((entry) => (
                        <div
                          key={entry.id}
                          className="rounded-[1.2rem] border border-zinc-900/8 bg-[var(--panel-muted)] p-4 dark:border-white/8"
                        >
                          <div className="flex items-center justify-between gap-3">
                            <div>
                              <p className="text-sm font-semibold text-zinc-950 dark:text-zinc-50">{entry.label}</p>
                              <p className="mt-1 text-xs text-zinc-500 dark:text-zinc-400">
                                {entry.entryCount} ledger entries
                              </p>
                            </div>
                            <p className="text-sm font-semibold text-zinc-950 dark:text-zinc-50">
                              {formatCurrency(entry.totalCostUsd)}
                            </p>
                          </div>
                          <div className="mt-3">
                            <TrendBar
                              value={entry.totalCostUsd}
                              total={accountingState.maxTypeCost}
                              tone={entry.label === "llm" ? "rose" : "cyan"}
                            />
                          </div>
                        </div>
                      ))
                    ) : (
                      <EmptyBlock
                        title="No cost data"
                        description="Cost aggregates will appear here after ledger entries are projected."
                      />
                    )}
                  </div>
                </Panel>

                <Panel title="By department" description="Ranked operator view of where spend is concentrating.">
                  <div className="space-y-4">
                    {overview.topDepartments.length ? (
                      overview.topDepartments.map((department) => (
                        <div
                          key={department.id}
                          className="rounded-[1.2rem] border border-zinc-900/8 bg-[var(--panel-muted)] p-4 dark:border-white/8"
                        >
                          <div className="flex items-center justify-between gap-3">
                            <div>
                              <p className="text-sm font-semibold text-zinc-950 dark:text-zinc-50">
                                {department.displayName}
                              </p>
                              <p className="mt-1 text-xs text-zinc-500 dark:text-zinc-400">{department.status}</p>
                            </div>
                            <p className="text-sm font-semibold text-zinc-950 dark:text-zinc-50">
                              {formatCurrency(department.totalCostUsd)}
                            </p>
                          </div>
                          <div className="mt-3">
                            <TrendBar
                              value={department.totalCostUsd}
                              total={accountingState.maxDepartmentCost}
                              tone="rose"
                            />
                          </div>
                        </div>
                      ))
                    ) : (
                      <EmptyBlock
                        title="No department spend yet"
                        description="Department spend rollups appear once usage is attached to accounting records."
                      />
                    )}
                  </div>
                </Panel>
              </div>

              <Panel title="Ledger" description="Atomic accounting records kept close to the backend-governed ledger.">
                {ledger.length ? (
                  <div className="overflow-hidden rounded-[1.4rem] border border-zinc-900/8 dark:border-white/8">
                    <table className="min-w-full divide-y divide-zinc-900/8 dark:divide-white/8">
                      <thead className="bg-[var(--panel-muted)]">
                        <tr className="text-left text-[11px] uppercase tracking-[0.18em] text-zinc-500 dark:text-zinc-400">
                          <th className="px-4 py-3 font-medium">Source</th>
                          <th className="px-4 py-3 font-medium">Usage</th>
                          <th className="px-4 py-3 font-medium">Cost</th>
                          <th className="px-4 py-3 font-medium">Trend</th>
                          <th className="px-4 py-3 font-medium">Occurred</th>
                        </tr>
                      </thead>
                      <tbody className="divide-y divide-zinc-900/8 dark:divide-white/8">
                        {ledger.map((entry) => (
                          <tr key={entry.id} className="bg-white/70 dark:bg-white/3">
                            <td className="p-4 text-sm">
                              <div>
                                <p className="font-medium text-zinc-950 dark:text-zinc-50">{entry.sourceLabel}</p>
                                <p className="mt-1 text-xs text-zinc-500 dark:text-zinc-400">
                                  {entry.provider} · {entry.model}
                                </p>
                              </div>
                            </td>
                            <td className="p-4 text-sm text-zinc-600 dark:text-zinc-300">
                              {entry.quantity.toLocaleString()} {entry.usageLabel}
                            </td>
                            <td className="p-4 text-sm font-medium text-zinc-950 dark:text-zinc-50">
                              {formatCurrency(entry.totalCostUsd)}
                            </td>
                            <td className="p-4 text-sm">
                              <StatusBadge
                                status={entry.totalCostUsd > 1 ? "paused" : "active"}
                                label={entry.totalCostUsd > 1 ? "Up" : "Flat"}
                              />
                            </td>
                            <td className="p-4 text-sm text-zinc-500 dark:text-zinc-400">
                              {formatDateTime(entry.occurredAt)}
                            </td>
                          </tr>
                        ))}
                      </tbody>
                    </table>
                  </div>
                ) : (
                  <EmptyBlock
                    title="Ledger is empty"
                    description="Ledger entries will appear here after accounting jobs process usage facts."
                  />
                )}
              </Panel>
            </>
          )}
        </div>
      </DashboardLayout>
    </ProtectedRoute>
  );
}
