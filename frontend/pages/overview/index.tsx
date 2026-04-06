import { useEffect, useMemo, useState } from "react";
import Link from "next/link";
import { AlertTriangle, ArrowRight, BrainCircuit, HandCoins, ShieldCheck, Waypoints } from "lucide-react";

import DashboardLayout from "@/components/DashboardLayout";
import {
  EmptyBlock,
  InspectorPanel,
  KeyValueGrid,
  MetricCard,
  Panel,
  StatusBadge,
  TimelineList,
  formatCompactNumber,
  formatCurrency,
  formatDateTime,
  overviewIcons,
} from "@/components/os/operations-ui";
import ProtectedRoute from "@/components/ProtectedRoute";
import { Alert, AlertDescription, Button, Spinner } from "@/components/ui";
import { getApiErrorMessage, systemStateApi, type AgentRegistryEntry, type OrganizationStateSummary } from "@/lib/api";

const revenueMultiplier = 4.75;

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

    const agentTaskMap = new Map<string, string>();
    overview.active_tasks.forEach((task) => {
      if (task.agent_id && !agentTaskMap.has(task.agent_id)) {
        agentTaskMap.set(task.agent_id, task.summary);
      }
    });

    const alerts: Array<{
      id: string;
      tone: "amber" | "rose";
      title: string;
      detail: string;
      owner: string;
    }> = [
      ...overview.recent_executions
        .filter((execution) => execution.status === "failed")
        .slice(0, 2)
        .map((execution) => ({
          id: `execution-${execution.id}`,
          tone: "rose" as const,
          title: `${execution.workflow_name} failed`,
          detail: `Execution ${execution.id.slice(0, 8)} stopped after ${execution.duration_ms ? `${execution.duration_ms}ms` : "an unknown duration"}.`,
          owner: "Execution visibility",
        })),
    ];

    if (overview.pending_decisions.length > 2) {
      alerts.unshift({
        id: "decision-backlog",
        tone: "amber" as const,
        title: "Approval queue is growing",
        detail: `${overview.pending_decisions.length} decisions are waiting on a human review.`,
        owner: "Inbox",
      });
    }

    if (overview.summary.total_cost_usd > 250) {
      alerts.push({
        id: "cost-spike",
        tone: "amber" as const,
        title: "Cost spike detected",
        detail: `Tracked spend reached ${formatCurrency(overview.summary.total_cost_usd)} in the last 24 hours.`,
        owner: "Accounting",
      });
    }

    const activity = [
      ...overview.active_agents.slice(0, 2).map((agent) => ({
        id: `agent-${agent.id}`,
        title: `${agent.display_name} is supervising ${agent.task_count} open task${agent.task_count === 1 ? "" : "s"}`,
        detail: agentTaskMap.get(agent.id) ?? "Awaiting the next assignment in the organization queue.",
        time: formatDateTime(agent.last_seen_at),
        tone: agent.status === "attention" ? ("amber" as const) : ("emerald" as const),
      })),
      ...overview.recent_executions.slice(0, 2).map((execution) => ({
        id: `recent-${execution.id}`,
        title: `${execution.workflow_name} ${execution.status === "failed" ? "stalled" : "completed"} in ${execution.duration_ms ? `${execution.duration_ms}ms` : "recent activity"}`,
        detail:
          execution.status === "failed"
            ? "An operator should inspect the failed step and decide whether to replay or intervene."
            : "Execution stayed within expected timing and trace budgets.",
        time: formatDateTime(execution.started_at),
        tone: execution.status === "failed" ? ("rose" as const) : ("cyan" as const),
      })),
      ...overview.pending_decisions.slice(0, 2).map((decision) => ({
        id: `decision-${decision.id}`,
        title: `${decision.decision_type} requires review`,
        detail: `Expected impact is waiting in the inbox before the execution can continue.`,
        time: formatDateTime(decision.requested_at ?? decision.created_at),
        tone: "amber" as const,
      })),
    ].slice(0, 6);

    return { revenueToday, profitToday, totalAgentCost, agentTaskMap, alerts, activity };
  }, [overview]);

  const inspector = overview ? (
    <InspectorPanel
      title={overview.organization.name}
      subtitle="The overview is a read model over agents, tasks, decisions, memory, and spend. Raw traces remain available from each linked surface."
      sections={[
        {
          title: "Current posture",
          content: (
            <div className="space-y-3">
              <div className="flex items-center justify-between">
                <span>Pending decisions</span>
                <StatusBadge
                  status={overview.summary.pending_decision_count > 0 ? "paused" : "active"}
                  label={overview.summary.pending_decision_count > 0 ? "Needs review" : "Stable"}
                />
              </div>
              <div className="flex items-center justify-between">
                <span>Memory topics</span>
                <span>{overview.memory.recent_topics.length}</span>
              </div>
              <div className="flex items-center justify-between">
                <span>Policy mode</span>
                <span>{overview.policy.http_default_deny ? "Guarded" : "Open"}</span>
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
          title: "Financial posture",
          content: (
            <div className="space-y-2">
              <div className="flex items-center justify-between">
                <span>Tracked cost</span>
                <span>{formatCurrency(overview.summary.total_cost_usd)}</span>
              </div>
              <div className="flex items-center justify-between">
                <span>Projected revenue</span>
                <span>{formatCurrency(derived?.revenueToday ?? 0)}</span>
              </div>
              <div className="flex items-center justify-between">
                <span>Profit</span>
                <span>{formatCurrency(derived?.profitToday ?? 0)}</span>
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
            title="Organization overview"
            description="One screen for the state of the digital company: what is running, what needs attention, and what it is costing."
            action={
              overview?.generated_at ? (
                <StatusBadge status="active" label={`Updated ${formatDateTime(overview.generated_at)}`} />
              ) : null
            }
          >
            <div className="grid gap-4 xl:grid-cols-5">
              <MetricCard
                eyebrow="Active agents"
                value={overview ? formatCompactNumber(overview.summary.active_agent_count) : "0"}
                delta="Currently assigned to live work"
                icon={<BrainCircuit className="h-4 w-4" />}
              />
              <MetricCard
                eyebrow="Tasks running"
                value={overview ? formatCompactNumber(overview.summary.active_task_count) : "0"}
                delta="Open units of work across the system"
                icon={<Waypoints className="h-4 w-4" />}
              />
              <MetricCard
                eyebrow="Pending approvals"
                value={overview ? formatCompactNumber(overview.summary.pending_decision_count) : "0"}
                delta="Decisions waiting on human review"
                tone="amber"
                icon={<ShieldCheck className="h-4 w-4" />}
              />
              <MetricCard
                eyebrow="Token cost today"
                value={overview ? formatCurrency(overview.summary.total_cost_usd) : "$0"}
                delta="Canonical LLM and memory spend"
                tone="rose"
                icon={<HandCoins className="h-4 w-4" />}
              />
              <MetricCard
                eyebrow="Revenue today"
                value={derived ? formatCurrency(derived.revenueToday) : "$0"}
                delta={
                  derived
                    ? `${formatCurrency(derived.profitToday)} gross margin after infrastructure cost`
                    : "Derived operating estimate"
                }
                tone="emerald"
                icon={overviewIcons.financial}
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
              <div className="grid gap-6 2xl:grid-cols-[1.3fr_1fr]">
                <Panel
                  title="Active agents"
                  description="Persistent agent identities with current assignment and spend context."
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
                  title="Human-in-the-loop queue"
                  description="Reviewable items with the minimum context needed to decide."
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
                            <div>
                              <p className="text-sm font-semibold text-slate-950 dark:text-slate-50">
                                {decision.decision_type}
                              </p>
                              <p className="mt-2 text-sm leading-6 text-slate-600 dark:text-slate-300">
                                {String(
                                  decision.context_json?.summary ??
                                    "Operator approval required before this execution continues.",
                                )}
                              </p>
                              <p className="mt-2 text-xs text-slate-500 dark:text-slate-400">
                                Requested {formatDateTime(decision.requested_at ?? decision.created_at)}
                              </p>
                            </div>
                            <div className="flex shrink-0 items-center gap-2">
                              <Button asChild size="sm" className="rounded-full">
                                <Link href="/inbox">Approve</Link>
                              </Button>
                              <Button asChild size="sm" variant="outline" className="rounded-full">
                                <Link href="/inbox">Reject</Link>
                              </Button>
                            </div>
                          </div>
                        </div>
                      ))}
                    </div>
                  ) : (
                    <EmptyBlock
                      title="Inbox is clear"
                      description="No decisions are currently waiting on a human operator."
                    />
                  )}
                </Panel>
              </div>

              <div className="grid gap-6 2xl:grid-cols-[0.95fr_1.05fr]">
                <Panel
                  title="Alerts and issues"
                  description="Operational anomalies, failed executions, and policy pressure."
                >
                  {derived.alerts.length ? (
                    <div className="space-y-3">
                      {derived.alerts.map((alert) => (
                        <div
                          key={alert.id}
                          className="rounded-[1.25rem] border border-slate-900/8 bg-[var(--panel-muted)] px-4 py-4 dark:border-white/8"
                        >
                          <div className="flex items-center justify-between gap-3">
                            <div className="flex items-center gap-3">
                              <span className="flex h-9 w-9 items-center justify-center rounded-2xl border border-slate-900/10 bg-white dark:border-white/10 dark:bg-white/5">
                                {alert.tone === "rose" ? (
                                  overviewIcons.attention
                                ) : alert.tone === "amber" ? (
                                  overviewIcons.paused
                                ) : (
                                  <AlertTriangle className="h-4 w-4" />
                                )}
                              </span>
                              <div>
                                <p className="text-sm font-semibold text-slate-950 dark:text-slate-50">{alert.title}</p>
                                <p className="mt-1 text-sm leading-6 text-slate-600 dark:text-slate-300">
                                  {alert.detail}
                                </p>
                              </div>
                            </div>
                            <StatusBadge status={alert.tone === "rose" ? "failed" : "paused"} label={alert.owner} />
                          </div>
                        </div>
                      ))}
                    </div>
                  ) : (
                    <EmptyBlock
                      title="No active alerts"
                      description="Executions, approval queues, and spend are staying inside expected thresholds."
                    />
                  )}
                </Panel>

                <Panel
                  title="Recent activity feed"
                  description="Short operational narrative for the last visible window."
                >
                  <TimelineList items={derived.activity} />
                </Panel>
              </div>

              <Panel
                title="System state summary"
                description="A concise readout of health, memory, and economics for the current operating window."
              >
                <KeyValueGrid
                  columns={3}
                  items={[
                    {
                      label: "Executions in 24h",
                      value: `${formatCompactNumber(overview.summary.execution_count_24h)} completed or active`,
                    },
                    {
                      label: "Memory observations",
                      value: `${formatCompactNumber(overview.summary.memory_observation_count)} records in active scope`,
                    },
                    {
                      label: "Tracked spend",
                      value: `${formatCurrency(overview.summary.total_cost_usd)} across ${formatCurrency(derived.totalAgentCost)} attached to active agents`,
                    },
                  ]}
                />
              </Panel>
            </>
          )}
        </div>
      </DashboardLayout>
    </ProtectedRoute>
  );
}
