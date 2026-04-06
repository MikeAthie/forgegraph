import { expect, test, type Page, type Route } from "@playwright/test";

import { createTestUser, ensureUserRegistered, openAuthenticatedPage } from "./helpers";

function apiSuccess<T>(data: T) {
  return {
    data,
    meta: {
      requestId: "playwright-executions",
      timestamp: "2026-04-01T12:00:00.000Z",
    },
  };
}

const succeededRunId = "11111111-1111-1111-1111-111111111111";
const failedRunId = "22222222-2222-2222-2222-222222222222";
const pausedRunId = "33333333-3333-3333-3333-333333333333";

const listRuns = [
  {
    id: succeededRunId,
    graph_id: "workflow-execution-001",
    graph_name: "E2E Execution Visibility",
    graph_version_id: "workflow-execution-version-001",
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
    id: failedRunId,
    graph_id: "workflow-execution-002",
    graph_name: "Failure escalation",
    graph_version_id: "workflow-execution-version-002",
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
  id: succeededRunId,
  owner_id: "owner-execution-001",
  thread_id: null,
  graph_id: "workflow-execution-001",
  graph_name: "E2E Execution Visibility",
  graph_version_id: "workflow-execution-version-001",
  graph_version: 3,
  status: "succeeded",
  queue_status: "completed",
  queue_attempts: 1,
  queue_available_at: null,
  started_at: "2026-04-01T11:48:00.000Z",
  ended_at: "2026-04-01T11:49:05.000Z",
  input_json: {
    request: "Run the workflow and summarize the result.",
  },
  output_json: {
    ok: true,
  },
  error_message: "",
  duration_ms: 65000,
  node_runs: [
    {
      id: "step-execution-001",
      node_id: "summarize",
      node_type: "agent",
      status: "succeeded",
      attempt: 1,
      started_at: "2026-04-01T11:40:00.000Z",
      ended_at: "2026-04-01T11:41:05.000Z",
      duration_ms: 65000,
      input_json: {
        prompt: "Summarize the current execution.",
      },
      output_json: {
        ok: true,
      },
      error_json: null,
      agent_trace: {
        final_output: '{"ok": true}',
        step_count: 1,
        tool_call_count: 0,
        steps: [
          {
            step_index: 1,
            action: "summarize",
            final_answer: '{"ok": true}',
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
  id: pausedRunId,
  graph_id: "workflow-execution-003",
  graph_name: "E2E Human Gate",
  graph_version_id: "workflow-execution-version-003",
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
      id: "step-execution-002",
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
    prompt_message: "Please review this run.",
    required_fields: ["ticket"],
  },
};

async function mockExecutionApis(
  page: Page,
  options?: {
    runs?: typeof listRuns;
    executionDetails?: Record<string, Record<string, unknown>>;
    missingExecutionId?: string;
  },
): Promise<void> {
  const runs = options?.runs ?? listRuns;
  const details: Record<string, Record<string, unknown>> = {
    [succeededRunId]: succeededDetail,
    [pausedRunId]: pausedDetail,
    ...(options?.executionDetails ?? {}),
  };

  await page.route(/\/api\/decisions\/count(?:\?.*)?$/, async (route: Route) => {
    await route.fulfill({
      status: 200,
      contentType: "application/json",
      body: JSON.stringify(apiSuccess({ count: 0 })),
    });
  });

  await page.route(/\/api\/runs\/?(?:\?.*)?$/, async (route: Route) => {
    await route.fulfill({
      status: 200,
      contentType: "application/json",
      body: JSON.stringify(apiSuccess(runs)),
    });
  });

  await page.route(/\/api\/executions\/[^/]+(?:\?.*)?$/, async (route: Route) => {
    const executionId = route.request().url().split("/api/executions/")[1]?.split("?")[0] ?? "";
    if (options?.missingExecutionId && executionId === options.missingExecutionId) {
      await route.fulfill({
        status: 404,
        contentType: "application/json",
        body: JSON.stringify({
          error: {
            code: "NOT_FOUND",
            message: "Execution not found.",
          },
          meta: {
            requestId: "playwright-execution-missing",
            timestamp: "2026-04-01T12:00:00.000Z",
          },
        }),
      });
      return;
    }

    const detail = details[executionId];
    if (!detail) {
      await route.fulfill({
        status: 404,
        contentType: "application/json",
        body: JSON.stringify({
          error: {
            code: "NOT_FOUND",
            message: "Execution not found.",
          },
          meta: {
            requestId: "playwright-execution-missing",
            timestamp: "2026-04-01T12:00:00.000Z",
          },
        }),
      });
      return;
    }

    await route.fulfill({
      status: 200,
      contentType: "application/json",
      body: JSON.stringify(apiSuccess(detail)),
    });
  });
}

test.describe("Execution Visibility", () => {
  test("shows a seeded execution in the visibility screen and opens detail", async ({ page, request }, testInfo) => {
    const user = createTestUser(testInfo, "executions");
    await ensureUserRegistered(request, user);
    await mockExecutionApis(page);

    await openAuthenticatedPage(page, user, "/runs");

    await expect(page.getByRole("heading", { name: /distributed trace for humans/i })).toBeVisible();
    await expect(page.getByRole("button", { name: /e2e execution visibility/i })).toBeVisible();

    const executionDetailHref = await page.getByRole("link", { name: /open execution detail/i }).getAttribute("href");
    expect(executionDetailHref).toBe(`/executions/${succeededRunId}`);
    await page.goto(executionDetailHref!);

    await expect(page).toHaveURL(new RegExp(`/executions/${succeededRunId}$`));
    await expect(page.getByRole("heading", { name: /structured execution trace/i })).toBeVisible();
    await expect(page.getByText(/execution flow/i)).toBeVisible();
    await expect(page.getByText(/execution state/i)).toBeVisible();
    await expect(page.getByText(/"ok": true/i).first()).toBeVisible();
  });

  test("shows paused executions with human gate context", async ({ page, request }, testInfo) => {
    const user = createTestUser(testInfo, "executions-paused");
    await ensureUserRegistered(request, user);
    await mockExecutionApis(page);

    await openAuthenticatedPage(page, user, `/executions/${pausedRunId}`);

    await expect(page.getByRole("heading", { name: /structured execution trace/i })).toBeVisible();
    await expect(page.getByRole("heading", { name: /^human gate$/i })).toBeVisible();
    await expect(page.getByText("Please review this run.", { exact: true })).toBeVisible();
  });

  test("surfaces status badges across executions", async ({ page, request }, testInfo) => {
    const user = createTestUser(testInfo, "executions-status");
    await ensureUserRegistered(request, user);
    await mockExecutionApis(page);

    await openAuthenticatedPage(page, user, "/executions");

    await expect(page.getByRole("heading", { name: /distributed trace for humans/i })).toBeVisible();
    await expect(page.getByText(/^succeeded$/i).first()).toBeVisible();
    await expect(page.getByText(/^failed$/i).first()).toBeVisible();
  });

  test("shows an empty state when no executions exist", async ({ page, request }, testInfo) => {
    const user = createTestUser(testInfo, "executions-empty");
    await ensureUserRegistered(request, user);
    await mockExecutionApis(page, { runs: [] });

    await openAuthenticatedPage(page, user, "/executions");

    await expect(page.getByText(/no executions available/i)).toBeVisible();
  });

  test("shows an error for a non-existent execution", async ({ page, request }, testInfo) => {
    const user = createTestUser(testInfo, "executions-missing");
    await ensureUserRegistered(request, user);
    const missingRunId = "00000000-0000-0000-0000-000000000000";
    await mockExecutionApis(page, { missingExecutionId: missingRunId });

    await openAuthenticatedPage(page, user, `/executions/${missingRunId}`);

    await expect(page.getByText(/the requested resource was not found/i)).toBeVisible();
  });
});
