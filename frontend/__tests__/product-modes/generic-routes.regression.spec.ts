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
    expect(sawStateProjectionType(apiRequests, seed.companyId, "client_service_history")).toBe(true);
    expect(verticalProductModeApiRequests(apiRequests, forbiddenVerticalMarketingRoutePattern)).toEqual([]);
  });
});
