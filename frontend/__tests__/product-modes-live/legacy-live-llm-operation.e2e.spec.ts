import { expect, test, type APIRequestContext, type Page, type TestInfo } from "@playwright/test";

import { loginLive, startRunViaApi } from "../e2e/live-helpers";
import {
  collectLiveProductModeApiRequests,
  createLiveReportFromCompletedRun,
  forbiddenLegacyFunctionCompanies,
  legacyLiveOperationBrief,
  liveLegacyCompanyName,
  liveLlmSkipReason,
  liveProductModeRunNamespace,
  sawLiveApiPath,
  sawLiveCompanyScopedQuery,
  seedLiveLegacyProductMode,
  type LiveLegacyProductModeFixture,
  verticalLiveProductModeApiRequests,
  waitForLiveRunTerminal,
} from "./fixtures.live";

const liveSkipReason = liveLlmSkipReason();
type LiveLaunchResult = { runId: string; mode: "ui" | "backend" };

test.describe("Live product modes", () => {
  test.skip(Boolean(liveSkipReason), liveSkipReason ?? "Live LLM product-mode suite is disabled.");

  test("Legacy multi-pack company can produce live generic output under one Company", async ({
    page,
    request,
  }, testInfo) => {
    test.setTimeout(240_000);

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

    const launch = await launchLiveOperationFromUi(page, request, fixture, testInfo);
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
        },
        null,
        2,
      ),
      contentType: "application/json",
    });

    const completedRun = await waitForLiveRunTerminal(request, fixture.accessToken, runId);
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

async function launchLiveOperationFromUi(
  page: Page,
  request: APIRequestContext,
  fixture: LiveLegacyProductModeFixture,
  testInfo: TestInfo,
): Promise<LiveLaunchResult> {
  let lastFailure = "";
  for (let attempt = 0; attempt < 3; attempt += 1) {
    try {
      const runStartResponsePromise = page.waitForResponse(
        (response) => response.request().method() === "POST" && response.url().includes("/api/runs/start"),
        { timeout: 30_000 },
      );
      await page.getByTestId("company-launch-operation-input").fill(legacyLiveOperationBrief());
      await page.getByTestId("company-launch-operation-button").click();
      const runStartResponse = await runStartResponsePromise;
      if (runStartResponse.ok()) {
        const runStartBody = (await runStartResponse.json()) as { data: { id: string } };
        return { runId: runStartBody.data.id, mode: "ui" };
      }

      lastFailure = `${runStartResponse.status()} ${runStartResponse.statusText()}: ${await runStartResponse.text()}`;
      if (runStartResponse.status() < 500) {
        break;
      }
    } catch (error) {
      lastFailure = error instanceof Error ? error.message : String(error);
    }

    await page.waitForTimeout(1_500 * (attempt + 1));
    await page.reload({ waitUntil: "networkidle" }).catch(() => undefined);
  }

  if (!liveBackendLaunchFallbackAllowed()) {
    throw new Error(
      [
        `UI launch failed with ${lastFailure}.`,
        "The live LLM spec requires UI launch by default.",
        "Set LIVE_LLM_ALLOW_BACKEND_FALLBACK=true to allow backend-created operation plus UI verification.",
      ].join(" "),
    );
  }

  console.info(`Live product-mode UI launch failed; using explicit backend fallback. Last failure: ${lastFailure}`);
  testInfo.annotations.push({
    type: "live-launch-mode",
    description: "backend-fallback",
  });

  try {
    const fallback = await startRunViaApi(request, fixture.accessToken, {
      versionId: fixture.versionId,
      inputJson: {
        company_name: liveLegacyCompanyName,
        operation_brief: legacyLiveOperationBrief(),
      },
    });
    return { runId: fallback.runId, mode: "backend" };
  } catch (error) {
    const fallbackFailure = error instanceof Error ? error.message : String(error);
    throw new Error(`UI launch failed with ${lastFailure}; backend fallback failed with ${fallbackFailure}`);
  }
}

function liveBackendLaunchFallbackAllowed(): boolean {
  return (process.env.LIVE_LLM_ALLOW_BACKEND_FALLBACK ?? "").toLowerCase() === "true";
}
