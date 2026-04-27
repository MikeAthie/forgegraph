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

type CompanyListState = {
  graph: GraphListItem;
  latestVersion: GraphVersion | null;
  operations: RunListItem[];
  pendingApprovals: number;
};

export default function CompaniesIndexPage() {
  const [companies, setCompanies] = useState<CompanyListState[]>([]);
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
      active: companies.filter((company) =>
        company.operations.some((run) => translateRunStatus(String(run.status)) === "running"),
      ).length,
      attention: companies.filter(
        (company) => getCompanyStatus(company.operations, company.pendingApprovals) === "Needs attention",
      ).length,
    }),
    [companies],
  );

  return (
    <ProtectedRoute>
      <DashboardLayout
        inspector={
          <InspectorPanel
            title="Company Index"
            subtitle="This route is the company-first entry point for continuing work."
            sections={[
              {
                title: "Translation",
                content:
                  "This list is the company workspace portfolio: every card should tell you what the company does and whether it needs you.",
              },
              {
                title: "Focus",
                content: "Use this screen to select a company, continue work, or launch a new builder flow.",
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
                  <div className="rounded-[1.2rem] border border-slate-900/8 bg-[var(--panel-muted)] px-4 py-4 dark:border-white/8">
                    <p className="text-[11px] uppercase tracking-[0.18em] text-slate-500 dark:text-slate-400">
                      Companies
                    </p>
                    <p className="mt-2 text-2xl font-semibold text-slate-950 dark:text-slate-50">
                      {formatCompactNumber(summary.total)}
                    </p>
                  </div>
                  <div className="rounded-[1.2rem] border border-slate-900/8 bg-[var(--panel-muted)] px-4 py-4 dark:border-white/8">
                    <p className="text-[11px] uppercase tracking-[0.18em] text-slate-500 dark:text-slate-400">
                      Operating now
                    </p>
                    <p className="mt-2 text-2xl font-semibold text-slate-950 dark:text-slate-50">
                      {formatCompactNumber(summary.active)}
                    </p>
                  </div>
                  <div className="rounded-[1.2rem] border border-slate-900/8 bg-[var(--panel-muted)] px-4 py-4 dark:border-white/8">
                    <p className="text-[11px] uppercase tracking-[0.18em] text-slate-500 dark:text-slate-400">
                      Need attention
                    </p>
                    <p className="mt-2 text-2xl font-semibold text-slate-950 dark:text-slate-50">
                      {formatCompactNumber(summary.attention)}
                    </p>
                  </div>
                </div>
              </Panel>

              <Panel title="Company workspace" description="Continue work from the company you want to operate.">
                {companies.length ? (
                  <div className="grid gap-4 lg:grid-cols-2">
                    {companies.map((company) => {
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
                          className="rounded-[1.35rem] border border-slate-900/8 bg-[var(--panel-muted)] px-5 py-5 transition-colors hover:bg-slate-950 hover:text-white dark:border-white/8 dark:hover:bg-white dark:hover:text-slate-950"
                        >
                          <div className="flex items-start justify-between gap-4">
                            <div className="min-w-0">
                              <div className="flex items-center gap-3">
                                <span className="flex h-10 w-10 items-center justify-center rounded-2xl border border-slate-900/10 bg-white dark:border-white/10 dark:bg-white/5">
                                  <Building2 className="h-4 w-4" />
                                </span>
                                <div className="min-w-0">
                                  <p className="truncate text-sm font-semibold">{profile.companyName}</p>
                                  <p className="mt-1 text-xs text-slate-500 dark:text-slate-400">
                                    {profile.companyType}
                                  </p>
                                </div>
                              </div>
                              <p className="mt-4 text-sm leading-6 text-slate-600 dark:text-slate-300">
                                {profile.objective}
                              </p>
                            </div>
                            <StatusBadge
                              status={
                                status === "Needs attention" ? "failed" : status === "Operating" ? "running" : "pending"
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

                          <div className="mt-4 flex items-center justify-between gap-3 text-xs text-slate-500 dark:text-slate-400">
                            <span>
                              {latestOperation
                                ? `Latest activity ${formatDateTime(latestOperation.started_at)}`
                                : "No operations yet"}
                            </span>
                            <span className="inline-flex items-center gap-1 font-medium text-slate-900 dark:text-slate-50">
                              Open workspace
                              <ArrowRight className="h-3.5 w-3.5" />
                            </span>
                          </div>
                        </Link>
                      );
                    })}
                  </div>
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
