import { expect, test, type APIRequestContext, type Page, type TestInfo } from "@playwright/test";

import { apiBaseUrl, loginLive } from "../e2e/live-helpers";
import {
  atlasLegacyConsultOperationBrief,
  buildMeasurementReadinessEvidence,
  collectLiveProductModeApiRequests,
  createAtlasLegacyBoundaryMemo,
  createAtlasLegacyCommercialReadinessMemo,
  createAtlasLegacyConnectorReadinessMatrix,
  createAtlasLegacyConsultReviewBoardSignal,
  createAtlasLegacyMeasurementPlanArtifact,
  createLiveReportFromCompletedRun,
  executeAtlasLegacyAnalyticsTool,
  executeAtlasLegacyApprovalRouterTool,
  executeAtlasLegacyEmailSandboxTool,
  executeAtlasLegacyReportBuilderTool,
  forbiddenLegacyFunctionCompanies,
  launchAndWaitForLiveOperationFromUi,
  LIVE_LLM_RUN_TIMEOUT_MS,
  liveBackendLaunchFallbackAllowed,
  liveLegacyCompanyName,
  liveLlmJudgeEnabled,
  liveLlmSkipReason,
  liveProductModeRunNamespace,
  materializeAtlasLegacyConsultOutputs,
  runAtlasLegacyConsultQualityJudge,
  sawLiveApiPath,
  sawLiveCompanyScopedQuery,
  seedLiveAtlasLegacyConsultProductMode,
  verticalLiveProductModeApiRequests,
  withLiveLlmExecutionLock,
  type AtlasLegacyConsultQualityScorecard,
  type LiveAtlasLegacyConsultFixture,
  type LiveProductModeApiRequest,
} from "./fixtures.live";

const API_BASE_URL = apiBaseUrl();
const liveSkipReason = liveLlmSkipReason();
const legacyCompanyCardName = /^Legacy Eyewear\b/i;

test.use({ video: "on" });

test.describe("Live ATLAS Legacy consulting product mode", () => {
  test.skip(Boolean(liveSkipReason), liveSkipReason ?? "Live LLM ATLAS Legacy consult suite is disabled.");

  test("ATLAS can deliver a real LLM-backed generic consult output to Legacy Eyewear", async ({
    page,
    request,
  }, testInfo) => {
    test.setTimeout(LIVE_LLM_RUN_TIMEOUT_MS * 2 + 360_000);

    const apiRequests = collectLiveProductModeApiRequests(page);
    const fixture = await seedLiveAtlasLegacyConsultProductMode(request, testInfo);
    console.info(
      [
        `ATLAS Legacy consult namespace=${liveProductModeRunNamespace(testInfo)}`,
        `operationCreationMode=${fixture.operationCreationMode}`,
        `companyId=${fixture.companyId}`,
        `otherClientCompanyId=${fixture.otherClientCompanyId}`,
      ].join(" "),
    );

    await testInfo.attach("atlas-legacy-consult-fixture", {
      body: JSON.stringify(
        {
          operationCreationMode: fixture.operationCreationMode,
          serviceCatalogItemId: fixture.serviceCatalogItem.id,
          serviceEngagementId: fixture.serviceEngagement.id,
          companyId: fixture.companyId,
          otherClientCompanyId: fixture.otherClientCompanyId,
        },
        null,
        2,
      ),
      contentType: "application/json",
    });

    await loginLive(page, request, fixture.legacyOwner, "/companies");

    // This acceptance test protects the generic boundary:
    // Organization -> Company -> PackInstallation -> generic primitives.
    await expect(page.getByRole("link", { name: legacyCompanyCardName })).toHaveCount(1);
    await expectNoFunctionCompanies(page);
    await page.getByRole("link", { name: legacyCompanyCardName }).first().click();
    await page.waitForURL(new RegExp(`/companies/${fixture.companyId}$`));
    await expect(page.getByRole("heading", { name: liveLegacyCompanyName, level: 2 })).toBeVisible();
    await expect(page.getByTestId("command-ops-panel")).toBeVisible();
    await expect(page.getByTestId("commerce-inventory-panel")).toBeVisible();
    await expect(page.getByTestId(`artifact-card-${fixture.contextArtifact.id}`)).toContainText(
      "Legacy Eyewear shared company context",
    );

    await loginLive(page, request, fixture.atlasOperator, `/companies/${fixture.companyId}`);
    await expect(page.getByRole("heading", { name: liveLegacyCompanyName, level: 2 })).toBeVisible();
    await expect(page.getByTestId("installed-pack-role").filter({ hasText: /^primary$/i })).toHaveCount(1);
    await expect(page.getByTestId("installed-pack-role").filter({ hasText: /^addon$/i })).toHaveCount(
      fixture.installedPacks.filter((pack) => pack.role === "addon").length,
    );

    const {
      launch,
      completedRun,
      attempts: liveRunAttempts,
    } = await withLiveLlmExecutionLock(testInfo, async () => {
      const launchRun = await launchAndWaitForLiveOperationFromUi(
        page,
        request,
        fixture,
        testInfo,
        atlasLegacyConsultOperationBrief(),
      );
      return launchRun;
    });
    console.info(
      [
        `ATLAS Legacy consult launchMode=${launch.mode}`,
        `fallbackAllowed=${liveBackendLaunchFallbackAllowed()}`,
        `runId=${launch.runId}`,
      ].join(" "),
    );
    await testInfo.attach("atlas-legacy-consult-launch", {
      body: JSON.stringify(
        {
          operationCreationMode: fixture.operationCreationMode,
          launchMode: launch.mode,
          fallbackAllowed: liveBackendLaunchFallbackAllowed(),
          runId: launch.runId,
          attempts: liveRunAttempts,
        },
        null,
        2,
      ),
      contentType: "application/json",
    });

    if (!liveBackendLaunchFallbackAllowed()) {
      expect(launch.mode).toBe("ui");
    }
    expect(completedRun.status).toBe("succeeded");
    expect(completedRun.graph_id).toBe(fixture.companyId);
    expect(completedRun.node_runs?.filter((nodeRun) => nodeRun.status === "failed")).toEqual([]);

    const runOutputText = JSON.stringify(completedRun.output_json ?? {});
    expect(runOutputText.length).toBeGreaterThan(120);
    expect(runOutputText).toMatch(/Legacy Eyewear/i);
    expect(runOutputText).toMatch(/DEPP GOLD/i);
    expect(runOutputText).toMatch(/599\s*MXN|599/i);
    expect(runOutputText).toMatch(/inventory|stock|quantity|constraint/i);
    expect(runOutputText).toMatch(/channel|social|email|WhatsApp|landing/i);
    expect(runOutputText).toMatch(/approval|checkpoint|execute|execution|step/i);
    expect(runOutputText).toMatch(/missing|capabilit|tool|connector/i);

    const report = await createLiveReportFromCompletedRun(
      request,
      fixture.accessToken,
      fixture,
      completedRun,
      testInfo,
    );
    const reportArtifactBeforeDelivery = report.reportRun.artifact;
    expect(reportArtifactBeforeDelivery).toBeTruthy();
    if (!reportArtifactBeforeDelivery) {
      throw new Error("ATLAS Legacy consult report did not create a generic WorkArtifact before quality judging.");
    }
    const emailSandboxReceipt = await executeAtlasLegacyEmailSandboxTool(request, fixture, completedRun, testInfo);
    const reportBuilderReceipt = await executeAtlasLegacyReportBuilderTool(
      request,
      fixture,
      completedRun,
      report,
      testInfo,
    );
    const analyticsReceipt = await executeAtlasLegacyAnalyticsTool(request, fixture, completedRun, report, testInfo);
    const approvalRouterReceipt = await executeAtlasLegacyApprovalRouterTool(
      request,
      fixture,
      completedRun,
      report,
      testInfo,
    );
    const boundaryMemoArtifact = await createAtlasLegacyBoundaryMemo(request, fixture, completedRun, testInfo);
    const measurementReadiness = buildMeasurementReadinessEvidence(report.metricSnapshot.id);
    const connectorReadinessArtifact = await createAtlasLegacyConnectorReadinessMatrix(
      request,
      fixture,
      completedRun,
      {
        emailSandboxReceipt,
        reportBuilderReceipt,
        analyticsReceipt,
        approvalRouterReceipt,
      },
      testInfo,
    );
    const commercialReadinessArtifact = await createAtlasLegacyCommercialReadinessMemo(
      request,
      fixture,
      completedRun,
      testInfo,
    );
    const measurementPlanArtifact = await createAtlasLegacyMeasurementPlanArtifact(
      request,
      fixture,
      completedRun,
      report.metricSnapshot.id,
      testInfo,
    );

    expect(emailSandboxReceipt.company_id).toBe(fixture.companyId);
    expect(emailSandboxReceipt.operation_id).toBe(completedRun.id);
    expect(emailSandboxReceipt.tool_id).toBe("email.send_dry_run");
    expect(emailSandboxReceipt.result?.mode).toBe("dry_run");
    expect(emailSandboxReceipt.result?.evidence_mode).toBe("sandbox");
    expect(emailSandboxReceipt.result?.status).toBe("dry_run");
    expect(emailSandboxReceipt.result?.recipient_domains).toEqual(["legacy.example"]);
    expect(emailSandboxReceipt.result?.recipient_hashes?.[0]).toMatch(/^sha256:/);
    expect(JSON.stringify(emailSandboxReceipt.result)).not.toMatch(/owner@legacy\.example|Private draft body/i);
    expect(reportBuilderReceipt.company_id).toBe(fixture.companyId);
    expect(reportBuilderReceipt.operation_id).toBe(completedRun.id);
    expect(reportBuilderReceipt.tool_id).toBe("report_builder");
    expect(reportBuilderReceipt.result?.mode).toBe("dry_run");
    expect(analyticsReceipt.tool_id).toBe("analytics_connector");
    expect(analyticsReceipt.result?.mode).toBe("dry_run");
    expect(approvalRouterReceipt.tool_id).toBe("approval_router");
    expect(approvalRouterReceipt.result?.mode).toBe("dry_run");
    expect(boundaryMemoArtifact.company_id).toBe(fixture.companyId);
    expect(boundaryMemoArtifact.title).toMatch(/cross-company boundary/i);
    expect(connectorReadinessArtifact.company_id).toBe(fixture.companyId);
    expect(connectorReadinessArtifact.title).toMatch(/connector readiness/i);
    expect(commercialReadinessArtifact.company_id).toBe(fixture.companyId);
    expect(commercialReadinessArtifact.title).toMatch(/commercial readiness/i);
    expect(measurementPlanArtifact.company_id).toBe(fixture.companyId);
    expect(measurementPlanArtifact.title).toMatch(/measurement readiness/i);

    await testInfo.attach("atlas-legacy-consult-email-sandbox-receipt", {
      body: JSON.stringify(emailSandboxReceipt, null, 2),
      contentType: "application/json",
    });
    await testInfo.attach("atlas-legacy-consult-report-builder-receipt", {
      body: JSON.stringify(reportBuilderReceipt, null, 2),
      contentType: "application/json",
    });
    await testInfo.attach("atlas-legacy-consult-analytics-receipt", {
      body: JSON.stringify(analyticsReceipt, null, 2),
      contentType: "application/json",
    });
    await testInfo.attach("atlas-legacy-consult-approval-router-receipt", {
      body: JSON.stringify(approvalRouterReceipt, null, 2),
      contentType: "application/json",
    });
    await testInfo.attach("atlas-legacy-consult-boundary-memo", {
      body: JSON.stringify(boundaryMemoArtifact, null, 2),
      contentType: "application/json",
    });
    await testInfo.attach("atlas-legacy-consult-connector-readiness-matrix", {
      body: JSON.stringify(connectorReadinessArtifact, null, 2),
      contentType: "application/json",
    });
    await testInfo.attach("atlas-legacy-consult-commercial-readiness-memo", {
      body: JSON.stringify(commercialReadinessArtifact, null, 2),
      contentType: "application/json",
    });
    await testInfo.attach("atlas-legacy-consult-measurement-plan", {
      body: JSON.stringify(measurementPlanArtifact, null, 2),
      contentType: "application/json",
    });

    let judgeScorecard: AtlasLegacyConsultQualityScorecard | null = null;
    if (liveLlmJudgeEnabled()) {
      const judge = await runAtlasLegacyConsultQualityJudge(request, fixture, completedRun, report, testInfo, {
        emailSandboxReceipt,
        reportBuilderReceipt,
        analyticsReceipt,
        approvalRouterReceipt,
        boundaryMemoArtifact,
        connectorReadinessArtifact,
        commercialReadinessArtifact,
        measurementPlanArtifact,
        measurementReadiness,
      });
      console.info(
        [
          `ATLAS Legacy consult qualityJudgeAverage=${judge.scorecard.overall_average}`,
          `decision=${judge.scorecard.decision}`,
          `hardFail=${judge.scorecard.hard_fail}`,
          `evaluationId=${judge.evaluation.id}`,
        ].join(" "),
      );
      await testInfo.attach("atlas-legacy-consult-scorecard", {
        body: JSON.stringify(judge.scorecard, null, 2),
        contentType: "application/json",
      });
      await testInfo.attach("atlas-legacy-consult-evaluation", {
        body: JSON.stringify(judge.evaluation, null, 2),
        contentType: "application/json",
      });

      judgeScorecard = judge.scorecard;
      expect(judge.evaluation.company_id).toBe(fixture.companyId);
      expect(["PASS", "WARN"]).toContain(judge.evaluation.status);
      expect(judge.scorecard.schema_version).toBe("consulting_review_board_v1");
      expect(["client_ready", "revision_required"]).toContain(judge.scorecard.decision);
      expect(judge.scorecard.hard_fail).toBe(false);
      expect(judge.scorecard.overall_average).toBeGreaterThanOrEqual(1);
      expect(judge.scorecard.overall_average).toBeLessThanOrEqual(5);
      assertReviewBoardSection("ATLAS", judge.scorecard.atlas);
      assertReviewBoardSection("Legacy Eyewear", judge.scorecard.legacy);
      assertReviewBoardSection("engagement", judge.scorecard.engagement);
      assertReviewBoardImprovements(judge.scorecard);
      expect(judge.scorecard.company_improvement_plan.length).toBeGreaterThanOrEqual(1);
      expect(judge.scorecard.company_improvement_plan.some((item) => item.primitive === "CompanySignal")).toBe(true);
      expect(JSON.stringify(judge.scorecard)).toMatch(/social|email|whatsapp|landing/i);
      if (judge.scorecard.decision === "client_ready") {
        expect(judge.scorecard.approval_gate.client_deliverable_status).toBe("approved_for_review");
      } else {
        expect(judge.scorecard.approval_gate.client_deliverable_status).not.toBe("approved_for_review");
      }
    } else {
      testInfo.annotations.push({
        type: "live-quality-judge",
        description: "disabled by LIVE_LLM_JUDGE=false",
      });
    }

    const approvalAllowed =
      !judgeScorecard ||
      (judgeScorecard.decision === "client_ready" &&
        judgeScorecard.approval_gate.client_deliverable_status === "approved_for_review");
    const outputs = approvalAllowed
      ? await materializeAtlasLegacyConsultOutputs(request, fixture, completedRun, testInfo, report)
      : null;
    const revisionSignal =
      !approvalAllowed && judgeScorecard
        ? await createAtlasLegacyConsultReviewBoardSignal(request, fixture, judgeScorecard, testInfo)
        : null;
    const communicationSignalId = outputs?.missingCapabilitySignal.id ?? revisionSignal?.id ?? null;
    if (!communicationSignalId) {
      throw new Error("ATLAS Legacy communication scenario requires a generic CompanySignal.");
    }
    const communication = await validateAtlasLegacyCommunicationScenario(
      request,
      fixture,
      communicationSignalId,
      testInfo,
    );

    const reportArtifact = report.reportRun.artifact;
    expect(reportArtifact).toBeTruthy();
    if (!reportArtifact) {
      throw new Error("ATLAS Legacy consult report did not create a generic WorkArtifact.");
    }
    expect(reportArtifact.company_id).toBe(fixture.companyId);
    expect(report.reportRun.company_id).toBe(fixture.companyId);
    if (approvalAllowed) {
      expect(outputs).toBeTruthy();
      if (!outputs) {
        throw new Error("Client-ready ATLAS Legacy consult did not materialize deliverable and approval outputs.");
      }
      expect(outputs.serviceEngagement.company_id).toBe(fixture.companyId);
      expect(outputs.serviceDeliverable.company_id).toBe(fixture.companyId);
      expect(outputs.serviceDeliverable.artifact_id).toBe(reportArtifact.id);
      expect(outputs.serviceDeliverable.report_run_id).toBe(outputs.report.reportRun.id);
      expect(outputs.missingCapabilitySignal.company_id).toBe(fixture.companyId);
      expect(outputs.publicationDraft.company_id).toBe(fixture.companyId);
      expect(outputs.approvalTaskId).toBeTruthy();
    } else {
      expect(revisionSignal).toBeTruthy();
      expect(revisionSignal?.company_id).toBe(fixture.companyId);
    }

    await page.goto(`/companies/${fixture.companyId}`);
    await page.waitForLoadState("networkidle");
    await expect(page.getByText(new RegExp(`Operation ${launch.runId.slice(0, 8)}`, "i"))).toBeVisible({
      timeout: 30_000,
    });
    await expect(page.getByTestId("service-history-panel")).toBeVisible();
    await expect(page.getByTestId("communication-panel")).toBeVisible();
    await expect(page.getByText(/Execution remains blocked until WhatsApp provider is configured/i)).toBeVisible();
    if (approvalAllowed) {
      await expect(page.getByText(/Missing execution capabilities/i).first()).toBeVisible();
    } else {
      expect(revisionSignal?.company_id).toBe(fixture.companyId);
    }

    await loginLive(page, request, fixture.legacyOwner, `/companies/${fixture.companyId}`);
    await expect(page.getByRole("heading", { name: liveLegacyCompanyName, level: 2 })).toBeVisible();
    await expect(page.getByTestId("service-history-panel")).toBeVisible();
    await expect(page.getByTestId("communication-panel")).toBeVisible();
    await expect(page.getByText(/Can you explain why WhatsApp is recommended/i)).toBeVisible();
    await expect(page.getByText(/manual first step/i)).toBeVisible();
    await expect(page.getByText(/Execution remains blocked until WhatsApp provider is configured/i)).toHaveCount(0);
    await expect(page.getByText(/pack manifest|private config|internal task config|operator-only/i)).toHaveCount(0);
    if (approvalAllowed && outputs) {
      await expectLegacyOwnerCanReadDeliverableWithoutInternalNotes(request, fixture);

      await page.goto(`/approvals?item=${outputs.approvalTaskId}`);
      await page.waitForLoadState("networkidle");
      await expect(page.getByRole("heading", { name: /Decide with context/i })).toBeVisible();
      await expect(page.getByText(liveLegacyCompanyName).first()).toBeVisible();
      await expect(page.getByText(/publication-approval|Approval required|approval checkpoint/i).first()).toBeVisible();
    } else {
      await page.goto("/approvals");
      await page.waitForLoadState("networkidle");
      await expect(page.getByText(/ATLAS Legacy consult requires review-board improvements/i)).toHaveCount(0);
    }

    await loginLive(page, request, fixture.otherClientUser, "/companies");
    await expect(page.getByRole("link", { name: new RegExp(fixture.otherClientCompanyName, "i") })).toHaveCount(1);
    await expect(page.getByRole("link", { name: legacyCompanyCardName })).toHaveCount(0);
    await expectNoFunctionCompanies(page);
    await expectOtherClientCannotReadLegacyConsult(request, fixture, outputs?.approvalTaskId ?? null);

    expect(verticalLiveProductModeApiRequests(apiRequests)).toEqual([]);
    expectOnlyGenericLiveRoutes(apiRequests);
    expect(sawLiveApiPath(apiRequests, "/api/graphs/")).toBe(true);
    expect(sawLiveApiPath(apiRequests, `/api/graphs/${fixture.companyId}`)).toBe(true);
    expect(sawLiveApiPath(apiRequests, `/api/companies/${fixture.companyId}/operating-model`)).toBe(true);
    expect(sawLiveApiPath(apiRequests, `/api/companies/${fixture.companyId}/packs`)).toBe(true);
    expect(sawLiveApiPath(apiRequests, "/api/runs/start") || launch.mode === "backend").toBe(true);
    if (approvalAllowed) {
      expect(sawLiveApiPath(apiRequests, "/api/approvals/") || sawLiveApiPath(apiRequests, "/api/approvals")).toBe(
        true,
      );
    }
    expect(sawLiveCompanyScopedQuery(apiRequests, "/api/work-artifacts", fixture.companyId)).toBe(true);
    expect(sawLiveCompanyScopedQuery(apiRequests, "/api/report-runs", fixture.companyId)).toBe(true);
    expect(sawLiveCompanyScopedQuery(apiRequests, "/api/state-projections", fixture.companyId)).toBe(true);
    expect(sawLiveCompanyScopedQuery(apiRequests, "/api/communication/threads", fixture.companyId)).toBe(true);
    expect(communication.threadId).toBeTruthy();
  });
});

async function expectNoFunctionCompanies(page: Page): Promise<void> {
  for (const separatedCompany of forbiddenLegacyFunctionCompanies) {
    await expect(page.getByRole("link", { name: new RegExp(`^${separatedCompany}\\b`, "i") })).toHaveCount(0);
    await expect(page.getByText(separatedCompany, { exact: true })).toHaveCount(0);
  }
}

function assertReviewBoardSection(label: string, section: AtlasLegacyConsultQualityScorecard["atlas"]): void {
  expect(section.average).toBeGreaterThanOrEqual(1);
  expect(section.average).toBeLessThanOrEqual(5);
  expect(section.scores.length).toBeGreaterThanOrEqual(6);
  for (const score of section.scores) {
    expect(score.score).toBeGreaterThanOrEqual(1);
    expect(score.score).toBeLessThanOrEqual(5);
    expect(score.area).toBeTruthy();
    expect(score.rationale).toBeTruthy();
    expect(score.improvement).toBeTruthy();
  }
  if (section.average === 5) {
    for (const score of section.scores) {
      expect(score.rationale).toMatch(/exceptional|top-tier|best-in-class|outstanding/i);
    }
  }
  expect(label).toBeTruthy();
}

function assertReviewBoardImprovements(scorecard: AtlasLegacyConsultQualityScorecard): void {
  const allAveragesExceedRareThreshold =
    scorecard.atlas.average > 4.7 && scorecard.legacy.average > 4.7 && scorecard.engagement.average > 4.7;
  if (allAveragesExceedRareThreshold) {
    return;
  }
  expect(scorecard.atlas.required_improvements.length).toBeGreaterThanOrEqual(2);
  expect(scorecard.legacy.required_improvements.length).toBeGreaterThanOrEqual(2);
  expect(scorecard.engagement.required_improvements.length).toBeGreaterThanOrEqual(2);
}

async function expectLegacyOwnerCanReadDeliverableWithoutInternalNotes(
  request: APIRequestContext,
  fixture: LiveAtlasLegacyConsultFixture,
): Promise<void> {
  const engagementResponse = await request.get(
    `${API_BASE_URL}/api/service-engagements/${fixture.serviceEngagement.id}`,
    {
      headers: authHeaders(fixture.legacyOwnerAccessToken),
    },
  );
  expect(engagementResponse.ok()).toBe(true);
  const engagementBody = (await engagementResponse.json()) as { data: { engagement: Record<string, unknown> } };
  expect(engagementBody.data.engagement.company_id).toBe(fixture.companyId);
  expect(engagementBody.data.engagement.internal_notes).toBeUndefined();

  const deliverablesResponse = await request.get(
    `${API_BASE_URL}/api/service-engagements/${fixture.serviceEngagement.id}/deliverables`,
    {
      headers: authHeaders(fixture.legacyOwnerAccessToken),
    },
  );
  expect(deliverablesResponse.ok()).toBe(true);
  const deliverablesBody = (await deliverablesResponse.json()) as {
    data: { deliverables: Array<{ company_id: string; visibility: string }> };
  };
  expect(deliverablesBody.data.deliverables.length).toBeGreaterThan(0);
  expect(deliverablesBody.data.deliverables.every((deliverable) => deliverable.company_id === fixture.companyId)).toBe(
    true,
  );
  expect(deliverablesBody.data.deliverables.every((deliverable) => deliverable.visibility !== "internal")).toBe(true);
}

async function validateAtlasLegacyCommunicationScenario(
  request: APIRequestContext,
  fixture: LiveAtlasLegacyConsultFixture,
  signalId: string,
  testInfo: TestInfo,
): Promise<{ threadId: string }> {
  const keyPrefix = [liveProductModeRunNamespace(testInfo), fixture.companyId, "communication"].join(":");
  const threadResponse = await request.post(`${API_BASE_URL}/api/communication/threads`, {
    headers: authHeaders(fixture.accessToken, `${keyPrefix}:thread`),
    data: {
      company_id: fixture.companyId,
      service_engagement_id: fixture.serviceEngagement.id,
      title: "Legacy DEPP GOLD launch consult",
      thread_type: "service_engagement",
      visibility_mode: "mixed",
      source_key: `${keyPrefix}:primary`,
      metadata: {
        product_mode_live: true,
      },
    },
  });
  expect(threadResponse.ok()).toBe(true);
  const threadBody = (await threadResponse.json()) as {
    data: { thread: { id: string } };
  };
  const threadId = threadBody.data.thread.id;

  const questionResponse = await request.post(`${API_BASE_URL}/api/communication/threads/${threadId}/messages`, {
    headers: authHeaders(fixture.legacyOwnerAccessToken, `${keyPrefix}:legacy-question`),
    data: {
      message_kind: "request",
      body: "Can you explain why WhatsApp is recommended if the connector is missing?",
      body_format: "markdown",
      visibility: "customer",
      metadata: {},
      attachments: [],
    },
  });
  expect(questionResponse.ok()).toBe(true);

  const replyResponse = await request.post(`${API_BASE_URL}/api/communication/threads/${threadId}/messages`, {
    headers: authHeaders(fixture.accessToken, `${keyPrefix}:atlas-reply`),
    data: {
      message_kind: "response",
      body: "WhatsApp is recommended as a manual first step. Automation requires connecting a WhatsApp/Twilio/Brevo capability.",
      body_format: "markdown",
      visibility: "customer",
      metadata: {},
      attachments: [],
    },
  });
  expect(replyResponse.ok()).toBe(true);

  const internalResponse = await request.post(`${API_BASE_URL}/api/communication/threads/${threadId}/messages`, {
    headers: authHeaders(fixture.accessToken, `${keyPrefix}:internal-note`),
    data: {
      message_kind: "agent_observation",
      body: "Execution remains blocked until WhatsApp provider is configured. Keep missing-capability recommendation open.",
      body_format: "markdown",
      visibility: "internal",
      metadata: {},
      attachments: [],
    },
  });
  expect(internalResponse.ok()).toBe(true);
  const internalBody = (await internalResponse.json()) as {
    data: { message: { id: string } };
  };

  const attachmentResponse = await request.post(
    `${API_BASE_URL}/api/communication/messages/${internalBody.data.message.id}/attachments`,
    {
      headers: authHeaders(fixture.accessToken, `${keyPrefix}:internal-signal-attachment`),
      data: {
        attachments: [{ type: "company_signal", id: signalId }],
      },
    },
  );
  expect(attachmentResponse.ok()).toBe(true);

  const legacyMessagesResponse = await request.get(`${API_BASE_URL}/api/communication/threads/${threadId}/messages`, {
    headers: authHeaders(fixture.legacyOwnerAccessToken),
  });
  expect(legacyMessagesResponse.ok()).toBe(true);
  const legacyMessagesBody = (await legacyMessagesResponse.json()) as {
    data: { messages: Array<{ body: string; visibility: string }> };
  };
  expect(legacyMessagesBody.data.messages.map((message) => message.visibility)).toEqual(["customer", "customer"]);
  expect(JSON.stringify(legacyMessagesBody.data.messages)).not.toMatch(/Execution remains blocked/i);

  const atlasMessagesResponse = await request.get(`${API_BASE_URL}/api/communication/threads/${threadId}/messages`, {
    headers: authHeaders(fixture.accessToken),
  });
  expect(atlasMessagesResponse.ok()).toBe(true);
  const atlasMessagesBody = (await atlasMessagesResponse.json()) as {
    data: {
      messages: Array<{
        id: string;
        body: string;
        visibility: string;
        attachments: Array<{ type: string; target_id: string }>;
      }>;
    };
  };
  expect(atlasMessagesBody.data.messages.map((message) => message.visibility)).toEqual([
    "customer",
    "customer",
    "internal",
  ]);
  const internalMessage = atlasMessagesBody.data.messages.find((message) => message.visibility === "internal");
  expect(internalMessage?.body).toMatch(/Execution remains blocked/i);
  expect(internalMessage?.attachments).toContainEqual(
    expect.objectContaining({ type: "company_signal", target_id: signalId }),
  );

  const otherThreadResponse = await request.get(`${API_BASE_URL}/api/communication/threads/${threadId}`, {
    headers: authHeaders(fixture.otherClientAccessToken),
  });
  expect([403, 404]).toContain(otherThreadResponse.status());
  const otherThreadsResponse = await request.get(`${API_BASE_URL}/api/communication/threads`, {
    headers: authHeaders(fixture.otherClientAccessToken),
    params: { company_id: fixture.companyId },
  });
  expect([200, 403, 404]).toContain(otherThreadsResponse.status());
  if (otherThreadsResponse.status() === 200) {
    const otherThreadsBody = (await otherThreadsResponse.json()) as {
      data: { threads: unknown[] };
    };
    expect(otherThreadsBody.data.threads).toEqual([]);
  }

  await testInfo.attach("atlas-legacy-communication-scenario", {
    body: JSON.stringify(
      {
        threadId,
        internalMessageId: internalBody.data.message.id,
        attachedSignalId: signalId,
      },
      null,
      2,
    ),
    contentType: "application/json",
  });

  return { threadId };
}

async function expectOtherClientCannotReadLegacyConsult(
  request: APIRequestContext,
  fixture: LiveAtlasLegacyConsultFixture,
  approvalTaskId: string | null,
): Promise<void> {
  const deniedRequests = [
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
    request.get(`${API_BASE_URL}/api/service-engagements/${fixture.serviceEngagement.id}`, {
      headers: authHeaders(fixture.otherClientAccessToken),
    }),
    request.get(`${API_BASE_URL}/api/service-engagements/${fixture.serviceEngagement.id}/deliverables`, {
      headers: authHeaders(fixture.otherClientAccessToken),
    }),
  ];
  if (approvalTaskId) {
    deniedRequests.push(
      request.get(`${API_BASE_URL}/api/approvals/${approvalTaskId}`, {
        headers: authHeaders(fixture.otherClientAccessToken),
      }),
    );
  }
  const deniedResponses = await Promise.all(deniedRequests);

  for (const response of deniedResponses) {
    expect([403, 404]).toContain(response.status());
  }
}

function expectOnlyGenericLiveRoutes(apiRequests: LiveProductModeApiRequest[]): void {
  const disallowed = apiRequests.filter((request) =>
    /\/api\/(?:marketing|growth-marketing|digital-marketing|marketing-campaigns)(?:\/|$)/i.test(request.pathname),
  );
  expect(disallowed).toEqual([]);
}

function authHeaders(accessToken: string, idempotencyKey?: string): Record<string, string> {
  return {
    Authorization: `Bearer ${accessToken}`,
    ...(idempotencyKey ? { "Idempotency-Key": idempotencyKey } : {}),
  };
}
