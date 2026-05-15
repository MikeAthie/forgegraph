import {
  agentsApi,
  decisionsApi,
  departmentsApi,
  memoryApi,
  routingApi,
  type AgentRegistryEntry,
  type DepartmentDTO,
  type MemoryObservation,
  type TaskRoutingRecordDTO,
} from "@/lib/api";
import { toApprovalVMFromDecision } from "@/domain/translation";
import type {
  ApprovalVM,
  DepartmentActivityStatusVM,
  DepartmentActivityVM,
  DepartmentBlockerVM,
  DepartmentProposalVM,
  DepartmentVM,
  OperationRefVM,
  OperationVM,
  TaskVM,
} from "@/domain/translation";
import { operationRepository } from "./operationRepository";

type DepartmentKnowledgeVM = {
  title: string;
  content: string;
  topic: string;
};

function asText(value: unknown): string | null {
  return typeof value === "string" && value.trim() ? value.trim() : null;
}

function sentenceCase(value: string): string {
  const normalized = value.replace(/[_-]+/g, " ").trim();
  return normalized ? `${normalized.charAt(0).toUpperCase()}${normalized.slice(1)}` : "Department";
}

function getDepartmentRole(agent: AgentRegistryEntry): string {
  const capabilities = Object.keys(agent.capabilities_json ?? {});
  if (capabilities.length > 0) {
    return `Owns ${capabilities.slice(0, 2).map(sentenceCase).join(" and ").toLowerCase()}`;
  }
  return asText(agent.default_model) ? "AI reasoning department" : "Company thinking department";
}

function getActivityStatus(agent: AgentRegistryEntry): DepartmentActivityStatusVM {
  if (agent.pending_decisions > 0) {
    return "waiting";
  }
  if (agent.status === "active" || agent.task_count > 0) {
    return "active";
  }
  return "idle";
}

function getDepartmentPurpose(agent: AgentRegistryEntry): string {
  const policyKeys = Object.keys(agent.policy_snapshot_json ?? {});
  if (policyKeys.length > 0) {
    return `Uses ${policyKeys.slice(0, 2).map(sentenceCase).join(" and ").toLowerCase()} policy to decide how work should move.`;
  }
  if (agent.default_model) {
    return `Reasons with ${agent.default_model} to turn company context into useful recommendations.`;
  }
  return "Turns company context into recommendations, approvals, and task direction.";
}

function toDepartmentVMFromAgent(agent: AgentRegistryEntry): DepartmentVM {
  const activityStatus = getActivityStatus(agent);
  const role = getDepartmentRole(agent);

  return {
    id: agent.id,
    label: agent.display_name,
    name: agent.display_name,
    role,
    responsibility: getDepartmentPurpose(agent),
    purpose: getDepartmentPurpose(agent),
    tools: [],
    category: "department",
    activityStatus,
    currentFocus:
      activityStatus === "waiting"
        ? "Waiting for an approval before it can move its recommendation forward."
        : activityStatus === "active"
          ? "Thinking through active company work and shaping the next useful move."
          : "Ready to contribute when a company operation needs its judgment.",
    activeTaskCount: agent.task_count,
    pendingDecisionCount: agent.pending_decisions,
    totalCostUsd: agent.total_cost_usd,
    defaultModel: agent.default_model,
    lastOperationId: agent.last_execution_id,
  };
}

function toDepartmentVMFromRegistry(department: DepartmentDTO): DepartmentVM {
  const typeLabel = department.department_type ? sentenceCase(department.department_type) : "Department";
  const serviceTags = department.service_tags ?? [];
  const responsibility =
    typeof department.metadata?.responsibility === "string" && department.metadata.responsibility.trim()
      ? department.metadata.responsibility.trim()
      : serviceTags.length
        ? `Owns ${serviceTags.slice(0, 3).map(sentenceCase).join(", ").toLowerCase()} work.`
        : "Owns routed company work, handoffs, and decisions for its service area.";

  return {
    id: department.id,
    label: department.name,
    name: department.name,
    role: department.role === "lead" ? "You lead this department" : `${typeLabel} work owner`,
    responsibility,
    purpose: responsibility,
    tools: serviceTags,
    category: "department",
    activityStatus: "idle",
    currentFocus: "Ready to own routed work for accessible company operations.",
    activeTaskCount: 0,
    pendingDecisionCount: 0,
    totalCostUsd: 0,
    defaultModel: null,
    lastOperationId: null,
  };
}

function toKnowledgeVM(memory: MemoryObservation): DepartmentKnowledgeVM {
  return {
    title: memory.title || memory.topic_key || "Knowledge item",
    content: memory.content,
    topic: memory.topic_key,
  };
}

function getTaskFreshness(task: TaskVM): string {
  return task.updatedAt ?? task.startedAt ?? task.createdAt ?? "";
}

function getOperationName(operation: OperationVM): string {
  if (operation.brief && operation.brief !== "Company operation") {
    return operation.brief;
  }
  if (operation.companyName) {
    return `${operation.companyName} operation`;
  }
  return `Operation ${operation.id.slice(0, 8)}`;
}

function toOperationRefVM(operation: OperationVM, role: string): OperationRefVM {
  return {
    id: operation.id,
    name: getOperationName(operation),
    status: operation.status,
    role,
    currentStage:
      operation.status === "completed"
        ? "Deliverable ready"
        : operation.status === "failed"
          ? "Needs attention"
          : operation.currentDepartmentName
            ? `${operation.currentDepartmentName} is participating`
            : "Coordinating department work",
    startedAt: operation.startedAt,
  };
}

function toProposalStatus(approval: ApprovalVM): DepartmentProposalVM["status"] {
  if (approval.status === "approved") {
    return "accepted";
  }
  if (approval.status === "rejected") {
    return "rejected";
  }
  return "awaiting approval";
}

function buildOperationRefs(
  department: DepartmentVM,
  tasks: TaskVM[],
  operations: OperationVM[],
  approvals: ApprovalVM[],
  routingRecords: TaskRoutingRecordDTO[],
): OperationRefVM[] {
  const operationIds = new Set<string>();
  if (department.lastOperationId) {
    operationIds.add(department.lastOperationId);
  }
  for (const task of tasks) {
    if (task.operationId) {
      operationIds.add(task.operationId);
    }
  }
  for (const approval of approvals) {
    if (approval.operationId) {
      operationIds.add(approval.operationId);
    }
  }
  for (const routingRecord of routingRecords) {
    if (routingRecord.run_id) {
      operationIds.add(routingRecord.run_id);
    }
  }

  const taskOperationIds = new Set(tasks.flatMap((task) => (task.operationId ? [task.operationId] : [])));
  const approvalOperationIds = new Set(
    approvals.flatMap((approval) => (approval.operationId ? [approval.operationId] : [])),
  );
  const refs: OperationRefVM[] = [];
  for (const operation of operations) {
    const isCurrent = operation.currentDepartmentName === department.name;
    if (!operationIds.has(operation.id) && !isCurrent) {
      continue;
    }
    const hasTask = taskOperationIds.has(operation.id);
    const hasApproval = approvalOperationIds.has(operation.id);
    const role = isCurrent
      ? "Currently shaping the operation"
      : hasApproval
        ? "Proposed an action awaiting review"
        : hasTask
          ? "Contributing assigned tasks"
          : "Recent participant";
    refs.push(toOperationRefVM(operation, role));
  }

  if (refs.length > 0) {
    return refs;
  }

  if (!department.lastOperationId) {
    return [];
  }

  return [
    {
      id: department.lastOperationId,
      name: `Operation ${department.lastOperationId.slice(0, 8)}`,
      status: "queued",
      role: "Recent participant",
      currentStage: "Not currently active",
      startedAt: null,
    },
  ];
}

function buildProposals(approvals: ApprovalVM[], operations: OperationRefVM[]): DepartmentProposalVM[] {
  const operationById = new Map(operations.map((operation) => [operation.id, operation]));
  return approvals.map((approval) => ({
    id: approval.id,
    description: approval.promptMessage,
    status: toProposalStatus(approval),
    operation: operationById.get(approval.operationId) ?? null,
    createdAt: approval.createdAt,
  }));
}

function buildBlockers(
  approvals: ApprovalVM[],
  tasks: TaskVM[],
  operations: OperationRefVM[],
  routingRecords: TaskRoutingRecordDTO[],
): DepartmentBlockerVM[] {
  const operationById = new Map(operations.map((operation) => [operation.id, operation]));
  const approvalBlockers = approvals.flatMap((approval) =>
    approval.status === "pending"
      ? [
          {
            id: approval.id,
            description: approval.promptMessage,
            status: "waiting" as const,
            operation: operationById.get(approval.operationId) ?? null,
          },
        ]
      : [],
  );

  const taskBlockers = tasks.flatMap((task) =>
    task.status === "paused" || task.status === "failed"
      ? [
          {
            id: task.id,
            description: task.issuePreview || task.summary,
            status: task.status === "failed" ? ("failed" as const) : ("waiting" as const),
            operation: task.operationId ? (operationById.get(task.operationId) ?? null) : null,
          },
        ]
      : [],
  );

  const routingBlockers = routingRecords.flatMap((record) =>
    record.status === "blocked"
      ? [
          {
            id: record.id,
            description: record.reason || "Routed work is blocked before this department can continue.",
            status: "waiting" as const,
            operation: operationById.get(record.run_id) ?? null,
          },
        ]
      : [],
  );

  return [...approvalBlockers, ...taskBlockers, ...routingBlockers];
}

function buildFocus(
  department: DepartmentVM,
  tasks: TaskVM[],
  approvals: ApprovalVM[],
  operations: OperationRefVM[],
  knowledge: DepartmentKnowledgeVM[],
) {
  const currentTask = tasks.find((task) => task.status === "running" || task.status === "paused") ?? tasks[0] ?? null;
  const pendingApproval = approvals.find((approval) => approval.status === "pending") ?? null;
  const currentOperation = operations[0] ?? null;
  const objective =
    currentTask?.summary ||
    pendingApproval?.promptMessage ||
    currentOperation?.name ||
    department.currentFocus ||
    "Ready to interpret company context and propose the next useful move.";
  const knowledgeSignal = knowledge[0]?.title ? ` Recent knowledge points to ${knowledge[0].title}.` : "";
  const reasoning = pendingApproval
    ? `This department has formed a proposal and is waiting for an approval before the company acts.${knowledgeSignal}`
    : currentTask
      ? `It is turning that intent into task work while keeping the operation aligned to the company objective.${knowledgeSignal}`
      : `It is not blocked; it is available to reason through the next operation when needed.${knowledgeSignal}`;

  return {
    objective,
    reasoning,
  };
}

export const departmentRepository = {
  list: async (): Promise<DepartmentVM[]> => {
    const departments = await departmentsApi.list();
    if (departments.length > 0) {
      return departments.map(toDepartmentVMFromRegistry);
    }
    const agents = await agentsApi.list();
    return agents.map(toDepartmentVMFromAgent);
  },

  listTasks: async (): Promise<TaskVM[]> => operationRepository.listTasks(),

  listApprovalBlockers: async (): Promise<ApprovalVM[]> => {
    const decisions = await decisionsApi.list();
    return decisions.map(toApprovalVMFromDecision);
  },

  listActivity: async (): Promise<DepartmentActivityVM[]> => {
    const [departments, tasks, approvals, operations, routingInbox] = await Promise.all([
      departmentRepository.list(),
      departmentRepository.listTasks(),
      departmentRepository.listApprovalBlockers(),
      operationRepository.list(),
      routingApi.listInbox(),
    ]);

    return Promise.all(
      departments.map(async (department) => {
        const departmentTasks = tasks
          .filter((task) => task.agentId === department.id || task.departmentId === department.id)
          .sort((left, right) => getTaskFreshness(right).localeCompare(getTaskFreshness(left)));
        const departmentApprovals = approvals
          .filter((approval) => approval.agentId === department.id || approval.departmentId === department.id)
          .sort((left, right) => right.createdAt.localeCompare(left.createdAt));
        const departmentRoutingRecords = routingInbox.filter(
          (record) =>
            record.to_department_id === department.id ||
            (record.task_record_id ? departmentTasks.some((task) => task.id === record.task_record_id) : false),
        );
        const knowledge = await departmentRepository.listKnowledge(department.id, 3);
        const operationRefs = buildOperationRefs(
          department,
          departmentTasks,
          operations,
          departmentApprovals,
          departmentRoutingRecords,
        );
        const focus = buildFocus(department, departmentTasks, departmentApprovals, operationRefs, knowledge);
        const waitingCount =
          departmentApprovals.filter((approval) => approval.status === "pending").length +
          departmentRoutingRecords.filter((record) => record.status === "blocked").length;
        const activityStatus: DepartmentActivityStatusVM =
          waitingCount > 0
            ? "waiting"
            : departmentTasks.some((task) => task.status === "running" || task.status === "queued") ||
                departmentRoutingRecords.some((record) => ["queued", "claimed", "in_progress"].includes(record.status))
              ? "active"
              : (department.activityStatus ?? "idle");

        return {
          department: {
            ...department,
            activityStatus,
            currentFocus: focus.objective,
            activeTaskCount: departmentTasks.length + departmentRoutingRecords.length,
            pendingDecisionCount: waitingCount,
          },
          focus,
          proposals: buildProposals(departmentApprovals, operationRefs),
          tasks: departmentTasks,
          operations: operationRefs,
          blockers: buildBlockers(
            departmentApprovals,
            departmentTasks,
            operationRefs,
            departmentRoutingRecords,
          ),
          approvals: departmentApprovals,
        };
      }),
    );
  },

  listKnowledge: async (departmentId: string, limit = 3): Promise<DepartmentKnowledgeVM[]> => {
    const memory = await memoryApi.timeline({ agent_id: departmentId, limit });
    return memory.map(toKnowledgeVM);
  },
};

type DepartmentRepository = typeof departmentRepository;
