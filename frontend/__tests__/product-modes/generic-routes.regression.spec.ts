import { expect, test } from "@playwright/test";

import {
  buildLegacyMultiPackProductModeState,
  collectProductModeApiRequests,
  installProductModeMocks,
  legacyMultiPackIds,
  sawCompanyScopedProductModeQuery,
  sawProductModeApiPath,
  verticalProductModeApiRequests,
} from "./fixtures";
import {
  createCompanyViaApi,
  createTestUser,
  ensureUserRegistered,
  fetchLatestGraphVersion,
  getAccessToken,
  openBackendAuthenticatedPage,
} from "../e2e/helpers";

const forbiddenVerticalMarketingRoutePattern =
  /\/api\/(?:marketing|growth-marketing|digital-marketing|marketing-campaigns|atlas|legacy)(?:\/|$)/i;

function sawStateProjectionType(apiRequests: string[], companyId: string, projectionType: string): boolean {
  return apiRequests.some((requestUrl) => {
    const url = new URL(requestUrl);
    return (
      url.pathname === "/api/state-projections" &&
      url.searchParams.get("company_id") === companyId &&
      url.searchParams.get("projection_type") === projectionType
    );
  });
}

test.describe("Product modes", () => {
  test("generic product-mode routes stay company scoped and vertical free", async ({ page, request }, testInfo) => {
    expect(testInfo.title).not.toMatch(/marketing/i);

    const apiRequests = collectProductModeApiRequests(page);
    const user = createTestUser(testInfo, "product-mode-routes");
    await ensureUserRegistered(request, user);
    const accessToken = await getAccessToken(request, user);
    const seed = await createCompanyViaApi(request, accessToken, {
      name: "Legacy Eyewear",
      companyType: "Eyewear Company",
      objective: "Exercise generic product-mode routes for a multi-pack company workspace.",
      autonomyMode: "assisted",
      aiAccessMode: "managed",
    });
    const latestVersion = await fetchLatestGraphVersion(request, accessToken, seed.companyId);

    const state = buildLegacyMultiPackProductModeState({
      companyId: seed.companyId,
      companyName: "Legacy Eyewear",
      graphVersion: latestVersion,
      pendingApprovalCount: 0,
      operations: [
        {
          id: "52222222-2222-4222-8222-222222222222",
          status: "succeeded",
          startedAt: "2026-05-10T10:00:00.000Z",
          endedAt: "2026-05-10T10:05:00.000Z",
          operationBrief: "Prepare the Legacy Eyewear generic route regression readout.",
          deliverable: "Deliverable: generic company routes, pack state, artifacts, projections, and report history.",
          llmMode: "managed",
        },
      ],
    });

    await installProductModeMocks(page, state);
    await openBackendAuthenticatedPage(page, request, user, "/companies");

    // This regression protects the architecture boundary:
    // Organization -> Company -> PackInstallation -> generic primitives.
    const legacyCompanyLink = page.getByRole("link", { name: /Legacy Eyewear/i });
    await expect(legacyCompanyLink).toHaveCount(1);
    await legacyCompanyLink.first().click();
    await page.waitForURL(new RegExp(`/companies/${seed.companyId}$`));

    await expect(page.getByTestId("command-ops-panel")).toBeVisible();
    await page.getByTestId(`operating-model-pack-card-${legacyMultiPackIds.primary}`).scrollIntoViewIfNeeded();
    await expect(page.getByTestId(`operating-model-pack-card-${legacyMultiPackIds.primary}`)).toBeVisible();
    await page.getByTestId(`artifact-card-${legacyMultiPackIds.artifact}`).scrollIntoViewIfNeeded();
    await expect(page.getByTestId(`artifact-card-${legacyMultiPackIds.artifact}`)).toBeVisible();
    await page.getByTestId("service-history-panel").scrollIntoViewIfNeeded();
    await expect(page.getByTestId("service-history-panel")).toBeVisible();
    await page.getByTestId("communication-panel").scrollIntoViewIfNeeded();
    await expect(page.getByTestId("communication-panel")).toBeVisible();
    await expect(page.getByText(/Can you explain why WhatsApp is recommended/i)).toBeVisible();
    await expect(page.getByText(/manual first step/i)).toBeVisible();
    await expect(page.getByText(/Execution remains blocked/i)).toHaveCount(0);
    await page.getByTestId("whiteboard-panel").scrollIntoViewIfNeeded();
    await expect(page.getByTestId("whiteboard-panel")).toBeVisible();
    await expect(page.getByTestId("whiteboard-summary")).toContainText(/WhatsApp is recommended/i);
    await expect(page.getByTestId("whiteboard-board")).toBeVisible();
    await expect(page.getByTestId("whiteboard-board-lane-strategy")).toContainText(/Strategy intake/i);
    await expect(page.getByTestId("whiteboard-board-lane-deployment-ops")).toContainText(/Deployment readiness/i);
    await expect(page.getByTestId("whiteboard-card-priority-legacy-whiteboard-strategy-card")).toContainText(/High/i);
    await expect(page.getByTestId("whiteboard-card-reassign-legacy-whiteboard-strategy-card")).toBeVisible();
    await page.getByTestId("whiteboard-card-start-legacy-whiteboard-strategy-card").click();
    await expect(page.getByTestId("whiteboard-card-status-legacy-whiteboard-strategy-card")).toContainText(
      /in_progress/i,
    );
    await expect(page.getByTestId("whiteboard-phase-section")).toBeVisible();
    await expect(page.getByTestId("whiteboard-phase-workstreams")).toContainText(/Copywriting/i);
    await expect(page.getByTestId("whiteboard-phase-gate")).toContainText(/Pass/i);
    await expect(page.getByTestId("whiteboard-phase-gate")).toContainText(/Captured/i);
    await expect(page.getByTestId("whiteboard-phase-approval")).toContainText(/Queued/i);
    await expect(page.getByTestId("whiteboard-deployment-section")).toBeVisible();
    await expect(page.getByTestId("whiteboard-deployment-channels")).toContainText(/Email/i);
    await expect(page.getByTestId("whiteboard-deployment-channels")).toContainText(/Captured|Receipt/i);
    await expect(page.getByTestId("whiteboard-deployment-channel-whatsapp")).toContainText(/Blocked/i);
    await expect(page.getByTestId("whiteboard-performance-section")).toBeVisible();
    await expect(page.getByTestId("whiteboard-performance-sources")).toContainText(/Email/i);
    await expect(page.getByTestId("whiteboard-performance-source-whatsapp")).toContainText(/Blocked/i);
    await expect(page.getByTestId("whiteboard-performance-state")).toContainText(/legacy-performance-report-run/i);
    await expect(page.getByTestId("whiteboard-routing-tasks")).toContainText(/Content\/Creative/i);
    await expect(page.getByTestId("whiteboard-routing-tasks")).toContainText(/Client Services/i);
    await page.getByTestId("commerce-inventory-panel").scrollIntoViewIfNeeded();
    await expect(page.getByTestId("commerce-inventory-panel")).toBeVisible();

    await expect(page.locator('[data-testid*="marketing" i]')).toHaveCount(0);

    expect(sawProductModeApiPath(apiRequests, "/api/companies/")).toBe(true);
    expect(sawProductModeApiPath(apiRequests, "/api/portfolio-health")).toBe(true);
    expect(sawProductModeApiPath(apiRequests, "/api/cross-company-queues")).toBe(true);
    expect(sawProductModeApiPath(apiRequests, `/api/companies/${seed.companyId}`)).toBe(true);
    expect(sawProductModeApiPath(apiRequests, `/api/companies/${seed.companyId}/operating-model-versions/latest`)).toBe(
      true,
    );
    expect(sawProductModeApiPath(apiRequests, "/api/operating-model-packs")).toBe(true);
    expect(sawProductModeApiPath(apiRequests, `/api/companies/${seed.companyId}/packs`)).toBe(true);
    expect(sawProductModeApiPath(apiRequests, `/api/companies/${seed.companyId}/operating-model`)).toBe(true);
    expect(sawProductModeApiPath(apiRequests, `/api/companies/${seed.companyId}/programs`)).toBe(true);
    expect(sawCompanyScopedProductModeQuery(apiRequests, "/api/work-artifacts", seed.companyId)).toBe(true);
    expect(sawCompanyScopedProductModeQuery(apiRequests, "/api/state-projections", seed.companyId)).toBe(true);
    expect(sawCompanyScopedProductModeQuery(apiRequests, "/api/periodic-reviews", seed.companyId)).toBe(true);
    expect(sawCompanyScopedProductModeQuery(apiRequests, "/api/metric-snapshots", seed.companyId)).toBe(true);
    expect(sawCompanyScopedProductModeQuery(apiRequests, "/api/report-runs", seed.companyId)).toBe(true);
    expect(sawCompanyScopedProductModeQuery(apiRequests, "/api/communication/threads", seed.companyId)).toBe(true);
    expect(sawCompanyScopedProductModeQuery(apiRequests, "/api/whiteboards", seed.companyId)).toBe(true);
    expect(sawProductModeApiPath(apiRequests, `/api/whiteboards/${legacyMultiPackIds.whiteboard}/board`)).toBe(true);
    expect(
      sawProductModeApiPath(
        apiRequests,
        `/api/whiteboards/${legacyMultiPackIds.whiteboard}/board/cards/legacy-whiteboard-strategy-card`,
      ),
    ).toBe(true);
    expect(sawStateProjectionType(apiRequests, seed.companyId, "client_service_history")).toBe(true);
    expect(verticalProductModeApiRequests(apiRequests, forbiddenVerticalMarketingRoutePattern)).toEqual([]);
  });

  test("P1 Atlas UI controls dispatch generic company and whiteboard commands", async ({ page, request }, testInfo) => {
    const apiRequests = collectProductModeApiRequests(page);
    const user = createTestUser(testInfo, "product-mode-p1-controls");
    await ensureUserRegistered(request, user);
    const accessToken = await getAccessToken(request, user);
    const seed = await createCompanyViaApi(request, accessToken, {
      name: "Legacy Eyewear",
      companyType: "Eyewear Company",
      objective: "Exercise P1 Atlas controls through generic routes.",
      autonomyMode: "assisted",
      aiAccessMode: "managed",
    });
    const latestVersion = await fetchLatestGraphVersion(request, accessToken, seed.companyId);
    const state = buildLegacyMultiPackProductModeState({
      companyId: seed.companyId,
      companyName: "Legacy Eyewear",
      graphVersion: latestVersion,
      pendingApprovalCount: 0,
      operations: [
        {
          id: "53333333-3333-4333-8333-333333333333",
          status: "succeeded",
          startedAt: "2026-05-10T10:00:00.000Z",
          endedAt: "2026-05-10T10:05:00.000Z",
          operationBrief: "Exercise P1 Atlas controls through generic routes.",
          deliverable: "Deliverable: P1 connector, whiteboard, phase, and performance controls.",
          llmMode: "managed",
        },
      ],
    });
    const whiteboard = state.whiteboards?.[0];
    const phase = whiteboard?.phase_contracts?.[0];
    expect(whiteboard).toBeTruthy();
    expect(phase).toBeTruthy();
    if (!whiteboard || !phase) {
      throw new Error("P1 control regression fixture did not create a whiteboard phase.");
    }
    const phaseId = "legacy-eyewear.p1-ui-phase";
    phase.phase_id = phaseId;
    phase.phase_name = "P1 UI Phase";
    phase.workstreams = [
      {
        id: "strategy_brief",
        name: "Strategy Brief",
        status: "queued",
        required: true,
        output_type: "artifact",
        department_id: "strategy",
        department_name: "Strategy",
        reason: "Complete the primary strategy brief.",
        created_at: "2026-05-12T12:12:00.000Z",
        updated_at: "2026-05-12T12:12:00.000Z",
      },
    ];
    phase.gate = {
      gate_id: "legacy-eyewear.p1-ui-gate",
      criteria: [
        { key: "readiness", value_type: "number", operator: ">=", threshold: 80 },
        { key: "legal_precheck", value_type: "enum", operator: "in", expected: ["pass"] },
      ],
      approval_required: true,
    };
    phase.current_state = {
      status: "started",
      all_workstreams_completed: false,
      synthesis: null,
      gate: null,
      applied_actions: {},
    };
    phase.allowed_actions = [];
    whiteboard.status = "in_content";
    whiteboard.work_status = "planning";
    if (whiteboard.performance_contract) {
      whiteboard.performance_contract.allowed_actions = ["report"];
      whiteboard.performance_contract.current_state.report_run_id = "";
      whiteboard.performance_contract.current_state.evaluation_id = "";
    }

    await installProductModeMocks(page, state);
    await openBackendAuthenticatedPage(page, request, user, "/companies");
    await page
      .getByRole("link", { name: /Legacy Eyewear/i })
      .first()
      .click();
    await page.waitForURL(new RegExp(`/companies/${seed.companyId}$`));

    await page.getByTestId("connector-management-panel").scrollIntoViewIfNeeded();
    await expect(page.getByTestId("connector-management-panel")).toBeVisible();
    await expect(page.getByTestId("connector-toggle-email_connector")).toBeChecked();
    await page.getByTestId("connector-sandbox-core-preset").click();
    await expect(page.getByTestId("connector-toggle-social_connector")).toBeChecked();
    await expect(page.getByTestId("connector-toggle-analytics_connector")).toBeChecked();
    await expect(page.getByTestId("connector-toggle-whatsapp_connector")).not.toBeChecked();
    await page.getByTestId("connector-save-button").click();
    expect(state.installedPacks[0]?.config).not.toHaveProperty("workstream_phases");
    expect(state.installedPacks[0]?.config).not.toHaveProperty("deployment_policies");
    expect(state.installedPacks[0]?.config.available_connectors).toEqual(
      expect.arrayContaining(["email_connector", "social_connector", "analytics_connector"]),
    );

    await page.getByTestId("whiteboard-panel").scrollIntoViewIfNeeded();
    await page.getByTestId("whiteboard-context-edit-toggle").click();
    await page.getByTestId("whiteboard-context-objective").fill("Updated from P1 context editor.");
    await page
      .getByTestId("whiteboard-context-constraints")
      .fill(
        JSON.stringify({ legal_compliance_constraints: "No unsupported claims.", visual_constraints: "Product only." }),
      );
    await page.getByTestId("whiteboard-context-stakeholders").fill(JSON.stringify({ approval_owner: "Legacy owner" }));
    await page
      .getByTestId("whiteboard-context-resources")
      .fill(JSON.stringify({ scope: "Campaign strategy", success_metrics: ["qualified intent"] }));
    await page
      .getByTestId("whiteboard-context-delivery")
      .fill(JSON.stringify({ requested_channels: ["email"], connector_readiness: "sandbox" }));
    await page.getByTestId("whiteboard-context-save-button").click();
    await expect(page.getByTestId("whiteboard-known-fields")).toContainText(/Updated from P1 context editor/i);

    await page.getByTestId(`whiteboard-phase-workstream-strategy_brief-summary`).fill("Strategy brief complete.");
    await page
      .getByTestId(`whiteboard-phase-workstream-strategy_brief-context`)
      .fill(JSON.stringify({ channel: "email", source: "p1-regression" }));
    await page.getByTestId(`whiteboard-phase-workstream-strategy_brief-complete`).click();
    await expect(page.getByTestId(`whiteboard-phase-workstream-strategy_brief`)).toContainText(/Completed/i);

    await page.getByTestId(`whiteboard-phase-synthesize-${phaseId}`).click();
    await expect(page.getByTestId("whiteboard-phase-gate")).toContainText(/Captured/i);
    await page.getByTestId(`whiteboard-phase-evaluate-${phaseId}`).click();
    await expect(page.getByTestId("whiteboard-phase-gate")).toContainText(/Pass/i);
    await expect(page.getByTestId("whiteboard-phase-approval")).toContainText(/Queued/i);

    await page.getByTestId("whiteboard-performance-section").scrollIntoViewIfNeeded();
    await page.getByTestId("whiteboard-performance-report-button").click();
    await expect(page.getByTestId("whiteboard-performance-report")).toContainText(/mock-performance-report-run/i);
    await page.getByTestId("whiteboard-performance-evaluate-button").click();
    await expect(page.getByTestId("whiteboard-performance-evaluation")).toContainText(/mock-performance-evaluation/i);

    expect(
      sawProductModeApiPath(
        apiRequests,
        `/api/companies/${seed.companyId}/packs/${legacyMultiPackIds.primary}.installation`,
      ),
    ).toBe(true);
    expect(sawProductModeApiPath(apiRequests, `/api/whiteboards/${legacyMultiPackIds.whiteboard}`)).toBe(true);
    expect(
      sawProductModeApiPath(
        apiRequests,
        `/api/whiteboards/${legacyMultiPackIds.whiteboard}/phases/${phaseId}/workstreams/strategy_brief/complete`,
      ),
    ).toBe(true);
    expect(
      sawProductModeApiPath(
        apiRequests,
        `/api/whiteboards/${legacyMultiPackIds.whiteboard}/phases/${phaseId}/synthesize`,
      ),
    ).toBe(true);
    expect(
      sawProductModeApiPath(
        apiRequests,
        `/api/whiteboards/${legacyMultiPackIds.whiteboard}/phases/${phaseId}/evaluate`,
      ),
    ).toBe(true);
    expect(
      sawProductModeApiPath(apiRequests, `/api/whiteboards/${legacyMultiPackIds.whiteboard}/performance/report`),
    ).toBe(true);
    expect(
      sawProductModeApiPath(apiRequests, `/api/whiteboards/${legacyMultiPackIds.whiteboard}/performance/evaluate`),
    ).toBe(true);
    expect(verticalProductModeApiRequests(apiRequests, forbiddenVerticalMarketingRoutePattern)).toEqual([]);
  });

  test("mocked ATLAS Legacy consult communication keeps internal notes scoped", async ({
    browser,
    request,
  }, testInfo) => {
    test.setTimeout(90_000);

    const legacyOwner = createTestUser(testInfo, "legacy-communication");
    const atlasOperator = createTestUser(testInfo, "atlas-communication");
    const otherClientUser = createTestUser(testInfo, "other-client-communication");
    await Promise.all([
      ensureUserRegistered(request, legacyOwner),
      ensureUserRegistered(request, atlasOperator),
      ensureUserRegistered(request, otherClientUser),
    ]);
    const atlasAccessToken = await getAccessToken(request, atlasOperator);
    const seed = await createCompanyViaApi(request, atlasAccessToken, {
      name: "Legacy Eyewear",
      companyType: "Eyewear Company",
      objective: "Exercise generic communication routes for an ATLAS consult.",
      autonomyMode: "assisted",
      aiAccessMode: "managed",
    });
    const latestVersion = await fetchLatestGraphVersion(request, atlasAccessToken, seed.companyId);
    const state = buildLegacyMultiPackProductModeState({
      companyId: seed.companyId,
      companyName: "Legacy Eyewear",
      graphVersion: latestVersion,
      pendingApprovalCount: 0,
      operations: [
        {
          id: "53333333-3333-4333-8333-333333333333",
          status: "succeeded",
          startedAt: "2026-05-10T10:00:00.000Z",
          endedAt: "2026-05-10T10:05:00.000Z",
          operationBrief: "Prepare the Legacy Eyewear consult communication readout.",
          deliverable: "Deliverable: generic communication thread, messages, signal attachment, and visibility.",
          llmMode: "managed",
        },
      ],
    });
    const thread = state.communicationThreads?.[0];
    expect(thread).toBeTruthy();
    const operatorThread = { ...thread!, can_send_internal: true };
    const operatorMessages: NonNullable<typeof state.communicationMessages>[string] = [
      ...(state.communicationMessages?.[thread!.id] ?? []),
      {
        id: "atlas-internal-missing-capability-note",
        thread_id: thread!.id,
        organization_id: thread!.organization_id,
        company_id: seed.companyId,
        sender_kind: "system",
        sender_user_id: null,
        sender_agent_id: null,
        sender_company_id: null,
        sender_organization_id: thread!.organization_id,
        message_kind: "agent_observation",
        body: "Execution remains blocked until WhatsApp provider is configured. Keep missing-capability recommendation open.",
        body_format: "markdown",
        visibility: "internal",
        redacted: false,
        redacted_at: null,
        metadata: {},
        attachments: [
          {
            id: "missing-capability-attachment",
            message_id: "atlas-internal-missing-capability-note",
            type: "company_signal",
            target_id: legacyMultiPackIds.signal,
            metadata: {},
            created_at: "2026-05-12T12:04:00.000Z",
          },
        ],
        created_at: "2026-05-12T12:04:00.000Z",
        updated_at: "2026-05-12T12:04:00.000Z",
      },
    ];

    const operatorState: typeof state = {
      ...state,
      communicationThreads: [operatorThread],
      communicationMessages: { [thread!.id]: operatorMessages },
    };

    const allApiRequests: string[] = [];

    const legacyContext = await browser.newContext();
    const legacyPage = await legacyContext.newPage();
    const legacyRequests = collectProductModeApiRequests(legacyPage);
    try {
      await installProductModeMocks(legacyPage, state);
      await openBackendAuthenticatedPage(legacyPage, request, legacyOwner, "/companies");
      await legacyPage
        .getByRole("link", { name: /Legacy Eyewear/i })
        .first()
        .click();
      await legacyPage.waitForURL(new RegExp(`/companies/${seed.companyId}$`));
      await legacyPage.getByTestId("communication-panel").scrollIntoViewIfNeeded();

      await expect(legacyPage.getByText(/Can you explain why WhatsApp is recommended/i)).toBeVisible();
      await expect(legacyPage.getByText(/manual first step/i)).toBeVisible();
      await expect(
        legacyPage.getByText(/Execution remains blocked until WhatsApp provider is configured/i),
      ).toHaveCount(0);
      await expect(legacyPage.getByTestId("communication-internal-badge")).toHaveCount(0);
    } finally {
      allApiRequests.push(...legacyRequests);
      await legacyContext.close();
    }

    const atlasContext = await browser.newContext();
    const atlasPage = await atlasContext.newPage();
    const atlasRequests = collectProductModeApiRequests(atlasPage);
    try {
      await installProductModeMocks(atlasPage, operatorState);
      await openBackendAuthenticatedPage(atlasPage, request, atlasOperator, "/companies");
      await atlasPage
        .getByRole("link", { name: /Legacy Eyewear/i })
        .first()
        .click();
      await atlasPage.waitForURL(new RegExp(`/companies/${seed.companyId}$`));
      await atlasPage.getByTestId("communication-panel").scrollIntoViewIfNeeded();

      await expect(atlasPage.getByText(/Can you explain why WhatsApp is recommended/i)).toBeVisible();
      await expect(atlasPage.getByText(/manual first step/i)).toBeVisible();
      await expect(
        atlasPage.getByText(/Execution remains blocked until WhatsApp provider is configured/i),
      ).toBeVisible();
      await expect(atlasPage.getByTestId("communication-internal-badge")).toBeVisible();
      await expect(
        atlasPage.getByTestId(`communication-attachment-company_signal-${legacyMultiPackIds.signal}`),
      ).toBeVisible();
    } finally {
      allApiRequests.push(...atlasRequests);
      await atlasContext.close();
    }

    const otherState = buildLegacyMultiPackProductModeState({
      companyId: "other-client-company",
      companyName: "Other Client",
      graphVersion: latestVersion,
      pendingApprovalCount: 0,
      operations: [],
    });
    const otherContext = await browser.newContext();
    const otherPage = await otherContext.newPage();
    const otherRequests = collectProductModeApiRequests(otherPage);
    try {
      await installProductModeMocks(otherPage, {
        ...otherState,
        communicationThreads: [],
        communicationMessages: {},
      });
      await openBackendAuthenticatedPage(otherPage, request, otherClientUser, "/companies");

      const legacyThreadsForOtherClient = await otherPage.evaluate(async (legacyCompanyId) => {
        const response = await fetch(`/api/communication/threads?company_id=${legacyCompanyId}`);
        const body = await response.json().catch(() => null);
        return { status: response.status, body };
      }, seed.companyId);
      expect([200, 403, 404]).toContain(legacyThreadsForOtherClient.status);
      if (legacyThreadsForOtherClient.status === 200) {
        expect(legacyThreadsForOtherClient.body.data.threads).toEqual([]);
      }

      const legacyMessagesForOtherClient = await otherPage.evaluate(async (threadId) => {
        const response = await fetch(`/api/communication/threads/${threadId}/messages`);
        const body = await response.json().catch(() => null);
        return { status: response.status, body };
      }, thread!.id);
      expect([200, 403, 404]).toContain(legacyMessagesForOtherClient.status);
      if (legacyMessagesForOtherClient.status === 200) {
        expect(legacyMessagesForOtherClient.body.data.messages).toEqual([]);
      }
    } finally {
      allApiRequests.push(...otherRequests);
      await otherContext.close();
    }

    expect(sawCompanyScopedProductModeQuery(allApiRequests, "/api/communication/threads", seed.companyId)).toBe(true);
    expect(verticalProductModeApiRequests(allApiRequests, forbiddenVerticalMarketingRoutePattern)).toEqual([]);
  });
});
