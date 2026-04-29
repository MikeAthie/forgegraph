import type { NodeRunItem, RunDetail, RunListItem } from "@/lib/api";

export const operationId = "11111111-1111-1111-1111-111111111111";

export type OperationListFixtureInput = {
  id?: string;
  companyName?: string;
  setupVersion?: number;
  startedAt?: string;
  status?: RunListItem["status"];
  durationMs?: number | null;
};

export type DepartmentActivityFixtureInput = {
  id?: string;
  departmentId?: string;
  departmentType?: string;
  status?: NodeRunItem["status"];
  durationMs?: number | null;
  input?: Record<string, unknown>;
  deliverable?: Record<string, unknown> | null;
  issue?: Record<string, unknown> | null;
};

export type OperationDetailFixtureInput = {
  status?: RunDetail["status"];
  durationMs?: number | null;
  activities?: NodeRunItem[];
  pausedApproval?: {
    departmentId: string;
    departmentName: string;
    promptMessage: string;
  };
};

export const makeOperationListItem = (input: OperationListFixtureInput = {}): RunListItem => ({
  id: input.id ?? "operation-1",
  graph_id: "company-1",
  graph_name: input.companyName ?? "Revenue triage",
  graph_version_id: "setup-1",
  graph_version: input.setupVersion ?? 3,
  status: input.status ?? "running",
  queue_status: "processing",
  queue_attempts: 1,
  queue_available_at: null,
  started_at: input.startedAt ?? "2026-04-05T10:00:00Z",
  ended_at: null,
  duration_ms: input.durationMs ?? null,
  memory_activity: {
    has_activity: true,
    save_node_count: 1,
    saved_observation_count: 2,
    retrieval_node_count: 1,
    retrieved_observation_count: 4,
    influenced_node_count: 1,
    influenced_observation_count: 2,
    degraded: false,
    operations: [],
  },
});

export const makeDepartmentActivity = (input: DepartmentActivityFixtureInput = {}): NodeRunItem => ({
  id: input.id ?? "department-activity-1",
  node_id: input.departmentId ?? "fetch_customer",
  node_type: input.departmentType ?? "tool",
  status: input.status ?? "succeeded",
  attempt: 1,
  started_at: "2026-04-05T10:00:00Z",
  ended_at: "2026-04-05T10:00:01Z",
  duration_ms: input.durationMs ?? 1000,
  input_json: input.input ?? { customer_id: "cust_123" },
  output_json: input.deliverable ?? { customer_name: "Jackie" },
  error_json: input.issue ?? null,
  agent_trace: null,
  memory_activity: null,
});

export const makeOperationDetail = (input: OperationDetailFixtureInput = {}): RunDetail => {
  const pausedApproval = input.pausedApproval ?? null;

  return {
    id: operationId,
    owner_id: "owner-1",
    graph_id: "company-1",
    graph_name: "Revenue triage",
    graph_version_id: "setup-1",
    graph_version: 3,
    status: input.status ?? "running",
    queue_status: "processing",
    queue_attempts: 1,
    queue_available_at: null,
    started_at: "2026-04-05T10:00:00Z",
    ended_at: null,
    input_json: { operation_brief: "Review revenue risk" },
    output_json: null,
    error_message: "",
    duration_ms: input.durationMs ?? 1000,
    node_runs: input.activities ?? [makeDepartmentActivity()],
    agent_events: [],
    memory_activity: null,
    paused_node_id: pausedApproval?.departmentId ?? null,
    pause_payload: pausedApproval
      ? {
          node_id: pausedApproval.departmentId,
          node_name: pausedApproval.departmentName,
          prompt_message: pausedApproval.promptMessage,
        }
      : null,
  };
};
