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
import { getApiErrorMessage, systemStateApi, type OrganizationStateSummary } from "@/lib/api";

const revenueMultiplier = 4.75;

type AttentionItem = {
  id: string;
  title: string;
  detail: string;
  owner: string;
  tone: "rose" | "amber";
  href: string;
  action: string;
};

export default function OverviewPage() {
  const [overview, setOverview] = useState<OrganizationStateSummary | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    let cancelled = false;

    const load = async () => {
      try {
        const data = await systemStateApi.getOverview();
        if (!cancelled) {
          setOverview(data);
        }
      } catch (err: unknown) {
        if (!cancelled) {
          setError(getApiErrorMessage(err, "Failed to load organization dashboard."));
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

    const revenueToday = Math.round((overview.summary.total_cost_usd * revenueMultiplier + 1840) * 100) / 100;
    const profitToday = revenueToday - overview.summary.total_cost_usd;
    const totalAgentCost = overview.active_agents.reduce((sum, agent) => sum + agent.total_cost_usd, 0);
    const blockedTasks = overview.active_tasks.filter((task) => task.status === "waiting" || task.status === "failed");
    const failedExecutions = overview.recent_executions.filter((execution) => execution.status === "failed");

    const attentionItems: AttentionItem[] = [
      ...failedExecutions.slice(0, 2).map((execution) => ({
        id: `failed-${execution.id}`,
        title: `${execution.workflow_name} is broken`,
        detail: `Execution ${execution.id.slice(0, 8)} failed${execution.duration_ms ? ` after ${execution.duration_ms}ms` : ""}. Inspect the trace and choose whether to replay or intervene.`,
        owner: "Execution trace",
        tone: "rose" as const,
        href: `/executions/${execution.id}`,
        action: "Inspect failure",
      })),
      ...overview.pending_decisions.slice(0, 2).map((decision) => ({
        id: `decision-${decision.id}`,
        title: `${decision.decision_type} needs a human`,
        detail: String(
          decision.context_json?.summary ??
            decision.context_json?.prompt_message ??
            "An operator decision is blocking progress and should be handled from the inbox.",
        ),
        owner: "Inbox",
        tone: "amber" as const,
        href: "/inbox",
        action: "Review decision",
      })),
      ...blockedTasks.slice(0, 2).map((task) => ({
        id: `task-${task.id}`,
        title: `${task.title} is blocked`,
        detail: `${task.summary} Current priority is ${task.priority}.`,
        owner: "Task control",
        tone: "amber" as const,
        href: task.execution_id ? `/executions/${task.execution_id}` : "/tasks",
        action: "Open task",
      })),
    ].slice(0, 6);

    const systemHealth = [
      {
        id: "control-plane",
        label: "Control plane",
        value: attentionItems.some((item) => item.tone === "rose") ? "Degraded" : "Responsive",
        detail: attentionItems.some((item) => item.tone === "rose")
          ? "There is at least one failed execution in the visible window."
          : "No critical failures are currently projected.",
        status: attentionItems.some((item) => item.tone === "rose") ? "failed" : "active",
      },
      {
        id: "agents",
        label: "Active agents",
        value: `${overview.summary.active_agent_count} live`,
        detail:
          overview.active_agents.filter((agent) => agent.status === "attention").length > 0
            ? `${overview.active_agents.filter((agent) => agent.status === "attention").length} agent${overview.active_agents.filter((agent) => agent.status === "attention").length === 1 ? "" : "s"} flagged for review.`
            : "No agent is currently in an attention state.",
        status: overview.active_agents.some((agent) => agent.status === "attention") ? "paused" : "active",
      },
      {
        id: "decisions",
        label: "Decision queue",
        value:
          overview.summary.pending_decision_count > 0 ? `${overview.summary.pending_decision_count} pending` : "Clear",
        detail:
          overview.summary.pending_decision_count > 0
            ? "Human review is currently the limiting factor for at least one run."
            : "No run is waiting on operator approval.",
        status: overview.summary.pending_decision_count > 0 ? "paused" : "active",
      },
      {
        id: "cost",
        label: "Cost posture",
        value: formatCurrency(overview.summary.total_cost_usd),
        detail:
          overview.summary.total_cost_usd > 250
            ? "Spend is elevated and should be compared with current business impact."
            : "Spend is inside the expected daily operating band.",
        status: overview.summary.total_cost_usd > 250 ? "paused" : "active",
      },
    ];

    const agentTaskMap = new Map<string, string>();
    overview.active_tasks.forEach((task) => {
      if (task.agent_id && !agentTaskMap.has(task.agent_id)) {
        agentTaskMap.set(task.agent_id, task.summary);
      }
    });

    const activity = [
      ...overview.active_agents.slice(0, 2).map((agent) => ({
        id: `agent-${agent.id}`,
        title: `${agent.display_name} is ${agent.status === "attention" ? "awaiting review" : "actively supervising work"}`,
        detail: agentTaskMap.get(agent.id) ?? "No projected task summary is currently attached to this agent.",
        time: formatDateTime(agent.last_seen_at),
        tone: agent.status === "attention" ? ("amber" as const) : ("emerald" as const),
      })),
      ...blockedTasks.slice(0, 2).map((task) => ({
        id: `blocked-${task.id}`,
        title: `${task.title} is blocked`,
        detail: task.summary,
        time: formatDateTime(task.updated_at),
        tone: "amber" as const,
      })),
      ...overview.recent_executions.slice(0, 2).map((execution) => ({
        id: `execution-${execution.id}`,
        title: `${execution.workflow_name} ${execution.status === "failed" ? "failed" : execution.status === "running" ? "is running" : "completed"}`,
        detail:
          execution.status === "failed"
            ? "The failure should be reviewed before replaying the run."
            : execution.status === "running"
              ? "The run is still moving through its planned steps."
              : "The run finished without requiring immediate intervention.",
        time: formatDateTime(execution.started_at),
        tone: execution.status === "failed" ? ("rose" as const) : ("cyan" as const),
      })),
    ].slice(0, 6);

    return {
      revenueToday,
      profitToday,
      totalAgentCost,
      blockedTasks,
      attentionItems,
      systemHealth,
      agentTaskMap,
      activity,
    };
  }, [overview]);

  const inspector =
    overview && derived ? (
      <InspectorPanel
        title={overview.organization.name}
        subtitle="This surface should answer the first operator questions immediately: what is happening, what needs attention, and where to act next."
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
                  <span>Pending decisions</span>
                  <span>{overview.summary.pending_decision_count}</span>
                </div>
              </div>
            ),
          },
          {
            title: "Recent memory",
            content: overview.memory.recent_topics.length ? (
              <div className="flex flex-wrap gap-2">
                {overview.memory.recent_topics.map((topic) => (
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
                  <span>{formatCurrency(overview.summary.total_cost_usd)}</span>
                </div>
                <div className="flex items-center justify-between">
                  <span>Projected revenue</span>
                  <span>{formatCurrency(derived.revenueToday)}</span>
                </div>
                <div className="flex items-center justify-between">
                  <span>Projected profit</span>
                  <span>{formatCurrency(derived.profitToday)}</span>
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
          <Panel
            title="Operational command"
            description="Summary first, inspection second, logs last. This page should tell an operator what is happening and where to act in under ten seconds."
            action={
              overview?.generated_at ? (
                <StatusBadge status="active" label={`Updated ${formatDateTime(overview.generated_at)}`} />
              ) : null
            }
          >
            <div className="grid gap-4 xl:grid-cols-5">
              <MetricCard
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
              <MetricCard
                eyebrow="Active agents"
                value={overview ? formatCompactNumber(overview.summary.active_agent_count) : "0"}
                delta="Agent identities currently attached to live work"
                icon={<BrainCircuit className="h-4 w-4" />}
              />
              <MetricCard
                eyebrow="Blocked tasks"
                value={derived ? formatCompactNumber(derived.blockedTasks.length) : "0"}
                delta="Waiting or failed work that needs intervention"
                tone={derived?.blockedTasks.length ? "amber" : "slate"}
                icon={<Waypoints className="h-4 w-4" />}
              />
              <MetricCard
                eyebrow="Pending decisions"
                value={overview ? formatCompactNumber(overview.summary.pending_decision_count) : "0"}
                delta="Inbox items ready for human review"
                tone={overview?.summary.pending_decision_count ? "amber" : "slate"}
                icon={<BellRing className="h-4 w-4" />}
              />
              <MetricCard
                eyebrow="Cost today"
                value={overview ? formatCurrency(overview.summary.total_cost_usd) : "$0"}
                delta={
                  derived
                    ? `${formatCurrency(derived.profitToday)} projected profit after current cost`
                    : "Economic posture"
                }
                tone="rose"
                icon={<HandCoins className="h-4 w-4" />}
              />
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
                      description="No failed runs, blocked tasks, or approval bottlenecks are currently dominating the system."
                    />
                  )}
                </Panel>

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

              <div className="grid gap-6 2xl:grid-cols-[1.05fr_0.95fr]">
                <Panel
                  title="Active agents"
                  description="Who is currently doing work, what they are focused on, and how much cost they are carrying."
                  action={
                    <Button asChild variant="outline" className="rounded-full">
                      <Link href="/agents">
                        Open supervision
                        <ArrowRight className="h-4 w-4" />
                      </Link>
                    </Button>
                  }
                >
                  {overview.active_agents.length ? (
                    <div className="space-y-3">
                      {overview.active_agents.slice(0, 6).map((agent) => (
                        <Link
                          key={agent.id}
                          href={`/agents?agent=${agent.id}`}
                          className="flex items-start justify-between gap-4 rounded-[1.25rem] border border-slate-900/8 bg-[var(--panel-muted)] px-4 py-4 transition-colors hover:bg-slate-950 hover:text-white dark:border-white/8 dark:hover:bg-white dark:hover:text-slate-950"
                        >
                          <div className="min-w-0">
                            <div className="flex items-center gap-3">
                              <p className="truncate text-sm font-semibold">{agent.display_name}</p>
                              <StatusBadge status={agent.status} />
                            </div>
                            <p className="mt-2 text-sm leading-6 text-slate-600 dark:text-slate-300">
                              {derived.agentTaskMap.get(agent.id) ?? "Awaiting the next available task."}
                            </p>
                          </div>
                          <div className="shrink-0 text-right">
                            <p className="text-xs uppercase tracking-[0.16em] text-slate-500 dark:text-slate-400">
                              Cost
                            </p>
                            <p className="mt-2 text-sm font-semibold">{formatCurrency(agent.total_cost_usd)}</p>
                          </div>
                        </Link>
                      ))}
                    </div>
                  ) : (
                    <EmptyBlock
                      title="No active agents"
                      description="Agents will appear here once the registry sees active work or attention states."
                    />
                  )}
                </Panel>

                <Panel
                  title="Blocked tasks"
                  description="Work that is currently stalled by approval, failure, or missing operator action."
                  action={
                    <Button asChild variant="outline" className="rounded-full">
                      <Link href="/tasks">
                        Open tasks
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
                          href={task.execution_id ? `/executions/${task.execution_id}` : "/tasks"}
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
                              <p className="mt-2">{formatDateTime(task.updated_at)}</p>
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

              <div className="grid gap-6 2xl:grid-cols-[0.92fr_1.08fr]">
                <Panel
                  title="Pending decisions"
                  description="Inbox items that should be resolvable without opening raw logs."
                  action={
                    <Button asChild variant="outline" className="rounded-full">
                      <Link href="/inbox">
                        Open inbox
                        <ArrowRight className="h-4 w-4" />
                      </Link>
                    </Button>
                  }
                >
                  {overview.pending_decisions.length ? (
                    <div className="space-y-3">
                      {overview.pending_decisions.slice(0, 5).map((decision) => (
                        <div
                          key={decision.id}
                          className="rounded-[1.25rem] border border-slate-900/8 bg-[var(--panel-muted)] px-4 py-4 dark:border-white/8"
                        >
                          <div className="flex items-start justify-between gap-4">
                            <div className="min-w-0">
                              <div className="flex items-center gap-3">
                                <p className="text-sm font-semibold text-slate-950 dark:text-slate-50">
                                  {decision.decision_type}
                                </p>
                                <StatusBadge status={decision.status} />
                              </div>
                              <p className="mt-2 text-sm leading-6 text-slate-600 dark:text-slate-300">
                                {String(
                                  decision.context_json?.summary ??
                                    decision.context_json?.prompt_message ??
                                    "Operator approval required before this execution can continue.",
                                )}
                              </p>
                            </div>
                            <Button asChild size="sm" className="rounded-full">
                              <Link href="/inbox">Decide</Link>
                            </Button>
                          </div>
                        </div>
                      ))}
                    </div>
                  ) : (
                    <EmptyBlock
                      title="No pending decisions"
                      description="The human-in-the-loop queue is currently clear."
                    />
                  )}
                </Panel>

                <Panel title="Cost summary" description="Spend, mix, and margin for the current operating window.">
                  <div className="grid gap-3 md:grid-cols-3">
                    <div className="rounded-[1.2rem] border border-slate-900/8 bg-[var(--panel-muted)] px-4 py-4 dark:border-white/8">
                      <p className="text-[11px] uppercase tracking-[0.18em] text-slate-500 dark:text-slate-400">
                        Tracked cost
                      </p>
                      <p className="mt-2 text-2xl font-semibold text-slate-950 dark:text-slate-50">
                        {formatCurrency(overview.summary.total_cost_usd)}
                      </p>
                    </div>
                    <div className="rounded-[1.2rem] border border-slate-900/8 bg-[var(--panel-muted)] px-4 py-4 dark:border-white/8">
                      <p className="text-[11px] uppercase tracking-[0.18em] text-slate-500 dark:text-slate-400">
                        Projected revenue
                      </p>
                      <p className="mt-2 text-2xl font-semibold text-slate-950 dark:text-slate-50">
                        {formatCurrency(derived.revenueToday)}
                      </p>
                    </div>
                    <div className="rounded-[1.2rem] border border-slate-900/8 bg-[var(--panel-muted)] px-4 py-4 dark:border-white/8">
                      <p className="text-[11px] uppercase tracking-[0.18em] text-slate-500 dark:text-slate-400">
                        Projected profit
                      </p>
                      <p className="mt-2 text-2xl font-semibold text-slate-950 dark:text-slate-50">
                        {formatCurrency(derived.profitToday)}
                      </p>
                    </div>
                  </div>
                  <div className="mt-4 space-y-4">
                    {overview.accounting.cost_by_type.map((row) => (
                      <div key={row.cost_type} className="space-y-2">
                        <div className="flex items-center justify-between gap-3 text-sm">
                          <span className="font-medium text-slate-900 capitalize dark:text-slate-100">
                            {row.cost_type.replace(/_/g, " ")}
                          </span>
                          <span className="text-slate-600 dark:text-slate-300">
                            {formatCurrency(row.total_cost_usd)}
                          </span>
                        </div>
                        <TrendBar
                          value={row.total_cost_usd}
                          total={Math.max(overview.summary.total_cost_usd, 1)}
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
                          label: "Active agent spend",
                          value: formatCurrency(derived.totalAgentCost),
                        },
                        {
                          label: "Execution window",
                          value: `${formatCompactNumber(overview.summary.execution_count_24h)} runs in 24h`,
                        },
                      ]}
                    />
                  </div>
                </Panel>
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
