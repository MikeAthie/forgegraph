import { expect, test } from "@playwright/test";

import { loginLive } from "../e2e/live-helpers";
import {
  collectLiveProductModeApiRequests,
  createLiveReportFromCompletedRun,
  forbiddenLegacyFunctionCompanies,
  launchAndWaitForLiveOperationFromUi,
  LIVE_LLM_RUN_TIMEOUT_MS,
  liveBackendLaunchFallbackAllowed,
  liveLegacyCompanyName,
  liveLlmSkipReason,
  liveProductModeRunNamespace,
  sawLiveApiPath,
  sawLiveCompanyScopedQuery,
  seedLiveLegacyProductMode,
  verticalLiveProductModeApiRequests,
  withLiveLlmExecutionLock,
} from "./fixtures.live";

const liveSkipReason = liveLlmSkipReason();

test.describe("Live product modes", () => {
  test.skip(Boolean(liveSkipReason), liveSkipReason ?? "Live LLM product-mode suite is disabled.");

  test("Legacy multi-pack company can produce live generic output under one Company", async ({
    page,
    request,
  }, testInfo) => {
    test.setTimeout(LIVE_LLM_RUN_TIMEOUT_MS * 2 + 180_000);

    const apiRequests = collectLiveProductModeApiRequests(page);
    const fixture = await seedLiveLegacyProductMode(request, testInfo);
    console.info(
      `Live product-mode fixture namespace=${liveProductModeRunNamespace(testInfo)} companyId=${fixture.companyId} organizationId=${fixture.organizationId}`,
    );

    await loginLive(page, request, fixture.user, "/companies");

    // This live E2E protects the backend-owned generic boundary:
    // Organization -> Company -> PackInstallation -> generic primitives.
    const legacyCompanyLink = page.getByRole("link", { name: new RegExp(liveLegacyCompanyName, "i") });
    await expect(legacyCompanyLink).toHaveCount(1);

    for (const separatedCompany of forbiddenLegacyFunctionCompanies) {
      await expect(page.getByRole("link", { name: new RegExp(separatedCompany, "i") })).toHaveCount(0);
      await expect(page.getByText(separatedCompany, { exact: true })).toHaveCount(0);
    }

    await legacyCompanyLink.first().click();
    await page.waitForURL(new RegExp(`/companies/${fixture.companyId}$`));

    await expect(page.getByRole("heading", { name: liveLegacyCompanyName, level: 2 })).toBeVisible();
    await expect(page.getByTestId("command-ops-panel")).toBeVisible();
    await expect(page.getByTestId("commerce-inventory-panel")).toBeVisible();

    const primaryCards = page.getByTestId("installed-pack-role").filter({ hasText: /^primary$/i });
    const addOnCards = page.getByTestId("installed-pack-role").filter({ hasText: /^addon$/i });
    await expect(primaryCards).toHaveCount(1);
    await expect(addOnCards).toHaveCount(fixture.installedPacks.filter((pack) => pack.role === "addon").length);

    const { launch, completedRun, attempts: liveRunAttempts } = await withLiveLlmExecutionLock(testInfo, async () =>
      launchAndWaitForLiveOperationFromUi(page, request, fixture, testInfo),
    );
    const runId = launch.runId;
    console.info(
      [
        `Live product-mode run launchMode=${launch.mode}`,
        `fallbackAllowed=${liveBackendLaunchFallbackAllowed()}`,
        `runId=${runId}`,
        `companyId=${fixture.companyId}`,
      ].join(" "),
    );
    await testInfo.attach("live-product-mode-launch", {
      body: JSON.stringify(
        {
          launchMode: launch.mode,
          fallbackAllowed: liveBackendLaunchFallbackAllowed(),
          runId,
          companyId: fixture.companyId,
          attempts: liveRunAttempts,
        },
        null,
        2,
      ),
      contentType: "application/json",
    });

    expect(completedRun.status).toBe("succeeded");
    expect(completedRun.graph_id).toBe(fixture.companyId);
    expect(completedRun.node_runs?.filter((nodeRun) => nodeRun.status === "failed")).toEqual([]);

    const deliverable = completedRun.output_json?.deliverable;
    expect(typeof deliverable === "string" && deliverable.trim().length > 40).toBe(true);
    const runOutputText = JSON.stringify(completedRun.output_json ?? {});
    expect(runOutputText.length).toBeGreaterThan(80);
    expect(runOutputText).toContain(liveLegacyCompanyName);
    expect(runOutputText).toMatch(/NC-29026|GAGA|quiet-status|price-book/i);

    const report = await createLiveReportFromCompletedRun(request, fixture.accessToken, fixture, completedRun, testInfo);

    await page.goto(`/companies/${fixture.companyId}`);
    await page.waitForLoadState("networkidle");

    await expect(page.getByText(new RegExp(`Operation ${runId.slice(0, 8)}`, "i"))).toBeVisible({ timeout: 30_000 });
    await expect(page.getByText(/Latest deliverable preview/i).first()).toBeVisible();
    await expect(page.getByText(/NC-29026|GAGA|quiet-status|price-book/i).first()).toBeVisible();

    const reportArtifact = report.reportRun.artifact;
    expect(reportArtifact).toBeTruthy();
    if (!reportArtifact) {
      throw new Error("Live report did not create a generic WorkArtifact.");
    }
    expect(reportArtifact.company_id).toBe(fixture.companyId);
    expect(JSON.stringify(report.reportRun.generated_sections ?? reportArtifact.content ?? {}).length).toBeGreaterThan(
      40,
    );
    expect(report.serviceHistoryProjection?.company_id).toBe(fixture.companyId);

    await expect(page.getByTestId(`artifact-card-${reportArtifact.id}`)).toContainText(reportArtifact.title);
    await expect(page.getByTestId("service-history-panel")).toBeVisible();
    await expect(page.getByTestId("service-history-panel")).toContainText(/Historial|History|Report/i);

    if (report.currentStateProjection) {
      await expect(page.getByTestId(`state-projection-card-${report.currentStateProjection.id}`)).toBeVisible();
    }

    for (const separatedCompany of forbiddenLegacyFunctionCompanies) {
      await expect(page.getByRole("heading", { name: separatedCompany })).toHaveCount(0);
      await expect(page.getByRole("link", { name: separatedCompany })).toHaveCount(0);
    }

    expect(sawLiveApiPath(apiRequests, "/api/graphs/")).toBe(true);
    expect(sawLiveApiPath(apiRequests, `/api/graphs/${fixture.companyId}`)).toBe(true);
    expect(sawLiveApiPath(apiRequests, `/api/graphs/${fixture.companyId}/versions/latest`)).toBe(true);
    expect(sawLiveApiPath(apiRequests, "/api/runs/start") || launch.mode === "backend").toBe(true);
    expect(sawLiveApiPath(apiRequests, "/api/operating-model-packs")).toBe(true);
    expect(sawLiveApiPath(apiRequests, `/api/companies/${fixture.companyId}/packs`)).toBe(true);
    expect(sawLiveApiPath(apiRequests, `/api/companies/${fixture.companyId}/operating-model`)).toBe(true);
    expect(sawLiveApiPath(apiRequests, `/api/companies/${fixture.companyId}/programs`)).toBe(true);
    expect(sawLiveCompanyScopedQuery(apiRequests, "/api/work-artifacts", fixture.companyId)).toBe(true);
    expect(sawLiveCompanyScopedQuery(apiRequests, "/api/state-projections", fixture.companyId)).toBe(true);
    expect(sawLiveCompanyScopedQuery(apiRequests, "/api/periodic-reviews", fixture.companyId)).toBe(true);
    expect(sawLiveCompanyScopedQuery(apiRequests, "/api/metric-snapshots", fixture.companyId)).toBe(true);
    expect(sawLiveCompanyScopedQuery(apiRequests, "/api/report-runs", fixture.companyId)).toBe(true);
    expect(verticalLiveProductModeApiRequests(apiRequests)).toEqual([]);
  });
});
