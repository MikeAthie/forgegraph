import { expect, test, type Page, type Route } from "@playwright/test";

import {
  buildLegacyMultiPackProductModeState,
  collectProductModeApiRequests,
  legacyMultiPackIds,
  sawProductModeApiPath,
  verticalProductModeApiRequests,
  installProductModeMocks,
  type ProductModeMockState,
} from "../product-modes/fixtures";
import {
  createCompanyViaCompanyApi,
  createTestUser,
  ensureUserRegistered,
  fetchLatestCompanyOperatingModelVersion,
  getAccessToken,
  openBackendAuthenticatedPage,
} from "./helpers";

const forbiddenVerticalRoutePattern =
  /\/api\/(?:marketing|growth-marketing|digital-marketing|marketing-campaigns|atlas|legacy)(?:\/|$)/i;
const storageApiPattern = /\/api\/(?:graphs|workflows)(?:\/|$)/i;
const strategyCardId = "legacy-whiteboard-strategy-card";
const contentCardId = "legacy-whiteboard-content-task";

type ApiEvent = {
  method: string;
  pathname: string;
};

function apiSuccess<T>(data: T) {
  return {
    data,
    meta: {
      requestId: "playwright-workboard-stress",
      timestamp: "2026-05-31T12:00:00.000Z",
    },
  };
}

function stressRunId(index: number): string {
  return `90000000-0000-4000-8000-${String(index).padStart(12, "0")}`;
}

function collectApiDiagnostics(page: Page) {
  const apiEvents: ApiEvent[] = [];
  const failedApiResponses: string[] = [];
  const consoleErrors: string[] = [];

  page.on("request", (request) => {
    const url = new URL(request.url());
    if (url.pathname.startsWith("/api/")) {
      apiEvents.push({ method: request.method(), pathname: url.pathname });
    }
  });

  page.on("response", (response) => {
    const url = new URL(response.url());
    if (url.pathname.startsWith("/api/") && response.status() >= 400) {
      failedApiResponses.push(`${response.status()} ${response.request().method()} ${url.pathname}`);
    }
  });

  page.on("console", (message) => {
    if (message.type() === "error") {
      consoleErrors.push(message.text());
    }
  });

  return { apiEvents, failedApiResponses, consoleErrors };
}

function sawApiEvent(events: ApiEvent[], method: string, pathname: string): boolean {
  return events.some((event) => event.method === method && event.pathname === pathname);
}

async function fulfillJson(route: Route, data: unknown): Promise<void> {
  await route.fulfill({
    status: 200,
    contentType: "application/json",
    body: JSON.stringify(apiSuccess(data)),
  });
}

async function installPlanningAliasMocks(
  page: Page,
  state: ProductModeMockState,
  counters: { readyForPlanning: number; startPlanning: number; getPlanning: number; synthesizePlanning: number },
): Promise<void> {
  const routePromises: Array<ReturnType<Page["route"]>> = [];
  const route = (...args: Parameters<Page["route"]>) => {
    routePromises.push(page.route(...args));
  };

  const getWhiteboard = (route: Route) => {
    const url = new URL(route.request().url());
    const whiteboardId = url.pathname.match(/\/api\/whiteboards\/([^/]+)/)?.[1] ?? "";
    return (state.whiteboards ?? []).find((item) => item.id === whiteboardId) ?? null;
  };

  const planningPayload = {
    status: "planning",
    work_status: "planning",
    workstreams: [],
    all_workstreams_completed: false,
    synthesis: null,
    gate: null,
    content_unblocked: false,
    content_routing_record_id: null,
    planning_complete: false,
    next_routing_record_id: "stress-planning-routing-record",
  };

  route(/\/api\/whiteboards\/[^/]+\/ready-for-planning(?:\?.*)?$/, async (route: Route) => {
    const whiteboard = getWhiteboard(route);
    if (route.request().method() !== "POST" || !whiteboard) {
      await route.continue();
      return;
    }
    counters.readyForPlanning += 1;
    whiteboard.work_status = "ready_for_planning";
    whiteboard.status = "ready_for_strategy";
    whiteboard.work_missing_fields = [];
    whiteboard.missing_fields = [];
    whiteboard.completion_score = 100;
    whiteboard.semantic_aliases = {
      ...(whiteboard.semantic_aliases ?? {}),
      work_status: { legacy_field: "status", legacy_value: "ready_for_strategy", value: "ready_for_planning" },
    };
    const board = (state.whiteboardBoards ?? []).find((item) => item.whiteboard_id === whiteboard.id);
    if (board) {
      board.project.work_status = whiteboard.work_status;
      board.project.status = whiteboard.work_status;
      board.project.legacy_status = whiteboard.status;
      board.project.completion_score = whiteboard.completion_score;
    }
    await fulfillJson(route, { whiteboard });
  });

  route(/\/api\/whiteboards\/[^/]+\/start-planning(?:\?.*)?$/, async (route: Route) => {
    const whiteboard = getWhiteboard(route);
    if (route.request().method() !== "POST" || !whiteboard) {
      await route.continue();
      return;
    }
    counters.startPlanning += 1;
    whiteboard.work_status = "planning";
    whiteboard.status = "in_strategy";
    whiteboard.planning = planningPayload;
    await fulfillJson(route, {
      planning: planningPayload,
      strategy: planningPayload,
      whiteboard,
    });
  });

  route(/\/api\/whiteboards\/[^/]+\/planning(?:\?.*)?$/, async (route: Route) => {
    const whiteboard = getWhiteboard(route);
    if (route.request().method() !== "GET" || !whiteboard) {
      await route.continue();
      return;
    }
    counters.getPlanning += 1;
    await fulfillJson(route, { planning: whiteboard.planning ?? planningPayload });
  });

  route(/\/api\/whiteboards\/[^/]+\/planning\/synthesize(?:\?.*)?$/, async (route: Route) => {
    const whiteboard = getWhiteboard(route);
    if (route.request().method() !== "POST" || !whiteboard) {
      await route.continue();
      return;
    }
    counters.synthesizePlanning += 1;
    const planning = {
      ...planningPayload,
      synthesis: {
        asset_id: "stress-planning-synthesis",
        asset_version_id: "stress-planning-synthesis-v1",
        created_at: "2026-05-31T12:05:00.000Z",
      },
      planning_complete: true,
    };
    whiteboard.planning = planning;
    await fulfillJson(route, {
      planning,
      strategy: planning,
      whiteboard,
    });
  });

  await Promise.all(routePromises);
}

test.describe("Company workboard stress flow", () => {
  test("survives repeated brief, operation, board, and planning mutations without leaving generic route boundaries", async ({
    page,
    request,
  }, testInfo) => {
    test.setTimeout(150_000);

    const apiRequests = collectProductModeApiRequests(page);
    const diagnostics = collectApiDiagnostics(page);
    const user = createTestUser(testInfo, "workboard-stress");
    await ensureUserRegistered(request, user);
    const accessToken = await getAccessToken(request, user);
    const seed = await createCompanyViaCompanyApi(request, accessToken, {
      name: "Stress Operations Studio",
      companyType: "Operations Studio",
      objective:
        "Stress generic company, planning, board, communication, operation, deployment, and performance surfaces.",
      autonomyMode: "assisted",
      aiAccessMode: "managed",
    });
    const latestVersion = await fetchLatestCompanyOperatingModelVersion(request, accessToken, seed.companyId);

    let launchedOperationCount = 0;
    const planningCounters = {
      readyForPlanning: 0,
      startPlanning: 0,
      getPlanning: 0,
      synthesizePlanning: 0,
    };
    const state = buildLegacyMultiPackProductModeState({
      companyId: seed.companyId,
      companyName: "Stress Operations Studio",
      graphVersion: latestVersion,
      pendingApprovalCount: 2,
      operations: [
        {
          id: stressRunId(1),
          status: "running",
          startedAt: "2026-05-31T08:00:00.000Z",
          operationBrief: "Advance a live workstream while board cards are changing.",
          currentNodeId: latestVersion.graph_json.nodes[1]?.id ?? latestVersion.graph_json.nodes[0]?.id ?? null,
          llmMode: "managed",
        },
        {
          id: stressRunId(2),
          status: "failed",
          startedAt: "2026-05-31T07:00:00.000Z",
          endedAt: "2026-05-31T07:08:00.000Z",
          failedNodeId: latestVersion.graph_json.nodes[1]?.id ?? latestVersion.graph_json.nodes[0]?.id ?? null,
          errorMessage: "LLM timeout while packaging the stress readout.",
          llmMode: "managed",
        },
        {
          id: stressRunId(3),
          status: "succeeded",
          startedAt: "2026-05-31T06:00:00.000Z",
          endedAt: "2026-05-31T06:06:00.000Z",
          operationBrief: "Prepare the first stress-cycle deliverable.",
          deliverable: "Deliverable: initial stress-cycle operating memo, board summary, and routing readout.",
          llmMode: "managed",
        },
      ],
      onStart: (input) => {
        launchedOperationCount += 1;
        const inputJson =
          input.input_json && typeof input.input_json === "object" ? (input.input_json as Record<string, unknown>) : {};
        return {
          id: stressRunId(10 + launchedOperationCount),
          status: "succeeded",
          startedAt: `2026-05-31T09:0${launchedOperationCount}:00.000Z`,
          endedAt: `2026-05-31T09:1${launchedOperationCount}:00.000Z`,
          operationBrief: String(inputJson.operation_brief ?? "Run a stress-cycle company operation."),
          deliverable: `Deliverable: stress-cycle ${launchedOperationCount} completed with board state preserved.`,
          llmMode: "managed",
        };
      },
      onReplay: () => ({
        id: stressRunId(2),
        status: "succeeded",
        startedAt: "2026-05-31T07:10:00.000Z",
        endedAt: "2026-05-31T07:15:00.000Z",
        deliverable: "Deliverable: retried stress readout completed with sanitized failure context.",
        llmMode: "managed",
      }),
    });

    await installProductModeMocks(page, state);
    await installPlanningAliasMocks(page, state, planningCounters);
    await openBackendAuthenticatedPage(page, request, user, "/companies");

    await expect(page.getByRole("link", { name: /Stress Operations Studio/i })).toHaveCount(1);
    await page.getByRole("link", { name: /Stress Operations Studio/i }).first().click();
    await page.waitForURL(new RegExp(`/companies/${seed.companyId}$`));
    await expect(page.getByTestId("command-ops-panel")).toBeVisible();
    await expect(page.getByText(/initial stress-cycle operating memo/i).first()).toBeVisible();

    const briefUpdates = [
      "Add enterprise stakeholders and preserve customer-safe board visibility.",
      "Cannot use paid ads; keep evidence customer visible only when explicitly safe.",
      "Prioritize speed over cost while keeping deployment and performance review intact.",
    ];
    for (const update of briefUpdates) {
      await page.getByTestId("operating-brief-input").fill(update);
      await expect(page.getByTestId("operating-brief-submit-button")).toBeEnabled();
      await page.getByTestId("operating-brief-submit-button").click();
      await expect(page.getByTestId("command-ops-response-card")).toContainText(/assumptions were recorded/i);
    }
    await expect(page.getByText(/^Enterprise clients$/i)).toBeVisible();
    await expect(page.getByText(/^Cannot use paid ads$/i)).toBeVisible();

    await page.getByTestId("company-retry-operation-button").click();
    await expect(page.getByText(/retried stress readout completed/i).first()).toBeVisible();

    for (const index of [1, 2, 3]) {
      await page
        .getByTestId("company-launch-operation-input")
        .fill(`Run stress-cycle operation ${index} and keep workboard routing stable.`);
      await expect(page.getByTestId("company-launch-operation-button")).toBeEnabled();
      await page.getByTestId("company-launch-operation-button").click();
      await expect(page.getByText(new RegExp(`stress-cycle ${index} completed`, "i")).first()).toBeVisible();
    }

    await page.getByTestId("whiteboard-panel").scrollIntoViewIfNeeded();
    await expect(page.getByTestId("whiteboard-summary")).toContainText(/WhatsApp is recommended/i);
    await expect(page.getByTestId("whiteboard-status")).toContainText(/Work Status/i);
    await expect(page.getByTestId("whiteboard-known-fields")).toContainText(/Work Context/i);

    const readyForPlanningResponsePromise = page.waitForResponse((response) => {
      const url = new URL(response.url());
      return url.pathname === `/api/whiteboards/${legacyMultiPackIds.whiteboard}/ready-for-planning`;
    });
    await page.getByTestId("whiteboard-mark-ready-button").click();
    const readyForPlanningResponse = await readyForPlanningResponsePromise;
    expect(readyForPlanningResponse.ok()).toBe(true);
    const readyForPlanningBody = await readyForPlanningResponse.json();
    expect(readyForPlanningBody.data.whiteboard.work_status).toBe("ready_for_planning");
    await expect(page.getByTestId("whiteboard-status")).toContainText(/Ready For Planning/i);

    await page.getByTestId("whiteboard-board").scrollIntoViewIfNeeded();
    await expect(page.getByTestId("whiteboard-board")).toBeVisible();
    const boardCards = page.locator('[data-testid^="whiteboard-board-card-"]');
    const initialBoardCardCount = await boardCards.count();
    for (const expectedGrowth of [1, 2, 3]) {
      await page.getByTestId("whiteboard-routing-create-card").click();
      await expect.poll(() => boardCards.count()).toBe(initialBoardCardCount + expectedGrowth);
    }

    await page.getByTestId(`whiteboard-card-start-${strategyCardId}`).click();
    await expect(page.getByTestId(`whiteboard-card-status-${strategyCardId}`)).toContainText(/in_progress/i);
    await page.getByTestId(`whiteboard-card-priority-action-${strategyCardId}`).click();
    await expect(page.getByTestId(`whiteboard-card-priority-${strategyCardId}`)).toContainText(/Urgent/i);
    await page.getByTestId(`whiteboard-card-reassign-${strategyCardId}`).click();
    await expect(page.getByTestId("whiteboard-board-lane-traffic")).toContainText(/Strategy intake/i);

    await page.getByTestId(`whiteboard-card-evidence-button-${contentCardId}`).click();
    await expect(page.getByTestId(`whiteboard-card-evidence-${contentCardId}`)).toContainText(
      /2 evidence refs/i,
    );
    await page.getByTestId(`whiteboard-card-ready-${contentCardId}`).click();
    await expect(page.getByTestId(`whiteboard-card-status-${contentCardId}`)).toContainText(/ready_for_review/i);
    await page.getByTestId(`whiteboard-card-complete-${contentCardId}`).click();
    await expect(page.getByTestId(`whiteboard-card-status-${contentCardId}`)).toContainText(/completed/i);

    const planningResults = await page.evaluate(async (whiteboardId) => {
      const startResponse = await fetch(`/api/whiteboards/${whiteboardId}/start-planning`, { method: "POST" });
      const getResponse = await fetch(`/api/whiteboards/${whiteboardId}/planning`);
      const synthesizeResponse = await fetch(`/api/whiteboards/${whiteboardId}/planning/synthesize`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ scores: { completeness: 1 } }),
      });
      return {
        start: { status: startResponse.status, body: await startResponse.json() },
        get: { status: getResponse.status, body: await getResponse.json() },
        synthesize: { status: synthesizeResponse.status, body: await synthesizeResponse.json() },
      };
    }, legacyMultiPackIds.whiteboard);
    expect(planningResults.start.status).toBe(200);
    expect(planningResults.get.status).toBe(200);
    expect(planningResults.synthesize.status).toBe(200);
    expect(planningResults.synthesize.body.data.planning.planning_complete).toBe(true);

    await page.getByTestId("whiteboard-deployment-section").scrollIntoViewIfNeeded();
    await expect(page.getByTestId("whiteboard-deployment-channel-whatsapp")).toContainText(/Blocked/i);
    await page.getByTestId("whiteboard-performance-section").scrollIntoViewIfNeeded();
    await expect(page.getByTestId("whiteboard-performance-source-whatsapp")).toContainText(/Blocked/i);
    await expect(page.getByText(/llm timeout while packaging the stress readout/i)).not.toBeVisible();

    expect(launchedOperationCount).toBe(3);
    expect(planningCounters).toEqual({
      readyForPlanning: 1,
      startPlanning: 1,
      getPlanning: 1,
      synthesizePlanning: 1,
    });
    expect(sawProductModeApiPath(apiRequests, "/api/companies/")).toBe(true);
    expect(sawProductModeApiPath(apiRequests, `/api/companies/${seed.companyId}`)).toBe(true);
    expect(
      sawProductModeApiPath(apiRequests, `/api/companies/${seed.companyId}/operating-model-versions/latest`),
    ).toBe(true);
    expect(sawProductModeApiPath(apiRequests, `/api/whiteboards/${legacyMultiPackIds.whiteboard}/ready-for-planning`))
      .toBe(true);
    expect(sawApiEvent(diagnostics.apiEvents, "POST", `/api/whiteboards/${legacyMultiPackIds.whiteboard}/board/cards`))
      .toBe(true);
    expect(
      diagnostics.apiEvents.filter((event) => storageApiPattern.test(event.pathname)).map((event) => event.pathname),
    ).toEqual([]);
    expect(verticalProductModeApiRequests(apiRequests, forbiddenVerticalRoutePattern)).toEqual([]);
    expect(diagnostics.failedApiResponses).toEqual([]);
    expect(diagnostics.consoleErrors).toEqual([]);
  });
});
