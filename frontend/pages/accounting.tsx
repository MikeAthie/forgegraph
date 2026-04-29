import { useEffect, useMemo, useState } from "react";
import { ArrowDownRight, ArrowUpRight, Wallet } from "lucide-react";

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
import type { AccountingLedgerEntryVM, AccountingOverviewVM } from "@/domain/translation/viewModels";

const weeklyMultiplier = 5.4;
const monthlyMultiplier = 22.6;

export default function AccountingPage() {
  const [overview, setOverview] = useState<AccountingOverviewVM | null>(null);
  const [ledger, setLedger] = useState<AccountingLedgerEntryVM[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    let cancelled = false;

    const load = async () => {
      try {
        const [overviewData, ledgerData] = await Promise.all([
          accountingRepository.getOverview(),
          accountingRepository.listLedger(),
        ]);
        if (!cancelled) {
          setOverview(overviewData);
          setLedger(ledgerData.slice(0, 12));
        }
      } catch (err: unknown) {
        if (!cancelled) {
          setError(translateProductError(err, "accounting"));
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
  }, []);

  const financials = useMemo(() => {
    if (!overview) {
      return null;
    }

    const today = overview.totalCostUsd;
    const week = Math.round(today * weeklyMultiplier * 100) / 100;
    const month = Math.round(today * monthlyMultiplier * 100) / 100;
    const revenueToday = Math.round((today * 4.8 + 1900) * 100) / 100;
    const revenueMonth = Math.round(revenueToday * 22 * 100) / 100;

    return {
      today,
      week,
      month,
      revenueToday,
      revenueMonth,
      profitToday: revenueToday - today,
      profitMonth: revenueMonth - month,
      maxTypeCost: Math.max(...overview.costByType.map((entry) => entry.totalCostUsd), 1),
      maxDepartmentCost: Math.max(...overview.topDepartments.map((department) => department.totalCostUsd), 1),
    };
  }, [overview]);

  const inspector = financials ? (
    <InspectorPanel
      title="Accounting posture"
      subtitle="Costs stay append-only and canonical. This screen is a read model that makes economic activity legible for operators."
      sections={[
        {
          title: "Today",
          content: (
            <div className="space-y-2">
              <div className="flex items-center justify-between">
                <span>Spend</span>
                <span>{formatCurrency(financials.today)}</span>
              </div>
              <div className="flex items-center justify-between">
                <span>Revenue</span>
                <span>{formatCurrency(financials.revenueToday)}</span>
              </div>
              <div className="flex items-center justify-between">
                <span>Profit</span>
                <span>{formatCurrency(financials.profitToday)}</span>
              </div>
            </div>
          ),
        },
        {
          title: "Month",
          content: (
            <div className="space-y-2">
              <div className="flex items-center justify-between">
                <span>Spend</span>
                <span>{formatCurrency(financials.month)}</span>
              </div>
              <div className="flex items-center justify-between">
                <span>Revenue</span>
                <span>{formatCurrency(financials.revenueMonth)}</span>
              </div>
              <div className="flex items-center justify-between">
                <span>Profit</span>
                <span>{formatCurrency(financials.profitMonth)}</span>
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
            description="This surface treats spend, revenue, and profit like operational facts. The interface stays closer to financial software than an analytics marketing dashboard."
          />

          {error ? (
            <Alert variant="destructive">
              <AlertDescription>{error}</AlertDescription>
            </Alert>
          ) : null}

          {loading || !overview || !financials ? (
            <div className="flex min-h-[320px] items-center justify-center rounded-[1.75rem] border border-slate-900/10 bg-white/70 dark:border-white/10 dark:bg-slate-950/50">
              <Spinner size="lg" />
            </div>
          ) : (
            <>
              <div className="grid gap-4 xl:grid-cols-5">
                <MetricCard
                  eyebrow="Cost today"
                  value={formatCurrency(financials.today)}
                  delta="Tracked LLM and memory spend"
                  tone="rose"
                  icon={<Wallet className="h-4 w-4" />}
                />
                <MetricCard
                  eyebrow="Cost week"
                  value={formatCurrency(financials.week)}
                  delta="Projected from current daily trajectory"
                  icon={<ArrowUpRight className="h-4 w-4" />}
                />
                <MetricCard
                  eyebrow="Cost month"
                  value={formatCurrency(financials.month)}
                  delta="Projected month-to-date operating spend"
                  icon={<ArrowUpRight className="h-4 w-4" />}
                />
                <MetricCard
                  eyebrow="Revenue"
                  value={formatCurrency(financials.revenueToday)}
                  delta="Mock value for company-OS scenarios"
                  tone="emerald"
                  icon={<ArrowUpRight className="h-4 w-4" />}
                />
                <MetricCard
                  eyebrow="Profit / loss"
                  value={formatCurrency(financials.profitToday)}
                  delta={
                    financials.profitToday >= 0
                      ? "Positive contribution margin today"
                      : "Spend exceeds modeled revenue today"
                  }
                  tone={financials.profitToday >= 0 ? "emerald" : "amber"}
                  icon={<ArrowDownRight className="h-4 w-4" />}
                />
              </div>

              <div className="grid gap-6 2xl:grid-cols-[0.92fr_1.08fr]">
                <Panel title="Cost breakdown" description="Cost by source type with a small trend indication.">
                  <div className="space-y-4">
                    {overview.costByType.length ? (
                      overview.costByType.map((entry) => (
                        <div
                          key={entry.id}
                          className="rounded-[1.2rem] border border-slate-900/8 bg-[var(--panel-muted)] px-4 py-4 dark:border-white/8"
                        >
                          <div className="flex items-center justify-between gap-3">
                            <div>
                              <p className="text-sm font-semibold text-slate-950 dark:text-slate-50">{entry.label}</p>
                              <p className="mt-1 text-xs text-slate-500 dark:text-slate-400">
                                {entry.entryCount} ledger entries
                              </p>
                            </div>
                            <p className="text-sm font-semibold text-slate-950 dark:text-slate-50">
                              {formatCurrency(entry.totalCostUsd)}
                            </p>
                          </div>
                          <div className="mt-3">
                            <TrendBar
                              value={entry.totalCostUsd}
                              total={financials.maxTypeCost}
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
                          className="rounded-[1.2rem] border border-slate-900/8 bg-[var(--panel-muted)] px-4 py-4 dark:border-white/8"
                        >
                          <div className="flex items-center justify-between gap-3">
                            <div>
                              <p className="text-sm font-semibold text-slate-950 dark:text-slate-50">
                                {department.displayName}
                              </p>
                              <p className="mt-1 text-xs text-slate-500 dark:text-slate-400">{department.status}</p>
                            </div>
                            <p className="text-sm font-semibold text-slate-950 dark:text-slate-50">
                              {formatCurrency(department.totalCostUsd)}
                            </p>
                          </div>
                          <div className="mt-3">
                            <TrendBar
                              value={department.totalCostUsd}
                              total={financials.maxDepartmentCost}
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

              <Panel title="Ledger" description="Atomic accounting records kept close to the source of truth.">
                {ledger.length ? (
                  <div className="overflow-hidden rounded-[1.4rem] border border-slate-900/8 dark:border-white/8">
                    <table className="min-w-full divide-y divide-slate-900/8 dark:divide-white/8">
                      <thead className="bg-[var(--panel-muted)]">
                        <tr className="text-left text-[11px] uppercase tracking-[0.18em] text-slate-500 dark:text-slate-400">
                          <th className="px-4 py-3 font-medium">Source</th>
                          <th className="px-4 py-3 font-medium">Usage</th>
                          <th className="px-4 py-3 font-medium">Cost</th>
                          <th className="px-4 py-3 font-medium">Trend</th>
                          <th className="px-4 py-3 font-medium">Occurred</th>
                        </tr>
                      </thead>
                      <tbody className="divide-y divide-slate-900/8 dark:divide-white/8">
                        {ledger.map((entry) => (
                          <tr key={entry.id} className="bg-white/70 dark:bg-white/3">
                            <td className="px-4 py-4 text-sm">
                              <div>
                                <p className="font-medium text-slate-950 dark:text-slate-50">{entry.sourceLabel}</p>
                                <p className="mt-1 text-xs text-slate-500 dark:text-slate-400">
                                  {entry.provider} · {entry.model}
                                </p>
                              </div>
                            </td>
                            <td className="px-4 py-4 text-sm text-slate-600 dark:text-slate-300">
                              {entry.quantity.toLocaleString()} {entry.usageLabel}
                            </td>
                            <td className="px-4 py-4 text-sm font-medium text-slate-950 dark:text-slate-50">
                              {formatCurrency(entry.totalCostUsd)}
                            </td>
                            <td className="px-4 py-4 text-sm">
                              <StatusBadge
                                status={entry.totalCostUsd > 1 ? "paused" : "active"}
                                label={entry.totalCostUsd > 1 ? "Up" : "Flat"}
                              />
                            </td>
                            <td className="px-4 py-4 text-sm text-slate-500 dark:text-slate-400">
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
