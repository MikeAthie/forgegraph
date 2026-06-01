import type { Page, Route } from "@playwright/test";

function apiSuccess<T>(data: T) {
  return {
    data,
    meta: {
      requestId: "playwright-operations",
      timestamp: "2026-04-01T12:00:00.000Z",
    },
  };
}

export const succeededOperationId = "11111111-1111-1111-1111-111111111111";
export const failedOperationId = "22222222-2222-2222-2222-222222222222";
export const pausedOperationId = "33333333-3333-3333-3333-333333333333";

const listOperations = [
  {
    id: succeededOperationId,
    graph_id: "company-operation-001",
    graph_name: "Revenue Operating Pulse",
    graph_version_id: "company-operation-version-001",
    graph_version: 3,
    status: "succeeded",
    queue_status: "completed",
    queue_attempts: 1,
    queue_available_at: null,
    started_at: "2026-04-01T11:48:00.000Z",
    ended_at: "2026-04-01T11:49:05.000Z",
    duration_ms: 65000,
    memory_activity: {
      has_activity: true,
      retrieved_observation_count: 2,
      stored_observation_count: 1,
      degraded: false,
    },
  },
  {
    id: failedOperationId,
    graph_id: "company-operation-002",
    graph_name: "Creative Recovery Drill",
    graph_version_id: "company-operation-version-002",
    graph_version: 4,
    status: "failed",
    queue_status: "failed",
    queue_attempts: 3,
    queue_available_at: null,
    started_at: "2026-04-01T11:45:00.000Z",
    ended_at: "2026-04-01T11:47:10.000Z",
    duration_ms: 130000,
    memory_activity: {
      has_activity: false,
      retrieved_observation_count: 0,
      stored_observation_count: 0,
      degraded: false,
    },
  },
];

const succeededDetail = {
  id: succeededOperationId,
  owner_id: "owner-operation-001",
  thread_id: null,
  graph_id: "company-operation-001",
  graph_name: "Revenue Operating Pulse",
  graph_version_id: "company-operation-version-001",
  graph_version: 3,
  status: "succeeded",
  queue_status: "completed",
  queue_attempts: 1,
  queue_available_at: null,
  started_at: "2026-04-01T11:48:00.000Z",
  ended_at: "2026-04-01T11:49:05.000Z",
  input_json: {
    operation_brief: "Start the company operation and summarize the result.",
  },
  output_json: {
    deliverable: "Revenue pulse is ready for review.",
  },
  error_message: "",
  duration_ms: 65000,
  node_runs: [
    {
      id: "department-activity-001",
      node_id: "summarize",
      node_type: "agent",
      status: "succeeded",
      attempt: 1,
      started_at: "2026-04-01T11:40:00.000Z",
      ended_at: "2026-04-01T11:41:05.000Z",
      duration_ms: 65000,
      input_json: {
        prompt: "Summarize the current operation.",
      },
      output_json: {
        deliverable: "Revenue pulse is ready for review.",
      },
      error_json: null,
      agent_trace: {
        final_output: "Revenue pulse is ready for review.",
        step_count: 1,
        tool_call_count: 0,
        steps: [
          {
            step_index: 1,
            action: "summarize",
            final_answer: "Revenue pulse is ready for review.",
            finish_reason: "completed",
          },
        ],
        usage: {
          total_tokens: 1200,
        },
      },
      memory_activity: null,
    },
  ],
  agent_events: [],
  memory_activity: {
    has_activity: true,
    retrieved_observation_count: 2,
    stored_observation_count: 1,
    degraded: false,
  },
  paused_node_id: null,
  pause_payload: null,
};

const pausedDetail = {
  ...succeededDetail,
  id: pausedOperationId,
  graph_id: "company-operation-003",
  graph_name: "Finance Approval Gate",
  graph_version_id: "company-operation-version-003",
  graph_version: 2,
  status: "paused",
  queue_status: "paused",
  queue_attempts: 1,
  started_at: "2026-04-01T11:50:00.000Z",
  ended_at: null,
  duration_ms: 32000,
  output_json: null,
  node_runs: [
    {
      ...succeededDetail.node_runs[0],
      id: "department-activity-002",
      node_id: "human_gate",
      status: "paused",
      output_json: null,
      agent_trace: null,
    },
  ],
  paused_node_id: "human_gate",
  pause_payload: {
    node_id: "human_gate",
    node_name: "Human Gate",
    prompt_message: "Please review this operation.",
    required_fields: ["ticket"],
  },
};

export async function mockOperationApis(
  page: Page,
  options?: {
    operations?: typeof listOperations;
    missingOperationId?: string;
  },
): Promise<void> {
  const operations = options?.operations ?? listOperations;
  const details: Record<string, Record<string, unknown>> = {
    [succeededOperationId]: succeededDetail,
    [pausedOperationId]: pausedDetail,
  };

  await Promise.all([
    page.route(/\/api\/decisions\/count(?:\?.*)?$/, async (route: Route) => {
      await route.fulfill({
        status: 200,
        contentType: "application/json",
        body: JSON.stringify(apiSuccess({ count: 0 })),
      });
    }),

    page.route(/\/api\/runs\/?(?:\?.*)?$/, async (route: Route) => {
      await route.fulfill({
        status: 200,
        contentType: "application/json",
        body: JSON.stringify(apiSuccess(operations)),
      });
    }),

    page.route(/\/api\/runs\/[^/]+(?:\?.*)?$/, async (route: Route) => {
      const operationId = route.request().url().split("/api/runs/")[1]?.split("?")[0] ?? "";
      if (options?.missingOperationId && operationId === options.missingOperationId) {
        await route.fulfill({
          status: 404,
          contentType: "application/json",
          body: JSON.stringify({
            error: {
              code: "NOT_FOUND",
              message: "Operation not found.",
            },
            meta: {
              requestId: "playwright-operation-missing",
              timestamp: "2026-04-01T12:00:00.000Z",
            },
          }),
        });
        return;
      }

      const detail = details[operationId];
      await route.fulfill({
        status: detail ? 200 : 404,
        contentType: "application/json",
        body: JSON.stringify(
          detail
            ? apiSuccess(detail)
            : {
                error: {
                  code: "NOT_FOUND",
                  message: "Operation not found.",
                },
              },
        ),
      });
    }),
  ]);
}
