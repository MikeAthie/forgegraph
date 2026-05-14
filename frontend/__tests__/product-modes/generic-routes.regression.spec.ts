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
  /\/api\/(?:marketing|growth-marketing|digital-marketing|marketing-campaigns)(?:\/|$)/i;

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
    await page.getByTestId("commerce-inventory-panel").scrollIntoViewIfNeeded();
    await expect(page.getByTestId("commerce-inventory-panel")).toBeVisible();

    await expect(page.locator('[data-testid*="marketing" i]')).toHaveCount(0);

    expect(sawProductModeApiPath(apiRequests, "/api/graphs/")).toBe(true);
    expect(sawProductModeApiPath(apiRequests, "/api/portfolio-health")).toBe(true);
    expect(sawProductModeApiPath(apiRequests, "/api/cross-company-queues")).toBe(true);
    expect(sawProductModeApiPath(apiRequests, `/api/graphs/${seed.companyId}`)).toBe(true);
    expect(sawProductModeApiPath(apiRequests, `/api/graphs/${seed.companyId}/versions/latest`)).toBe(true);
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
    expect(sawStateProjectionType(apiRequests, seed.companyId, "client_service_history")).toBe(true);
    expect(verticalProductModeApiRequests(apiRequests, forbiddenVerticalMarketingRoutePattern)).toEqual([]);
  });

  test("mocked ATLAS Legacy consult communication keeps internal notes scoped", async ({ browser, request }, testInfo) => {
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
      await legacyPage.getByRole("link", { name: /Legacy Eyewear/i }).first().click();
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
      await atlasPage.getByRole("link", { name: /Legacy Eyewear/i }).first().click();
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
