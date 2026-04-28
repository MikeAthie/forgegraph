import { useEffect, useMemo, useState } from "react";
import Link from "next/link";
import { ArrowRight, Building2, Plus } from "lucide-react";

import DashboardLayout from "@/components/DashboardLayout";
import ProtectedRoute from "@/components/ProtectedRoute";
import {
  EmptyBlock,
  InspectorPanel,
  Panel,
  SectionHeader,
  StatusBadge,
  formatCompactNumber,
  formatDateTime,
} from "@/components/os/operations-ui";
import { Alert, AlertDescription, Button, Spinner } from "@/components/ui";
import { approvalsApi, getApiErrorMessage, graphsApi, runsApi, type GraphListItem, type RunListItem } from "@/lib/api";
import { getCompanyProfileFromGraph, getCompanyStatus, translateRunStatus } from "@/lib/company-workspace";
import type { GraphVersion } from "@/lib/graph-types";
import { cn } from "@/lib/utils";

type CompanyListState = {
  graph: GraphListItem;
  latestVersion: GraphVersion | null;
  operations: RunListItem[];
  pendingApprovals: number;
};

type CompanyFilter = "all" | "operating" | "attention";

function isCompanyOperating(company: CompanyListState): boolean {
  return company.operations.some((run) => translateRunStatus(String(run.status)) === "running");
}

function needsAttention(company: CompanyListState): boolean {
  const status = getCompanyStatus(company.operations, company.pendingApprovals);
  return status === "Needs attention" || status === "Awaiting approval";
}

export default function CompaniesIndexPage() {
  const [companies, setCompanies] = useState<CompanyListState[]>([]);
  const [activeFilter, setActiveFilter] = useState<CompanyFilter>("all");
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    let cancelled = false;

    const load = async () => {
      try {
        const [graphs, runs, approvals] = await Promise.all([
          graphsApi.list(),
          runsApi.list(),
          approvalsApi.list("pending"),
        ]);
        const versions = await Promise.all(graphs.map((graph) => graphsApi.getLatestVersion(graph.id)));

        if (!cancelled) {
          setCompanies(
            graphs.map((graph, index) => {
              const graphRuns = runs
                .filter((run) => run.graph_id === graph.id)
                .sort((a, b) => (b.started_at ?? "").localeCompare(a.started_at ?? ""));
              const graphRunIds = new Set(graphRuns.map((run) => run.id));
              const pendingApprovals = approvals.filter((approval) => graphRunIds.has(approval.run_id)).length;
              return {
                graph,
                latestVersion: versions[index] ?? null,
                operations: graphRuns,
                pendingApprovals,
              };
            }),
          );
        }
      } catch (loadError: unknown) {
        if (!cancelled) {
          setError(getApiErrorMessage(loadError, "Failed to load companies."));
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

  const summary = useMemo(
    () => ({
      total: companies.length,
      active: companies.filter(isCompanyOperating).length,
      attention: companies.filter(needsAttention).length,
    }),
    [companies],
  );

  const filteredCompanies = useMemo(() => {
    if (activeFilter === "operating") {
      return companies.filter(isCompanyOperating);
    }
    if (activeFilter === "attention") {
      return companies.filter(needsAttention);
    }
    return companies;
  }, [activeFilter, companies]);

  const filterCards: Array<{
    id: CompanyFilter;
    label: string;
    value: number;
    description: string;
  }> = [
    {
      id: "all",
      label: "Total companies",
      value: summary.total,
      description: "Every company in this workspace",
    },
    {
      id: "operating",
      label: "Operating now",
      value: summary.active,
      description: "Companies with live work in progress",
    },
    {
      id: "attention",
      label: "Need attention",
      value: summary.attention,
      description: "Failures or approvals waiting on you",
    },
  ];

  return (
    <ProtectedRoute>
      <DashboardLayout
        inspector={
          <InspectorPanel
            title="Company Portfolio"
            subtitle="Use this view to decide where attention should go next across the companies in this organization."
            sections={[
              {
                title: "Read the posture",
                content:
                  "The three summary cards filter the list. Start with companies that need attention, then check work currently operating.",
              },
              {
                title: "Pick the next move",
                content:
                  "Open a company when you need the operation history, latest deliverable, departments, or controls to launch another operation.",
              },
            ]}
          />
        }
      >
        <div className="space-y-6">
          <SectionHeader
            eyebrow="Companies"
            title="Operate AI-driven companies"
            description="Select an existing company, review its current posture, or create a new company without seeing engine language."
            action={
              <Button asChild className="rounded-full">
                <Link href="/companies/new">
                  <Plus className="h-4 w-4" />
                  Create company
                </Link>
              </Button>
            }
          />

          {error ? (
            <Alert variant="destructive">
              <AlertDescription>{error}</AlertDescription>
            </Alert>
          ) : null}

          {loading ? (
            <div className="flex min-h-[320px] items-center justify-center rounded-[1.75rem] border border-slate-900/10 bg-white/70 dark:border-white/10 dark:bg-slate-950/50">
              <Spinner size="lg" />
            </div>
          ) : (
            <>
              <Panel
                title="Portfolio posture"
                description="A fast read of the companies currently available in this workspace."
              >
                <div className="grid gap-3 md:grid-cols-3">
                  {filterCards.map((filter) => {
                    const selected = activeFilter === filter.id;
                    return (
                      <button
                        key={filter.id}
                        type="button"
                        aria-pressed={selected}
                        onClick={() => setActiveFilter(filter.id)}
                        className={cn(
                          "min-h-[7.75rem] rounded-[1.2rem] border px-4 py-4 text-left transition-colors focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-slate-950 focus-visible:ring-offset-2 focus-visible:ring-offset-white dark:focus-visible:ring-slate-100 dark:focus-visible:ring-offset-slate-950",
                          selected
                            ? "border-slate-950 bg-slate-950 text-white shadow-[0_24px_48px_-34px_rgba(15,23,42,0.85)] dark:border-slate-100 dark:bg-slate-100 dark:text-slate-950"
                            : "border-slate-900/8 bg-[var(--panel-muted)] hover:bg-white dark:border-white/8 dark:hover:bg-white/8",
                        )}
                      >
                        <p
                          className={cn(
                            "text-[11px] uppercase tracking-[0.18em]",
                            selected ? "text-white/70 dark:text-slate-600" : "text-slate-500 dark:text-slate-400",
                          )}
                        >
                          {filter.label}
                        </p>
                        <p
                          className={cn(
                            "mt-2 text-2xl font-semibold",
                            selected ? "text-white dark:text-slate-950" : "text-slate-950 dark:text-slate-50",
                          )}
                        >
                          {formatCompactNumber(filter.value)}
                        </p>
                        <p
                          className={cn(
                            "mt-3 text-xs leading-5",
                            selected ? "text-white/70 dark:text-slate-600" : "text-slate-500 dark:text-slate-400",
                          )}
                        >
                          {filter.description}
                        </p>
                      </button>
                    );
                  })}
                </div>
              </Panel>

              <Panel
                title="Company workspace"
                description={`Showing ${formatCompactNumber(filteredCompanies.length)} of ${formatCompactNumber(summary.total)} companies.`}
              >
                {companies.length ? (
                  filteredCompanies.length ? (
                    <div className="grid gap-4 lg:grid-cols-2">
                      {filteredCompanies.map((company) => {
                        const profile = getCompanyProfileFromGraph(
                          company.graph,
                          company.latestVersion?.graph_json ?? null,
                        );
                        const status = getCompanyStatus(company.operations, company.pendingApprovals);
                        const latestOperation = company.operations[0];

                        return (
                          <Link
                            key={company.graph.id}
                            href={`/companies/${company.graph.id}`}
                            className="group rounded-[1.35rem] border border-slate-900/8 bg-[var(--panel-muted)] px-5 py-5 transition-all duration-200 ease-out hover:-translate-y-0.5 hover:border-slate-900/18 hover:bg-white hover:shadow-[0_24px_56px_-42px_rgba(15,23,42,0.55)] focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-slate-950 focus-visible:ring-offset-2 focus-visible:ring-offset-white dark:border-white/8 dark:hover:border-white/18 dark:hover:bg-white/[0.07] dark:hover:shadow-[0_24px_56px_-42px_rgba(0,0,0,0.75)] dark:focus-visible:ring-slate-100 dark:focus-visible:ring-offset-slate-950"
                          >
                            <div className="flex items-start justify-between gap-4">
                              <div className="min-w-0">
                                <div className="flex items-center gap-3">
                                  <span className="flex h-10 w-10 shrink-0 items-center justify-center rounded-2xl border border-slate-900/10 bg-white text-slate-700 transition-colors group-hover:border-slate-900/20 group-hover:bg-slate-950 group-hover:text-white dark:border-white/10 dark:bg-white/5 dark:text-slate-200 dark:group-hover:border-white/20 dark:group-hover:bg-white dark:group-hover:text-slate-950">
                                    <Building2 className="h-4 w-4" />
                                  </span>
                                  <div className="min-w-0">
                                    <p className="truncate text-sm font-semibold text-slate-950 dark:text-slate-50">
                                      {profile.companyName}
                                    </p>
                                    <p className="mt-1 text-xs text-slate-500 transition-colors group-hover:text-slate-600 dark:text-slate-400 dark:group-hover:text-slate-300">
                                      {profile.companyType}
                                    </p>
                                  </div>
                                </div>
                                <p className="mt-4 text-sm leading-6 text-slate-600 transition-colors group-hover:text-slate-700 dark:text-slate-300 dark:group-hover:text-slate-200">
                                  {profile.objective}
                                </p>
                              </div>
                              <StatusBadge
                                status={
                                  status === "Needs attention"
                                    ? "failed"
                                    : status === "Operating"
                                      ? "running"
                                      : "pending"
                                }
                                label={status}
                              />
                            </div>

                            <div className="mt-4 flex flex-wrap gap-2">
                              <StatusBadge status={profile.autonomyMode} label={profile.autonomyMode} />
                              <StatusBadge
                                status={profile.aiAccessMode === "managed" ? "active" : "paused"}
                                label={profile.aiAccessMode === "managed" ? "Managed" : "BYOK"}
                              />
                              <StatusBadge status="pending" label={`${company.operations.length} operations`} />
                            </div>

                            <div className="mt-4 flex items-center justify-between gap-3 text-xs text-slate-500 transition-colors group-hover:text-slate-600 dark:text-slate-400 dark:group-hover:text-slate-300">
                              <span>
                                {latestOperation
                                  ? `Latest activity ${formatDateTime(latestOperation.started_at)}`
                                  : "No operations yet"}
                              </span>
                              <span className="inline-flex items-center gap-1 font-medium text-slate-900 transition-colors group-hover:text-slate-950 dark:text-slate-50 dark:group-hover:text-white">
                                Open workspace
                                <ArrowRight className="h-3.5 w-3.5 transition-transform group-hover:translate-x-0.5" />
                              </span>
                            </div>
                          </Link>
                        );
                      })}
                    </div>
                  ) : (
                    <EmptyBlock
                      title="No companies match this filter"
                      description="Choose another posture card to return to the companies that are available right now."
                    />
                  )
                ) : (
                  <EmptyBlock
                    title="No companies yet"
                    description="Create the first company to begin operating ForgeGraph in company-first language."
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
