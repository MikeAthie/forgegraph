import {
  expect,
  test,
  type APIRequestContext,
  type APIResponse,
  type Browser,
  type Page,
  type TestInfo,
} from "@playwright/test";

import { apiBaseUrl } from "../e2e/live-helpers";
import {
  collectLiveProductModeApiRequests,
  forbiddenLegacyFunctionCompanies,
  LIVE_LLM_RUN_TIMEOUT_MS,
  liveLegacyCompanyName,
  liveLlmSkipReason,
  liveProductModeRunNamespace,
  sawLiveApiPath,
  seedLiveAtlasLegacyConsultProductMode,
  verticalLiveProductModeApiRequests,
  type LiveAtlasLegacyConsultFixture,
  type LiveProductModeApiRequest,
} from "./fixtures.live";
import {
  waitForBackendPostResponse,
  waitForContractRevision,
  waitForOperation,
  waitForPerformanceMetricSnapshot,
  waitForPhaseWorkstreamMaterialization,
} from "./runtime-waits";

const API_BASE_URL = apiBaseUrl();
const liveSkipReason = liveLlmSkipReason();
const legacyCompanyCardName = /^Legacy Eyewear\b/i;
const agencyPhaseId = "digital_marketing_pro.v1.atlas_agency_work_graph";
const deploymentPolicyId = "digital_marketing_pro.v1.atlas_launch_deployment";
const performancePolicyId = "digital_marketing_pro.v1.atlas_performance_review";
const legacyCampaignRequest =
  "Can you create a campaign for Legacy DEPP GOLD with 10,000 MXN budget across email, WhatsApp, Instagram, Facebook, TikTok, and a landing page? Price is 599 MXN. Inventory is limited. Please create a strategy and execution plan?";
const helperAssistedSteps = [
  "Connector availability setup uses backend API because connector-management UI is not available yet.",
  "Onboarding field enrichment uses backend API because structured whiteboard field editing is not exposed in the company workspace yet.",
  "Workstream completion, synthesis, and gate scoring use backend API because production workstream authoring/evaluation UI is not available yet.",
  "Performance report and evaluation use backend API because report/evaluation controls are not exposed in the whiteboard panel yet.",
  "Isolation and durable-state checks use backend API to verify DB-owned state directly.",
];

type ApiSuccess<T> = { data: T };
type ApiCall = { method: string; pathname: string };
type OperatingModelPackHealth = {
  status: string;
  packs_dir: string;
  packs: Array<{
    pack_id: string;
    release_id?: string;
    source: string;
    config_hash: string;
    contains: string[];
  }>;
  missing_required_packs: string[];
  missing_required_contents?: Array<{ pack_id: string; missing: string[] }>;
};
type PackInstallation = {
  id: string;
  pack_id: string;
  role: string;
  config?: Record<string, unknown>;
  public_config?: Record<string, unknown>;
};
type CommunicationThread = { id: string };
type CommunicationMessage = {
  id: string;
  body: string;
  routed_whiteboard_id?: string | null;
  routed_classification?: string | null;
};
type ProductOperation = {
  id: string;
  kind: string;
  status: string;
  target_type: string;
  target_id: string;
  contract_revision: number;
  contract_revision_at_accept: number;
  contract_revision_at_completion: number;
  terminal: boolean;
  error?: { code?: string; message?: string } | null;
  metadata?: Record<string, unknown>;
};
type OperationEnvelope = {
  accepted?: boolean;
  operation?: ProductOperation;
};
type ContractReadiness = {
  contract_revision?: number;
  last_operation_id?: string;
  terminal?: boolean;
  pending_count?: number;
  running_count?: number;
  blocked_count?: number;
  completed_count?: number;
};
type WorkWhiteboard = {
  id: string;
  status: string;
  company_id: string;
  communication_thread_id?: string | null;
  source_message_id?: string | null;
  completion_score: number;
  phase_contracts?: PhaseContract[];
  deployment_contract?: DeploymentContract;
  performance_contract?: PerformanceContract;
};
type WhiteboardBoardCard = {
  id: string;
  title: string;
  department_slug: string;
  department_name: string;
  status: string;
  priority: string;
  customer_visible: boolean;
  allowed_actions: string[];
};
type WhiteboardBoard = {
  whiteboard_id: string;
  event_version: string;
  cards: WhiteboardBoardCard[];
  lanes: Array<{ department_slug: string; department_name: string; cards: WhiteboardBoardCard[] }>;
  allowed_actions: {
    can_modify_structure: boolean;
    can_update_assigned_cards: boolean;
    can_view_internal: boolean;
  };
};
type RequestClassification = {
  id: string;
  classification: "NEW_REQUEST" | "EXISTING_REQUEST" | "AMBIGUOUS_REQUEST";
  confidence: number;
};
type PhaseContract = {
  phase_id: string;
  phase_name: string;
  workstreams: Array<{
    id: string;
    name?: string;
    required?: boolean;
    status: string;
    dependencies?: Array<{ workstream_id?: string; type?: string; required_status?: string }>;
    dependency_state?: {
      status?: string;
      blocker_reason?: string;
      blockers?: Array<Record<string, unknown>>;
      provisional?: Array<Record<string, unknown>>;
    };
  }>;
  current_state: {
    status: string;
    all_workstreams_completed?: boolean;
    applied_actions?: Record<string, string>;
    gate?: { result?: string; score?: number };
  } & ContractReadiness;
} & ContractReadiness;
type DeploymentContract = {
  policy_id: string;
  status: string;
  channels: Array<{
    id: string;
    display_name: string;
    status: string;
    tool_execution_id?: string;
    company_signal_id?: string;
    routing_record_id?: string;
    blocked_reason_code?: string;
    receipt?: {
      result?: Record<string, unknown>;
      error?: Record<string, unknown> | null;
    };
  }>;
  current_state?: ContractReadiness;
} & ContractReadiness;
type PerformanceContract = {
  policy_id: string;
  status: string;
  sources: Array<{
    id: string;
    display_name: string;
    status: string;
    tool_execution_id?: string;
    company_signal_id?: string;
    routing_record_id?: string;
    blocked_reason_code?: string;
    metrics?: Record<string, unknown>;
  }>;
  current_state: {
    metric_snapshot_id?: string;
    report_run_id?: string;
    evaluation_id?: string;
    routing_record_ids?: string[];
  } & ContractReadiness;
} & ContractReadiness;
type PhaseActionResponse = OperationEnvelope & {
  whiteboard_phase_contract: PhaseContract;
  whiteboard: WorkWhiteboard;
  evaluation_id?: string;
};
type DeploymentActionResponse = OperationEnvelope & {
  deployment_contract: DeploymentContract;
  whiteboard: WorkWhiteboard;
};
type PerformanceActionResponse = OperationEnvelope & {
  performance_contract: PerformanceContract;
  whiteboard: WorkWhiteboard;
  evaluation_id?: string;
};

test.use({ video: "on" });

test.describe("Live ATLAS agency full product loop", () => {
  test.skip(Boolean(liveSkipReason), liveSkipReason ?? "Live ATLAS agency full-flow suite is disabled.");

  test("PM-LIVE-ATLAS-AGENCY-001: Legacy request becomes strategy, content, approval, deployment evidence, performance review, and optimization", async ({
    browser,
    page,
    request,
  }, testInfo) => {
    test.setTimeout(LIVE_LLM_RUN_TIMEOUT_MS * 2 + 420_000);

    const apiCalls: ApiCall[] = [];
    const pageRequests = collectLiveProductModeApiRequests(page);
    const fixture = await seedLiveAtlasLegacyConsultProductMode(request, testInfo);
    const packHealth = await assertOperatingModelPackHealth(request, fixture, apiCalls);
    await configureAtlasAgencyConnectorAvailability(request, fixture, testInfo, apiCalls);

    const { thread, message } = await createLegacyRequestMessageThroughUi(page, request, fixture, apiCalls);
    await expectWhiteboardCountForMessage(request, fixture, message.id, 0, apiCalls);
    const routed = await routeRequestMessageThroughUi(page, request, fixture, message.id, apiCalls);
    expect(routed.classification.classification).toBe("NEW_REQUEST");
    expect(routed.classification.confidence).toBeGreaterThan(0);
    expect(routed.whiteboard.company_id).toBe(fixture.companyId);
    expect(routed.whiteboard.status).toBe("onboarding");
    await expectWhiteboardCountForMessage(request, fixture, message.id, 1, apiCalls);

    const whiteboard = await completeOnboarding(page, request, fixture, routed.whiteboard.id, testInfo, apiCalls);
    expect(whiteboard.status).toBe("ready_for_strategy");
    expect(whiteboard.completion_score).toBeGreaterThanOrEqual(0);
    const onboardingBoard = await fetchWhiteboardBoard(request, fixture, whiteboard.id, apiCalls);
    expect(onboardingBoard.event_version).toBe("whiteboard_board_v1");
    expect(onboardingBoard.cards.length).toBeGreaterThan(0);

    const phaseStartOperation = await startPhaseThroughUi(
      page,
      request,
      fixture,
      whiteboard.id,
      agencyPhaseId,
      apiCalls,
    );
    expect(phaseStartOperation.status).toBe("completed");
    const startedAgency = await fetchPhaseContract(request, fixture, whiteboard.id, agencyPhaseId, apiCalls);
    const initialWorkstreams = workstreamsById(startedAgency);
    const initialParallelIds = [
      "account_brief_compilation",
      "strategy_brief",
      "legal_claims_precheck",
      "tech_execution_readiness",
      "media_channel_plan",
      "copy_message_house",
      "analytics_measurement_plan",
      "traffic_dependency_map",
    ];
    for (const workstreamId of initialParallelIds) {
      expect(initialWorkstreams[workstreamId]?.status).not.toBe("blocked");
    }
    expect(initialWorkstreams.copy_message_house?.dependency_state?.status).toBe("provisional");
    expect(initialWorkstreams.content_asset_map?.status).toBe("blocked");
    expect(initialWorkstreams.timing_flighting_plan?.status).toBe("blocked");
    expect(initialWorkstreams.deployment_readiness_plan?.status).toBe("blocked");

    const agency = await completeAgencyPhaseInDependencyOrder(
      request,
      fixture,
      whiteboard.id,
      agencyPhaseId,
      {
        strategy_readiness: 94,
        legal_precheck: "pass",
        measurement_readiness: 91,
        execution_readiness: 90,
        asset_plan_readiness: 92,
        timing_readiness: 89,
      },
      testInfo,
      apiCalls,
    );
    expect(agency.whiteboard.status).toBe("in_approval");
    expect(agency.contract.current_state.gate?.result).toBe("pass");
    const approvalTaskId = agency.contract.current_state.applied_actions?.approval_task_id;
    expect(approvalTaskId).toBeTruthy();

    const preDeploymentPerformance = await rawPost(
      request,
      `/api/whiteboards/${whiteboard.id}/performance/start`,
      fixture.accessToken,
      { policy_id: performancePolicyId },
      idempotency(testInfo, "performance-before-deployment"),
      apiCalls,
    );
    expect(preDeploymentPerformance.status()).toBeGreaterThanOrEqual(400);

    const approval = await resolveApprovalThroughUi(page, request, fixture, approvalTaskId!, apiCalls);
    expect(approval.status).toBe("approved");

    const deployment = await prepareDeploymentThroughUi(page, request, fixture, whiteboard.id, apiCalls);
    expect(deployment.operation.status).toBe("completed");
    const deploymentContract = deployment.deployment_contract;
    expect(["partial", "prepared", "executed"]).toContain(deploymentContract.status);
    const executedDeployment = deploymentContract.channels.find((channel) => channel.tool_execution_id);
    expect(executedDeployment).toBeTruthy();
    const emailDeployment = deploymentContract.channels.find((channel) => channel.id === "email");
    expect(emailDeployment?.tool_execution_id).toBeTruthy();
    const emailReceipt = emailDeployment?.receipt?.result ?? {};
    expect(emailReceipt.mode).toBe("dry_run");
    expect(emailReceipt.evidence_mode).toBe("sandbox");
    expect(emailReceipt).toHaveProperty("recipient_count");
    expect(emailReceipt).toHaveProperty("recipient_domains");
    expect(emailReceipt).toHaveProperty("recipient_hashes");
    expect(JSON.stringify(emailDeployment?.receipt ?? {})).not.toMatch(
      /(?:@|<p>|bearer\s+|authorization|access_token|app_secret|\+1555|https?:\/\/)/i,
    );
    const blockedDeployment = deploymentContract.channels.filter((channel) => channel.status === "blocked");
    expect(blockedDeployment.length).toBeGreaterThan(0);
    for (const channel of blockedDeployment) {
      expect(channel.company_signal_id).toBeTruthy();
      expect(channel.routing_record_id).toBeTruthy();
      expect(channel.tool_execution_id ?? "").toBe("");
    }

    const performance = await startPerformanceThroughUi(page, request, fixture, whiteboard.id, apiCalls);
    expect(performance.operation.status).toBe("completed");
    expect(performance.performance_contract.current_state.metric_snapshot_id).toBeTruthy();
    expect(performance.performance_contract.sources.some((source) => source.tool_execution_id)).toBe(true);
    expect(performance.performance_contract.sources.some((source) => source.status === "blocked")).toBe(true);

    const report = await postData<PerformanceActionResponse>(
      request,
      `/api/whiteboards/${whiteboard.id}/performance/report`,
      fixture.accessToken,
      { policy_id: performancePolicyId },
      idempotency(testInfo, "performance-report"),
      apiCalls,
    );
    const reportOperation = expectOperation(report, "performance_report");
    await waitForOperationAndContract(
      request,
      fixture,
      whiteboard.id,
      reportOperation,
      () => fetchPerformanceContract(request, fixture, whiteboard.id, apiCalls),
      apiCalls,
    );
    expect(report.performance_contract.current_state.report_run_id).toBeTruthy();

    const evaluation = await postData<PerformanceActionResponse>(
      request,
      `/api/whiteboards/${whiteboard.id}/performance/evaluate`,
      fixture.accessToken,
      {
        policy_id: performancePolicyId,
        scorecard: {
          channel_signal_quality: 62,
          execution_completeness: 84,
          optimization_confidence: 81,
        },
      },
      idempotency(testInfo, "performance-evaluate"),
      apiCalls,
    );
    const performanceEvaluationOperation = expectOperation(evaluation, "performance_evaluate");
    await waitForOperationAndContract(
      request,
      fixture,
      whiteboard.id,
      performanceEvaluationOperation,
      () => fetchPerformanceContract(request, fixture, whiteboard.id, apiCalls),
      apiCalls,
    );
    expect(evaluation.performance_contract.current_state.evaluation_id).toBeTruthy();
    expect((evaluation.performance_contract.current_state.routing_record_ids ?? []).length).toBeGreaterThan(0);
    const finalBoard = await fetchWhiteboardBoard(request, fixture, whiteboard.id, apiCalls);
    expect(finalBoard.cards.length).toBeGreaterThanOrEqual(onboardingBoard.cards.length);
    const finalLaneSlugs = finalBoard.lanes.map((lane) => lane.department_slug);
    expect(finalLaneSlugs).toEqual(
      expect.arrayContaining([
        "strategy_research",
        "qa_compliance",
        "channel_execution",
        "brand_content",
        "analytics_performance",
        "client_approval_ops",
      ]),
    );

    await expectOtherClientIsolation(
      request,
      fixture,
      thread.id,
      whiteboard.id,
      [deployment.operation.id, performanceEvaluationOperation.id],
      apiCalls,
    );
    await assertWorkspaceRendering(browser, page, request, fixture, whiteboard.id, apiCalls);

    const allApiRequests = [
      ...pageRequests,
      ...apiCalls.map((call) => ({
        method: call.method,
        pathname: call.pathname,
        url: `${API_BASE_URL}${call.pathname}`,
      })),
    ];
    expect(verticalLiveProductModeApiRequests(pageRequests)).toEqual([]);
    expectNoVerticalRoutes(allApiRequests);
    expect(sawLiveApiPath(allApiRequests, `/api/graphs/${fixture.companyId}`)).toBe(true);
    expect(allApiRequests.some((call) => call.pathname.startsWith("/api/communication/"))).toBe(true);
    expect(allApiRequests.some((call) => call.pathname.startsWith("/api/whiteboards/"))).toBe(true);
    await expectNoFunctionCompaniesCreated(request, fixture, apiCalls);

    await testInfo.attach("atlas-agency-full-flow-evidence", {
      body: JSON.stringify(
        {
          namespace: liveProductModeRunNamespace(testInfo),
          packHealth,
          classification: routed.classification,
          whiteboard: {
            id: whiteboard.id,
            finalStatus: evaluation.whiteboard.status,
            completionScore: whiteboard.completion_score,
          },
          board: {
            cardCount: finalBoard.cards.length,
            lanes: finalBoard.lanes.map((lane) => lane.department_slug),
            allowedActions: finalBoard.allowed_actions,
          },
          agency: {
            phaseId: agency.contract.phase_id,
            result: agency.contract.current_state.gate?.result,
            approvalTaskId,
            operations: {
              phaseStart: operationEvidence(phaseStartOperation),
              synthesis: operationEvidence(agency.synthesisOperation),
              gateEvaluation: operationEvidence(agency.evaluationOperation),
            },
            initialFanout: initialParallelIds.map((id) => ({
              id,
              status: initialWorkstreams[id]?.status,
              dependencyStatus: initialWorkstreams[id]?.dependency_state?.status,
            })),
            blockedBefore: ["content_asset_map", "timing_flighting_plan", "deployment_readiness_plan"].map((id) => ({
              id,
              status: initialWorkstreams[id]?.status,
              reason: initialWorkstreams[id]?.dependency_state?.blocker_reason,
            })),
            afterFoundations: agency.afterFoundations.workstreams.map((item) => ({
              id: item.id,
              status: item.status,
              dependencyStatus: item.dependency_state?.status,
            })),
            afterContentTiming: agency.afterContentTiming.workstreams.map((item) => ({
              id: item.id,
              status: item.status,
              dependencyStatus: item.dependency_state?.status,
            })),
          },
          approval,
          deployment: {
            status: deploymentContract.status,
            operation: operationEvidence(deployment.operation),
            executed: deploymentContract.channels.filter((channel) => channel.tool_execution_id),
            blocked: blockedDeployment,
          },
          performance: {
            status: evaluation.performance_contract.status,
            operations: {
              start: operationEvidence(performance.operation),
              report: operationEvidence(reportOperation),
              evaluation: operationEvidence(performanceEvaluationOperation),
            },
            metricSnapshotId: evaluation.performance_contract.current_state.metric_snapshot_id,
            reportRunId: evaluation.performance_contract.current_state.report_run_id,
            evaluationId: evaluation.performance_contract.current_state.evaluation_id,
            routingRecordIds: evaluation.performance_contract.current_state.routing_record_ids,
          },
          helperAssistedSteps,
          routes: Array.from(new Set(allApiRequests.map((call) => call.pathname))).sort(),
          kafkaEnabled: (process.env.COMMUNICATION_KAFKA_ENABLED ?? "false").toLowerCase() === "true",
          llmProvider: process.env.LIVE_LLM_PROVIDER ?? "repo-default",
        },
        null,
        2,
      ),
      contentType: "application/json",
    });
  });
});

async function assertOperatingModelPackHealth(
  request: APIRequestContext,
  fixture: LiveAtlasLegacyConsultFixture,
  apiCalls: ApiCall[],
): Promise<OperatingModelPackHealth> {
  const response = await rawGet(request, "/api/system/operating-model-packs/health", fixture.accessToken, apiCalls);
  if (!response.ok()) {
    throw new Error(
      `GET /api/system/operating-model-packs/health failed with ${response.status()}: ${await response.text()}`,
    );
  }
  const health = (await response.json()) as OperatingModelPackHealth;
  expect(health.status).toBe("ok");
  expect(health.missing_required_packs).toEqual([]);
  expect(health.missing_required_contents ?? []).toEqual([]);
  const atlasPack = health.packs.find((pack) => pack.pack_id === "digital_marketing_pro");
  expect(atlasPack?.config_hash).toMatch(/^sha256:[a-f0-9]+$/);
  expect(atlasPack?.contains).toEqual(
    expect.arrayContaining(["atlas_agency_work_graph", "atlas_launch_deployment", "atlas_performance_review"]),
  );
  return health;
}

async function configureAtlasAgencyConnectorAvailability(
  request: APIRequestContext,
  fixture: LiveAtlasLegacyConsultFixture,
  testInfo: TestInfo,
  apiCalls: ApiCall[],
): Promise<void> {
  const packs = await getData<{ packs: PackInstallation[] }>(
    request,
    `/api/companies/${fixture.companyId}/packs`,
    fixture.accessToken,
    apiCalls,
  );
  const installation =
    packs.packs.find((pack) => pack.pack_id === "digital_marketing_pro.v1") ??
    packs.packs.find((pack) => pack.role === "primary") ??
    packs.packs[0];
  expect(installation).toBeTruthy();
  const config: Record<string, unknown> = { ...(installation.config ?? {}) };
  delete config.workstream_phases;
  delete config.phases;
  delete config.deployment_policies;
  delete config.deployments;
  delete config.performance_policies;
  delete config.measurement_policies;
  config.skip_graph_version = true;
  config.available_connectors = ["email_connector", "social_connector", "analytics_connector"];
  await postOrPatchData<{ installation: PackInstallation }>(
    "PATCH",
    request,
    `/api/companies/${fixture.companyId}/packs/${installation.id}`,
    fixture.accessToken,
    { config },
    idempotency(testInfo, "configure-atlas-agency-connectors"),
    apiCalls,
  );
}

async function createLegacyRequestMessageThroughUi(
  page: Page,
  request: APIRequestContext,
  fixture: LiveAtlasLegacyConsultFixture,
  apiCalls: ApiCall[],
): Promise<{ thread: CommunicationThread; message: CommunicationMessage }> {
  await openLiveTokenSession(page, request, fixture.legacyOwnerAccessToken, `/companies/${fixture.companyId}`);
  await page.getByTestId("communication-panel").scrollIntoViewIfNeeded();
  await expect(page.getByTestId("communication-panel")).toBeVisible({ timeout: 30_000 });
  await page.getByTestId("communication-composer").fill(legacyCampaignRequest);
  await page.getByTestId("communication-send-button").click();
  await expect(page.getByTestId("communication-message-list").getByText(/Legacy DEPP GOLD/i)).toBeVisible({
    timeout: 30_000,
  });

  const deadline = Date.now() + 30_000;
  while (Date.now() < deadline) {
    const threads = await getData<{ threads: CommunicationThread[] }>(
      request,
      `/api/communication/threads?company_id=${fixture.companyId}`,
      fixture.legacyOwnerAccessToken,
      apiCalls,
    );
    for (const thread of threads.threads) {
      const messages = await getData<{ messages: Array<CommunicationMessage & { body: string }> }>(
        request,
        `/api/communication/threads/${thread.id}/messages`,
        fixture.legacyOwnerAccessToken,
        apiCalls,
      );
      const message = messages.messages.find((item) => item.body.includes("Legacy DEPP GOLD"));
      if (message) {
        expect(message.id).toBeTruthy();
        return { thread, message };
      }
    }
    await page.waitForTimeout(1000);
  }
  throw new Error("Legacy UI-created communication request was not persisted.");
}

async function routeRequestMessageThroughUi(
  page: Page,
  request: APIRequestContext,
  fixture: LiveAtlasLegacyConsultFixture,
  messageId: string,
  apiCalls: ApiCall[],
): Promise<{ classification: RequestClassification; whiteboard: WorkWhiteboard; routing_record_ids: string[] }> {
  await openLiveTokenSession(page, request, fixture.accessToken, `/companies/${fixture.companyId}`);
  await page.getByTestId("communication-panel").scrollIntoViewIfNeeded();
  const routeButton = page.getByTestId(`communication-message-route-request-${messageId}`);
  await expect(routeButton).toBeVisible({ timeout: 30_000 });
  await routeButton.click();
  const routedState = page.getByTestId(`communication-message-routed-${messageId}`);
  await expect(routedState).toContainText(/Routed to whiteboard/i, { timeout: 30_000 });

  const routedWhiteboards = await whiteboardsForMessage(request, fixture, messageId, apiCalls);
  expect(routedWhiteboards).toHaveLength(1);
  const messages = await getData<{ messages: CommunicationMessage[] }>(
    request,
    `/api/communication/threads/${routedWhiteboards[0].communication_thread_id}/messages`,
    fixture.accessToken,
    apiCalls,
  );
  const routedMessage = messages.messages.find((item) => item.id === messageId);
  expect(routedMessage?.routed_whiteboard_id).toBe(routedWhiteboards[0].id);
  const classification = {
    id: "",
    classification: (routedMessage?.routed_classification ?? "NEW_REQUEST") as RequestClassification["classification"],
    confidence: 1,
  };
  return { classification, whiteboard: routedWhiteboards[0], routing_record_ids: [] };
}

async function whiteboardsForMessage(
  request: APIRequestContext,
  fixture: LiveAtlasLegacyConsultFixture,
  messageId: string,
  apiCalls: ApiCall[],
): Promise<WorkWhiteboard[]> {
  const response = await getData<{ whiteboards: WorkWhiteboard[] }>(
    request,
    `/api/whiteboards?company_id=${fixture.companyId}`,
    fixture.accessToken,
    apiCalls,
  );
  return response.whiteboards.filter((whiteboard) => whiteboard.source_message_id === messageId);
}

async function expectWhiteboardCountForMessage(
  request: APIRequestContext,
  fixture: LiveAtlasLegacyConsultFixture,
  messageId: string,
  expectedCount: number,
  apiCalls: ApiCall[],
): Promise<void> {
  await expect
    .poll(async () => (await whiteboardsForMessage(request, fixture, messageId, apiCalls)).length)
    .toBe(expectedCount);
}

async function fetchWhiteboardBoard(
  request: APIRequestContext,
  fixture: LiveAtlasLegacyConsultFixture,
  whiteboardId: string,
  apiCalls: ApiCall[],
): Promise<WhiteboardBoard> {
  const response = await getData<{ board: WhiteboardBoard }>(
    request,
    `/api/whiteboards/${whiteboardId}/board`,
    fixture.accessToken,
    apiCalls,
  );
  expect(response.board.whiteboard_id).toBe(whiteboardId);
  return response.board;
}

async function completeOnboarding(
  page: Page,
  request: APIRequestContext,
  fixture: LiveAtlasLegacyConsultFixture,
  whiteboardId: string,
  testInfo: TestInfo,
  apiCalls: ApiCall[],
): Promise<WorkWhiteboard> {
  await postOrPatchData<{ whiteboard: WorkWhiteboard }>(
    "PATCH",
    request,
    `/api/whiteboards/${whiteboardId}`,
    fixture.accessToken,
    {
      objective: "Launch a measured demand campaign for Legacy DEPP GOLD without unsupported claims.",
      budget_limit: "10000 MXN",
      timeline: "two-week launch window",
      constraints: {
        inventory: "limited",
        compliance: "avoid unsupported medical or vision claims",
        approval: "client approval required before publishing",
      },
      target_audience: {
        segment: "Mexico City eyewear buyers looking for premium gold-tone frames",
      },
      brand_context: {
        voice: "premium, precise, understated",
      },
      product_context: {
        product: "Legacy DEPP GOLD",
        price: "599 MXN",
      },
      channel_context: {
        requested: ["email", "WhatsApp", "Instagram", "Facebook", "TikTok", "landing page"],
      },
      known_facts: {
        client: liveLegacyCompanyName,
        approval_owner: "Legacy owner",
        available_connector: "email and social sandbox",
      },
      assumptions: [
        "Email and social channels can be sandboxed; WhatsApp and landing-page connectors are not configured.",
        "Social provider publishing remains disabled unless a generic social connector is explicitly configured.",
      ],
    },
    idempotency(testInfo, "whiteboard-fill"),
    apiCalls,
  );
  await openLiveTokenSession(page, request, fixture.accessToken, `/companies/${fixture.companyId}`);
  await page.getByTestId("whiteboard-panel").scrollIntoViewIfNeeded();
  await page.getByTestId("whiteboard-mark-ready-button").click();
  await expect(page.getByTestId("whiteboard-status")).toContainText(/Ready For Planning|Ready For Strategy/i, {
    timeout: 30_000,
  });
  const ready = await getData<{ whiteboard: WorkWhiteboard }>(
    request,
    `/api/whiteboards/${whiteboardId}`,
    fixture.accessToken,
    apiCalls,
  );
  return ready.whiteboard;
}

async function startPhaseThroughUi(
  page: Page,
  request: APIRequestContext,
  fixture: LiveAtlasLegacyConsultFixture,
  whiteboardId: string,
  phaseId: string,
  apiCalls: ApiCall[],
): Promise<ProductOperation> {
  await openLiveTokenSession(page, request, fixture.accessToken, `/companies/${fixture.companyId}`);
  await page.getByTestId("whiteboard-panel").scrollIntoViewIfNeeded();
  const startButton = page.getByTestId(`whiteboard-phase-start-${phaseId}`);
  await expect(startButton).toBeVisible({ timeout: 30_000 });
  const startResponsePromise = waitForBackendPostResponse(
    page,
    `/api/whiteboards/${whiteboardId}/phases/${phaseId}/start`,
    30_000,
  );
  await startButton.click();
  const response = await startResponsePromise;
  const payload = await responseData<PhaseActionResponse>(
    response,
    `POST /api/whiteboards/${whiteboardId}/phases/${phaseId}/start`,
  );
  const operation = expectOperation(payload, "phase_start");
  await waitForOperationAndContract(
    request,
    fixture,
    whiteboardId,
    operation,
    () => fetchPhaseContract(request, fixture, whiteboardId, phaseId, apiCalls),
    apiCalls,
  );
  await expect(page.getByTestId(`whiteboard-phase-${phaseId}`)).toContainText(/In |Started|Strategy|Content/i, {
    timeout: 30_000,
  });
  await waitForPhaseWorkstreamMaterialization(
    () => fetchPhaseContract(request, fixture, whiteboardId, phaseId, apiCalls),
    30_000,
  );
  return operation;
}

async function fetchPhaseContract(
  request: APIRequestContext,
  fixture: LiveAtlasLegacyConsultFixture,
  whiteboardId: string,
  phaseId: string,
  apiCalls: ApiCall[],
): Promise<PhaseContract> {
  const response = await getData<{ whiteboard_phase_contract: PhaseContract }>(
    request,
    `/api/whiteboards/${whiteboardId}/phases/${phaseId}`,
    fixture.accessToken,
    apiCalls,
  );
  return response.whiteboard_phase_contract;
}

async function fetchDeploymentContract(
  request: APIRequestContext,
  fixture: LiveAtlasLegacyConsultFixture,
  whiteboardId: string,
  apiCalls: ApiCall[],
): Promise<DeploymentContract> {
  const response = await getData<{ deployment_contract: DeploymentContract }>(
    request,
    `/api/whiteboards/${whiteboardId}/deployment`,
    fixture.accessToken,
    apiCalls,
  );
  return response.deployment_contract;
}

async function fetchPerformanceContract(
  request: APIRequestContext,
  fixture: LiveAtlasLegacyConsultFixture,
  whiteboardId: string,
  apiCalls: ApiCall[],
): Promise<PerformanceContract> {
  const response = await getData<{ performance_contract: PerformanceContract }>(
    request,
    `/api/whiteboards/${whiteboardId}/performance`,
    fixture.accessToken,
    apiCalls,
  );
  return response.performance_contract;
}

async function fetchOperation(
  request: APIRequestContext,
  fixture: LiveAtlasLegacyConsultFixture,
  whiteboardId: string,
  operationId: string,
  apiCalls: ApiCall[],
): Promise<ProductOperation> {
  const response = await getData<{ operation: ProductOperation }>(
    request,
    `/api/whiteboards/${whiteboardId}/operations/${operationId}`,
    fixture.accessToken,
    apiCalls,
  );
  return response.operation;
}

async function waitForOperationAndContract<TContract extends ContractReadiness>(
  request: APIRequestContext,
  fixture: LiveAtlasLegacyConsultFixture,
  whiteboardId: string,
  operation: ProductOperation,
  fetchContract: () => Promise<TContract>,
  apiCalls: ApiCall[],
): Promise<void> {
  await waitForOperation(
    () => fetchOperation(request, fixture, whiteboardId, operation.id, apiCalls),
    ["completed"],
    60_000,
  );
  await waitForContractRevision(fetchContract, operationCompletionRevision(operation), 60_000);
}

function expectOperation(payload: OperationEnvelope, expectedKind: string): ProductOperation {
  expect(payload.accepted).toBe(true);
  expect(payload.operation?.id).toBeTruthy();
  expect(payload.operation?.kind).toBe(expectedKind);
  expect(payload.operation?.target_id).toBeTruthy();
  expect(payload.operation?.contract_revision_at_completion ?? 0).toBeGreaterThan(0);
  return payload.operation!;
}

function operationCompletionRevision(operation: ProductOperation): number {
  return (
    operation.contract_revision_at_completion ||
    operation.contract_revision ||
    operation.contract_revision_at_accept + 1
  );
}

function operationEvidence(operation: ProductOperation): Record<string, unknown> {
  return {
    id: operation.id,
    kind: operation.kind,
    status: operation.status,
    targetType: operation.target_type,
    targetId: operation.target_id,
    contractRevision: operationCompletionRevision(operation),
  };
}

function workstreamsById(contract: PhaseContract): Record<string, PhaseContract["workstreams"][number]> {
  return Object.fromEntries(contract.workstreams.map((workstream) => [workstream.id, workstream]));
}

async function completeAgencyPhaseInDependencyOrder(
  request: APIRequestContext,
  fixture: LiveAtlasLegacyConsultFixture,
  whiteboardId: string,
  phaseId: string,
  scorecard: Record<string, unknown>,
  testInfo: TestInfo,
  apiCalls: ApiCall[],
): Promise<{
  whiteboard: WorkWhiteboard;
  contract: PhaseContract;
  afterFoundations: PhaseContract;
  afterContentTiming: PhaseContract;
  synthesisOperation: ProductOperation;
  evaluationOperation: ProductOperation;
}> {
  const foundationalBatch = [
    "account_brief_compilation",
    "strategy_brief",
    "legal_claims_precheck",
    "tech_execution_readiness",
    "media_channel_plan",
    "copy_message_house",
    "analytics_measurement_plan",
    "traffic_dependency_map",
  ];
  for (const workstreamId of foundationalBatch) {
    await completePhaseWorkstream(request, fixture, whiteboardId, phaseId, workstreamId, testInfo, apiCalls);
  }
  const afterFoundations = await fetchPhaseContract(request, fixture, whiteboardId, phaseId, apiCalls);
  const foundationState = workstreamsById(afterFoundations);
  expect(foundationState.content_asset_map?.status).toBe("queued");
  expect(foundationState.timing_flighting_plan?.status).toBe("queued");
  expect(foundationState.deployment_readiness_plan?.status).toBe("blocked");

  for (const workstreamId of ["content_asset_map", "timing_flighting_plan"]) {
    await completePhaseWorkstream(request, fixture, whiteboardId, phaseId, workstreamId, testInfo, apiCalls);
  }
  const afterContentTiming = await fetchPhaseContract(request, fixture, whiteboardId, phaseId, apiCalls);
  expect(workstreamsById(afterContentTiming).deployment_readiness_plan?.status).toBe("queued");

  await completePhaseWorkstream(
    request,
    fixture,
    whiteboardId,
    phaseId,
    "deployment_readiness_plan",
    testInfo,
    apiCalls,
  );
  const synthesis = await postData<PhaseActionResponse>(
    request,
    `/api/whiteboards/${whiteboardId}/phases/${phaseId}/synthesize`,
    fixture.accessToken,
    {},
    idempotency(testInfo, `phase-synthesize-${phaseId}`),
    apiCalls,
  );
  const synthesisOperation = expectOperation(synthesis, "phase_synthesize");
  await waitForOperationAndContract(
    request,
    fixture,
    whiteboardId,
    synthesisOperation,
    () => fetchPhaseContract(request, fixture, whiteboardId, phaseId, apiCalls),
    apiCalls,
  );
  const evaluated = await postData<PhaseActionResponse>(
    request,
    `/api/whiteboards/${whiteboardId}/phases/${phaseId}/evaluate`,
    fixture.accessToken,
    { scorecard },
    idempotency(testInfo, `phase-evaluate-${phaseId}`),
    apiCalls,
  );
  const evaluationOperation = expectOperation(evaluated, "phase_gate_evaluate");
  await waitForOperationAndContract(
    request,
    fixture,
    whiteboardId,
    evaluationOperation,
    () => fetchPhaseContract(request, fixture, whiteboardId, phaseId, apiCalls),
    apiCalls,
  );
  return {
    whiteboard: evaluated.whiteboard,
    contract: evaluated.whiteboard_phase_contract,
    afterFoundations,
    afterContentTiming,
    synthesisOperation,
    evaluationOperation,
  };
}

async function completePhaseWorkstream(
  request: APIRequestContext,
  fixture: LiveAtlasLegacyConsultFixture,
  whiteboardId: string,
  phaseId: string,
  workstreamId: string,
  testInfo: TestInfo,
  apiCalls: ApiCall[],
): Promise<void> {
  await postData<{ whiteboard_phase_contract: PhaseContract }>(
    request,
    `/api/whiteboards/${whiteboardId}/phases/${phaseId}/workstreams/${workstreamId}/complete`,
    fixture.accessToken,
    {
      result: {
        summary: `${workstreamId} completed for Legacy DEPP GOLD.`,
        context: {
          company: liveLegacyCompanyName,
          product: "Legacy DEPP GOLD",
          price: "599 MXN",
          budget: "10000 MXN",
        },
      },
    },
    idempotency(testInfo, `phase-complete-${phaseId}-${workstreamId}`),
    apiCalls,
  );
}

async function completeStartedPhase(
  request: APIRequestContext,
  fixture: LiveAtlasLegacyConsultFixture,
  whiteboardId: string,
  phaseId: string,
  scorecard: Record<string, unknown>,
  testInfo: TestInfo,
  apiCalls: ApiCall[],
): Promise<{ whiteboard: WorkWhiteboard; contract: PhaseContract }> {
  const started = await getData<{ whiteboard_phase_contract: PhaseContract }>(
    request,
    `/api/whiteboards/${whiteboardId}/phases/${phaseId}`,
    fixture.accessToken,
    apiCalls,
  );
  for (const workstream of started.whiteboard_phase_contract.workstreams.filter((item) => item.required !== false)) {
    await postData<{ whiteboard_phase_contract: PhaseContract }>(
      request,
      `/api/whiteboards/${whiteboardId}/phases/${phaseId}/workstreams/${workstream.id}/complete`,
      fixture.accessToken,
      {
        result: {
          summary: `${workstream.name || workstream.id} completed for Legacy DEPP GOLD.`,
          context: {
            company: liveLegacyCompanyName,
            product: "Legacy DEPP GOLD",
            price: "599 MXN",
            budget: "10000 MXN",
          },
        },
      },
      idempotency(testInfo, `phase-complete-${phaseId}-${workstream.id}`),
      apiCalls,
    );
  }
  await postData<{ whiteboard_phase_contract: PhaseContract; whiteboard: WorkWhiteboard }>(
    request,
    `/api/whiteboards/${whiteboardId}/phases/${phaseId}/synthesize`,
    fixture.accessToken,
    {},
    idempotency(testInfo, `phase-synthesize-${phaseId}`),
    apiCalls,
  );
  const evaluated = await postData<{ whiteboard_phase_contract: PhaseContract; whiteboard: WorkWhiteboard }>(
    request,
    `/api/whiteboards/${whiteboardId}/phases/${phaseId}/evaluate`,
    fixture.accessToken,
    { scorecard },
    idempotency(testInfo, `phase-evaluate-${phaseId}`),
    apiCalls,
  );
  return { whiteboard: evaluated.whiteboard, contract: evaluated.whiteboard_phase_contract };
}

async function resolveApprovalThroughUi(
  page: Page,
  request: APIRequestContext,
  fixture: LiveAtlasLegacyConsultFixture,
  approvalTaskId: string,
  apiCalls: ApiCall[],
): Promise<{ id: string; status: string }> {
  await openLiveTokenSession(page, request, fixture.accessToken, `/approvals?item=${approvalTaskId}`);
  await expect(page.getByRole("heading", { name: /Decide with context/i })).toBeVisible({ timeout: 30_000 });
  await expect(page.getByText(liveLegacyCompanyName).first()).toBeVisible({ timeout: 30_000 });
  await page.getByPlaceholder(/Add guidance/i).fill("Approved content package for sandbox deployment preparation.");
  const resolveResponsePromise = waitForBackendPostResponse(page, `/api/approvals/${approvalTaskId}/resolve`, 30_000);
  await page.getByRole("button", { name: "Approve with notes" }).click();
  await resolveResponsePromise;
  await expect
    .poll(
      async () =>
        (
          await getData<{ id: string; status: string }>(
            request,
            `/api/approvals/${approvalTaskId}`,
            fixture.accessToken,
            apiCalls,
          )
        ).status,
      { timeout: 30_000 },
    )
    .toBe("approved");
  return getData<{ id: string; status: string }>(
    request,
    `/api/approvals/${approvalTaskId}`,
    fixture.accessToken,
    apiCalls,
  );
}

async function prepareDeploymentThroughUi(
  page: Page,
  request: APIRequestContext,
  fixture: LiveAtlasLegacyConsultFixture,
  whiteboardId: string,
  apiCalls: ApiCall[],
): Promise<{ deployment_contract: DeploymentContract; whiteboard: WorkWhiteboard; operation: ProductOperation }> {
  await openLiveTokenSession(page, request, fixture.accessToken, `/companies/${fixture.companyId}`);
  await page.getByTestId("whiteboard-panel").scrollIntoViewIfNeeded();
  const deploymentResponsePromise = waitForBackendPostResponse(
    page,
    `/api/whiteboards/${whiteboardId}/deployment/prepare`,
    60_000,
  );
  await page.getByTestId("whiteboard-prepare-deployment-button").click();
  const response = await deploymentResponsePromise;
  const payload = await responseData<DeploymentActionResponse>(
    response,
    `POST /api/whiteboards/${whiteboardId}/deployment/prepare`,
  );
  const operation = expectOperation(payload, "deployment_prepare");
  await waitForOperationAndContract(
    request,
    fixture,
    whiteboardId,
    operation,
    () => fetchDeploymentContract(request, fixture, whiteboardId, apiCalls),
    apiCalls,
  );
  await expect(page.getByTestId("whiteboard-deployment-section")).toContainText(/Receipt|Blocked/i, {
    timeout: 30_000,
  });
  const deploymentContract = await fetchDeploymentContract(request, fixture, whiteboardId, apiCalls);
  const whiteboard = await getData<{ whiteboard: WorkWhiteboard }>(
    request,
    `/api/whiteboards/${whiteboardId}`,
    fixture.accessToken,
    apiCalls,
  );
  return { deployment_contract: deploymentContract, whiteboard: whiteboard.whiteboard, operation };
}

async function startPerformanceThroughUi(
  page: Page,
  request: APIRequestContext,
  fixture: LiveAtlasLegacyConsultFixture,
  whiteboardId: string,
  apiCalls: ApiCall[],
): Promise<{ performance_contract: PerformanceContract; whiteboard: WorkWhiteboard; operation: ProductOperation }> {
  await openLiveTokenSession(page, request, fixture.accessToken, `/companies/${fixture.companyId}`);
  await page.getByTestId("whiteboard-panel").scrollIntoViewIfNeeded();
  const performanceResponsePromise = waitForBackendPostResponse(
    page,
    `/api/whiteboards/${whiteboardId}/performance/start`,
    60_000,
  );
  await page.getByTestId("whiteboard-start-performance-button").click();
  const response = await performanceResponsePromise;
  const payload = await responseData<PerformanceActionResponse>(
    response,
    `POST /api/whiteboards/${whiteboardId}/performance/start`,
  );
  const operation = expectOperation(payload, "performance_start");
  await waitForOperationAndContract(
    request,
    fixture,
    whiteboardId,
    operation,
    () => fetchPerformanceContract(request, fixture, whiteboardId, apiCalls),
    apiCalls,
  );
  await expect(page.getByTestId("whiteboard-performance-section")).toContainText(/Receipt|Blocked|Metrics/i, {
    timeout: 30_000,
  });
  await waitForPerformanceMetricSnapshot(
    () => fetchPerformanceContract(request, fixture, whiteboardId, apiCalls),
    30_000,
  );
  const performanceContract = await fetchPerformanceContract(request, fixture, whiteboardId, apiCalls);
  const whiteboard = await getData<{ whiteboard: WorkWhiteboard }>(
    request,
    `/api/whiteboards/${whiteboardId}`,
    fixture.accessToken,
    apiCalls,
  );
  return { performance_contract: performanceContract, whiteboard: whiteboard.whiteboard, operation };
}

async function assertWorkspaceRendering(
  browser: Browser,
  page: Page,
  request: APIRequestContext,
  fixture: LiveAtlasLegacyConsultFixture,
  whiteboardId: string,
  apiCalls: ApiCall[],
): Promise<void> {
  await openLiveTokenSession(page, request, fixture.accessToken, `/companies/${fixture.companyId}`);
  await page.waitForLoadState("networkidle");
  await expect(page.getByText(liveLegacyCompanyName).first()).toBeVisible({ timeout: 30_000 });
  await page.getByTestId("communication-panel").scrollIntoViewIfNeeded();
  await expect(page.getByTestId("communication-panel")).toBeVisible({ timeout: 30_000 });
  await page.getByTestId("whiteboard-panel").scrollIntoViewIfNeeded();
  await expect(page.getByTestId("whiteboard-panel")).toBeVisible({ timeout: 30_000 });
  await expect(page.getByTestId("whiteboard-summary")).toContainText(/DEPP GOLD/i, { timeout: 30_000 });
  await page.getByTestId("whiteboard-board").scrollIntoViewIfNeeded();
  await expect(page.getByTestId("whiteboard-board")).toBeVisible({ timeout: 30_000 });
  await expect(page.getByTestId("whiteboard-board")).toContainText(/Strategy|Content|Channel|Analytics/i, {
    timeout: 30_000,
  });
  const startButtons = page.locator('[data-testid^="whiteboard-card-start-"]');
  if ((await startButtons.count()) > 0) {
    await startButtons.first().click();
    await expect(page.locator('[data-testid^="whiteboard-card-status-"]').first()).toContainText(/in_progress/i, {
      timeout: 30_000,
    });
  }
  await page.getByTestId("whiteboard-phase-section").scrollIntoViewIfNeeded();
  await expect(page.getByTestId("whiteboard-phase-section")).toBeVisible({ timeout: 30_000 });
  await expect(page.getByTestId(`whiteboard-phase-${agencyPhaseId}`)).toContainText(
    /Strategy brief|Deployment readiness/i,
  );
  await page.getByTestId("whiteboard-deployment-section").scrollIntoViewIfNeeded();
  await expect(page.getByTestId("whiteboard-deployment-section")).toBeVisible({ timeout: 30_000 });
  await page.getByTestId("whiteboard-performance-section").scrollIntoViewIfNeeded();
  await expect(page.getByTestId("whiteboard-performance-section")).toBeVisible({ timeout: 30_000 });

  const customerContext = await browser.newContext();
  const customerPage = await customerContext.newPage();
  const customerRequests = collectLiveProductModeApiRequests(customerPage);
  try {
    await openLiveTokenSession(
      customerPage,
      request,
      fixture.legacyOwnerAccessToken,
      `/companies/${fixture.companyId}`,
    );
    await customerPage.waitForLoadState("networkidle");
    await customerPage.getByTestId("communication-panel").scrollIntoViewIfNeeded();
    await expect(customerPage.getByTestId("communication-panel")).toBeVisible({ timeout: 30_000 });
    await customerPage.getByTestId("whiteboard-panel").scrollIntoViewIfNeeded();
    await expect(customerPage.getByTestId("whiteboard-panel")).toBeVisible({ timeout: 30_000 });
    await expect(customerPage.getByTestId("whiteboard-summary")).toContainText(/DEPP GOLD/i, { timeout: 30_000 });
    await customerPage.getByTestId("whiteboard-board").scrollIntoViewIfNeeded();
    await expect(customerPage.getByTestId("whiteboard-board")).toBeVisible({ timeout: 30_000 });
    await expect(customerPage.locator('[data-testid^="whiteboard-card-reassign-"]')).toHaveCount(0);
    await expect(
      customerPage.getByText(/private config|pack manifest|raw prompt|debug trace|evidence bundle/i),
    ).toHaveCount(0);
  } finally {
    apiCalls.push(...customerRequests.map((call) => ({ method: call.method, pathname: call.pathname })));
    await customerContext.close();
  }

  const otherContext = await browser.newContext();
  const otherPage = await otherContext.newPage();
  const otherRequests = collectLiveProductModeApiRequests(otherPage);
  try {
    await openLiveTokenSession(otherPage, request, fixture.otherClientAccessToken, "/companies");
    await expect(otherPage.getByRole("link", { name: legacyCompanyCardName })).toHaveCount(0);
    await expect(otherPage.getByText(whiteboardId)).toHaveCount(0);
  } finally {
    apiCalls.push(...otherRequests.map((call) => ({ method: call.method, pathname: call.pathname })));
    await otherContext.close();
  }
}

async function expectOtherClientIsolation(
  request: APIRequestContext,
  fixture: LiveAtlasLegacyConsultFixture,
  threadId: string,
  whiteboardId: string,
  operationIds: string[],
  apiCalls: ApiCall[],
): Promise<void> {
  const denied = await Promise.all([
    rawGet(request, `/api/graphs/${fixture.companyId}`, fixture.otherClientAccessToken, apiCalls),
    rawGet(request, `/api/communication/threads/${threadId}`, fixture.otherClientAccessToken, apiCalls),
    rawGet(request, `/api/whiteboards/${whiteboardId}`, fixture.otherClientAccessToken, apiCalls),
    rawGet(request, `/api/whiteboards/${whiteboardId}/board`, fixture.otherClientAccessToken, apiCalls),
    rawGet(request, `/api/whiteboards/${whiteboardId}/deployment`, fixture.otherClientAccessToken, apiCalls),
    rawGet(request, `/api/whiteboards/${whiteboardId}/performance`, fixture.otherClientAccessToken, apiCalls),
    ...operationIds.map((operationId) =>
      rawGet(
        request,
        `/api/whiteboards/${whiteboardId}/operations/${operationId}`,
        fixture.otherClientAccessToken,
        apiCalls,
      ),
    ),
  ]);
  for (const response of denied) {
    expect(response.status()).toBe(404);
  }
}

async function expectNoFunctionCompaniesCreated(
  request: APIRequestContext,
  fixture: LiveAtlasLegacyConsultFixture,
  apiCalls: ApiCall[],
): Promise<void> {
  const companies = await getData<
    Array<{ name: string }> | { graphs?: Array<{ name: string }>; companies?: Array<{ name: string }> }
  >(request, "/api/graphs/", fixture.accessToken, apiCalls);
  const list = Array.isArray(companies) ? companies : [...(companies.graphs ?? []), ...(companies.companies ?? [])];
  const names = list.map((company) => company.name);
  expect(names.filter((name) => name === liveLegacyCompanyName).length).toBeGreaterThanOrEqual(1);
  for (const forbidden of forbiddenLegacyFunctionCompanies) {
    expect(names).not.toContain(forbidden);
  }
}

function expectNoVerticalRoutes(apiRequests: Array<{ method: string; pathname: string }>): void {
  const disallowed = apiRequests.filter((request) =>
    /\/api\/(?:marketing|atlas|legacy)(?:\/|$)/i.test(request.pathname),
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

async function getData<T>(
  request: APIRequestContext,
  path: string,
  accessToken: string,
  apiCalls: ApiCall[],
): Promise<T> {
  const response = await rawGet(request, path, accessToken, apiCalls);
  return responseData<T>(response, `GET ${path}`);
}

async function postData<T>(
  request: APIRequestContext,
  path: string,
  accessToken: string,
  data: unknown,
  idempotencyKey: string,
  apiCalls: ApiCall[],
): Promise<T> {
  const response = await rawPost(request, path, accessToken, data, idempotencyKey, apiCalls);
  return responseData<T>(response, `POST ${path}`);
}

async function postOrPatchData<T>(
  method: "POST" | "PATCH",
  request: APIRequestContext,
  path: string,
  accessToken: string,
  data: unknown,
  idempotencyKey: string,
  apiCalls: ApiCall[],
): Promise<T> {
  const response =
    method === "PATCH"
      ? await request.patch(`${API_BASE_URL}${path}`, {
          headers: authHeaders(accessToken, idempotencyKey),
          data,
          failOnStatusCode: false,
        })
      : await rawPost(request, path, accessToken, data, idempotencyKey, apiCalls);
  if (method === "PATCH") {
    apiCalls.push({ method, pathname: new URL(`${API_BASE_URL}${path}`).pathname });
  }
  return responseData<T>(response, `${method} ${path}`);
}

async function rawGet(
  request: APIRequestContext,
  path: string,
  accessToken: string,
  apiCalls: ApiCall[],
): Promise<APIResponse> {
  apiCalls.push({ method: "GET", pathname: new URL(`${API_BASE_URL}${path}`).pathname });
  return request.get(`${API_BASE_URL}${path}`, {
    headers: authHeaders(accessToken),
    failOnStatusCode: false,
  });
}

async function rawPost(
  request: APIRequestContext,
  path: string,
  accessToken: string,
  data: unknown,
  idempotencyKey: string,
  apiCalls: ApiCall[],
): Promise<APIResponse> {
  apiCalls.push({ method: "POST", pathname: new URL(`${API_BASE_URL}${path}`).pathname });
  return request.post(`${API_BASE_URL}${path}`, {
    headers: authHeaders(accessToken, idempotencyKey),
    data,
    failOnStatusCode: false,
  });
}

async function responseData<T>(response: APIResponse, action: string): Promise<T> {
  if (!response.ok()) {
    throw new Error(`${action} failed with ${response.status()}: ${await response.text()}`);
  }
  const body = (await response.json()) as ApiSuccess<T>;
  return body.data;
}

function authHeaders(accessToken: string, idempotencyKey?: string): Record<string, string> {
  return {
    Authorization: `Bearer ${accessToken}`,
    ...(idempotencyKey ? { "Idempotency-Key": idempotencyKey } : {}),
  };
}

function idempotency(testInfo: TestInfo, suffix: string): string {
  return `${liveProductModeRunNamespace(testInfo)}:${suffix}`.slice(0, 240);
}
