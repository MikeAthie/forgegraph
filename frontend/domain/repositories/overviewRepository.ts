import { systemStateApi } from "@/lib/api";
import { toOperationStatusVM, toTaskVMFromRecord, type OperationStatusVM, type TaskVM } from "@/domain/translation";

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
    recentTopics: string[];
  };
  costByType: OverviewCostRowVM[];
  generatedAt: string;
};

export const overviewRepository = {
  get: async (): Promise<OrganizationOverviewVM> => {
    const overview = await systemStateApi.getOverview();

    return {
      organization: overview.organization,
      summary: {
        activeDepartmentCount: overview.summary.active_agent_count,
        activeTaskCount: overview.summary.active_task_count,
        pendingApprovalCount: overview.summary.pending_decision_count,
        operationCount24h: overview.summary.execution_count_24h,
        knowledgeItemCount: overview.summary.memory_observation_count,
        totalCostUsd: overview.summary.total_cost_usd,
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
        recentTopics: overview.memory.recent_topics,
      },
      costByType: overview.accounting.cost_by_type.map((row) => ({
        type: row.cost_type,
        totalCostUsd: row.total_cost_usd,
        entryCount: row.entry_count,
      })),
      generatedAt: overview.generated_at,
    };
  },
};

export type OverviewRepository = typeof overviewRepository;
