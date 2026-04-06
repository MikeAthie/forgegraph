import { expect, test, type Page, type Route } from "@playwright/test";

import {
  createTestUser,
  ensureUserRegistered,
  openAuthenticatedPage,
  seedFrontendControlPlaneFixture,
  type FrontendControlPlaneFixture,
} from "./helpers";

type ResolutionStatus = "approved" | "rejected";

function apiSuccess<T>(data: T) {
  return {
    data,
    meta: {
      requestId: "playwright-control-surface",
      timestamp: "2026-04-01T12:00:00.000Z",
    },
  };
}

function buildControlPlaneState(fixture: FrontendControlPlaneFixture) {
  const organization = {
    id: fixture.organizationId,
    name: "Playwright Control Plane",
  };

  const activeAgents = [
    {
      id: fixture.agentIds.ops,
      organization_id: fixture.organizationId,
      slug: "ops-conductor",
      display_name: "Ops Conductor",
      status: "attention",
      source_workflow_id: "11111111-1111-1111-1111-111111111111",
      source_workflow_revision_id: "11111111-1111-1111-1111-111111111112",
      source_node_id: fixture.approval.nodeId,
      default_model: "gpt-5.4",
      last_execution_id: fixture.runIds.paused,
      last_seen_at: "2026-04-01T11:58:00.000Z",
      policy_snapshot_json: {
        approvals: "required_for_vendor_payments",
        budget_mode: "guarded",
      },
      capabilities_json: {
        approvals: true,
        routing: true,
      },
      task_count: 1,
      pending_decisions: 1,
      total_cost_usd: 42.35,
      created_at: "2026-04-01T08:00:00.000Z",
      updated_at: "2026-04-01T11:58:00.000Z",
    },
    {
      id: fixture.agentIds.finance,
      organization_id: fixture.organizationId,
      slug: "billing-sentinel",
      display_name: "Billing Sentinel",
      status: "active",
      source_workflow_id: "22222222-2222-2222-2222-222222222221",
      source_workflow_revision_id: "22222222-2222-2222-2222-222222222222",
      source_node_id: "watch_budget",
      default_model: "gpt-5.4-mini",
      last_execution_id: fixture.runIds.running,
      last_seen_at: "2026-04-01T11:59:00.000Z",
      policy_snapshot_json: {
        alerts: "budget_and_usage",
      },
      capabilities_json: {
        monitoring: true,
        cost_controls: true,
      },
      task_count: 1,
      pending_decisions: 0,
      total_cost_usd: 19.8,
      created_at: "2026-04-01T08:05:00.000Z",
      updated_at: "2026-04-01T11:59:00.000Z",
    },
  ];

  const activeTasks = [
    {
      id: "33333333-3333-3333-3333-333333333331",
      organization_id: fixture.organizationId,
      execution_id: fixture.runIds.paused,
      agent_id: fixture.agentIds.ops,
      title: "Vendor payment review",
      status: "waiting",
      priority: "high",
      summary: "Ops Conductor is waiting for a decision in Vendor payment review.",
      source_node_id: fixture.approval.nodeId,
      current_step_id: "44444444-4444-4444-4444-444444444441",
      current_decision_id: "55555555-5555-5555-5555-555555555551",
      started_at: "2026-04-01T11:55:00.000Z",
      ended_at: null,
      created_at: "2026-04-01T11:55:00.000Z",
      updated_at: "2026-04-01T11:58:00.000Z",
    },
    {
      id: "33333333-3333-3333-3333-333333333332",
      organization_id: fixture.organizationId,
      execution_id: fixture.runIds.running,
      agent_id: fixture.agentIds.finance,
      title: "Budget watch",
      status: "running",
      priority: "normal",
      summary: "Billing Sentinel is aggregating spend against the configured guardrails.",
      source_node_id: "watch_budget",
      current_step_id: "44444444-4444-4444-4444-444444444442",
      current_decision_id: null,
      started_at: "2026-04-01T11:57:00.000Z",
      ended_at: null,
      created_at: "2026-04-01T11:57:00.000Z",
      updated_at: "2026-04-01T11:59:00.000Z",
    },
  ];

  const pendingDecision = {
    id: "55555555-5555-5555-5555-555555555551",
    organization_id: fixture.organizationId,
    execution_id: fixture.runIds.paused,
    task_id: activeTasks[0].id,
    agent_id: fixture.agentIds.ops,
    decision_type: "human_approval",
    status: "pending",
    source_approval_task_id: fixture.approval.id,
    context_json: {
      input: "Vendor payment over the safety threshold requires operator confirmation.",
      summary: "Vendor payment over the safety threshold requires operator confirmation.",
      reasoning_summary:
        "The payment exceeds the configured vendor threshold and would transfer funds without an explicit operator sign-off.",
    },
    resolution_json: {},
    requested_at: fixture.approval.createdAt,
    resolved_at: null,
    created_at: fixture.approval.createdAt,
    updated_at: fixture.approval.createdAt,
  };

  const approval = {
    id: fixture.approval.id,
    run_id: fixture.approval.runId,
    run_name: `Run ${fixture.approval.runId.slice(0, 8)}`,
    graph_name: fixture.approval.graphName,
    node_id: fixture.approval.nodeId,
    node_name: fixture.approval.nodeName,
    status: "pending",
    prompt_message: fixture.approval.promptMessage,
    payload: {
      prompt_message:
        "Vendor payment over the safety threshold requires operator confirmation before funds are released.",
      required_fields: ["feedback"],
    },
    result: null,
    created_at: fixture.approval.createdAt,
    resolved_at: null,
  };

  const memoryTimeline = [
    {
      id: "66666666-6666-6666-6666-666666666661",
      tenant_id: fixture.organizationId,
      graph_id: null,
      run_id: fixture.runIds.paused,
      session_id: null,
      agent_id: fixture.agentIds.ops,
      memory_chunk_id: null,
      type: "operator_guidance",
      title: "Payment escalation guidance",
      content: "Large vendor disbursements require explicit approval plus a short justification note.",
      scope: "run",
      topic_key: "payment-escalation-guidance",
      tool_name: "memory_write",
      revision_count: 1,
      duplicate_count: 0,
      last_seen_at: "2026-04-01T11:58:00.000Z",
      created_at: "2026-04-01T11:58:00.000Z",
      updated_at: "2026-04-01T11:58:00.000Z",
      deleted_at: null,
      is_deleted: false,
    },
  ];

  const failedExecution = {
    id: fixture.runIds.failed,
    owner_id: "77777777-7777-7777-7777-777777777771",
    thread_id: null,
    graph_id: "77777777-7777-7777-7777-777777777772",
    graph_name: "Failure escalation",
    graph_version_id: "77777777-7777-7777-7777-777777777773",
    graph_version: 4,
    status: "failed",
    queue_status: "failed",
    queue_attempts: 3,
    queue_available_at: null,
    started_at: "2026-04-01T11:40:00.000Z",
    ended_at: "2026-04-01T11:42:15.000Z",
    input_json: {
      incident_id: "INC-2049",
      severity: "high",
    },
    output_json: null,
    error_message: "Escalation API rejected the payload.",
    duration_ms: 135000,
    node_runs: [
      {
        id: "88888888-8888-8888-8888-888888888881",
        node_id: "collect_context",
        node_type: "agent",
        status: "succeeded",
        attempt: 1,
        started_at: "2026-04-01T11:40:00.000Z",
        ended_at: "2026-04-01T11:40:45.000Z",
        duration_ms: 45000,
        input_json: {
          incident_id: "INC-2049",
        },
        output_json: {
          summary: "Context package assembled for escalation.",
        },
        error_json: null,
        agent_trace: {
          final_output: "Prepared escalation package for delivery.",
          step_count: 1,
          tool_call_count: 0,
          steps: [
            {
              step_index: 1,
              action: "summarize",
              final_answer: "Prepared escalation package for delivery.",
              finish_reason: "completed",
            },
          ],
          usage: {
            total_tokens: 1200,
          },
        },
        memory_activity: null,
      },
      {
        id: "88888888-8888-8888-8888-888888888882",
        node_id: "write_ticket",
        node_type: "tool",
        status: "failed",
        attempt: 3,
        started_at: "2026-04-01T11:41:00.000Z",
        ended_at: "2026-04-01T11:42:15.000Z",
        duration_ms: 75000,
        input_json: {
          system: "escalation_api",
        },
        output_json: null,
        error_json: {
          message: "Escalation API rejected the payload.",
          code: "PAYLOAD_REJECTED",
        },
        agent_trace: {
          steps: [
            {
              step_index: 1,
              tool: "ticket_writer",
              tool_output: "Remote API returned validation failure.",
              finish_reason: "error",
            },
          ],
          usage: {
            total_tokens: 800,
          },
        },
        memory_activity: null,
      },
    ],
    agent_events: [],
    memory_activity: null,
    paused_node_id: null,
    pause_payload: null,
  };

  const overview = {
    organization,
    summary: {
      active_agent_count: activeAgents.length,
      active_task_count: activeTasks.length,
      pending_decision_count: 1,
      execution_count_24h: 3,
      memory_observation_count: 4,
      total_cost_usd: 62.15,
    },
    active_agents: activeAgents,
    active_tasks: activeTasks,
    pending_decisions: [pendingDecision],
    recent_executions: [
      {
        id: fixture.runIds.failed,
        workflow_id: "77777777-7777-7777-7777-777777777772",
        workflow_name: "Failure escalation",
        workflow_revision_id: "77777777-7777-7777-7777-777777777773",
        status: "failed",
        started_at: "2026-04-01T11:40:00.000Z",
        ended_at: "2026-04-01T11:42:15.000Z",
        duration_ms: 135000,
      },
      {
        id: fixture.runIds.running,
        workflow_id: "99999999-9999-9999-9999-999999999991",
        workflow_name: "Invoice monitoring",
        workflow_revision_id: "99999999-9999-9999-9999-999999999992",
        status: "running",
        started_at: "2026-04-01T11:57:00.000Z",
        ended_at: null,
        duration_ms: 30000,
      },
    ],
    memory: {
      active_observation_count: 4,
      recent_topics: ["payments", "budget-alerts"],
    },
    policy: {
      configured: true,
      allowed_providers: ["openai"],
      allowed_models: ["gpt-5.4", "gpt-5.4-mini"],
      http_default_deny: true,
    },
    accounting: {
      summary: {
        total_cost_usd: 62.15,
        total_tokens: 29400,
        active_budget_alerts: 1,
      },
      ledger: [],
      aggregates: [],
    },
    generated_at: "2026-04-01T12:00:00.000Z",
  };

  return {
    overview,
    approval,
    activeAgents,
    activeTasks,
    pendingDecision,
    memoryTimeline,
    failedExecution,
  };
}

async function mockControlPlaneApis(
  page: Page,
  fixture: FrontendControlPlaneFixture,
  options?: {
    resolutionOnResume?: ResolutionStatus;
  },
): Promise<void> {
  const state = buildControlPlaneState(fixture);
  let approvalStatus: "pending" | ResolutionStatus = "pending";

  await page.route(/\/api\/decisions\/count(?:\?.*)?$/, async (route: Route) => {
    await route.fulfill({
      status: 200,
      contentType: "application/json",
      body: JSON.stringify(apiSuccess({ count: approvalStatus === "pending" ? 1 : 0 })),
    });
  });

  await page.route(/\/api\/approvals\/count(?:\?.*)?$/, async (route: Route) => {
    await route.fulfill({
      status: 200,
      contentType: "application/json",
      body: JSON.stringify(apiSuccess({ count: approvalStatus === "pending" ? 1 : 0 })),
    });
  });

  await page.route(/\/api\/system-state\/overview(?:\?.*)?$/, async (route: Route) => {
    await route.fulfill({
      status: 200,
      contentType: "application/json",
      body: JSON.stringify(apiSuccess(state.overview)),
    });
  });

  await page.route(/\/api\/approvals\/?(?:\?.*)?$/, async (route: Route) => {
    if (route.request().method() !== "GET") {
      await route.continue();
      return;
    }

    const url = new URL(route.request().url());
    const requestedStatus = url.searchParams.get("status") ?? "pending";
    const task = {
      ...state.approval,
      status: approvalStatus,
      resolved_at: approvalStatus === "pending" ? null : "2026-04-01T12:01:00.000Z",
      result:
        approvalStatus === "pending"
          ? null
          : {
              approved: approvalStatus === "approved",
              feedback: `Operator ${approvalStatus} in Playwright coverage.`,
            },
    };

    const includeTask =
      requestedStatus === "all" ||
      requestedStatus === approvalStatus ||
      (approvalStatus === "pending" && requestedStatus === "pending");

    await route.fulfill({
      status: 200,
      contentType: "application/json",
      body: JSON.stringify(apiSuccess(includeTask ? [task] : [])),
    });
  });

  await page.route(/\/api\/agents\/?(?:\?.*)?$/, async (route: Route) => {
    await route.fulfill({
      status: 200,
      contentType: "application/json",
      body: JSON.stringify(apiSuccess(state.activeAgents)),
    });
  });

  await page.route(/\/api\/tasks\/?(?:\?.*)?$/, async (route: Route) => {
    await route.fulfill({
      status: 200,
      contentType: "application/json",
      body: JSON.stringify(apiSuccess(state.activeTasks)),
    });
  });

  await page.route(/\/api\/decisions\/?(?:\?.*)?$/, async (route: Route) => {
    const decision =
      approvalStatus === "pending"
        ? state.pendingDecision
        : {
            ...state.pendingDecision,
            status: approvalStatus,
            resolution_json: {
              output:
                approvalStatus === "approved"
                  ? "Operator approved the payment after reviewing the risk summary."
                  : "Operator rejected the payment and left the execution paused for follow-up.",
            },
            resolved_at: "2026-04-01T12:01:00.000Z",
            updated_at: "2026-04-01T12:01:00.000Z",
          };

    await route.fulfill({
      status: 200,
      contentType: "application/json",
      body: JSON.stringify(apiSuccess([decision])),
    });
  });

  await page.route(/\/api\/memory\/observations\/timeline(?:\?.*)?$/, async (route: Route) => {
    await route.fulfill({
      status: 200,
      contentType: "application/json",
      body: JSON.stringify(apiSuccess(state.memoryTimeline)),
    });
  });

  await page.route(new RegExp(`/api/executions/${fixture.runIds.failed}(?:\\?.*)?$`), async (route: Route) => {
    await route.fulfill({
      status: 200,
      contentType: "application/json",
      body: JSON.stringify(apiSuccess(state.failedExecution)),
    });
  });

  await page.route(/\/api\/runs\/[^/]+\/resume(?:\?.*)?$/, async (route: Route) => {
    approvalStatus = options?.resolutionOnResume ?? "approved";
    await route.fulfill({
      status: 200,
      contentType: "application/json",
      body: JSON.stringify(apiSuccess({ resumed: true })),
    });
  });
}

test.describe("Frontend Control Surface", () => {
  test("shows backend-owned system state on the overview page", async ({ page, request }, testInfo) => {
    const user = createTestUser(testInfo, "control-overview");
    await ensureUserRegistered(request, user);
    const fixture = seedFrontendControlPlaneFixture(user);
    await mockControlPlaneApis(page, fixture);

    await openAuthenticatedPage(page, user, "/overview", { organizationId: fixture.organizationId });

    await expect(page.getByRole("heading", { name: /organization overview/i })).toBeVisible();
    await expect(page.getByRole("heading", { name: /^active agents$/i })).toBeVisible();
    await expect(page.getByText(/^tasks running$/i)).toBeVisible();
    await expect(page.getByText(/^pending approvals$/i)).toBeVisible();
    await expect(page.getByText(/^token cost today$/i)).toBeVisible();
    await expect(page.getByRole("link", { name: /ops conductor attention/i })).toBeVisible();
    await expect(page.getByRole("link", { name: /billing sentinel active/i })).toBeVisible();
    await expect(
      page.getByText(/vendor payment over the safety threshold requires operator confirmation/i),
    ).toBeVisible();
    await expect(page.getByText(/failure escalation failed/i)).toBeVisible();
  });

  for (const resolution of ["approved", "rejected"] as const) {
    test(`updates the inbox after a ${resolution} decision`, async ({ page, request }, testInfo) => {
      const user = createTestUser(testInfo, `control-inbox-${resolution}`);
      await ensureUserRegistered(request, user);
      const fixture = seedFrontendControlPlaneFixture(user);
      await mockControlPlaneApis(page, fixture, { resolutionOnResume: resolution });

      await openAuthenticatedPage(page, user, "/inbox", { organizationId: fixture.organizationId });

      await expect(page.getByRole("heading", { name: /review consequential agent decisions/i })).toBeVisible();
      await expect(page.getByText(fixture.approval.promptMessage, { exact: true })).toBeVisible();

      const notes = `Operator ${resolution} in Playwright coverage.`;
      await page.getByPlaceholder(/add guidance, corrections, or operator feedback/i).fill(notes);

      if (resolution === "approved") {
        await page.getByRole("button", { name: /approve with notes/i }).click();
      } else {
        await page.getByRole("button", { name: /^reject$/i }).click();
      }

      await expect(page.getByText(/inbox is clear/i)).toBeVisible();

      await page.getByRole("button", { name: new RegExp(`^${resolution}$`, "i") }).click();
      await expect(page.getByRole("button", { name: new RegExp(fixture.approval.graphName, "i") })).toBeVisible();
      await expect(page.getByText(/read only/i)).toBeVisible();
    });
  }

  test("shows selected agent status, current task, decision trace, and memory context", async ({
    page,
    request,
  }, testInfo) => {
    const user = createTestUser(testInfo, "control-agent");
    await ensureUserRegistered(request, user);
    const fixture = seedFrontendControlPlaneFixture(user);
    await mockControlPlaneApis(page, fixture);

    await openAuthenticatedPage(page, user, `/agents?agent=${fixture.agentIds.ops}`, {
      organizationId: fixture.organizationId,
    });

    await expect(page.getByRole("heading", { name: /understand and control one agent at a time/i })).toBeVisible();
    await expect(page.getByRole("button", { name: /ops conductor attention/i })).toBeVisible();
    await expect(
      page
        .locator("div")
        .filter({ hasText: /^Ops Conductor is waiting for a decision in Vendor payment review\.$/ })
        .first(),
    ).toBeVisible();
    await expect(page.getByText(/payment escalation guidance/i)).toBeVisible();
    await expect(
      page.getByText(/vendor payment over the safety threshold requires operator confirmation/i),
    ).toBeVisible();
    await expect(page.getByText(/decision is waiting on resolution/i)).toBeVisible();
  });

  test("shows failed execution steps and the failure inspection state", async ({ page, request }, testInfo) => {
    const user = createTestUser(testInfo, "control-failure");
    await ensureUserRegistered(request, user);
    const fixture = seedFrontendControlPlaneFixture(user);
    await mockControlPlaneApis(page, fixture);

    await openAuthenticatedPage(page, user, `/executions/${fixture.runIds.failed}`, {
      organizationId: fixture.organizationId,
    });

    await expect(page.getByRole("heading", { name: /structured execution trace/i })).toBeVisible();
    await expect(page.getByText(/failure point/i)).toBeVisible();
    await expect(page.getByRole("button", { name: /write_ticket failed tool/i })).toBeVisible();
    await expect(page.getByText(/execution requires intervention here/i)).toBeVisible();

    await page.getByRole("button", { name: /write_ticket/i }).click();
    await expect(page.getByText(/escalation api rejected the payload/i)).toBeVisible();
    await expect(page.getByText(/execution state/i)).toBeVisible();
  });

  test("surfaces clear error messaging when overview state cannot be loaded", async ({ page, request }, testInfo) => {
    const user = createTestUser(testInfo, "control-errors");
    await ensureUserRegistered(request, user);
    const fixture = seedFrontendControlPlaneFixture(user);
    await mockControlPlaneApis(page, fixture);

    await page.route(/\/api\/system-state\/overview(?:\?.*)?$/, async (route: Route) => {
      await route.fulfill({
        status: 503,
        contentType: "application/json",
        body: JSON.stringify({
          error: {
            code: "SERVICE_UNAVAILABLE",
            message: "Organization projections are temporarily unavailable.",
          },
          meta: {
            requestId: "playwright-overview-error",
            timestamp: "2026-04-01T12:00:00.000Z",
          },
        }),
      });
    });

    await openAuthenticatedPage(page, user, "/overview", { organizationId: fixture.organizationId });

    await expect(page.getByText(/organization projections are temporarily unavailable/i)).toBeVisible();
  });
});
