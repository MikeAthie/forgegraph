import { useCallback, useMemo } from "react";
import Link from "next/link";
import { useQuery, useQueryClient } from "@tanstack/react-query";
import {
  ArrowRight,
  Activity,
  BellRing,
  BrainCircuit,
  Database,
  HandCoins,
  Siren,
  TimerReset,
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
} from "@/components/os/operations-ui";
import { formatCompactNumber, formatCurrency, formatDateTime, formatDuration } from "@/components/os/operations-format";
import { overviewIcons } from "@/components/os/overview-icons";
import ProtectedRoute from "@/components/ProtectedRoute";
import { Alert, AlertDescription, Button, Spinner } from "@/components/ui";
import { useAuth } from "@/contexts/AuthContext";
import { translateProductError } from "@/domain/errors";
import { overviewRepository } from "@/domain/repositories";
import type { MetricProvenanceVM } from "@/domain/translation";
import type { OrganizationOverviewVM, OverviewSectionVM } from "@/domain/repositories/overviewRepository";
import { useStateFeed, type StateFeedMessage } from "@/hooks/useStateFeed";

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
  "group block h-full rounded-[1.75rem] focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-zinc-950 focus-visible:ring-offset-2 focus-visible:ring-offset-white dark:focus-visible:ring-zinc-100 dark:focus-visible:ring-offset-zinc-950";

const metricCardLinkClass =
  "h-full transition-[color,background-color,border-color,box-shadow,transform] duration-200 ease-out motion-reduce:transition-none motion-reduce:transform-none group-hover:-tranzinc-y-0.5 group-hover:border-zinc-900/20 group-hover:bg-white group-hover:shadow-[0_30px_70px_-48px_rgba(15,23,42,0.7)] dark:group-hover:border-white/20 dark:group-hover:bg-white/[0.07]";

const OVERVIEW_FEED_EVENT_TYPES = [
  "overview.updated",
  "task.created",
  "task.updated",
  "decision.created",
  "decision.updated",
  "agent.updated",
  "memory.created",
  "accounting.updated",
  "dead_letter.created",
  "projection.stale",
  "projection.recovered",
];

const OVERVIEW_FEED_EVENT_TYPE_SET = new Set(OVERVIEW_FEED_EVENT_TYPES);

function stateFeedMessageType(message: StateFeedMessage) {
  return message.type || message.event_type || message.event?.type || message.event?.event_type || "";
}

const SOURCE_LABELS: Record<string, string> = {
  backend_projection: "Backend freshness",
  backend_memory: "Backend knowledge",
  backend_ops: "Backend operations",
  backend_accounting: "Backend accounting",
  backend_ledger: "Backend ledger",
};

function sourceLabel(source: string): string {
  return SOURCE_LABELS[source] ?? source.replace(/_/g, " ");
}

function metricProvenanceLine(metric: MetricProvenanceVM): string {
  const computedAt = metric.computedAt ? `Computed ${formatDateTime(metric.computedAt)}` : "computed_at unavailable";
  const freshness = typeof metric.freshnessMs === "number" ? ` · freshness ${Math.round(metric.freshnessMs)}ms` : "";

  return `${sourceLabel(metric.source)} · ${computedAt}${freshness}`;
}

function financialMetricLabel(metric: MetricProvenanceVM): string {
  if (metric.status === "available" && typeof metric.value === "number") {
    return formatCurrency(metric.value);
  }

  return notInstrumentedLabel;
}

function projectionStatusLabel(projection: OrganizationOverviewVM["projection"]): string {
  if (!projection) {
    return "Freshness unavailable";
  }
  const status = projection.status ?? "fresh";
  const lag =
    typeof projection.lag_seconds === "number" && projection.lag_seconds > 0
      ? ` · ${Math.round(projection.lag_seconds)}s lag`
      : "";
  const sequence =
    typeof projection.last_sequence === "number" ? ` · seq ${projection.last_sequence.toLocaleString()}` : "";
  return `Freshness ${status}${lag}${sequence}`;
}

type CardMetadata = Pick<
  OverviewSectionVM,
  "source" | "lastUpdatedAt" | "freshnessMs" | "status" | "stale" | "degraded"
>;

function overviewCardDetail(section: CardMetadata): string {
  const freshness =
    typeof section.freshnessMs === "number" ? ` · freshness ${formatDuration(section.freshnessMs)}` : "";
  return `${sourceLabel(section.source)} · ${section.status} · Updated ${formatDateTime(section.lastUpdatedAt)}${freshness}`;
}

function overviewCardTone(
  section: CardMetadata,
  hasAttention = false,
): "slate" | "emerald" | "amber" | "rose" | "cyan" {
  if (section.degraded || hasAttention) {
    return "rose";
  }
  if (section.stale || section.status === "stale" || section.status === "rebuilding") {
    return "amber";
  }
  return section.status === "fresh" ? "emerald" : "slate";
}

type OverviewDerivedState = {
  blockedTasks: OrganizationOverviewVM["activeTasks"];
  attentionItems: AttentionItem[];
  systemHealth: Array<{ id: string; label: string; value: string; detail: string; status: string }>;
  departmentTaskMap: Map<string, string>;
  activity: Parameters<typeof TimelineList>[0]["items"];
};

type CompanyOsCard = {
  href: string;
  ariaLabel: string;
  eyebrow: string;
  value: string;
  section: CardMetadata;
  tone: "slate" | "emerald" | "amber" | "rose" | "cyan";
  icon: React.ReactNode;
};

function useOverviewController() {
  const { user, isAuthenticated } = useAuth();
  const queryClient = useQueryClient();
  const organizationId = user?.default_organization_id ?? null;
  const {
    data: overviewData,
    isLoading: loading,
    error: overviewError,
  } = useQuery({
    queryKey: ["overview", organizationId ?? "current"],
    queryFn: overviewRepository.get,
    enabled: isAuthenticated,
  });
  const overview = overviewData ?? null;
  const effectiveOrganizationId = overview?.organization.id ?? organizationId;
  const invalidateOverview = useCallback(() => {
    void queryClient.invalidateQueries({ queryKey: ["overview"] });
  }, [queryClient]);
  const handleStateFeedEvent = useCallback(
    (event: StateFeedMessage) => {
      const type = stateFeedMessageType(event);
      if (event.requires_refetch || OVERVIEW_FEED_EVENT_TYPE_SET.has(type)) {
        invalidateOverview();
      }
    },
    [invalidateOverview],
  );
  const stateFeed = useStateFeed({
    scope: "organization",
    organizationId: effectiveOrganizationId,
    enabled: isAuthenticated && Boolean(effectiveOrganizationId),
    lastSeenStateVersion: overview?.projection?.state_feed_version ?? null,
    eventTypes: OVERVIEW_FEED_EVENT_TYPES,
    onEvent: handleStateFeedEvent,
    onFullResync: invalidateOverview,
  });

  const error = overviewError ? translateProductError(overviewError, "operation") : null;

  const derived = useMemo<OverviewDerivedState | null>(() => {
    if (!overview) {
      return null;
    }

    const blockedTasks = overview.activeTasks.filter((task) => task.status === "paused" || task.status === "failed");
    const failedOperations = overview.recentOperations.filter((operation) => operation.status === "failed");
    const recoveryNeeded = overview.operations.deadLetterCount > 0 || overview.operations.status === "degraded";

    const attentionItems: AttentionItem[] = [
      ...(recoveryNeeded
        ? [
            {
              id: "operator-recovery",
              title: "Operator recovery needs attention",
              detail: `${overview.operations.deadLetterCount} recovery item${overview.operations.deadLetterCount === 1 ? "" : "s"} require review. Freshness is ${overview.operations.projectionStatus}.`,
              owner: "Recovery",
              tone: "rose" as const,
              href: "/ops",
              action: "Open recovery",
            },
          ]
        : []),
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
        value: recoveryNeeded || attentionItems.some((item) => item.tone === "rose") ? "Degraded" : "Responsive",
        detail: recoveryNeeded
          ? "Operator-visible recovery records or freshness delay require attention."
          : attentionItems.some((item) => item.tone === "rose")
            ? "There is at least one failed operation in the visible window."
            : "No critical failures are currently projected.",
        status: recoveryNeeded || attentionItems.some((item) => item.tone === "rose") ? "failed" : "active",
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
        value: financialMetricLabel(overview.metricProvenance.totalCostUsd),
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
        title: `${operation.companyName} operation ${operation.status === "failed" ? "needs attention" : operation.status === "running" ? "is running" : "completed"}`,
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

    return { blockedTasks, attentionItems, systemHealth, departmentTaskMap, activity };
  }, [overview]);

  const projectionCardMetadata: CardMetadata = {
    source: overview?.projection?.source ?? "backend_projection",
    lastUpdatedAt:
      overview?.projection?.last_updated_at ?? overview?.projection?.watermark ?? overview?.generatedAt ?? null,
    freshnessMs: overview?.projection?.freshness_ms ?? overview?.projection?.projection_lag_ms ?? null,
    status: overview?.projection?.status ?? "fresh",
    stale: Boolean(overview?.projection?.stale ?? overview?.projection?.status === "stale"),
    degraded: Boolean(overview?.projection?.degraded ?? overview?.projection?.status === "degraded"),
  };
  const companyOsCards: CompanyOsCard[] = overview
    ? [
        {
          href: "#active-departments",
          ariaLabel: "Jump to active departments",
          eyebrow: "Active Departments",
          value: formatCompactNumber(overview.running.activeAgentCount),
          section: overview.running,
          tone: overviewCardTone(overview.running),
          icon: <BrainCircuit className="size-4" />,
        },
        {
          href: "#blocked-tasks",
          ariaLabel: "Jump to running tasks",
          eyebrow: "Running Tasks",
          value: formatCompactNumber(overview.running.runningTaskCount),
          section: overview.running,
          tone: overviewCardTone(overview.running),
          icon: <Activity className="size-4" />,
        },
        {
          href: "#pending-approvals",
          ariaLabel: "Jump to blocked decisions",
          eyebrow: "Blocked Decisions",
          value: formatCompactNumber(overview.decisions.pendingDecisionCount),
          section: overview.decisions,
          tone: overviewCardTone(overview.decisions, overview.decisions.pendingDecisionCount > 0),
          icon: <BellRing className="size-4" />,
        },
        {
          href: "#usage-budget",
          ariaLabel: "Jump to cost today",
          eyebrow: "Cost Today",
          value: financialMetricLabel(overview.metricProvenance.totalCostUsd),
          section: overview.costs,
          tone: overviewCardTone(overview.costs),
          icon: <HandCoins className="size-4" />,
        },
        {
          href: "#memory",
          ariaLabel: "Jump to memory writes",
          eyebrow: "Memory Writes",
          value: formatCompactNumber(overview.memory.writeCount24h),
          section: overview.memory.section,
          tone: overviewCardTone(overview.memory.section),
          icon: <Database className="size-4" />,
        },
        {
          href: "/ops",
          ariaLabel: "Open recovery items",
          eyebrow: "Recovery Items",
          value: formatCompactNumber(overview.failures.deadLetterCount),
          section: overview.failures,
          tone: overviewCardTone(overview.failures, overview.failures.deadLetterCount > 0),
          icon: <Siren className="size-4" />,
        },
        {
          href: "#system-health",
          ariaLabel: "Jump to freshness",
          eyebrow: "Freshness",
          value:
            typeof overview.projection?.lag_seconds === "number"
              ? formatDuration(overview.projection.lag_seconds * 1000)
              : "Pending",
          section: projectionCardMetadata,
          tone: overviewCardTone(projectionCardMetadata),
          icon: <Waypoints className="size-4" />,
        },
        {
          href: "/ops",
          ariaLabel: "Open processing diagnostics",
          eyebrow: "Processing Delay",
          value: formatDuration(overview.failures.runtimeIntentLagSeconds * 1000),
          section: overview.failures,
          tone: overviewCardTone(overview.failures, overview.failures.runtimeIntentLagSeconds > 0),
          icon: <TimerReset className="size-4" />,
        },
      ]
    : [];

  return { overview, derived, loading, error, stateFeed, companyOsCards };
}

type OverviewController = ReturnType<typeof useOverviewController>;

function OverviewInspector({
  overview,
  derived,
}: {
  overview: OrganizationOverviewVM | null;
  derived: OverviewDerivedState | null;
}) {
  if (!overview || !derived) {
    return null;
  }

  return (
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
      ]}
    />
  );
}

function CommandOpsPanel({ controller }: { controller: OverviewController }) {
  const { overview } = controller;

  return (
    <Panel
      title="Command Ops"
      description="Summary first, inspection second, logs last. This page should tell an operator what is happening and where to act in under ten seconds."
      action={overview?.generatedAt ? <CommandOpsBadges controller={controller} /> : null}
    >
      <div className="grid gap-4 md:grid-cols-2 xl:grid-cols-4">
        {controller.companyOsCards.map((card) => (
          <Link key={card.eyebrow} href={card.href} className={metricLinkClass} aria-label={card.ariaLabel}>
            <MetricCard
              className={metricCardLinkClass}
              eyebrow={card.eyebrow}
              value={card.value}
              delta={overviewCardDetail(card.section)}
              tone={card.tone}
              icon={card.icon}
            />
          </Link>
        ))}
      </div>
    </Panel>
  );
}

function CommandOpsBadges({ controller }: { controller: OverviewController }) {
  const { overview, stateFeed } = controller;
  if (!overview) {
    return null;
  }

  return (
    <div className="flex flex-wrap items-center justify-end gap-2">
      <StatusBadge status="active" label={`Updated ${formatDateTime(overview.generatedAt)}`} />
      <StatusBadge status={overview.projection?.status ?? "stale"} label={projectionStatusLabel(overview.projection)} />
      {stateFeed.status === "unavailable" ? <StatusBadge status="stale" label="Live feed unavailable" /> : null}
      {overview.operations.deadLetterCount > 0 ? (
        <StatusBadge
          status="degraded"
          label={`${overview.operations.deadLetterCount} recovery item${overview.operations.deadLetterCount === 1 ? "" : "s"}`}
        />
      ) : null}
    </div>
  );
}

function OverviewLoadedContent({ controller }: { controller: OverviewController }) {
  if (controller.loading || !controller.overview || !controller.derived) {
    return (
      <div className="flex min-h-[320px] items-center justify-center rounded-[1.75rem] border border-zinc-900/10 bg-white/70 dark:border-white/10 dark:bg-zinc-950/50">
        <Spinner size="lg" />
      </div>
    );
  }

  return (
    <>
      <AttentionSystemGrid overview={controller.overview} derived={controller.derived} />
      <DepartmentTaskGrid overview={controller.overview} derived={controller.derived} />
      <ApprovalUsageGrid overview={controller.overview} />
      <Panel title="What is happening" description="Short operational narrative for the visible window.">
        <TimelineList items={controller.derived.activity} />
      </Panel>
    </>
  );
}

function AttentionSystemGrid({
  overview,
  derived,
}: {
  overview: OrganizationOverviewVM;
  derived: OverviewDerivedState;
}) {
  return (
    <div className="grid gap-6 2xl:grid-cols-[1.18fr_0.82fr]">
      <AttentionPanel items={derived.attentionItems} />
      <SystemHealthPanel items={derived.systemHealth} />
    </div>
  );
}

function AttentionPanel({ items }: { items: AttentionItem[] }) {
  return (
    <div id="attention-required" className="scroll-mt-36">
      <Panel
        title="Attention required"
        description="Critical and near-critical work that should pull operator focus first."
        action={
          <StatusBadge
            status={items.length ? "failed" : "active"}
            label={items.length ? `${items.length} open` : "Clear"}
          />
        }
      >
        {items.length ? (
          <div className="space-y-3">
            {items.map((item) => (
              <AttentionRow key={item.id} item={item} />
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
  );
}

function AttentionRow({ item }: { item: AttentionItem }) {
  return (
    <div className="rounded-[1.25rem] border border-zinc-900/8 bg-[var(--panel-muted)] p-4 dark:border-white/8">
      <div className="flex items-start justify-between gap-4">
        <div className="min-w-0">
          <div className="flex items-center gap-3">
            <span className="flex size-9 items-center justify-center rounded-2xl border border-zinc-900/10 bg-white dark:border-white/10 dark:bg-white/5">
              {item.tone === "rose" ? overviewIcons.attention : overviewIcons.paused}
            </span>
            <div className="min-w-0">
              <p className="truncate text-sm font-semibold text-zinc-950 dark:text-zinc-50">{item.title}</p>
              <p className="mt-1 text-sm leading-6 text-zinc-600 dark:text-zinc-300">{item.detail}</p>
            </div>
          </div>
        </div>
        <div className="flex shrink-0 items-center gap-2">
          <StatusBadge status={item.tone === "rose" ? "failed" : "paused"} label={item.owner} />
          <Button asChild size="sm" className="rounded-full">
            <Link href={item.href}>
              {item.action}
              <ArrowRight className="size-4" />
            </Link>
          </Button>
        </div>
      </div>
    </div>
  );
}

function SystemHealthPanel({ items }: { items: OverviewDerivedState["systemHealth"] }) {
  return (
    <div id="system-health" className="scroll-mt-36">
      <Panel
        title="System health"
        description="Fast readout of the operating posture across control, humans, and economics."
      >
        <div className="space-y-3">
          {items.map((item) => (
            <SystemHealthRow key={item.id} item={item} />
          ))}
        </div>
      </Panel>
    </div>
  );
}

function SystemHealthRow({ item }: { item: OverviewDerivedState["systemHealth"][number] }) {
  return (
    <div className="rounded-[1.2rem] border border-zinc-900/8 bg-[var(--panel-muted)] p-4 dark:border-white/8">
      <div className="flex items-center justify-between gap-3">
        <div>
          <p className="text-sm font-semibold text-zinc-950 dark:text-zinc-50">{item.label}</p>
          <p className="mt-1 text-sm leading-6 text-zinc-600 dark:text-zinc-300">{item.detail}</p>
        </div>
        <div className="text-right">
          <p className="text-sm font-semibold text-zinc-950 dark:text-zinc-50">{item.value}</p>
          <div className="mt-2">
            <StatusBadge status={item.status} />
          </div>
        </div>
      </div>
    </div>
  );
}

function DepartmentTaskGrid({
  overview,
  derived,
}: {
  overview: OrganizationOverviewVM;
  derived: OverviewDerivedState;
}) {
  return (
    <div className="grid gap-6 2xl:grid-cols-[1.05fr_0.95fr]">
      <ActiveDepartmentsPanel overview={overview} derived={derived} />
      <BlockedTasksPanel tasks={derived.blockedTasks} />
    </div>
  );
}

function ActiveDepartmentsPanel({
  overview,
  derived,
}: {
  overview: OrganizationOverviewVM;
  derived: OverviewDerivedState;
}) {
  return (
    <div id="active-departments" className="scroll-mt-36">
      <Panel
        title="Active departments"
        description="Which departments are currently doing work, what they are focused on, and how much cost they are carrying."
        action={
          <Button asChild variant="outline" className="rounded-full">
            <Link href="/departments">
              Open departments
              <ArrowRight className="size-4" />
            </Link>
          </Button>
        }
      >
        {overview.activeDepartments.length ? (
          <div className="space-y-3">
            {overview.activeDepartments.slice(0, 6).map((department) => (
              <DepartmentRow
                key={department.id}
                department={department}
                summary={derived.departmentTaskMap.get(department.id) ?? "Awaiting the next available task."}
              />
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
  );
}

function DepartmentRow({
  department,
  summary,
}: {
  department: OrganizationOverviewVM["activeDepartments"][number];
  summary: string;
}) {
  return (
    <Link
      href={`/departments?department=${department.id}`}
      className="flex items-start justify-between gap-4 rounded-[1.25rem] border border-zinc-900/8 bg-[var(--panel-muted)] p-4 transition-colors hover:bg-zinc-950 hover:text-white dark:border-white/8 dark:hover:bg-white dark:hover:text-zinc-950"
    >
      <div className="min-w-0">
        <div className="flex items-center gap-3">
          <p className="truncate text-sm font-semibold">{department.name}</p>
          <StatusBadge status={department.status} />
        </div>
        <p className="mt-2 text-sm leading-6 text-zinc-600 dark:text-zinc-300">{summary}</p>
      </div>
      <div className="shrink-0 text-right">
        <p className="text-xs uppercase tracking-[0.16em] text-zinc-500 dark:text-zinc-400">Cost</p>
        <p className="mt-2 text-sm font-semibold">{formatCurrency(department.totalCostUsd)}</p>
      </div>
    </Link>
  );
}

function BlockedTasksPanel({ tasks }: { tasks: OverviewDerivedState["blockedTasks"] }) {
  return (
    <div id="blocked-tasks" className="scroll-mt-36">
      <Panel
        title="Department activity needing help"
        description="Work that is currently stalled by approval, failure, or missing operator action."
        action={
          <Button asChild variant="outline" className="rounded-full">
            <Link href="/tasks">
              Open activity
              <ArrowRight className="size-4" />
            </Link>
          </Button>
        }
      >
        {tasks.length ? (
          <div className="space-y-3">
            {tasks.map((task) => (
              <BlockedTaskRow key={task.id} task={task} />
            ))}
          </div>
        ) : (
          <EmptyBlock
            title="No blocked tasks"
            description="Waiting and failed task items are clear in the current window."
          />
        )}
      </Panel>
    </div>
  );
}

function BlockedTaskRow({ task }: { task: OverviewDerivedState["blockedTasks"][number] }) {
  return (
    <Link
      href={task.operationId ? `/runs/${task.operationId}` : "/tasks"}
      className="block rounded-[1.2rem] border border-zinc-900/8 bg-[var(--panel-muted)] p-4 transition-colors hover:bg-zinc-950 hover:text-white dark:border-white/8 dark:hover:bg-white dark:hover:text-zinc-950"
    >
      <div className="flex items-start justify-between gap-3">
        <div className="min-w-0">
          <div className="flex items-center gap-3">
            <p className="truncate text-sm font-semibold">{task.title}</p>
            <StatusBadge status={task.status} />
          </div>
          <p className="mt-2 text-sm leading-6 text-zinc-600 dark:text-zinc-300">{task.summary}</p>
        </div>
        <div className="shrink-0 text-right text-xs text-zinc-500 dark:text-zinc-400">
          <p>{task.priority} priority</p>
          <p className="mt-2">{formatDateTime(task.updatedAt)}</p>
        </div>
      </div>
    </Link>
  );
}

function ApprovalUsageGrid({ overview }: { overview: OrganizationOverviewVM }) {
  return (
    <div className="grid gap-6 2xl:grid-cols-[0.92fr_1.08fr]">
      <PendingApprovalsPanel overview={overview} />
      <UsageBudgetPanel overview={overview} />
    </div>
  );
}

function PendingApprovalsPanel({ overview }: { overview: OrganizationOverviewVM }) {
  return (
    <div id="pending-approvals" className="scroll-mt-36">
      <Panel
        title="Pending approvals"
        description="Approval items that should be resolvable without opening raw logs."
        action={
          <Button asChild variant="outline" className="rounded-full">
            <Link href="/approvals">
              Open approvals
              <ArrowRight className="size-4" />
            </Link>
          </Button>
        }
      >
        {overview.pendingApprovals.length ? (
          <div className="space-y-3">
            {overview.pendingApprovals.slice(0, 5).map((approval) => (
              <ApprovalRow key={approval.id} approval={approval} />
            ))}
          </div>
        ) : (
          <EmptyBlock title="No pending approvals" description="The human-in-the-loop queue is currently clear." />
        )}
      </Panel>
    </div>
  );
}

function ApprovalRow({ approval }: { approval: OrganizationOverviewVM["pendingApprovals"][number] }) {
  return (
    <div className="rounded-[1.25rem] border border-zinc-900/8 bg-[var(--panel-muted)] p-4 dark:border-white/8">
      <div className="flex items-start justify-between gap-4">
        <div className="min-w-0">
          <div className="flex items-center gap-3">
            <p className="text-sm font-semibold text-zinc-950 dark:text-zinc-50">{approval.label}</p>
            <StatusBadge status={approval.status} />
          </div>
          <p className="mt-2 text-sm leading-6 text-zinc-600 dark:text-zinc-300">{approval.promptMessage}</p>
        </div>
        <Button asChild size="sm" className="rounded-full">
          <Link href="/approvals">Decide</Link>
        </Button>
      </div>
    </div>
  );
}

function UsageBudgetPanel({ overview }: { overview: OrganizationOverviewVM }) {
  return (
    <div id="usage-budget" className="scroll-mt-36">
      <Panel
        title="Usage and budget"
        description="Backend-owned spend and metric provenance for the current operating window."
      >
        <div className="grid gap-3 md:grid-cols-3">
          <CostMetricCard
            label="Tracked cost"
            value={financialMetricLabel(overview.metricProvenance.totalCostUsd)}
            detail={metricProvenanceLine(overview.metricProvenance.totalCostUsd)}
          />
          <CostMetricCard
            label="Revenue"
            value={notInstrumentedLabel}
            detail={metricProvenanceLine(overview.metricProvenance.revenue)}
          />
          <CostMetricCard
            label="Profit"
            value={notInstrumentedLabel}
            detail={metricProvenanceLine(overview.metricProvenance.profit)}
          />
        </div>
        <div className="mt-4 space-y-4">
          {overview.costByType.map((row) => (
            <div key={row.type} className="space-y-2">
              <div className="flex items-center justify-between gap-3 text-sm">
                <span className="font-medium text-zinc-900 capitalize dark:text-zinc-100">
                  {row.type.replace(/_/g, " ")}
                </span>
                <span className="text-zinc-600 dark:text-zinc-300">{formatCurrency(row.totalCostUsd)}</span>
              </div>
              <TrendBar value={row.totalCostUsd} total={Math.max(overview.summary.totalCostUsd, 1)} tone="rose" />
            </div>
          ))}
        </div>
        <div className="mt-4">
          <KeyValueGrid
            columns={2}
            items={[
              { label: "Cost source types", value: formatCompactNumber(overview.costByType.length) },
              {
                label: "Operating window",
                value: `${formatCompactNumber(overview.summary.operationCount24h)} operations in 24h`,
              },
            ]}
          />
        </div>
      </Panel>
    </div>
  );
}

function CostMetricCard({ label, value, detail }: { label: string; value: string; detail: string }) {
  return (
    <div className="rounded-[1.2rem] border border-zinc-900/8 bg-[var(--panel-muted)] p-4 dark:border-white/8">
      <p className="text-[11px] uppercase tracking-[0.18em] text-zinc-500 dark:text-zinc-400">{label}</p>
      <p className="mt-2 text-2xl font-semibold text-zinc-950 dark:text-zinc-50">{value}</p>
      <p className="mt-2 text-xs leading-5 text-zinc-500 dark:text-zinc-400">{detail}</p>
    </div>
  );
}

export default function OverviewPage() {
  const controller = useOverviewController();
  const inspector = useMemo(
    () => <OverviewInspector overview={controller.overview} derived={controller.derived} />,
    [controller.derived, controller.overview],
  );

  return (
    <ProtectedRoute>
      <DashboardLayout inspector={inspector}>
        <div className="space-y-6">
          <CommandOpsPanel controller={controller} />
          {controller.error ? (
            <Alert variant="destructive">
              <AlertDescription>{controller.error}</AlertDescription>
            </Alert>
          ) : null}
          <OverviewLoadedContent controller={controller} />
        </div>
      </DashboardLayout>
    </ProtectedRoute>
  );
}
