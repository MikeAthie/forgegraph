import {
  systemStateApi,
  type AccountingMetric,
  type MetricProvenance,
  type OverviewSectionMetadata,
  type ProjectionMetadata,
} from "@/lib/api";
import {
  toOperationStatusVM,
  toTaskVMFromRecord,
  type MetricProvenanceVM,
  type OperationStatusVM,
  type TaskVM,
} from "@/domain/translation";

export type OverviewDepartmentVM = {
  id: string;
  name: string;
  status: string;
  lastSeenAt: string | null;
  totalCostUsd: number;
};

export type OverviewApprovalVM = {
  id: string;
  operationId: string | null;
  taskId: string | null;
  departmentId: string | null;
  status: string;
  label: string;
  promptMessage: string;
  requestedAt: string;
};

export type OverviewOperationVM = {
  id: string;
  companyId: string;
  companyName: string;
  setupRevisionId: string;
  status: OperationStatusVM;
  startedAt: string | null;
  endedAt: string | null;
  durationMs: number | null;
};

export type OverviewCostRowVM = {
  type: string;
  totalCostUsd: number;
  entryCount: number;
};

export type OverviewSectionVM = {
  source: string;
  computedAt: string | null;
  lastUpdatedAt: string | null;
  freshnessMs: number | null;
  status: string;
  stale: boolean;
  degraded: boolean;
};

export type OrganizationOverviewVM = {
  organization: {
    id: string;
    name: string;
  };
  summary: {
    activeDepartmentCount: number;
    activeTaskCount: number;
    pendingApprovalCount: number;
    operationCount24h: number;
    knowledgeItemCount: number;
    totalCostUsd: number;
  };
  activeDepartments: OverviewDepartmentVM[];
  activeTasks: TaskVM[];
  pendingApprovals: OverviewApprovalVM[];
  recentOperations: OverviewOperationVM[];
  memory: {
    activeKnowledgeCount: number;
    writeCount24h: number;
    recentTopics: string[];
    section: OverviewSectionVM;
  };
  running: OverviewSectionVM & {
    activeAgentCount: number;
    runningTaskCount: number;
    operationCount24h: number;
  };
  blocked: OverviewSectionVM & {
    blockedTaskCount: number;
  };
  decisions: OverviewSectionVM & {
    pendingDecisionCount: number;
  };
  costs: OverviewSectionVM & {
    totalCostUsd: number;
    currency: string;
  };
  failures: OverviewSectionVM & {
    deadLetterCount: number;
    taskDeadLetterCount: number;
    eventDeadLetterCount: number;
    runtimeIntentDeadLetterCount: number;
    runtimeIntentLagSeconds: number;
  };
  metricProvenance: {
    totalCostUsd: MetricProvenanceVM;
    revenue: MetricProvenanceVM;
    profit: MetricProvenanceVM;
  };
  costByType: OverviewCostRowVM[];
  projection: ProjectionMetadata | null;
  operations: {
    status: string;
    deadLetterCount: number;
    taskDeadLetterCount: number;
    eventDeadLetterCount: number;
    runtimeIntentDeadLetterCount: number;
    projectionStatus: string;
    projectionLagSeconds: number;
    runtimeIntentLagSeconds: number;
  };
  generatedAt: string;
};

function metricProvenance(metric: MetricProvenance | undefined, fallback: MetricProvenanceVM): MetricProvenanceVM {
  if (!metric) {
    return fallback;
  }

  return {
    source: metric.source,
    computedAt: metric.computed_at,
    freshnessMs: metric.freshness_ms,
    status: metric.status,
    value: metric.value ?? null,
  };
}

function metricFromAccountingMetric(
  metric: AccountingMetric | undefined,
  fallback: MetricProvenanceVM,
): MetricProvenanceVM {
  if (!metric) {
    return fallback;
  }

  if (metric.status === "available") {
    return {
      source: metric.source,
      computedAt: metric.computed_at,
      freshnessMs: null,
      status: metric.status,
      value: metric.value,
      currency: metric.currency,
    };
  }

  return {
    source: metric.source,
    computedAt: metric.computed_at,
    freshnessMs: null,
    status: metric.status,
    value: null,
    reason: metric.reason,
  };
}

function sectionMetadata(
  section: Partial<OverviewSectionMetadata> | undefined,
  fallback: Partial<OverviewSectionMetadata>,
): OverviewSectionVM {
  const resolved = section ?? fallback;
  const status = String(resolved.status ?? fallback.status ?? "fresh");
  return {
    source: String(resolved.source ?? fallback.source ?? "backend_projection"),
    computedAt: resolved.computed_at ?? fallback.computed_at ?? null,
    lastUpdatedAt:
      resolved.last_updated_at ?? fallback.last_updated_at ?? resolved.computed_at ?? fallback.computed_at ?? null,
    freshnessMs:
      typeof resolved.freshness_ms === "number"
        ? resolved.freshness_ms
        : typeof fallback.freshness_ms === "number"
          ? fallback.freshness_ms
          : null,
    status,
    stale: Boolean(resolved.stale ?? fallback.stale ?? status === "stale"),
    degraded: Boolean(resolved.degraded ?? fallback.degraded ?? status === "degraded"),
  };
}

export const overviewRepository = {
  get: async (): Promise<OrganizationOverviewVM> => {
    const overview = await systemStateApi.getOverview();
    const accountingProvenance = overview.accounting.metric_provenance ?? {};
    const accountingMetrics = overview.accounting.metrics ?? {};
    const projectionFallback: Partial<OverviewSectionMetadata> = {
      source: "backend_projection",
      computed_at:
        overview.projection?.computed_at ?? overview.accounting.projection?.computed_at ?? overview.generated_at,
      last_updated_at:
        overview.projection?.last_updated_at ??
        overview.projection?.watermark ??
        overview.accounting.projection?.watermark ??
        overview.generated_at,
      freshness_ms: overview.projection?.freshness_ms ?? overview.projection?.projection_lag_ms ?? 0,
      status: overview.projection?.status ?? overview.accounting.projection?.status ?? "fresh",
      stale: overview.projection?.stale ?? overview.projection?.status === "stale",
      degraded: overview.projection?.degraded ?? overview.projection?.status === "degraded",
    };
    const totalCostUsd = metricFromAccountingMetric(accountingMetrics.cost, {
      source: "backend_ledger",
      computedAt: overview.accounting.generated_at ?? overview.generated_at,
      freshnessMs: null,
      status: "available",
      value: overview.summary.total_cost_usd,
      currency: "USD",
    });
    const revenue = metricFromAccountingMetric(
      accountingMetrics.revenue,
      metricProvenance(accountingProvenance.revenue, {
        source: "backend_accounting",
        computedAt: overview.accounting.generated_at ?? overview.generated_at,
        freshnessMs: null,
        status: "not_instrumented",
        value: null,
      }),
    );
    const profit = metricFromAccountingMetric(
      accountingMetrics.profit,
      metricProvenance(accountingProvenance.profit, {
        source: "backend_accounting",
        computedAt: overview.accounting.generated_at ?? overview.generated_at,
        freshnessMs: null,
        status: "not_instrumented",
        value: null,
      }),
    );
    const runningSection = sectionMetadata(overview.running, projectionFallback);
    const blockedSection = sectionMetadata(overview.blocked, projectionFallback);
    const decisionsSection = sectionMetadata(overview.decisions, projectionFallback);
    const costSection = sectionMetadata(overview.costs, {
      source: totalCostUsd.source,
      computed_at: totalCostUsd.computedAt ?? overview.accounting.generated_at ?? overview.generated_at,
      last_updated_at: totalCostUsd.computedAt ?? overview.accounting.generated_at ?? overview.generated_at,
      freshness_ms: totalCostUsd.freshnessMs ?? 0,
      status: totalCostUsd.status === "available" ? "fresh" : totalCostUsd.status,
      stale: false,
      degraded: totalCostUsd.status !== "available",
    });
    const failureSection = sectionMetadata(overview.failures, {
      source: "backend_ops",
      computed_at: overview.operations?.generated_at ?? overview.generated_at,
      last_updated_at: overview.operations?.generated_at ?? overview.generated_at,
      freshness_ms: 0,
      status: overview.operations?.status ?? "fresh",
      stale: false,
      degraded: overview.operations?.status === "degraded",
    });
    const memorySection = sectionMetadata(overview.memory, projectionFallback);

    return {
      organization: overview.organization,
      summary: {
        activeDepartmentCount: overview.summary.active_agent_count,
        activeTaskCount: overview.summary.active_task_count,
        pendingApprovalCount: overview.summary.pending_decision_count,
        operationCount24h: overview.summary.execution_count_24h,
        knowledgeItemCount: overview.summary.memory_observation_count,
        totalCostUsd:
          totalCostUsd.status === "available" && typeof totalCostUsd.value === "number" ? totalCostUsd.value : 0,
      },
      activeDepartments: overview.active_agents.map((department) => ({
        id: department.id,
        name: department.display_name,
        status: department.status,
        lastSeenAt: department.last_seen_at,
        totalCostUsd: department.total_cost_usd,
      })),
      activeTasks: overview.active_tasks.map(toTaskVMFromRecord),
      pendingApprovals: overview.pending_decisions.map((approval) => ({
        id: approval.id,
        operationId: approval.execution_id,
        taskId: approval.task_id,
        departmentId: approval.agent_id,
        status: approval.status,
        label: approval.decision_type.replace(/_/g, " "),
        promptMessage: String(
          approval.context_json?.summary ??
            approval.context_json?.prompt_message ??
            "Operator approval required before this operation can continue.",
        ),
        requestedAt: approval.requested_at ?? approval.created_at,
      })),
      recentOperations: overview.recent_executions.map((operation) => ({
        id: operation.id,
        companyId: operation.workflow_id,
        companyName: operation.workflow_name,
        setupRevisionId: operation.workflow_revision_id,
        status: toOperationStatusVM(operation.status),
        startedAt: operation.started_at,
        endedAt: operation.ended_at,
        durationMs: operation.duration_ms,
      })),
      memory: {
        activeKnowledgeCount: overview.memory.active_observation_count,
        writeCount24h: overview.memory.memory_write_count_24h ?? overview.memory.active_observation_count,
        recentTopics: overview.memory.recent_topics,
        section: memorySection,
      },
      running: {
        ...runningSection,
        activeAgentCount: overview.running?.active_agent_count ?? overview.summary.active_agent_count,
        runningTaskCount: overview.running?.running_task_count ?? overview.summary.active_task_count,
        operationCount24h: overview.running?.operation_count_24h ?? overview.summary.execution_count_24h,
      },
      blocked: {
        ...blockedSection,
        blockedTaskCount:
          overview.blocked?.blocked_task_count ??
          overview.active_tasks.filter((task) =>
            ["paused", "waiting", "waiting_for_decision", "failed"].includes(task.status),
          ).length,
      },
      decisions: {
        ...decisionsSection,
        pendingDecisionCount: overview.decisions?.pending_decision_count ?? overview.summary.pending_decision_count,
      },
      costs: {
        ...costSection,
        totalCostUsd:
          overview.costs?.total_cost_usd ??
          (totalCostUsd.status === "available" && typeof totalCostUsd.value === "number" ? totalCostUsd.value : 0),
        currency: overview.costs?.currency ?? totalCostUsd.currency ?? "USD",
      },
      failures: {
        ...failureSection,
        deadLetterCount: overview.failures?.dead_letter_count ?? overview.operations?.dead_letter_count ?? 0,
        taskDeadLetterCount:
          overview.failures?.task_dead_letter_count ?? overview.operations?.task_dead_letter_count ?? 0,
        eventDeadLetterCount:
          overview.failures?.event_dead_letter_count ?? overview.operations?.event_dead_letter_count ?? 0,
        runtimeIntentDeadLetterCount:
          overview.failures?.runtime_intent_dead_letter_count ??
          overview.operations?.runtime_intent_dead_letter_count ??
          0,
        runtimeIntentLagSeconds:
          overview.failures?.runtime_intent_lag_seconds ?? overview.operations?.runtime_intent_lag_seconds ?? 0,
      },
      metricProvenance: {
        totalCostUsd: metricFromAccountingMetric(
          accountingMetrics.cost,
          metricProvenance(accountingProvenance.total_cost_usd, totalCostUsd),
        ),
        revenue,
        profit,
      },
      costByType: overview.accounting.cost_by_type.map((row) => ({
        type: row.cost_type,
        totalCostUsd: row.total_cost_usd,
        entryCount: row.entry_count,
      })),
      projection: overview.projection ?? overview.accounting.projection ?? null,
      operations: {
        status: overview.operations?.status ?? "fresh",
        deadLetterCount: overview.operations?.dead_letter_count ?? 0,
        taskDeadLetterCount: overview.operations?.task_dead_letter_count ?? 0,
        eventDeadLetterCount: overview.operations?.event_dead_letter_count ?? 0,
        runtimeIntentDeadLetterCount: overview.operations?.runtime_intent_dead_letter_count ?? 0,
        projectionStatus: overview.operations?.projection_status ?? overview.projection?.status ?? "fresh",
        projectionLagSeconds: overview.operations?.projection_lag_seconds ?? overview.projection?.lag_seconds ?? 0,
        runtimeIntentLagSeconds: overview.operations?.runtime_intent_lag_seconds ?? 0,
      },
      generatedAt: overview.generated_at,
    };
  },
};

export type OverviewRepository = typeof overviewRepository;
