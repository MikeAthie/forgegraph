import { useEffect, useMemo, useState } from "react";
import Link from "next/link";
import {
  AlertTriangle,
  ArrowRight,
  BellRing,
  BrainCircuit,
  HandCoins,
  ShieldCheck,
  Siren,
  Waypoints,
} from "lucide-react";

import DashboardLayout from "@/components/DashboardLayout";
import {
  EmptyBlock,
  InspectorPanel,
  KeyValueGrid,
  MetricCard,
  Panel,
  StatusBadge,
  TimelineList,
  TrendBar,
  formatCompactNumber,
  formatCurrency,
  formatDateTime,
  overviewIcons,
} from "@/components/os/operations-ui";
import ProtectedRoute from "@/components/ProtectedRoute";
import { Alert, AlertDescription, Button, Spinner } from "@/components/ui";
import { translateProductError } from "@/domain/errors";
import { overviewRepository } from "@/domain/repositories";
import type { MetricProvenanceVM } from "@/domain/translation";
import type { OrganizationOverviewVM } from "@/domain/repositories/overviewRepository";

const notInstrumentedLabel = "Not yet instrumented";

type AttentionItem = {
  id: string;
  title: string;
  detail: string;
  owner: string;
  tone: "rose" | "amber";
  href: string;
  action: string;
};

const metricLinkClass =
  "group block h-full rounded-[1.75rem] focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-slate-950 focus-visible:ring-offset-2 focus-visible:ring-offset-white dark:focus-visible:ring-slate-100 dark:focus-visible:ring-offset-slate-950";

const metricCardLinkClass =
  "h-full transition-all duration-200 ease-out group-hover:-translate-y-0.5 group-hover:border-slate-900/20 group-hover:bg-white group-hover:shadow-[0_30px_70px_-48px_rgba(15,23,42,0.7)] dark:group-hover:border-white/20 dark:group-hover:bg-white/[0.07]";

function metricProvenanceLine(metric: MetricProvenanceVM): string {
  const computedAt = metric.computedAt ? `Computed ${formatDateTime(metric.computedAt)}` : "computed_at unavailable";
  const freshness = typeof metric.freshnessMs === "number" ? ` · freshness ${Math.round(metric.freshnessMs)}ms` : "";

  return `${metric.source} · ${computedAt}${freshness}`;
}

export default function OverviewPage() {
  const [overview, setOverview] = useState<OrganizationOverviewVM | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    let cancelled = false;

    const load = async () => {
      try {
        const data = await overviewRepository.get();
        if (!cancelled) {
          setOverview(data);
        }
      } catch (err: unknown) {
        if (!cancelled) {
          setError(translateProductError(err, "operation"));
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

  const derived = useMemo(() => {
    if (!overview) {
      return null;
    }

    const blockedTasks = overview.activeTasks.filter((task) => task.status === "paused" || task.status === "failed");
    const failedOperations = overview.recentOperations.filter((operation) => operation.status === "failed");

    const attentionItems: AttentionItem[] = [
      ...failedOperations.slice(0, 2).map((operation) => ({
        id: `failed-${operation.id}`,
        title: `${operation.companyName} needs attention`,
        detail: `Operation ${operation.id.slice(0, 8)} failed${operation.durationMs ? ` after ${operation.durationMs}ms` : ""}. Inspect the operation and choose whether to retry or intervene.`,
        owner: "Operation detail",
        tone: "rose" as const,
        href: `/runs/${operation.id}`,
        action: "Inspect failure",
      })),
      ...overview.pendingApprovals.slice(0, 2).map((approval) => ({
        id: `approval-${approval.id}`,
        title: `${approval.label} needs a human`,
        detail: approval.promptMessage,
        owner: "Approvals",
        tone: "amber" as const,
        href: "/approvals",
        action: "Review approval",
      })),
      ...blockedTasks.slice(0, 2).map((task) => ({
        id: `task-${task.id}`,
        title: `${task.title} is blocked`,
        detail: `${task.summary} Current priority is ${task.priority}.`,
        owner: "Activity",
        tone: "amber" as const,
        href: task.operationId ? `/runs/${task.operationId}` : "/tasks",
        action: "Open task",
      })),
    ].slice(0, 6);

    const systemHealth = [
      {
        id: "control-plane",
        label: "Control plane",
        value: attentionItems.some((item) => item.tone === "rose") ? "Degraded" : "Responsive",
        detail: attentionItems.some((item) => item.tone === "rose")
          ? "There is at least one failed operation in the visible window."
          : "No critical failures are currently projected.",
        status: attentionItems.some((item) => item.tone === "rose") ? "failed" : "active",
      },
      {
        id: "departments",
        label: "Active departments",
        value: `${overview.summary.activeDepartmentCount} live`,
        detail:
          overview.activeDepartments.filter((department) => department.status === "attention").length > 0
            ? `${overview.activeDepartments.filter((department) => department.status === "attention").length} department${overview.activeDepartments.filter((department) => department.status === "attention").length === 1 ? "" : "s"} flagged for review.`
            : "No department is currently in an attention state.",
        status: overview.activeDepartments.some((department) => department.status === "attention")
          ? "paused"
          : "active",
      },
      {
        id: "approvals",
        label: "Approval queue",
        value: overview.summary.pendingApprovalCount > 0 ? `${overview.summary.pendingApprovalCount} pending` : "Clear",
        detail:
          overview.summary.pendingApprovalCount > 0
            ? "Human review is currently the limiting factor for at least one operation."
            : "No operation is waiting on operator approval.",
        status: overview.summary.pendingApprovalCount > 0 ? "paused" : "active",
      },
      {
        id: "cost",
        label: "Cost posture",
        value: formatCurrency(overview.summary.totalCostUsd),
        detail: metricProvenanceLine(overview.metricProvenance.totalCostUsd),
        status: "active",
      },
    ];

    const departmentTaskMap = new Map<string, string>();
    overview.activeTasks.forEach((task) => {
      if (task.departmentId && !departmentTaskMap.has(task.departmentId)) {
        departmentTaskMap.set(task.departmentId, task.summary);
      }
    });

    const activity = [
      ...overview.activeDepartments.slice(0, 2).map((department) => ({
        id: `department-${department.id}`,
        title: `${department.name} is ${department.status === "attention" ? "awaiting review" : "actively supervising work"}`,
        detail:
          departmentTaskMap.get(department.id) ?? "No projected task summary is currently attached to this department.",
        time: formatDateTime(department.lastSeenAt),
        tone: department.status === "attention" ? ("amber" as const) : ("emerald" as const),
      })),
      ...blockedTasks.slice(0, 2).map((task) => ({
        id: `blocked-${task.id}`,
        title: `${task.title} is blocked`,
        detail: task.summary,
        time: formatDateTime(task.updatedAt),
        tone: "amber" as const,
      })),
      ...overview.recentOperations.slice(0, 2).map((operation) => ({
        id: `operation-${operation.id}`,
        title: `${operation.companyName} operation ${
          operation.status === "failed"
            ? "needs attention"
            : operation.status === "running"
              ? "is running"
              : "completed"
        }`,
        detail:
          operation.status === "failed"
            ? "The failure should be reviewed before replaying the operation."
            : operation.status === "running"
              ? "The operation is still moving through its planned steps."
              : "The operation finished without requiring immediate intervention.",
        time: formatDateTime(operation.startedAt),
        tone: operation.status === "failed" ? ("rose" as const) : ("cyan" as const),
      })),
    ].slice(0, 6);

    return {
      blockedTasks,
      attentionItems,
      systemHealth,
      departmentTaskMap,
      activity,
    };
  }, [overview]);

  const inspector =
    overview && derived ? (
      <InspectorPanel
        title={overview.organization.name}
        subtitle="This surface should answer the first operator questions immediately: what is happening across companies, what needs attention, and where to act next."
        sections={[
          {
            title: "Immediate posture",
            content: (
              <div className="space-y-3">
                <div className="flex items-center justify-between">
                  <span>Attention required</span>
                  <StatusBadge
                    status={derived.attentionItems.length > 0 ? "failed" : "active"}
                    label={derived.attentionItems.length > 0 ? `${derived.attentionItems.length} open` : "Clear"}
                  />
                </div>
                <div className="flex items-center justify-between">
                  <span>Blocked tasks</span>
                  <span>{derived.blockedTasks.length}</span>
                </div>
                <div className="flex items-center justify-between">
                  <span>Pending approvals</span>
                  <span>{overview.summary.pendingApprovalCount}</span>
                </div>
              </div>
            ),
          },
          {
            title: "Recent memory",
            content: overview.memory.recentTopics.length ? (
              <div className="flex flex-wrap gap-2">
                {overview.memory.recentTopics.map((topic) => (
                  <StatusBadge key={topic} status="pending" label={topic} />
                ))}
              </div>
            ) : (
              "No recent memory topics were projected into the current window."
            ),
          },
          {
            title: "Economic posture",
            content: (
              <div className="space-y-2">
                <div className="flex items-center justify-between">
                  <span>Tracked cost</span>
                  <span>{formatCurrency(overview.summary.totalCostUsd)}</span>
                </div>
                <div className="flex items-center justify-between">
                  <span>Revenue</span>
                  <span>{notInstrumentedLabel}</span>
                </div>
                <div className="flex items-center justify-between">
                  <span>Profit</span>
                  <span>{notInstrumentedLabel}</span>
                </div>
                <p className="pt-2 text-xs leading-5 text-slate-500 dark:text-slate-400">
                  {metricProvenanceLine(overview.metricProvenance.totalCostUsd)}
                </p>
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
          <Panel
            title="Command Ops"
            description="Summary first, inspection second, logs last. This page should tell an operator what is happening and where to act in under ten seconds."
            action={
              overview?.generatedAt ? (
                <StatusBadge status="active" label={`Updated ${formatDateTime(overview.generatedAt)}`} />
              ) : null
            }
          >
            <div className="grid gap-4 xl:grid-cols-5">
              <Link href="#system-health" className={metricLinkClass} aria-label="Jump to system health">
                <MetricCard
                  className={metricCardLinkClass}
                  eyebrow="System health"
                  value={derived?.attentionItems.length ? "Attention" : "Stable"}
                  delta={
                    derived?.attentionItems.length
                      ? `${derived.attentionItems.length} item${derived.attentionItems.length === 1 ? "" : "s"} need action`
                      : "No critical issues in the visible window"
                  }
                  tone={derived?.attentionItems.length ? "rose" : "emerald"}
                  icon={<Siren className="h-4 w-4" />}
                />
              </Link>
              <Link href="#active-departments" className={metricLinkClass} aria-label="Jump to active departments">
                <MetricCard
                  className={metricCardLinkClass}
                  eyebrow="Active departments"
                  value={overview ? formatCompactNumber(overview.summary.activeDepartmentCount) : "0"}
                  delta="Departments currently attached to live work"
                  icon={<BrainCircuit className="h-4 w-4" />}
                />
              </Link>
              <Link href="#blocked-tasks" className={metricLinkClass} aria-label="Jump to blocked tasks">
                <MetricCard
                  className={metricCardLinkClass}
                  eyebrow="Blocked tasks"
                  value={derived ? formatCompactNumber(derived.blockedTasks.length) : "0"}
                  delta="Waiting or failed work that needs intervention"
                  tone={derived?.blockedTasks.length ? "amber" : "slate"}
                  icon={<Waypoints className="h-4 w-4" />}
                />
              </Link>
              <Link href="#pending-approvals" className={metricLinkClass} aria-label="Jump to pending approvals">
                <MetricCard
                  className={metricCardLinkClass}
                  eyebrow="Pending approvals"
                  value={overview ? formatCompactNumber(overview.summary.pendingApprovalCount) : "0"}
                  delta="Approvals ready for human review"
                  tone={overview?.summary.pendingApprovalCount ? "amber" : "slate"}
                  icon={<BellRing className="h-4 w-4" />}
                />
              </Link>
              <Link href="#usage-budget" className={metricLinkClass} aria-label="Jump to usage and budget">
                <MetricCard
                  className={metricCardLinkClass}
                  eyebrow="Cost today"
                  value={overview ? formatCurrency(overview.summary.totalCostUsd) : "$0"}
                  delta={
                    overview ? metricProvenanceLine(overview.metricProvenance.totalCostUsd) : "Backend cost ledger"
                  }
                  tone="rose"
                  icon={<HandCoins className="h-4 w-4" />}
                />
              </Link>
            </div>
          </Panel>

          {error ? (
            <Alert variant="destructive">
              <AlertDescription>{error}</AlertDescription>
            </Alert>
          ) : null}

          {loading || !overview || !derived ? (
            <div className="flex min-h-[320px] items-center justify-center rounded-[1.75rem] border border-slate-900/10 bg-white/70 dark:border-white/10 dark:bg-slate-950/50">
              <Spinner size="lg" />
            </div>
          ) : (
            <>
              <div className="grid gap-6 2xl:grid-cols-[1.18fr_0.82fr]">
                <div id="attention-required" className="scroll-mt-36">
                  <Panel
                    title="Attention required"
                    description="Critical and near-critical work that should pull operator focus first."
                    action={
                      <StatusBadge
                        status={derived.attentionItems.length ? "failed" : "active"}
                        label={derived.attentionItems.length ? `${derived.attentionItems.length} open` : "Clear"}
                      />
                    }
                  >
                    {derived.attentionItems.length ? (
                      <div className="space-y-3">
                        {derived.attentionItems.map((item) => (
                          <div
                            key={item.id}
                            className="rounded-[1.25rem] border border-slate-900/8 bg-[var(--panel-muted)] px-4 py-4 dark:border-white/8"
                          >
                            <div className="flex items-start justify-between gap-4">
                              <div className="min-w-0">
                                <div className="flex items-center gap-3">
                                  <span className="flex h-9 w-9 items-center justify-center rounded-2xl border border-slate-900/10 bg-white dark:border-white/10 dark:bg-white/5">
                                    {item.tone === "rose" ? overviewIcons.attention : overviewIcons.paused}
                                  </span>
                                  <div className="min-w-0">
                                    <p className="truncate text-sm font-semibold text-slate-950 dark:text-slate-50">
                                      {item.title}
                                    </p>
                                    <p className="mt-1 text-sm leading-6 text-slate-600 dark:text-slate-300">
                                      {item.detail}
                                    </p>
                                  </div>
                                </div>
                              </div>
                              <div className="flex shrink-0 items-center gap-2">
                                <StatusBadge status={item.tone === "rose" ? "failed" : "paused"} label={item.owner} />
                                <Button asChild size="sm" className="rounded-full">
                                  <Link href={item.href}>
                                    {item.action}
                                    <ArrowRight className="h-4 w-4" />
                                  </Link>
                                </Button>
                              </div>
                            </div>
                          </div>
                        ))}
                      </div>
                    ) : (
                      <EmptyBlock
                        title="Nothing urgent is waiting"
                        description="No failed operations, blocked tasks, or approval bottlenecks are currently dominating the system."
                      />
                    )}
                  </Panel>
                </div>

                <div id="system-health" className="scroll-mt-36">
                  <Panel
                    title="System health"
                    description="Fast readout of the operating posture across control, humans, and economics."
                  >
                    <div className="space-y-3">
                      {derived.systemHealth.map((item) => (
                        <div
                          key={item.id}
                          className="rounded-[1.2rem] border border-slate-900/8 bg-[var(--panel-muted)] px-4 py-4 dark:border-white/8"
                        >
                          <div className="flex items-center justify-between gap-3">
                            <div>
                              <p className="text-sm font-semibold text-slate-950 dark:text-slate-50">{item.label}</p>
                              <p className="mt-1 text-sm leading-6 text-slate-600 dark:text-slate-300">{item.detail}</p>
                            </div>
                            <div className="text-right">
                              <p className="text-sm font-semibold text-slate-950 dark:text-slate-50">{item.value}</p>
                              <div className="mt-2">
                                <StatusBadge status={item.status} />
                              </div>
                            </div>
                          </div>
                        </div>
                      ))}
                    </div>
                  </Panel>
                </div>
              </div>

              <div className="grid gap-6 2xl:grid-cols-[1.05fr_0.95fr]">
                <div id="active-departments" className="scroll-mt-36">
                  <Panel
                    title="Active departments"
                    description="Which departments are currently doing work, what they are focused on, and how much cost they are carrying."
                    action={
                      <Button asChild variant="outline" className="rounded-full">
                        <Link href="/departments">
                          Open departments
                          <ArrowRight className="h-4 w-4" />
                        </Link>
                      </Button>
                    }
                  >
                    {overview.activeDepartments.length ? (
                      <div className="space-y-3">
                        {overview.activeDepartments.slice(0, 6).map((department) => (
                          <Link
                            key={department.id}
                            href={`/departments?department=${department.id}`}
                            className="flex items-start justify-between gap-4 rounded-[1.25rem] border border-slate-900/8 bg-[var(--panel-muted)] px-4 py-4 transition-colors hover:bg-slate-950 hover:text-white dark:border-white/8 dark:hover:bg-white dark:hover:text-slate-950"
                          >
                            <div className="min-w-0">
                              <div className="flex items-center gap-3">
                                <p className="truncate text-sm font-semibold">{department.name}</p>
                                <StatusBadge status={department.status} />
                              </div>
                              <p className="mt-2 text-sm leading-6 text-slate-600 dark:text-slate-300">
                                {derived.departmentTaskMap.get(department.id) ?? "Awaiting the next available task."}
                              </p>
                            </div>
                            <div className="shrink-0 text-right">
                              <p className="text-xs uppercase tracking-[0.16em] text-slate-500 dark:text-slate-400">
                                Cost
                              </p>
                              <p className="mt-2 text-sm font-semibold">{formatCurrency(department.totalCostUsd)}</p>
                            </div>
                          </Link>
                        ))}
                      </div>
                    ) : (
                      <EmptyBlock
                        title="No active departments"
                        description="Departments will appear here once the system sees active work or attention states."
                      />
                    )}
                  </Panel>
                </div>

                <div id="blocked-tasks" className="scroll-mt-36">
                  <Panel
                    title="Department activity needing help"
                    description="Work that is currently stalled by approval, failure, or missing operator action."
                    action={
                      <Button asChild variant="outline" className="rounded-full">
                        <Link href="/tasks">
                          Open activity
                          <ArrowRight className="h-4 w-4" />
                        </Link>
                      </Button>
                    }
                  >
                    {derived.blockedTasks.length ? (
                      <div className="space-y-3">
                        {derived.blockedTasks.map((task) => (
                          <Link
                            key={task.id}
                            href={task.operationId ? `/runs/${task.operationId}` : "/tasks"}
                            className="block rounded-[1.2rem] border border-slate-900/8 bg-[var(--panel-muted)] px-4 py-4 transition-colors hover:bg-slate-950 hover:text-white dark:border-white/8 dark:hover:bg-white dark:hover:text-slate-950"
                          >
                            <div className="flex items-start justify-between gap-3">
                              <div className="min-w-0">
                                <div className="flex items-center gap-3">
                                  <p className="truncate text-sm font-semibold">{task.title}</p>
                                  <StatusBadge status={task.status} />
                                </div>
                                <p className="mt-2 text-sm leading-6 text-slate-600 dark:text-slate-300">
                                  {task.summary}
                                </p>
                              </div>
                              <div className="shrink-0 text-right text-xs text-slate-500 dark:text-slate-400">
                                <p>{task.priority} priority</p>
                                <p className="mt-2">{formatDateTime(task.updatedAt)}</p>
                              </div>
                            </div>
                          </Link>
                        ))}
                      </div>
                    ) : (
                      <EmptyBlock
                        title="No blocked tasks"
                        description="Waiting and failed task projections are clear in the current window."
                      />
                    )}
                  </Panel>
                </div>
              </div>

              <div className="grid gap-6 2xl:grid-cols-[0.92fr_1.08fr]">
                <div id="pending-approvals" className="scroll-mt-36">
                  <Panel
                    title="Pending approvals"
                    description="Approval items that should be resolvable without opening raw logs."
                    action={
                      <Button asChild variant="outline" className="rounded-full">
                        <Link href="/approvals">
                          Open approvals
                          <ArrowRight className="h-4 w-4" />
                        </Link>
                      </Button>
                    }
                  >
                    {overview.pendingApprovals.length ? (
                      <div className="space-y-3">
                        {overview.pendingApprovals.slice(0, 5).map((approval) => (
                          <div
                            key={approval.id}
                            className="rounded-[1.25rem] border border-slate-900/8 bg-[var(--panel-muted)] px-4 py-4 dark:border-white/8"
                          >
                            <div className="flex items-start justify-between gap-4">
                              <div className="min-w-0">
                                <div className="flex items-center gap-3">
                                  <p className="text-sm font-semibold text-slate-950 dark:text-slate-50">
                                    {approval.label}
                                  </p>
                                  <StatusBadge status={approval.status} />
                                </div>
                                <p className="mt-2 text-sm leading-6 text-slate-600 dark:text-slate-300">
                                  {approval.promptMessage}
                                </p>
                              </div>
                              <Button asChild size="sm" className="rounded-full">
                                <Link href="/approvals">Decide</Link>
                              </Button>
                            </div>
                          </div>
                        ))}
                      </div>
                    ) : (
                      <EmptyBlock
                        title="No pending approvals"
                        description="The human-in-the-loop queue is currently clear."
                      />
                    )}
                  </Panel>
                </div>

                <div id="usage-budget" className="scroll-mt-36">
                  <Panel
                    title="Usage and budget"
                    description="Backend-owned spend and metric provenance for the current operating window."
                  >
                    <div className="grid gap-3 md:grid-cols-3">
                      <div className="rounded-[1.2rem] border border-slate-900/8 bg-[var(--panel-muted)] px-4 py-4 dark:border-white/8">
                        <p className="text-[11px] uppercase tracking-[0.18em] text-slate-500 dark:text-slate-400">
                          Tracked cost
                        </p>
                        <p className="mt-2 text-2xl font-semibold text-slate-950 dark:text-slate-50">
                          {formatCurrency(overview.summary.totalCostUsd)}
                        </p>
                        <p className="mt-2 text-xs leading-5 text-slate-500 dark:text-slate-400">
                          {metricProvenanceLine(overview.metricProvenance.totalCostUsd)}
                        </p>
                      </div>
                      <div className="rounded-[1.2rem] border border-slate-900/8 bg-[var(--panel-muted)] px-4 py-4 dark:border-white/8">
                        <p className="text-[11px] uppercase tracking-[0.18em] text-slate-500 dark:text-slate-400">
                          Revenue
                        </p>
                        <p className="mt-2 text-2xl font-semibold text-slate-950 dark:text-slate-50">
                          {notInstrumentedLabel}
                        </p>
                        <p className="mt-2 text-xs leading-5 text-slate-500 dark:text-slate-400">
                          {metricProvenanceLine(overview.metricProvenance.revenue)}
                        </p>
                      </div>
                      <div className="rounded-[1.2rem] border border-slate-900/8 bg-[var(--panel-muted)] px-4 py-4 dark:border-white/8">
                        <p className="text-[11px] uppercase tracking-[0.18em] text-slate-500 dark:text-slate-400">
                          Profit
                        </p>
                        <p className="mt-2 text-2xl font-semibold text-slate-950 dark:text-slate-50">
                          {notInstrumentedLabel}
                        </p>
                        <p className="mt-2 text-xs leading-5 text-slate-500 dark:text-slate-400">
                          {metricProvenanceLine(overview.metricProvenance.profit)}
                        </p>
                      </div>
                    </div>
                    <div className="mt-4 space-y-4">
                      {overview.costByType.map((row) => (
                        <div key={row.type} className="space-y-2">
                          <div className="flex items-center justify-between gap-3 text-sm">
                            <span className="font-medium text-slate-900 capitalize dark:text-slate-100">
                              {row.type.replace(/_/g, " ")}
                            </span>
                            <span className="text-slate-600 dark:text-slate-300">
                              {formatCurrency(row.totalCostUsd)}
                            </span>
                          </div>
                          <TrendBar
                            value={row.totalCostUsd}
                            total={Math.max(overview.summary.totalCostUsd, 1)}
                            tone="rose"
                          />
                        </div>
                      ))}
                    </div>
                    <div className="mt-4">
                      <KeyValueGrid
                        columns={2}
                        items={[
                          {
                            label: "Cost source types",
                            value: formatCompactNumber(overview.costByType.length),
                          },
                          {
                            label: "Operating window",
                            value: `${formatCompactNumber(overview.summary.operationCount24h)} operations in 24h`,
                          },
                        ]}
                      />
                    </div>
                  </Panel>
                </div>
              </div>

              <Panel title="What is happening" description="Short operational narrative for the visible window.">
                <TimelineList items={derived.activity} />
              </Panel>
            </>
          )}
        </div>
      </DashboardLayout>
    </ProtectedRoute>
  );
}
