import type {
  ApprovalTask,
  DecisionRecord,
  GraphDetail,
  GraphListItem,
  NodeRunItem,
  RunDetail,
  RunListItem,
  TaskRecord,
} from "@/lib/api";
import type { GraphJson, GraphVersion } from "@/lib/graph-types";
import {
  getCompanyProfileFromGraph,
  getDepartmentExplanation,
  getDepartmentTaskLabel,
  getCurrentDepartmentLabel,
  summarizeDeliverable,
  translateFailure,
  translateRunStatus,
} from "@/lib/company-workspace";
import { translateFailureDetails } from "@/domain/errors";
import type {
  ApprovalRiskVM,
  ApprovalVM,
  CompanyVM,
  DeliverableVM,
  DepartmentVM,
  OperationFailureVM,
  OperationStatusVM,
  OperationVM,
  TaskStatusVM,
  TaskVM,
} from "./viewModels";

export type * from "./viewModels";

function truncate(value: string, length = 220): string {
  return value.length <= length ? value : `${value.slice(0, length - 1)}…`;
}

function stringifyPreview(value: unknown): string | null {
  if (value === null || value === undefined) {
    return null;
  }
  if (typeof value === "string") {
    return value;
  }
  try {
    return JSON.stringify(value);
  } catch {
    return String(value);
  }
}

export function toOperationStatusVM(status: string): OperationStatusVM {
  return translateRunStatus(status);
}

function toTaskStatusVM(status: string): TaskStatusVM {
  const normalized = status.toLowerCase();
  if (normalized === "succeeded" || normalized === "success" || normalized === "completed") {
    return "completed";
  }
  if (normalized === "dead_lettered") {
    return "dead_lettered";
  }
  if (normalized === "retry_scheduled") {
    return "retry_scheduled";
  }
  if (normalized === "waiting_for_decision") {
    return "waiting_for_decision";
  }
  if (normalized === "cancelled" || normalized === "canceled") {
    return "cancelled";
  }
  if (normalized === "failed" || normalized === "error") {
    return "failed";
  }
  if (normalized === "paused" || normalized === "waiting") {
    return "paused";
  }
  if (normalized === "claimed") {
    return "claimed";
  }
  if (normalized === "created") {
    return "created";
  }
  if (normalized === "running") {
    return "running";
  }
  if (normalized === "skipped") {
    return "skipped";
  }
  return "queued";
}

function getDepartmentNodes(setupJson: GraphJson | null | undefined) {
  return setupJson?.nodes.filter((item) => item.type !== "output") ?? [];
}

function getDepartmentName(departmentId: string | null | undefined, setupJson: GraphJson | null | undefined): string {
  const department = setupJson?.nodes.find((item) => item.id === departmentId);
  return department?.name || "Department";
}

function toDepartmentVMs(setupJson: GraphJson | null | undefined): DepartmentVM[] {
  return getDepartmentNodes(setupJson).map((department, index) => ({
    id: department.id || `department-${index + 1}`,
    label: department.name || "Department",
    responsibility: getDepartmentExplanation(department.name || "Department", setupJson ?? null),
    tools: Array.isArray(department.config?.tools) ? department.config.tools.map(String) : [],
    category: department.type === "agent" ? "department" : "skill",
  }));
}

function toTaskVMFromDepartmentActivity(activity: NodeRunItem, setupJson: GraphJson | null | undefined): TaskVM {
  const departmentName = getDepartmentTaskLabel(activity, setupJson ?? null);
  const resultPreview = stringifyPreview(activity.output_json);
  const issuePreview = stringifyPreview(activity.error_json);
  const latestTrace = activity.agent_trace?.steps?.[activity.agent_trace.steps.length - 1];
  const summary =
    activity.agent_trace?.final_output ||
    latestTrace?.final_answer ||
    latestTrace?.tool_output ||
    resultPreview ||
    issuePreview ||
    "No readable activity summary is available yet.";

  return {
    id: activity.id,
    departmentId: activity.node_id,
    departmentName,
    title: departmentName,
    status: toTaskStatusVM(String(activity.status)),
    summary: truncate(String(summary)),
    startedAt: activity.started_at,
    endedAt: activity.ended_at,
    durationMs: activity.duration_ms,
    attempt: activity.attempt,
    attemptCount: activity.attempt,
    requiresApproval: activity.status === "waiting" || activity.node_type === "human_gate",
    toolName: latestTrace?.tool ? String(latestTrace.tool) : null,
    resultPreview: resultPreview ? truncate(resultPreview) : null,
    issuePreview: issuePreview ? translateFailureDetails(issuePreview, "department") : null,
  };
}

export function toTaskVMFromRecord(record: TaskRecord): TaskVM {
  return {
    id: record.id,
    operationId: record.execution_id,
    agentId: record.agent_id,
    departmentId: record.department_id ?? record.agent_id,
    departmentName: record.department_name ?? record.title,
    title: record.title,
    status: toTaskStatusVM(String(record.status)),
    priority: record.priority,
    summary: record.summary || "No activity summary is available yet.",
    startedAt: record.started_at,
    endedAt: record.ended_at,
    createdAt: record.created_at,
    updatedAt: record.updated_at,
    durationMs: null,
    attemptCount: record.attempt_count ?? null,
    currentStepId: record.current_step_id,
    currentDecisionId: record.current_decision_id,
    lifecycleTaskId: record.lifecycle_task_id ?? null,
    requiresApproval:
      Boolean(record.current_decision_id) || record.status === "waiting_for_decision" || record.status === "paused",
    retryMetadata: record.retry_metadata ?? null,
    latestRetry: record.latest_retry ?? null,
    deadLetter: record.dead_letter ?? null,
    staleEventCount: record.stale_event_count ?? 0,
    lateEventCount: record.late_event_count ?? 0,
    recoveryOptions: record.recovery_options ?? [],
    judge: record.judge
      ? {
          id: record.judge.id,
          title: record.judge.title,
          criteriaCount: record.judge.criteria_count,
          passThreshold: record.judge.pass_threshold,
          status: record.judge.status,
          score: record.judge.score,
          evaluatedAt: record.judge.evaluated_at,
        }
      : null,
  };
}

function toDeliverableVM(
  operation: Pick<RunDetail, "id" | "status" | "ended_at" | "input_json" | "output_json" | "node_runs">,
): DeliverableVM {
  const ready = toOperationStatusVM(String(operation.status)) === "completed";
  const preview = summarizeDeliverable(operation);
  const lastCompletedTask = [...operation.node_runs].reverse().find((item) => item.output_json);
  const outputTitle =
    operation.output_json && typeof operation.output_json.title === "string" ? operation.output_json.title.trim() : "";
  const briefTitle =
    typeof operation.input_json?.operation_brief === "string"
      ? operation.input_json.operation_brief.trim()
      : typeof operation.input_json?.objective === "string"
        ? operation.input_json.objective.trim()
        : "";
  const readyTitle = outputTitle || (briefTitle ? `Deliverable: ${truncate(briefTitle, 72)}` : "Operation deliverable");

  return {
    id: `${operation.id}:deliverable`,
    operationId: operation.id,
    title: ready ? readyTitle : "Deliverable pending",
    preview,
    content: ready ? preview : null,
    ready,
    createdAt: operation.ended_at,
    sourceDepartmentName: lastCompletedTask ? getDepartmentTaskLabel(lastCompletedTask, null) : null,
  };
}

function toOperationFailureVM(
  operation: Pick<RunDetail, "error_message" | "node_runs" | "status">,
  setupJson: GraphJson | null | undefined,
): OperationFailureVM | null {
  const failure = translateFailure(operation, setupJson ?? null);
  if (!failure) {
    return null;
  }

  return {
    title: failure.title,
    summary: translateFailureDetails(failure.technicalDetails ?? failure.summary, "operation"),
    nextSteps: failure.nextSteps,
    actionHint: failure.actionHint,
    detailsForSupport: failure.technicalDetails ?? null,
  };
}

export function toOperationVM(operation: RunDetail, setupJson?: GraphJson | null): OperationVM {
  const tasks = operation.node_runs.map((activity) => ({
    ...toTaskVMFromDepartmentActivity(activity, setupJson ?? null),
    operationId: operation.id,
  }));

  return {
    id: operation.id,
    companyId: operation.graph_id,
    companyName: operation.graph_name,
    setupVersionId: operation.graph_version_id,
    setupVersion: operation.graph_version,
    status: toOperationStatusVM(String(operation.status)),
    queueStatus: operation.queue_status ?? null,
    attempts: operation.queue_attempts ?? 0,
    startedAt: operation.started_at,
    endedAt: operation.ended_at,
    durationMs: operation.duration_ms,
    brief: String(operation.input_json?.operation_brief ?? operation.input_json?.objective ?? "Company operation"),
    currentDepartmentName: getCurrentDepartmentLabel(operation, setupJson ?? null),
    tasks,
    deliverable: toDeliverableVM(operation),
    failure: toOperationFailureVM(operation, setupJson ?? null),
    memoryActivity: operation.memory_activity,
    aiAccess: operation.llm_access,
  };
}

export function toOperationListVM(operation: RunListItem): OperationVM {
  return {
    id: operation.id,
    companyId: operation.graph_id,
    companyName: operation.graph_name,
    setupVersionId: operation.graph_version_id,
    setupVersion: operation.graph_version,
    status: toOperationStatusVM(String(operation.status)),
    queueStatus: operation.queue_status ?? null,
    attempts: operation.queue_attempts ?? 0,
    startedAt: operation.started_at,
    endedAt: operation.ended_at,
    durationMs: operation.duration_ms,
    brief: "Company operation",
    currentDepartmentName: "Department",
    tasks: [],
    deliverable: {
      id: `${operation.id}:deliverable`,
      operationId: operation.id,
      title: "Deliverable pending",
      preview: "Open the operation to review the deliverable.",
      content: null,
      ready: false,
      createdAt: operation.ended_at,
    },
    failure: null,
    memoryActivity: operation.memory_activity,
    aiAccess: operation.llm_access,
  };
}

export function toCompanyVM(
  company: GraphListItem | GraphDetail,
  setupVersion: GraphVersion | null,
  operations: OperationVM[],
  pendingApprovalCount: number,
): CompanyVM {
  const profile = getCompanyProfileFromGraph(company, setupVersion?.graph_json ?? null);
  const latestOperation = operations[0] ?? null;
  const companyStatus =
    pendingApprovalCount > 0
      ? "Awaiting approval"
      : operations.some((operation) => operation.status === "failed")
        ? "Needs attention"
        : operations.some((operation) => operation.status === "running")
          ? "Operating"
          : operations.some((operation) => operation.status === "completed")
            ? "Stable"
            : "Ready to launch";

  return {
    id: company.id,
    name: profile.companyName,
    description: profile.objective,
    createdAt: company.created_at,
    updatedAt: company.updated_at,
    setupVersionId: setupVersion?.id ?? null,
    setupVersion: setupVersion?.version ?? ("latest_version" in company ? company.latest_version : null),
    setupVersionCount: "version_count" in company ? company.version_count : company.versions.length,
    profile,
    departments: toDepartmentVMs(setupVersion?.graph_json ?? null),
    status: companyStatus,
    pendingApprovalCount,
    operationCount: operations.length,
    latestOperation,
  };
}

function estimateApprovalRisk(promptMessage: string, requiredFields: string[]): ApprovalRiskVM {
  if (promptMessage.length > 240 || requiredFields.length > 2) {
    return "high";
  }
  if (promptMessage.length > 120 || requiredFields.length > 0) {
    return "medium";
  }
  return "low";
}

export function toApprovalVM(approval: ApprovalTask): ApprovalVM {
  const requiredFields = approval.payload?.required_fields ?? [];
  const risk = estimateApprovalRisk(approval.prompt_message ?? "", requiredFields);
  const estimatedCost =
    Math.round((0.18 + (approval.prompt_message?.length ?? 0) * 0.00045 + requiredFields.length * 0.06) * 100) / 100;

  return {
    id: approval.id,
    operationId: approval.run_id,
    operationName: approval.run_name,
    companyName: approval.graph_name,
    agentId: null,
    departmentId: approval.node_id,
    departmentName: approval.node_name,
    status: approval.status,
    promptMessage: approval.prompt_message,
    requiredFields,
    result: approval.result ?? null,
    createdAt: approval.created_at,
    resolvedAt: approval.resolved_at ?? null,
    estimatedCost,
    risk,
    consequence:
      risk === "high"
        ? "This decision can materially change customer-facing or financial behavior."
        : risk === "medium"
          ? "This decision affects a meaningful operating path and should include operator guidance."
          : "This is a contained decision with limited downstream impact.",
    blastRadius:
      requiredFields.length > 0
        ? `${requiredFields.length} required field${requiredFields.length === 1 ? "" : "s"} will be carried into the resumed operation.`
        : "The operation will resume immediately after the decision is recorded.",
  };
}

export function toApprovalVMFromDecision(decision: DecisionRecord): ApprovalVM {
  const promptMessage = String(
    decision.context_json?.summary ??
      decision.context_json?.prompt_message ??
      "Operator approval is required before this operation can continue.",
  );
  const risk = estimateApprovalRisk(promptMessage, []);
  const status =
    decision.status === "approved" || decision.status === "rejected"
      ? decision.status
      : decision.status === "resolved"
        ? "approved"
        : "pending";

  return {
    id: decision.id,
    operationId: decision.execution_id ?? "",
    operationName: "Operation approval",
    companyName: "Company",
    agentId: decision.agent_id,
    departmentId: decision.agent_id ?? "",
    departmentName: "Department",
    status,
    promptMessage,
    requiredFields: [],
    result: decision.resolution_json ?? null,
    createdAt: decision.requested_at ?? decision.created_at,
    resolvedAt: decision.resolved_at,
    estimatedCost: Math.round((0.12 + promptMessage.length * 0.00035) * 100) / 100,
    risk,
    consequence:
      risk === "high"
        ? "This approval can materially change customer-facing or financial behavior."
        : risk === "medium"
          ? "This approval affects a meaningful operating path and should include operator guidance."
          : "This is a contained approval with limited downstream impact.",
    blastRadius: "The operation will resume after the approval is recorded.",
  };
}

function getDepartmentProgressVM(
  operation: OperationVM,
  setupJson: GraphJson | null | undefined,
): DepartmentVM[] {
  const tasksByDepartmentId = new Map(operation.tasks.map((task) => [task.departmentId, task]));
  return getDepartmentNodes(setupJson).map((department, index) => {
    const task = tasksByDepartmentId.get(department.id);
    return {
      id: department.id || `department-${index + 1}`,
      label: department.name || getDepartmentName(department.id, setupJson),
      responsibility: getDepartmentExplanation(department.name || "Department", setupJson ?? null),
      tools: Array.isArray(department.config?.tools) ? department.config.tools.map(String) : [],
      category: department.type === "agent" ? "department" : "skill",
      status: task?.status ?? "queued",
    };
  });
}
