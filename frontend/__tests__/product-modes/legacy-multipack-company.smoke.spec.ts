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

test.describe("Product modes", () => {
  test("Legacy Eyewear stays one Company with a primary pack and add-ons", async ({ page, request }, testInfo) => {
    const apiRequests = collectProductModeApiRequests(page);
    const user = createTestUser(testInfo, "product-mode-legacy");
    await ensureUserRegistered(request, user);
    const accessToken = await getAccessToken(request, user);
    const seed = await createCompanyViaApi(request, accessToken, {
      name: "Legacy Eyewear",
      companyType: "Eyewear Company",
      objective: "Operate eyewear service delivery, reporting, and add-on capabilities from one Company.",
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
          id: "51111111-1111-4111-8111-111111111111",
          status: "succeeded",
          startedAt: "2026-05-10T10:00:00.000Z",
          endedAt: "2026-05-10T10:05:00.000Z",
          operationBrief: "Prepare the Legacy Eyewear quarterly service review.",
          deliverable: "Deliverable: Legacy Eyewear report, artifact history, and next service actions.",
          llmMode: "managed",
        },
      ],
    });

    await installProductModeMocks(page, state);
    await openBackendAuthenticatedPage(page, request, user, "/companies");

    // This smoke protects the company-agnostic boundary: one backend-owned Company receives multiple
    // PackInstallations, while artifacts, reports, history, and projections stay scoped by company_id.
    const legacyCompanyLink = page.getByRole("link", { name: /Legacy Eyewear/i });
    await expect(legacyCompanyLink).toHaveCount(1);
    await expect(legacyCompanyLink.first()).toContainText(/Eyewear Company/i);

    for (const separatedCompany of ["Legacy Marketing", "Legacy Accounting", "Legacy Legal", "Legacy Consulting"]) {
      await expect(page.getByRole("link", { name: new RegExp(separatedCompany, "i") })).toHaveCount(0);
      await expect(page.getByText(separatedCompany, { exact: true })).toHaveCount(0);
    }

    await legacyCompanyLink.first().click();
    await page.waitForURL(new RegExp(`/companies/${seed.companyId}$`));

    await expect(page.getByRole("heading", { name: "Legacy Eyewear", level: 2 })).toHaveCount(1);
    await expect(page.getByText(/^eyewear company$/i)).toBeVisible();
    await expect(page.getByTestId("command-ops-panel")).toBeVisible();
    await expect(page.getByTestId("commerce-inventory-panel")).toBeVisible();

    const primaryCard = page.getByTestId(`operating-model-pack-card-${legacyMultiPackIds.primary}`);
    const accountingCard = page.getByTestId(`operating-model-pack-card-${legacyMultiPackIds.accounting}`);
    const legalCard = page.getByTestId(`operating-model-pack-card-${legacyMultiPackIds.legal}`);
    const consultingCard = page.getByTestId(`operating-model-pack-card-${legacyMultiPackIds.consulting}`);

    await expect(primaryCard).toBeVisible();
    await expect(accountingCard).toBeVisible();
    await expect(legalCard).toBeVisible();
    await expect(consultingCard).toBeVisible();
    await expect(primaryCard.getByTestId("installed-pack-role")).toContainText(/^primary$/i);
    await expect(accountingCard.getByTestId("installed-pack-role")).toContainText(/^addon$/i);
    await expect(legalCard.getByTestId("installed-pack-role")).toContainText(/^addon$/i);
    await expect(consultingCard.getByTestId("installed-pack-role")).toContainText(/^addon$/i);
    await expect(page.getByTestId("installed-pack-role").filter({ hasText: /^primary$/i })).toHaveCount(1);
    await expect(page.getByTestId("installed-pack-role").filter({ hasText: /^addon$/i })).toHaveCount(3);

    await expect(page.getByTestId(`artifact-card-${legacyMultiPackIds.artifact}`)).toContainText(
      /Legacy Eyewear service report/i,
    );
    await expect(page.getByTestId(`state-projection-card-${legacyMultiPackIds.projection}`)).toContainText(
      /Legacy Eyewear is one Company/i,
    );
    await expect(page.getByTestId("service-history-panel")).toContainText(
      /Legacy Eyewear service history keeps artifacts, reports, and projections under the same Company/i,
    );
    await expect(page.getByText(/Latest report: Legacy Eyewear quarterly report/i)).toBeVisible();

    for (const separatedCompany of ["Legacy Marketing", "Legacy Accounting", "Legacy Legal", "Legacy Consulting"]) {
      await expect(page.getByRole("heading", { name: separatedCompany })).toHaveCount(0);
      await expect(page.getByRole("link", { name: separatedCompany })).toHaveCount(0);
    }

    expect(sawProductModeApiPath(apiRequests, `/api/companies/${seed.companyId}/operating-model`)).toBe(true);
    expect(sawProductModeApiPath(apiRequests, `/api/companies/${seed.companyId}/programs`)).toBe(true);
    expect(sawCompanyScopedProductModeQuery(apiRequests, "/api/work-artifacts", seed.companyId)).toBe(true);
    expect(sawCompanyScopedProductModeQuery(apiRequests, "/api/state-projections", seed.companyId)).toBe(true);
    expect(sawCompanyScopedProductModeQuery(apiRequests, "/api/metric-snapshots", seed.companyId)).toBe(true);
    expect(sawCompanyScopedProductModeQuery(apiRequests, "/api/report-runs", seed.companyId)).toBe(true);
    expect(verticalProductModeApiRequests(apiRequests)).toEqual([]);
  });
});
