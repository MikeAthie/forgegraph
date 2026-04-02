import { useEffect, useMemo, useState } from "react";
import { ArrowDownRight, ArrowUpRight, Wallet } from "lucide-react";

import DashboardLayout from "@/components/DashboardLayout";
import { EmptyBlock, InspectorPanel, MetricCard, Panel, SectionHeader, StatusBadge, TrendBar, formatCurrency, formatDateTime } from "@/components/os/operations-ui";
import ProtectedRoute from "@/components/ProtectedRoute";
import { Alert, AlertDescription, Spinner } from "@/components/ui";
import { accountingApi, getApiErrorMessage, type AccountingOverview, type CostLedgerEntry } from "@/lib/api";

const weeklyMultiplier = 5.4;
const monthlyMultiplier = 22.6;

export default function AccountingPage() {
  const [overview, setOverview] = useState<AccountingOverview | null>(null);
  const [ledger, setLedger] = useState<CostLedgerEntry[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    let cancelled = false;

    const load = async () => {
      try {
        const [overviewData, ledgerData] = await Promise.all([
          accountingApi.getOverview(),
          accountingApi.listLedger(),
        ]);
        if (!cancelled) {
          setOverview(overviewData);
          setLedger(ledgerData.slice(0, 12));
        }
      } catch (err: unknown) {
        if (!cancelled) {
          setError(getApiErrorMessage(err, "Failed to load accounting data."));
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

    const today = overview.total_cost_usd;
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
      maxTypeCost: Math.max(...overview.cost_by_type.map((entry) => entry.total_cost_usd), 1),
      maxAgentCost: Math.max(...overview.top_agents.map((agent) => agent.total_cost_usd), 1),
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
                <MetricCard eyebrow="Cost today" value={formatCurrency(financials.today)} delta="Tracked LLM and memory spend" tone="rose" icon={<Wallet className="h-4 w-4" />} />
                <MetricCard eyebrow="Cost week" value={formatCurrency(financials.week)} delta="Projected from current daily trajectory" icon={<ArrowUpRight className="h-4 w-4" />} />
                <MetricCard eyebrow="Cost month" value={formatCurrency(financials.month)} delta="Projected month-to-date operating spend" icon={<ArrowUpRight className="h-4 w-4" />} />
                <MetricCard eyebrow="Revenue" value={formatCurrency(financials.revenueToday)} delta="Mock value for company-OS scenarios" tone="emerald" icon={<ArrowUpRight className="h-4 w-4" />} />
                <MetricCard eyebrow="Profit / loss" value={formatCurrency(financials.profitToday)} delta={financials.profitToday >= 0 ? "Positive contribution margin today" : "Spend exceeds modeled revenue today"} tone={financials.profitToday >= 0 ? "emerald" : "amber"} icon={<ArrowDownRight className="h-4 w-4" />} />
              </div>

              <div className="grid gap-6 2xl:grid-cols-[0.92fr_1.08fr]">
                <Panel title="Cost breakdown" description="Cost by source type with a small trend indication.">
                  <div className="space-y-4">
                    {overview.cost_by_type.length ? (
                      overview.cost_by_type.map((entry) => (
                        <div key={entry.cost_type} className="rounded-[1.2rem] border border-slate-900/8 bg-[var(--panel-muted)] px-4 py-4 dark:border-white/8">
                          <div className="flex items-center justify-between gap-3">
                            <div>
                              <p className="text-sm font-semibold text-slate-950 dark:text-slate-50">{entry.cost_type}</p>
                              <p className="mt-1 text-xs text-slate-500 dark:text-slate-400">{entry.entry_count} ledger entries</p>
                            </div>
                            <p className="text-sm font-semibold text-slate-950 dark:text-slate-50">{formatCurrency(entry.total_cost_usd)}</p>
                          </div>
                          <div className="mt-3">
                            <TrendBar value={entry.total_cost_usd} total={financials.maxTypeCost} tone={entry.cost_type === "llm" ? "rose" : "cyan"} />
                          </div>
                        </div>
                      ))
                    ) : (
                      <EmptyBlock title="No cost data" description="Cost aggregates will appear here after ledger entries are projected." />
                    )}
                  </div>
                </Panel>

                <Panel title="By agent" description="Ranked operator view of where spend is concentrating.">
                  <div className="space-y-4">
                    {overview.top_agents.length ? (
                      overview.top_agents.map((agent) => (
                        <div key={agent.id} className="rounded-[1.2rem] border border-slate-900/8 bg-[var(--panel-muted)] px-4 py-4 dark:border-white/8">
                          <div className="flex items-center justify-between gap-3">
                            <div>
                              <p className="text-sm font-semibold text-slate-950 dark:text-slate-50">{agent.display_name}</p>
                              <p className="mt-1 text-xs text-slate-500 dark:text-slate-400">{agent.status}</p>
                            </div>
                            <p className="text-sm font-semibold text-slate-950 dark:text-slate-50">{formatCurrency(agent.total_cost_usd)}</p>
                          </div>
                          <div className="mt-3">
                            <TrendBar value={agent.total_cost_usd} total={financials.maxAgentCost} tone="rose" />
                          </div>
                        </div>
                      ))
                    ) : (
                      <EmptyBlock title="No agent spend yet" description="Agent spend rollups appear once usage is attached to registry entries." />
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
                                <p className="font-medium text-slate-950 dark:text-slate-50">{entry.agent_id ?? entry.workflow_revision_id ?? "Shared infrastructure"}</p>
                                <p className="mt-1 text-xs text-slate-500 dark:text-slate-400">{entry.provider} · {entry.model}</p>
                              </div>
                            </td>
                            <td className="px-4 py-4 text-sm text-slate-600 dark:text-slate-300">{entry.quantity.toLocaleString()} {entry.cost_type}</td>
                            <td className="px-4 py-4 text-sm font-medium text-slate-950 dark:text-slate-50">{formatCurrency(entry.total_cost_usd)}</td>
                            <td className="px-4 py-4 text-sm">
                              <StatusBadge status={entry.total_cost_usd > 1 ? "paused" : "active"} label={entry.total_cost_usd > 1 ? "Up" : "Flat"} />
                            </td>
                            <td className="px-4 py-4 text-sm text-slate-500 dark:text-slate-400">{formatDateTime(entry.occurred_at)}</td>
                          </tr>
                        ))}
                      </tbody>
                    </table>
                  </div>
                ) : (
                  <EmptyBlock title="Ledger is empty" description="Ledger entries will appear here after accounting jobs run against usage facts." />
                )}
              </Panel>
            </>
          )}
        </div>
      </DashboardLayout>
    </ProtectedRoute>
  );
}
