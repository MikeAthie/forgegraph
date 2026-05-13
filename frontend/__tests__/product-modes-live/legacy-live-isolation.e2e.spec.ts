import { expect, test, type APIRequestContext, type Page } from "@playwright/test";

import { apiBaseUrl, loginLive } from "../e2e/live-helpers";
import {
  collectLiveProductModeApiRequests,
  forbiddenLegacyFunctionCompanies,
  liveLegacyCompanyName,
  liveLlmSkipReason,
  liveProductModeRunNamespace,
  sawLiveApiPath,
  sawLiveCompanyScopedQuery,
  seedLiveLegacyIsolationProductMode,
  verticalLiveProductModeApiRequests,
  type LiveLegacyIsolationFixture,
  type LiveProductModeApiRequest,
} from "./fixtures.live";

const API_BASE_URL = apiBaseUrl();
const liveSkipReason = liveLlmSkipReason();
const legacyCompanyCardName = /^Legacy Eyewear\b/i;

test.describe("Live product-mode isolation", () => {
  test.skip(Boolean(liveSkipReason), liveSkipReason ?? "Live product-mode isolation suite is disabled.");

  test("Legacy live state stays isolated across operator, customer, and unrelated client", async ({
    browser,
    page,
    request,
  }, testInfo) => {
    test.setTimeout(180_000);

    const fixture = await seedLiveLegacyIsolationProductMode(request, testInfo);
    console.info(
      [
        `Live product-mode isolation namespace=${liveProductModeRunNamespace(testInfo)}`,
        `companyId=${fixture.companyId}`,
        `organizationId=${fixture.organizationId}`,
        `otherClientCompanyId=${fixture.otherClientCompanyId}`,
      ].join(" "),
    );
    const reportArtifact = fixture.report.reportRun.artifact;
    expect(reportArtifact).toBeTruthy();
    if (!reportArtifact) {
      throw new Error("Live isolation fixture did not create a generic report artifact.");
    }

    const operatorRequests = collectLiveProductModeApiRequests(page);
    await loginLive(page, request, fixture.atlasOperator, "/companies");

    // This live isolation test protects the generic boundary:
    // Organization -> Company -> PackInstallation -> generic primitives.
    const legacyCompanyLink = page.getByRole("link", { name: legacyCompanyCardName });
    await expect(legacyCompanyLink).toHaveCount(1);
    await expectNoFunctionCompanies(page);

    await legacyCompanyLink.first().click();
    await page.waitForURL(new RegExp(`/companies/${fixture.companyId}$`));
    await expect(page.getByRole("heading", { name: liveLegacyCompanyName, level: 2 })).toBeVisible();
    await expect(page.getByTestId("command-ops-panel")).toBeVisible();
    await expect(page.getByTestId("commerce-inventory-panel")).toBeVisible();
    await expect(page.getByTestId(`artifact-card-${reportArtifact.id}`)).toContainText(reportArtifact.title);
    await expect(page.getByTestId("service-history-panel")).toBeVisible();
    await expect(page.getByTestId("installed-pack-role").filter({ hasText: /^primary$/i })).toHaveCount(1);
    await expect(page.getByTestId("installed-pack-role").filter({ hasText: /^addon$/i })).toHaveCount(
      fixture.installedPacks.filter((pack) => pack.role === "addon").length,
    );

    const customerContext = await browser.newContext();
    const customerPage = await customerContext.newPage();
    const customerRequests = collectLiveProductModeApiRequests(customerPage);
    try {
      await openLiveTokenSession(customerPage, request, fixture.legacyCustomerAccessToken, "/companies");
      await expect(customerPage.getByRole("link", { name: legacyCompanyCardName })).toHaveCount(1);
      await expectNoFunctionCompanies(customerPage);

      await customerPage.goto(`/companies/${fixture.companyId}`);
      await expect(customerPage.getByRole("heading", { name: liveLegacyCompanyName, level: 2 })).toBeVisible();
      await expect(customerPage.getByTestId(`artifact-card-${reportArtifact.id}`)).toContainText(reportArtifact.title);
      await expect(customerPage.getByTestId("service-history-panel")).toBeVisible();
      await expect(customerPage.getByText(/manifest/i)).toHaveCount(0);
      await expect(customerPage.getByText(/private config/i)).toHaveCount(0);
      await expectCustomerMutationsDenied(request, fixture);
    } finally {
      await customerContext.close();
    }

    const otherClientContext = await browser.newContext();
    const otherClientPage = await otherClientContext.newPage();
    const otherClientRequests = collectLiveProductModeApiRequests(otherClientPage);
    try {
      await openLiveTokenSession(otherClientPage, request, fixture.otherClientAccessToken, "/companies");
      await expect(
        otherClientPage.getByRole("link", { name: new RegExp(fixture.otherClientCompanyName, "i") }),
      ).toHaveCount(1);
      await expect(otherClientPage.getByRole("link", { name: legacyCompanyCardName })).toHaveCount(0);
      await expectNoFunctionCompanies(otherClientPage);
      await expectOtherClientCannotReadLegacy(request, fixture);
    } finally {
      await otherClientContext.close();
    }

    const apiRequests = [...operatorRequests, ...customerRequests, ...otherClientRequests];
    expect(verticalLiveProductModeApiRequests(apiRequests)).toEqual([]);
    expectOnlyGenericLiveRoutes(apiRequests);
    expect(sawLiveApiPath(apiRequests, "/api/graphs/")).toBe(true);
    expect(sawLiveApiPath(apiRequests, `/api/graphs/${fixture.companyId}`)).toBe(true);
    expect(sawLiveApiPath(apiRequests, `/api/companies/${fixture.companyId}/operating-model`)).toBe(true);
    expect(sawLiveApiPath(apiRequests, `/api/companies/${fixture.companyId}/packs`)).toBe(true);
    expect(sawLiveCompanyScopedQuery(apiRequests, "/api/work-artifacts", fixture.companyId)).toBe(true);
    expect(sawLiveCompanyScopedQuery(apiRequests, "/api/report-runs", fixture.companyId)).toBe(true);
    expect(sawLiveCompanyScopedQuery(apiRequests, "/api/state-projections", fixture.companyId)).toBe(true);
  });
});

async function expectNoFunctionCompanies(page: Page) {
  for (const separatedCompany of forbiddenLegacyFunctionCompanies) {
    await expect(page.getByRole("link", { name: new RegExp(`^${separatedCompany}\\b`, "i") })).toHaveCount(0);
    await expect(page.getByText(separatedCompany, { exact: true })).toHaveCount(0);
  }
}

async function expectCustomerMutationsDenied(
  request: APIRequestContext,
  fixture: LiveLegacyIsolationFixture,
): Promise<void> {
  const deniedResponses = await Promise.all([
    request.post(`${API_BASE_URL}/api/companies/${fixture.companyId}/packs/install`, {
      headers: authHeaders(fixture.legacyCustomerAccessToken, `${fixture.companyId}:customer-pack-install-denied`),
      data: {
        pack_id: fixture.installedPacks[0]?.pack_id ?? "digital_marketing_pro.v1",
        role: "addon",
        config: {},
      },
    }),
    request.post(`${API_BASE_URL}/api/companies/${fixture.companyId}/programs`, {
      headers: authHeaders(fixture.legacyCustomerAccessToken, `${fixture.companyId}:customer-program-create-denied`),
      data: {
        template_id: "dmp.engagement",
        pack_id: fixture.installedPacks[0]?.pack_id ?? "digital_marketing_pro.v1",
        title: "Denied customer program mutation",
        objective: "This mutation should stay operator-only.",
      },
    }),
    request.post(`${API_BASE_URL}/api/periodic-reviews/${fixture.report.review.id}/run`, {
      headers: authHeaders(fixture.legacyCustomerAccessToken, `${fixture.companyId}:customer-review-run-denied`),
      data: {
        metric_snapshot_id: fixture.report.metricSnapshot.id,
        force: true,
        notes: "This mutation should stay operator-only.",
      },
    }),
  ]);

  for (const response of deniedResponses) {
    expect([403, 404]).toContain(response.status());
  }
}

async function expectOtherClientCannotReadLegacy(
  request: APIRequestContext,
  fixture: LiveLegacyIsolationFixture,
): Promise<void> {
  const deniedResponses = await Promise.all([
    request.get(`${API_BASE_URL}/api/graphs/${fixture.companyId}`, {
      headers: authHeaders(fixture.otherClientAccessToken),
    }),
    request.get(`${API_BASE_URL}/api/work-artifacts`, {
      headers: authHeaders(fixture.otherClientAccessToken),
      params: { company_id: fixture.companyId },
    }),
    request.get(`${API_BASE_URL}/api/report-runs`, {
      headers: authHeaders(fixture.otherClientAccessToken),
      params: { company_id: fixture.companyId },
    }),
    request.get(`${API_BASE_URL}/api/state-projections`, {
      headers: authHeaders(fixture.otherClientAccessToken),
      params: {
        company_id: fixture.companyId,
        projection_type: "client_service_history",
      },
    }),
  ]);

  for (const response of deniedResponses) {
    expect(response.status()).toBe(404);
  }
}

function expectOnlyGenericLiveRoutes(apiRequests: LiveProductModeApiRequest[]): void {
  const disallowed = apiRequests.filter((request) =>
    /\/api\/(?:marketing|growth-marketing|digital-marketing|marketing-campaigns)(?:\/|$)/i.test(request.pathname),
  );
  expect(disallowed).toEqual([]);
}

async function openLiveTokenSession(
  page: Page,
  request: APIRequestContext,
  accessToken: string,
  targetPath: string,
): Promise<void> {
  await page.context().clearCookies();
  await page.route(/.*\/api\/.*/, async (route) => {
    const requestUrl = new URL(route.request().url());
    const backendUrl = `${API_BASE_URL}${requestUrl.pathname}${requestUrl.search}`;
    const response = await request.fetch(backendUrl, {
      method: route.request().method(),
      headers: {
        ...route.request().headers(),
        Authorization: `Bearer ${accessToken}`,
      },
      data: route.request().postDataBuffer() ?? route.request().postData() ?? undefined,
      failOnStatusCode: false,
    });

    await route.fulfill({
      status: response.status(),
      headers: response.headers(),
      body: await response.body(),
    });
  });
  await page.addInitScript((token) => {
    window.sessionStorage.setItem("__FORGEGRAPH_E2E_ACCESS_TOKEN__", token);
    (window as Window & { __FORGEGRAPH_E2E_ACCESS_TOKEN__?: string }).__FORGEGRAPH_E2E_ACCESS_TOKEN__ = token;
  }, accessToken);
  await page.goto(targetPath);
  await page.waitForLoadState("networkidle");
}

function authHeaders(accessToken: string, idempotencyKey?: string): Record<string, string> {
  return {
    Authorization: `Bearer ${accessToken}`,
    ...(idempotencyKey ? { "Idempotency-Key": idempotencyKey } : {}),
  };
}
