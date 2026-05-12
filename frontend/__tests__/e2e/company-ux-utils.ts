import { expect, type Page, type Route } from "@playwright/test";

import type { GraphJson, GraphVersion } from "../../lib/graph-types";

export type MockOperationStatus = "pending" | "running" | "succeeded" | "failed" | "paused";

export type MockCompanyRuntimeState = {
  companyId: string;
  companyName: string;
  latestVersion: GraphVersion;
  operations: Array<{
    id: string;
    status: MockOperationStatus;
    deliverable?: string | null;
    errorMessage?: string;
    promptMessage?: string;
    startedAt?: string;
  }>;
  pendingApprovals?: number;
};

function apiSuccess<T>(data: T) {
  return {
    data,
    meta: {
      requestId: "playwright-company-workspace",
      timestamp: "2026-04-26T12:00:00.000Z",
    },
  };
}

function normalizeOperationStatus(
  status: MockOperationStatus,
): "queued" | "running" | "completed" | "failed" | "paused" {
  if (status === "succeeded") {
    return "completed";
  }
  if (status === "failed") {
    return "failed";
  }
  if (status === "paused") {
    return "paused";
  }
  if (status === "pending") {
    return "queued";
  }
  return "running";
}

function buildOperationListItem(
  state: MockCompanyRuntimeState,
  operation: MockCompanyRuntimeState["operations"][number],
  index: number,
) {
  return {
    id: operation.id,
    graph_id: state.companyId,
    graph_name: state.companyName,
    graph_version_id: state.latestVersion.id,
    graph_version: state.latestVersion.version,
    status: operation.status,
    queue_status:
      operation.status === "pending"
        ? "queued"
        : operation.status === "paused"
          ? "paused"
          : operation.status === "failed"
            ? "failed"
            : operation.status === "succeeded"
              ? "completed"
              : "running",
    queue_attempts: operation.status === "failed" ? 2 : 1,
    queue_available_at: null,
    started_at: operation.startedAt ?? `2026-04-26T12:0${index}:00.000Z`,
    ended_at:
      operation.status === "succeeded" || operation.status === "failed" ? `2026-04-26T12:1${index}:00.000Z` : null,
    duration_ms: operation.status === "pending" ? null : 65_000 + index * 1000,
    llm_access: {
      llm_mode: "managed",
      provider: "openai",
      credential_id: null,
      api_key_present: false,
    },
    memory_activity: {
      has_activity: true,
      save_node_count: 0,
      saved_observation_count: 0,
      retrieval_node_count: 0,
      retrieved_observation_count: 0,
      influenced_node_count: 0,
      influenced_observation_count: 0,
      degraded: false,
      operations: [],
    },
  };
}

function buildNodeRuns(graphJson: GraphJson, operation: MockCompanyRuntimeState["operations"][number]) {
  const departmentNodes = graphJson.nodes.filter((node) => node.type !== "output");
  const primary = departmentNodes[0];
  const secondary = departmentNodes[1] ?? departmentNodes[0];

  const nodeRuns = [];

  if (primary) {
    nodeRuns.push({
      id: `${operation.id}-step-1`,
      node_id: primary.id,
      node_type: primary.type,
      status: "succeeded",
      attempt: 1,
      started_at: "2026-04-26T12:00:00.000Z",
      ended_at: "2026-04-26T12:00:30.000Z",
      duration_ms: 30_000,
      input_json: {
        request: "Prepare the first department handoff.",
      },
      output_json: {
        final_output: `${primary.name} prepared the initial work package.`,
      },
      error_json: null,
      agent_trace: {
        final_output: `${primary.name} prepared the initial work package.`,
        step_count: 1,
        tool_call_count: 0,
        steps: [
          {
            step_index: 1,
            action: "produce_work",
            final_answer: `${primary.name} prepared the initial work package.`,
            finish_reason: "completed",
          },
        ],
        usage: {
          total_tokens: 500,
        },
      },
      memory_activity: null,
    });
  }

  if (secondary && secondary.id !== primary?.id) {
    nodeRuns.push({
      id: `${operation.id}-step-2`,
      node_id: secondary.id,
      node_type: secondary.type,
      status:
        operation.status === "failed"
          ? "failed"
          : operation.status === "running"
            ? "running"
            : operation.status === "paused"
              ? "paused"
              : "succeeded",
      attempt: operation.status === "failed" ? 2 : 1,
      started_at: "2026-04-26T12:00:31.000Z",
      ended_at: operation.status === "running" || operation.status === "paused" ? null : "2026-04-26T12:01:20.000Z",
      duration_ms: operation.status === "running" || operation.status === "paused" ? null : 49_000,
      input_json: {
        request: "Advance the company operation.",
      },
      output_json:
        operation.status === "failed" || operation.status === "paused"
          ? null
          : {
              final_output: operation.deliverable ?? `${secondary.name} completed the operation handoff.`,
            },
      error_json:
        operation.status === "failed"
          ? {
              message: operation.errorMessage ?? "Escalation API rejected the payload.",
            }
          : null,
      agent_trace:
        secondary.type === "agent"
          ? {
              final_output: operation.deliverable ?? `${secondary.name} completed the operation handoff.`,
              step_count: 1,
              tool_call_count: 0,
              steps: [
                {
                  step_index: 1,
                  action: "produce_work",
                  final_answer: operation.deliverable ?? `${secondary.name} completed the operation handoff.`,
                  finish_reason: operation.status === "failed" ? "error" : "completed",
                },
              ],
              usage: {
                total_tokens: 800,
              },
            }
          : null,
      memory_activity: null,
    });
  }

  return nodeRuns;
}

function buildOperationDetail(
  state: MockCompanyRuntimeState,
  operation: MockCompanyRuntimeState["operations"][number],
) {
  const listItem = buildOperationListItem(state, operation, 0);
  const nodeRuns = buildNodeRuns(state.latestVersion.graph_json, operation);

  return {
    id: operation.id,
    owner_id: "playwright-owner",
    thread_id: null,
    graph_id: state.companyId,
    graph_name: state.companyName,
    graph_version_id: state.latestVersion.id,
    graph_version: state.latestVersion.version,
    status: operation.status,
    queue_status: listItem.queue_status,
    queue_attempts: listItem.queue_attempts,
    queue_available_at: null,
    started_at: listItem.started_at,
    ended_at: listItem.ended_at,
    input_json: {
      company_name: state.companyName,
      objective: state.latestVersion.graph_json.metadata?.description ?? "Operate the company.",
    },
    output_json:
      operation.status === "succeeded"
        ? {
            deliverable: operation.deliverable ?? "Final deliverable ready for review.",
          }
        : null,
    error_message:
      operation.status === "failed" ? (operation.errorMessage ?? "Escalation API rejected the payload.") : "",
    duration_ms: listItem.duration_ms,
    node_runs: nodeRuns,
    agent_events: [],
    memory_activity: {
      has_activity: false,
      save_node_count: 0,
      saved_observation_count: 0,
      retrieval_node_count: 0,
      retrieved_observation_count: 0,
      influenced_node_count: 0,
      influenced_observation_count: 0,
      degraded: false,
      operations: [],
    },
    llm_access: listItem.llm_access,
    paused_node_id: operation.status === "paused" ? (nodeRuns[nodeRuns.length - 1]?.node_id ?? null) : null,
    pause_payload:
      operation.status === "paused"
        ? {
            node_id: nodeRuns[nodeRuns.length - 1]?.node_id ?? null,
            node_name:
              state.latestVersion.graph_json.nodes.find((node) => node.id === nodeRuns[nodeRuns.length - 1]?.node_id)
                ?.name ?? "Approval Required",
            prompt_message: operation.promptMessage ?? "Approval required before the company can continue.",
            required_fields: ["feedback"],
          }
        : null,
  };
}

export async function mockCompanyRuntimeApis(
  page: Page,
  state: MockCompanyRuntimeState,
  hooks?: {
    onLaunchOperation?: () => void;
    onRetryFailedOperation?: () => void;
  },
): Promise<void> {
  const routePromises: Array<ReturnType<Page["route"]>> = [];
  const route = (...args: Parameters<Page["route"]>) => {
    routePromises.push(page.route(...args));
  };

  route(/\/api\/decisions\/count(?:\?.*)?$/, async (route: Route) => {
    await route.fulfill({
      status: 200,
      contentType: "application/json",
      body: JSON.stringify(apiSuccess({ count: state.pendingApprovals ?? 0 })),
    });
  });

  route(/\/api\/approvals\/?(?:\?.*)?$/, async (route: Route) => {
    const approvals = Array.from({ length: state.pendingApprovals ?? 0 }).map((_, index) => ({
      id: `approval-${index + 1}`,
      run_id:
        state.operations.find((operation) => operation.status === "paused")?.id ??
        state.operations[0]?.id ??
        "approval-run",
      run_name: `Operation ${index + 1}`,
      graph_name: state.companyName,
      node_id: "approval-required",
      node_name: "Approval Required",
      status: "pending",
      prompt_message: "A human approval is required before the company continues.",
      payload: {
        prompt_message: "A human approval is required before the company continues.",
        required_fields: ["feedback"],
      },
      result: null,
      created_at: "2026-04-26T12:00:00.000Z",
      resolved_at: null,
    }));

    await route.fulfill({
      status: 200,
      contentType: "application/json",
      body: JSON.stringify(apiSuccess(approvals)),
    });
  });

  route(/\/api\/runs\/start(?:\?.*)?$/, async (route: Route) => {
    hooks?.onLaunchOperation?.();
    const latestOperation = state.operations[0];
    await route.fulfill({
      status: 200,
      contentType: "application/json",
      body: JSON.stringify(apiSuccess(buildOperationDetail(state, latestOperation))),
    });
  });

  route(/\/api\/runs\/[^/]+\/replay(?:\?.*)?$/, async (route: Route) => {
    hooks?.onRetryFailedOperation?.();
    const retryTarget = state.operations.find((operation) => operation.status === "failed") ?? state.operations[0];
    await route.fulfill({
      status: 200,
      contentType: "application/json",
      body: JSON.stringify(apiSuccess(buildOperationDetail(state, retryTarget))),
    });
  });

  route(/\/api\/runs\/?(?:\?.*)?$/, async (route: Route) => {
    await route.fulfill({
      status: 200,
      contentType: "application/json",
      body: JSON.stringify(
        apiSuccess(state.operations.map((operation, index) => buildOperationListItem(state, operation, index))),
      ),
    });
  });

  route(/\/api\/runs\/[^/]+(?:\?.*)?$/, async (route: Route) => {
    const runId = route.request().url().split("/api/runs/")[1]?.split("?")[0] ?? "";
    const operation = state.operations.find((item) => item.id === runId);
    expect(operation).toBeTruthy();
    await route.fulfill({
      status: 200,
      contentType: "application/json",
      body: JSON.stringify(apiSuccess(buildOperationDetail(state, operation!))),
    });
  });
  await Promise.all(routePromises);
}

export function operationLabelsFromGraph(graphJson: GraphJson): string[] {
  return graphJson.nodes.flatMap((node) => (node.type !== "output" ? [node.name] : []));
}

export function userFacingStatusLabel(status: MockOperationStatus): string {
  return normalizeOperationStatus(status);
}
