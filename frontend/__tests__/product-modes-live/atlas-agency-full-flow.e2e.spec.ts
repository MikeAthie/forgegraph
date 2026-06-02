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
const liveApiRoutePattern = /.*\/api\/.*/;
const liveApiRouteStates = new WeakMap<Page, { accessToken: string }>();
const liveSkipReason = liveLlmSkipReason();
const legacyCompanyCardName = /^Legacy Eyewear\b/i;
const agencyPhaseId = "digital_marketing_pro.v1.atlas_agency_work_graph";
const deploymentPolicyId = "digital_marketing_pro.v1.atlas_launch_deployment";
const performancePolicyId = "digital_marketing_pro.v1.atlas_performance_review";
const requireWhiteboardBoardKafka =
  (process.env.PLAYWRIGHT_ATLAS_REQUIRE_BOARD_KAFKA ?? "false").toLowerCase() === "true";
const atlasP2RealConnectors = (process.env.ATLAS_P2_REAL_CONNECTORS ?? "false").toLowerCase() === "true";
const liveAtlasFullFlowTimeoutMs = Number(
  process.env.LIVE_ATLAS_FULL_FLOW_TIMEOUT_MS ?? LIVE_LLM_RUN_TIMEOUT_MS * 2 + 900_000,
);
const legacyCampaignRequest =
  "Can you create a campaign for Legacy DEPP GOLD with 10,000 MXN budget across email, WhatsApp, Instagram, Facebook, TikTok, and a landing page? Price is 599 MXN. Inventory is limited. Please create a strategy and execution plan?";
const followUpCampaignRequest =
  "Create the next Legacy DEPP GOLD campaign using prior approved learnings. Keep appointment proof central, avoid unverified WhatsApp exclusivity claims, and do not assume WhatsApp or landing-page connectors are available unless approved.";
const helperAssistedSteps = [
  "Follow-up memory uplift uses backend communication and phase APIs because guided follow-up campaign authoring and memory-review UI are not available yet.",
  "Isolation and durable-state checks use backend API to verify DB-owned state directly.",
  "Evidence collection uses backend API reads to attach durable IDs, revisions, and operation state.",
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
type RouteRequestResponse = {
  classification: RequestClassification;
  whiteboard: WorkWhiteboard | null;
  routing_record_ids: string[];
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
type MemoryObservation = {
  id: string;
  graph_id?: string | null;
  run_id?: string | null;
  scope: string;
  type: string;
  title: string;
  content: string;
  topic_key: string;
};
type MemoryContextResponse = {
  observations: MemoryObservation[];
  degraded: boolean;
  strategies: string[];
  limit: number;
};
type DurableStateEvidence = {
  whiteboardId: string;
  whiteboardStatus: string;
  boardCardCount: number;
  phase: ContractReadiness & { phaseId: string; status: string; workstreamCount: number };
  deployment: ContractReadiness & { policyId: string; status: string; channelCount: number };
  performance: ContractReadiness & {
    policyId: string;
    status: string;
    sourceCount: number;
    metricSnapshotId?: string;
    reportRunId?: string;
    evaluationId?: string;
  };
  approval: { id: string; status: string; resolvedAt?: string | null };
  operations: Array<Record<string, unknown>>;
};
type MemoryReadinessEvidence = {
  observationId: string;
  graphId?: string | null;
  topicKey: string;
  title: string;
  content: string;
  contextObservationIds: string[];
  strategies: string[];
  degraded: boolean;
};
type MemoryUpliftEvidence = {
  threadId: string;
  messageId: string;
  whiteboardId: string;
  whiteboardStatus: string;
  classification: RequestClassification["classification"];
  confidence: number;
  routingRecordIds: string[];
  memoryObservationId: string;
  contextObservationIds: string[];
  reusedLearnings: string[];
  avoidedRejectedItems: string[];
  workstreamMemoryRefs: Array<{
    workstreamId: string;
    memoryObservationId: string;
    reusedLearnings: string[];
    avoidedRejectedItems: string[];
  }>;
  operationIds: string[];
  operations: Record<string, Record<string, unknown>>;
  gateResult?: string;
};
type ReleaseScoreSummary = {
  passed: boolean;
  atlasQuality: { score: number; checks: Record<string, boolean> };
  systemReliability: { score: number; checks: Record<string, boolean> };
  runtimeIntegrity: { score: number; checks: Record<string, boolean> };
};
type WhiteboardBoardKafkaTransportEvidence = {
  required: boolean;
  available: boolean;
  transport: "whiteboard_board_kafka";
  authoritative_state_source: "backend_db";
  enabled: boolean;
  topic: string;
  consumer_group: string;
  outbox: {
    pending: number;
    published: number;
    failed: number;
    deferred: number;
    total: number;
    backlog: number;
  };
  receipts: {
    handled: number;
    ignored: number;
    failed: number;
    total: number;
    idempotent_duplicate_policy?: string;
  };
  dead_letters: {
    active_count: number;
    total: number;
    recent: Array<Record<string, unknown>>;
  };
  recent_receipts: Array<Record<string, unknown>>;
  generated_at: string;
  error?: string;
  status?: number;
};
type ProjectionLagEvidence = {
  available: boolean;
  organization_id?: string;
  projection?: {
    status?: string;
    lag_seconds?: number;
    projection_lag_ms?: number;
    last_sequence?: number;
    state_feed_version?: number;
  };
  cursors?: Array<{ projection_name: string; last_sequence: number; status: string }>;
  active_dead_letters?: Array<Record<string, unknown>>;
  generated_at?: string;
  error?: string;
  status?: number;
};
type ReviewBoardEvaluationEvidence = {
  evaluationId: string;
  status: string;
  score: number;
  grade: string;
  schemaVersion: string;
  decision: string;
  approvalGate?: Record<string, unknown>;
  signalIds: string[];
  findingCount: number;
  blockingFindingCount: number;
};

test.use({ video: "on" });

test.describe("Live ATLAS agency full product loop", () => {
  test.skip(Boolean(liveSkipReason), liveSkipReason ?? "Live ATLAS agency full-flow suite is disabled.");

  test("PM-LIVE-ATLAS-AGENCY-001: Legacy request becomes strategy, content, approval, deployment evidence, performance review, and optimization", async ({
    browser,
    page,
    request,
  }, testInfo) => {
    test.setTimeout(liveAtlasFullFlowTimeoutMs);

    const apiCalls: ApiCall[] = [];
    const pageRequests = collectLiveProductModeApiRequests(page);
    const fixture = await seedLiveAtlasLegacyConsultProductMode(request, testInfo);
    const packHealth = await assertOperatingModelPackHealth(request, fixture, apiCalls);
    await configureAtlasAgencyConnectorAvailability(page, request, fixture, apiCalls);

    const { thread, message } = await createLegacyRequestMessageThroughUi(page, request, fixture, apiCalls);
    await expectWhiteboardCountForMessage(request, fixture, message.id, 0, apiCalls);
    const routed = await routeRequestMessageThroughUi(page, request, fixture, message.id, apiCalls);
    expect(routed.classification.classification).toBe("NEW_REQUEST");
    expect(routed.classification.confidence).toBeGreaterThan(0);
    expect(routed.whiteboard.company_id).toBe(fixture.companyId);
    expect(routed.whiteboard.status).toBe("onboarding");
    await expectWhiteboardCountForMessage(request, fixture, message.id, 1, apiCalls);

    const whiteboard = await completeOnboarding(page, request, fixture, routed.whiteboard.id, apiCalls);
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

    const agency = await completeAgencyPhaseInDependencyOrderThroughUi(
      page,
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

    const report = await reportPerformanceThroughUi(page, request, fixture, whiteboard.id, apiCalls);
    const reportOperation = report.operation;
    expect(report.performance_contract.current_state.report_run_id).toBeTruthy();

    const evaluation = await evaluatePerformanceThroughUi(page, request, fixture, whiteboard.id, apiCalls);
    const performanceEvaluationOperation = evaluation.operation;
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

    const operationsByAction = {
      phaseStart: phaseStartOperation,
      synthesis: agency.synthesisOperation,
      gateEvaluation: agency.evaluationOperation,
      deploymentPrepare: deployment.operation,
      performanceStart: performance.operation,
      performanceReport: reportOperation,
      performanceEvaluation: performanceEvaluationOperation,
    };
    const operationLifecycle = assertOperationLifecycleEvidence(operationsByAction);
    const memoryReadiness = await assertBackendMemoryReadiness(request, fixture, testInfo, apiCalls);
    const memoryUplift = await runFollowUpMemoryUplift(request, fixture, testInfo, memoryReadiness, apiCalls);
    const durableState = await assertBackendDurableStateReadable(
      request,
      fixture,
      whiteboard.id,
      agencyPhaseId,
      approvalTaskId!,
      Object.values(operationsByAction).map((operation) => operation.id),
      apiCalls,
    );

    await expectOtherClientIsolation(
      request,
      fixture,
      thread.id,
      whiteboard.id,
      Object.values(operationsByAction).map((operation) => operation.id),
      [memoryReadiness.observationId],
      apiCalls,
    );
    await expectOtherClientIsolation(
      request,
      fixture,
      memoryUplift.threadId,
      memoryUplift.whiteboardId,
      memoryUplift.operationIds,
      [memoryReadiness.observationId],
      apiCalls,
    );
    await assertWorkspaceRendering(browser, page, request, fixture, whiteboard.id, apiCalls);
    const projectionLag = await collectProjectionLagEvidence(request, fixture, apiCalls);
    const whiteboardBoardKafka = await collectWhiteboardBoardKafkaEvidence(
      request,
      fixture,
      whiteboard.id,
      requireWhiteboardBoardKafka,
      apiCalls,
    );

    let allApiRequests = [
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
    expect(allApiRequests.some((call) => call.pathname.startsWith("/api/memory/"))).toBe(true);
    await expectNoFunctionCompaniesCreated(request, fixture, apiCalls);
    const routes = Array.from(new Set(allApiRequests.map((call) => call.pathname))).sort();
    const releaseScore = buildReleaseScoreSummary({
      agency: agency.contract,
      initialWorkstreams,
      deploymentContract,
      blockedDeployment,
      performanceContract: evaluation.performance_contract,
      operationLifecycle,
      durableState,
      routes,
      memoryReadiness,
      memoryUplift,
    });
    expect(releaseScore.passed).toBe(true);
    const reviewBoard = await persistAtlasAgencyReviewBoardEvaluation(
      request,
      fixture,
      whiteboard.id,
      releaseScore,
      durableState,
      memoryUplift,
      apiCalls,
      testInfo,
    );
    allApiRequests = [
      ...pageRequests,
      ...apiCalls.map((call) => ({
        method: call.method,
        pathname: call.pathname,
        url: `${API_BASE_URL}${call.pathname}`,
      })),
    ];
    expectNoVerticalRoutes(allApiRequests);
    const finalRoutes = Array.from(new Set(allApiRequests.map((call) => call.pathname))).sort();

    await testInfo.attach("atlas-agency-full-flow-evidence", {
      body: JSON.stringify(
        {
          evidenceVersion: "atlas_agency_full_flow_v4",
          namespace: liveProductModeRunNamespace(testInfo),
          packHealth,
          classification: routed.classification,
          ids: {
            companyId: fixture.companyId,
            threadId: thread.id,
            messageId: message.id,
            whiteboardId: whiteboard.id,
            phaseId: agencyPhaseId,
            deploymentPolicyId,
            performancePolicyId,
          },
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
            operationLifecycle: {
              phaseStart: operationLifecycle.phaseStart,
              synthesis: operationLifecycle.synthesis,
              gateEvaluation: operationLifecycle.gateEvaluation,
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
            readiness: {
              contractRevision:
                deploymentContract.contract_revision ?? deploymentContract.current_state?.contract_revision,
              lastOperationId:
                deploymentContract.last_operation_id ?? deploymentContract.current_state?.last_operation_id,
            },
          },
          performance: {
            status: evaluation.performance_contract.status,
            operations: {
              start: operationEvidence(performance.operation),
              report: operationEvidence(reportOperation),
              evaluation: operationEvidence(performanceEvaluationOperation),
            },
            operationLifecycle: {
              start: operationLifecycle.performanceStart,
              report: operationLifecycle.performanceReport,
              evaluation: operationLifecycle.performanceEvaluation,
            },
            metricSnapshotId: evaluation.performance_contract.current_state.metric_snapshot_id,
            reportRunId: evaluation.performance_contract.current_state.report_run_id,
            evaluationId: evaluation.performance_contract.current_state.evaluation_id,
            routingRecordIds: evaluation.performance_contract.current_state.routing_record_ids,
          },
          durableState,
          memoryReadiness,
          memoryUplift,
          projectionLag,
          whiteboardBoardKafka,
          reviewBoard,
          connectorProviderEvidence: buildConnectorProviderEvidence(
            deploymentContract,
            evaluation.performance_contract,
          ),
          releaseScore,
          helperAssistedSteps,
          routes: finalRoutes,
          kafkaEnabled: {
            communication: (process.env.COMMUNICATION_KAFKA_ENABLED ?? "false").toLowerCase() === "true",
            whiteboardBoard: whiteboardBoardKafka.enabled,
            whiteboardBoardRequired: requireWhiteboardBoardKafka,
          },
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

async function waitForBackendResponse(
  page: Page,
  method: "GET" | "POST" | "PATCH",
  pathPart: string,
  timeout = 60_000,
): Promise<APIResponse> {
  const response = await page.waitForResponse(
    (candidate) => candidate.url().includes(pathPart) && candidate.request().method() === method,
    { timeout },
  );
  expect(response.ok()).toBeTruthy();
  return response;
}

async function configureAtlasAgencyConnectorAvailability(
  page: Page,
  request: APIRequestContext,
  fixture: LiveAtlasLegacyConsultFixture,
  apiCalls: ApiCall[],
): Promise<void> {
  await openLiveTokenSession(page, request, fixture.accessToken, `/companies/${fixture.companyId}`);
  await page.getByTestId("connector-management-panel").scrollIntoViewIfNeeded();
  await expect(page.getByTestId("connector-management-panel")).toBeVisible({ timeout: 30_000 });
  await page.getByTestId("connector-sandbox-core-preset").click();
  const patchResponsePromise = waitForBackendResponse(
    page,
    "PATCH",
    `/api/companies/${fixture.companyId}/packs/`,
    30_000,
  );
  await page.getByTestId("connector-save-button").click();
  await patchResponsePromise;
  for (const connectorId of ["email_connector", "social_connector", "analytics_connector"]) {
    await expect(page.getByTestId(`connector-toggle-${connectorId}`)).toBeChecked({ timeout: 30_000 });
  }

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
  const config = installation.public_config ?? installation.config ?? {};
  expect(config.available_connectors).toEqual(
    expect.arrayContaining(["email_connector", "social_connector", "analytics_connector"]),
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
  apiCalls: ApiCall[],
): Promise<WorkWhiteboard> {
  await openLiveTokenSession(page, request, fixture.accessToken, `/companies/${fixture.companyId}`);
  await page.getByTestId("whiteboard-panel").scrollIntoViewIfNeeded();
  await page.getByTestId("whiteboard-context-edit-toggle").click();
  await expect(page.getByTestId("whiteboard-context-editor")).toBeVisible({ timeout: 30_000 });
  await page
    .getByTestId("whiteboard-context-objective")
    .fill("Launch a measured demand campaign for Legacy DEPP GOLD without unsupported claims.");
  await page.getByTestId("whiteboard-context-budget").fill("10000 MXN");
  await page.getByTestId("whiteboard-context-timeline").fill("two-week launch window");
  await page.getByTestId("whiteboard-context-constraints").fill(
    JSON.stringify(
      {
        inventory: "limited",
        compliance: "avoid unsupported medical or vision claims",
        legal_compliance_constraints: "client approval required before publishing",
        visual_constraints: "premium product imagery only; no medical outcome visuals",
      },
      null,
      2,
    ),
  );
  await page.getByTestId("whiteboard-context-stakeholders").fill(
    JSON.stringify(
      {
        segment: "Mexico City eyewear buyers looking for premium gold-tone frames",
        approval_owner: "Legacy owner",
      },
      null,
      2,
    ),
  );
  await page.getByTestId("whiteboard-context-resources").fill(
    JSON.stringify(
      {
        scope: "strategy, content, deployment preparation, and performance review",
        product: "Legacy DEPP GOLD",
        offer: "Legacy DEPP GOLD at 599 MXN",
        success_metrics: ["qualified appointment intent", "email click-through", "social engagement"],
      },
      null,
      2,
    ),
  );
  await page.getByTestId("whiteboard-context-delivery").fill(
    JSON.stringify(
      {
        requested_channels: ["email", "WhatsApp", "Instagram", "Facebook", "TikTok", "landing page"],
        connectors: ["email_connector", "social_connector", "analytics_connector"],
        connector_readiness: {
          email_connector: "sandbox",
          social_connector: "sandbox",
          analytics_connector: "sandbox",
          whatsapp_connector: "not_configured",
          landing_page_connector: "not_configured",
        },
      },
      null,
      2,
    ),
  );
  await page
    .getByTestId("whiteboard-context-assumptions")
    .fill(
      "Email and social channels can be sandboxed; WhatsApp and landing-page connectors are not configured.\nSocial provider publishing remains disabled unless a generic social connector is explicitly configured.",
    );
  const patchResponsePromise = waitForBackendResponse(page, "PATCH", `/api/whiteboards/${whiteboardId}`, 30_000);
  await page.getByTestId("whiteboard-context-save-button").click();
  await patchResponsePromise;
  await expect(page.getByTestId("whiteboard-context-editor")).toBeHidden({ timeout: 30_000 });
  const readyResponsePromise = waitForBackendPostResponse(
    page,
    `/api/whiteboards/${whiteboardId}/ready-for-planning`,
    30_000,
  );
  await page.getByTestId("whiteboard-mark-ready-button").click();
  await readyResponsePromise;
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
    terminal: operation.terminal,
    targetType: operation.target_type,
    targetId: operation.target_id,
    contractRevisionAtAccept: operation.contract_revision_at_accept,
    contractRevisionAtCompletion: operation.contract_revision_at_completion,
    contractRevision: operationCompletionRevision(operation),
  };
}

function assertOperationLifecycleEvidence(
  operations: Record<string, ProductOperation>,
): Record<string, Record<string, unknown>> {
  const evidence: Record<string, Record<string, unknown>> = {};
  for (const [action, operation] of Object.entries(operations)) {
    expect(operation.id).toBeTruthy();
    expect(operation.status).toBe("completed");
    expect(operation.terminal).toBe(true);
    expect(operation.error ?? null).toBeNull();
    expect(operation.contract_revision_at_accept).toBeGreaterThanOrEqual(0);
    expect(operation.contract_revision_at_completion).toBeGreaterThanOrEqual(operation.contract_revision_at_accept);
    expect(operationCompletionRevision(operation)).toBeGreaterThan(0);
    evidence[action] = operationEvidence(operation);
  }
  return evidence;
}

function workstreamsById(contract: PhaseContract): Record<string, PhaseContract["workstreams"][number]> {
  return Object.fromEntries(contract.workstreams.map((workstream) => [workstream.id, workstream]));
}

async function assertBackendDurableStateReadable(
  request: APIRequestContext,
  fixture: LiveAtlasLegacyConsultFixture,
  whiteboardId: string,
  phaseId: string,
  approvalTaskId: string,
  operationIds: string[],
  apiCalls: ApiCall[],
): Promise<DurableStateEvidence> {
  const persistedWhiteboard = await getData<{ whiteboard: WorkWhiteboard }>(
    request,
    `/api/whiteboards/${whiteboardId}`,
    fixture.accessToken,
    apiCalls,
  );
  expect(persistedWhiteboard.whiteboard.id).toBe(whiteboardId);
  expect(persistedWhiteboard.whiteboard.company_id).toBe(fixture.companyId);

  const board = await fetchWhiteboardBoard(request, fixture, whiteboardId, apiCalls);
  expect(board.whiteboard_id).toBe(whiteboardId);
  expect(board.cards.length).toBeGreaterThan(0);

  const phase = await fetchPhaseContract(request, fixture, whiteboardId, phaseId, apiCalls);
  expect(phase.phase_id).toBe(phaseId);
  expect(phase.current_state.all_workstreams_completed).toBe(true);
  expect(phase.current_state.gate?.result).toBe("pass");
  expect(phase.contract_revision ?? phase.current_state.contract_revision ?? 0).toBeGreaterThan(0);
  expect(phase.last_operation_id ?? phase.current_state.last_operation_id).toBeTruthy();

  const deployment = await fetchDeploymentContract(request, fixture, whiteboardId, apiCalls);
  expect(deployment.policy_id).toBe(deploymentPolicyId);
  expect(["partial", "prepared", "executed"]).toContain(deployment.status);
  expect(deployment.contract_revision ?? deployment.current_state?.contract_revision ?? 0).toBeGreaterThan(0);
  expect(deployment.last_operation_id ?? deployment.current_state?.last_operation_id).toBeTruthy();

  const performance = await fetchPerformanceContract(request, fixture, whiteboardId, apiCalls);
  expect(performance.policy_id).toBe(performancePolicyId);
  expect(performance.current_state.metric_snapshot_id).toBeTruthy();
  expect(performance.current_state.report_run_id).toBeTruthy();
  expect(performance.current_state.evaluation_id).toBeTruthy();
  expect(performance.contract_revision ?? performance.current_state.contract_revision ?? 0).toBeGreaterThan(0);
  expect(performance.last_operation_id ?? performance.current_state.last_operation_id).toBeTruthy();

  const approval = await getData<{ id: string; status: string; resolved_at?: string | null }>(
    request,
    `/api/approvals/${approvalTaskId}`,
    fixture.accessToken,
    apiCalls,
  );
  expect(approval.id).toBe(approvalTaskId);
  expect(approval.status).toBe("approved");

  const operations: Array<Record<string, unknown>> = [];
  for (const operationId of operationIds) {
    const operation = await fetchOperation(request, fixture, whiteboardId, operationId, apiCalls);
    expect(operation.status).toBe("completed");
    expect(operation.terminal).toBe(true);
    operations.push(operationEvidence(operation));
  }

  return {
    whiteboardId,
    whiteboardStatus: persistedWhiteboard.whiteboard.status,
    boardCardCount: board.cards.length,
    phase: {
      phaseId: phase.phase_id,
      status: phase.current_state.status,
      workstreamCount: phase.workstreams.length,
      contract_revision: phase.contract_revision ?? phase.current_state.contract_revision,
      last_operation_id: phase.last_operation_id ?? phase.current_state.last_operation_id,
      terminal: phase.terminal ?? phase.current_state.terminal,
      pending_count: phase.pending_count ?? phase.current_state.pending_count,
      running_count: phase.running_count ?? phase.current_state.running_count,
      blocked_count: phase.blocked_count ?? phase.current_state.blocked_count,
      completed_count: phase.completed_count ?? phase.current_state.completed_count,
    },
    deployment: {
      policyId: deployment.policy_id,
      status: deployment.status,
      channelCount: deployment.channels.length,
      contract_revision: deployment.contract_revision ?? deployment.current_state?.contract_revision,
      last_operation_id: deployment.last_operation_id ?? deployment.current_state?.last_operation_id,
      terminal: deployment.terminal ?? deployment.current_state?.terminal,
      pending_count: deployment.pending_count ?? deployment.current_state?.pending_count,
      running_count: deployment.running_count ?? deployment.current_state?.running_count,
      blocked_count: deployment.blocked_count ?? deployment.current_state?.blocked_count,
      completed_count: deployment.completed_count ?? deployment.current_state?.completed_count,
    },
    performance: {
      policyId: performance.policy_id,
      status: performance.status,
      sourceCount: performance.sources.length,
      contract_revision: performance.contract_revision ?? performance.current_state.contract_revision,
      last_operation_id: performance.last_operation_id ?? performance.current_state.last_operation_id,
      terminal: performance.terminal ?? performance.current_state.terminal,
      pending_count: performance.pending_count ?? performance.current_state.pending_count,
      running_count: performance.running_count ?? performance.current_state.running_count,
      blocked_count: performance.blocked_count ?? performance.current_state.blocked_count,
      completed_count: performance.completed_count ?? performance.current_state.completed_count,
      metricSnapshotId: performance.current_state.metric_snapshot_id,
      reportRunId: performance.current_state.report_run_id,
      evaluationId: performance.current_state.evaluation_id,
    },
    approval: {
      id: approval.id,
      status: approval.status,
      resolvedAt: approval.resolved_at,
    },
    operations,
  };
}

async function assertBackendMemoryReadiness(
  request: APIRequestContext,
  fixture: LiveAtlasLegacyConsultFixture,
  testInfo: TestInfo,
  apiCalls: ApiCall[],
): Promise<MemoryReadinessEvidence> {
  const observation = await postData<MemoryObservation>(
    request,
    "/api/memory/observations",
    fixture.accessToken,
    {
      graph_id: fixture.companyId,
      scope: "graph",
      type: "case",
      title: "Legacy follow-up approval learning",
      content:
        "Prior approved learning: keep appointment-proof language, avoid unverified WhatsApp exclusivity claims, and stay within configured email/social sandbox connectors unless more connectors are approved.",
      topic_key: "legacy-follow-up-approval-learning",
    },
    idempotency(testInfo, "memory-follow-up-approval-learning"),
    apiCalls,
  );
  expect(observation.id).toBeTruthy();
  expect(observation.graph_id).toBe(fixture.companyId);
  expect(observation.scope).toBe("graph");

  const context = await fetchMemoryContext(
    request,
    fixture,
    "Legacy WhatsApp appointment proof follow-up approval learning",
    apiCalls,
  );
  const contextObservationIds = context.observations.map((item) => item.id);
  expect(contextObservationIds).toContain(observation.id);
  expect(context.strategies).toContain("fts");

  return {
    observationId: observation.id,
    graphId: observation.graph_id,
    topicKey: observation.topic_key,
    title: observation.title,
    content: observation.content,
    contextObservationIds,
    strategies: context.strategies,
    degraded: context.degraded,
  };
}

async function fetchMemoryContext(
  request: APIRequestContext,
  fixture: LiveAtlasLegacyConsultFixture,
  query: string,
  apiCalls: ApiCall[],
): Promise<MemoryContextResponse> {
  const params = new URLSearchParams({
    graph_id: fixture.companyId,
    query,
    limit: "5",
  });
  return getData<MemoryContextResponse>(
    request,
    `/api/memory/observations/context?${params.toString()}`,
    fixture.accessToken,
    apiCalls,
  );
}

async function runFollowUpMemoryUplift(
  request: APIRequestContext,
  fixture: LiveAtlasLegacyConsultFixture,
  testInfo: TestInfo,
  memoryReadiness: MemoryReadinessEvidence,
  apiCalls: ApiCall[],
): Promise<MemoryUpliftEvidence> {
  const reusedLearnings = [
    "Keep appointment-proof language central to the offer.",
    "Stay within configured email/social sandbox connectors unless more connectors are approved.",
  ];
  const avoidedRejectedItems = [
    "Avoid unverified WhatsApp exclusivity claims.",
    "Do not assume WhatsApp or landing-page connectors are available.",
  ];
  const namespace = liveProductModeRunNamespace(testInfo);
  const threadResponse = await postData<{ thread: CommunicationThread }>(
    request,
    "/api/communication/threads",
    fixture.accessToken,
    {
      company_id: fixture.companyId,
      title: "Legacy DEPP GOLD follow-up campaign",
      thread_type: "support",
      visibility_mode: "mixed",
      source_key: `${namespace}:atlas-follow-up-memory-uplift`,
      metadata: {
        source_memory_observation_id: memoryReadiness.observationId,
        source_memory_topic_key: memoryReadiness.topicKey,
      },
    },
    idempotency(testInfo, "follow-up-memory-thread"),
    apiCalls,
  );
  const messageResponse = await postData<{ message: CommunicationMessage }>(
    request,
    `/api/communication/threads/${threadResponse.thread.id}/messages`,
    fixture.legacyOwnerAccessToken,
    {
      message_kind: "request",
      body: followUpCampaignRequest,
      visibility: "customer",
      metadata: {
        source_memory_observation_id: memoryReadiness.observationId,
        source_memory_topic_key: memoryReadiness.topicKey,
      },
    },
    idempotency(testInfo, "follow-up-memory-message"),
    apiCalls,
  );
  const routed = await routeRequestMessageViaApi(
    request,
    fixture,
    messageResponse.message.id,
    testInfo,
    "follow-up-memory-route",
    apiCalls,
  );
  expect(routed.classification.classification).toBe("NEW_REQUEST");
  expect(routed.classification.confidence).toBeGreaterThan(0);
  const followUpWhiteboard = routed.whiteboard;
  if (!followUpWhiteboard) {
    throw new Error("Follow-up memory request did not create a whiteboard.");
  }
  expect(followUpWhiteboard.company_id).toBe(fixture.companyId);
  expect(followUpWhiteboard.source_message_id).toBe(messageResponse.message.id);

  const context = await fetchMemoryContext(request, fixture, followUpCampaignRequest, apiCalls);
  const contextObservationIds = context.observations.map((item) => item.id);
  expect(contextObservationIds).toContain(memoryReadiness.observationId);

  const patched = await postOrPatchData<{ whiteboard: WorkWhiteboard }>(
    "PATCH",
    request,
    `/api/whiteboards/${followUpWhiteboard.id}`,
    fixture.accessToken,
    {
      objective:
        "Launch a follow-up Legacy DEPP GOLD campaign that reuses approved appointment-proof learning and avoids unsupported channel claims.",
      budget_limit: "10000 MXN",
      timeline: "two-week follow-up launch window",
      constraints: {
        approved_learning: memoryReadiness.title,
        prior_memory_observation_id: memoryReadiness.observationId,
        rejected_claim: "unverified WhatsApp exclusivity claim",
        connector_scope: "email/social sandbox only unless connector evidence changes",
      },
      target_audience: {
        segment: "Mexico City eyewear buyers who need proof of appointment availability before buying",
      },
      brand_context: {
        voice: "premium, precise, understated",
        memory_reuse: reusedLearnings,
      },
      product_context: {
        product: "Legacy DEPP GOLD",
        price: "599 MXN",
      },
      channel_context: {
        requested: ["email", "Instagram", "Facebook", "TikTok"],
        deferred_until_approved: ["WhatsApp", "landing page"],
      },
      known_facts: {
        client: liveLegacyCompanyName,
        available_connector: "email and social sandbox",
        source_memory_observation_id: memoryReadiness.observationId,
        source_memory_content: memoryReadiness.content,
      },
      assumptions: [
        "Prior approved learning is reusable for this follow-up because it is graph-scoped memory.",
        "WhatsApp and landing-page connectors remain unavailable unless backend connector evidence is added.",
      ],
    },
    idempotency(testInfo, `follow-up-whiteboard-fill-${followUpWhiteboard.id}`),
    apiCalls,
  );
  expect(patched.whiteboard.id).toBe(followUpWhiteboard.id);
  const ready = await postData<{ whiteboard: WorkWhiteboard; routing_record_id: string }>(
    request,
    `/api/whiteboards/${followUpWhiteboard.id}/ready-for-strategy`,
    fixture.accessToken,
    {},
    idempotency(testInfo, `follow-up-ready-${followUpWhiteboard.id}`),
    apiCalls,
  );
  expect(ready.whiteboard.status).toBe("ready_for_strategy");
  expect(ready.routing_record_id).toBeTruthy();

  const phaseStartOperation = await startPhaseViaApi(
    request,
    fixture,
    followUpWhiteboard.id,
    agencyPhaseId,
    testInfo,
    apiCalls,
  );
  const workstreamMemoryRefs: MemoryUpliftEvidence["workstreamMemoryRefs"] = [];
  const agency = await completeAgencyPhaseInDependencyOrder(
    request,
    fixture,
    followUpWhiteboard.id,
    agencyPhaseId,
    {
      strategy_readiness: 96,
      legal_precheck: "pass",
      measurement_readiness: 94,
      execution_readiness: 93,
      asset_plan_readiness: 92,
      timing_readiness: 90,
      memory_reuse: "pass",
      rejected_claim_avoidance: "pass",
    },
    testInfo,
    apiCalls,
    (workstreamId) => {
      const memoryRef = {
        workstreamId,
        memoryObservationId: memoryReadiness.observationId,
        reusedLearnings,
        avoidedRejectedItems,
      };
      workstreamMemoryRefs.push(memoryRef);
      return {
        summary: `${workstreamId} reused the prior approved appointment-proof learning and avoided unsupported WhatsApp/landing-page assumptions.`,
        memory_refs: [memoryReadiness.observationId],
        reused_learnings: reusedLearnings,
        avoided_rejected_items: avoidedRejectedItems,
        context: {
          company: liveLegacyCompanyName,
          product: "Legacy DEPP GOLD",
          source_memory_observation_id: memoryReadiness.observationId,
          source_memory_topic_key: memoryReadiness.topicKey,
        },
      };
    },
  );
  expect(["in_content", "in_approval"]).toContain(agency.whiteboard.status);
  expect(agency.contract.current_state.gate?.result).toBe("pass");

  const operations = {
    phaseStart: operationEvidence(phaseStartOperation),
    synthesis: operationEvidence(agency.synthesisOperation),
    gateEvaluation: operationEvidence(agency.evaluationOperation),
  };
  return {
    threadId: threadResponse.thread.id,
    messageId: messageResponse.message.id,
    whiteboardId: followUpWhiteboard.id,
    whiteboardStatus: agency.whiteboard.status,
    classification: routed.classification.classification,
    confidence: routed.classification.confidence,
    routingRecordIds: [...routed.routing_record_ids, ready.routing_record_id],
    memoryObservationId: memoryReadiness.observationId,
    contextObservationIds,
    reusedLearnings,
    avoidedRejectedItems,
    workstreamMemoryRefs,
    operationIds: [phaseStartOperation.id, agency.synthesisOperation.id, agency.evaluationOperation.id],
    operations,
    gateResult: agency.contract.current_state.gate?.result,
  };
}

async function routeRequestMessageViaApi(
  request: APIRequestContext,
  fixture: LiveAtlasLegacyConsultFixture,
  messageId: string,
  testInfo: TestInfo,
  idempotencyLabel: string,
  apiCalls: ApiCall[],
): Promise<RouteRequestResponse> {
  return postData<RouteRequestResponse>(
    request,
    `/api/communication/messages/${messageId}/route-request`,
    fixture.accessToken,
    {},
    idempotency(testInfo, idempotencyLabel),
    apiCalls,
  );
}

async function startPhaseViaApi(
  request: APIRequestContext,
  fixture: LiveAtlasLegacyConsultFixture,
  whiteboardId: string,
  phaseId: string,
  testInfo: TestInfo,
  apiCalls: ApiCall[],
): Promise<ProductOperation> {
  const started = await postData<PhaseActionResponse>(
    request,
    `/api/whiteboards/${whiteboardId}/phases/${phaseId}/start`,
    fixture.accessToken,
    {},
    idempotency(testInfo, `phase-start-${phaseId}-${whiteboardId}`),
    apiCalls,
  );
  const operation = expectOperation(started, "phase_start");
  await waitForOperationAndContract(
    request,
    fixture,
    whiteboardId,
    operation,
    () => fetchPhaseContract(request, fixture, whiteboardId, phaseId, apiCalls),
    apiCalls,
  );
  await waitForPhaseWorkstreamMaterialization(
    () => fetchPhaseContract(request, fixture, whiteboardId, phaseId, apiCalls),
    30_000,
  );
  return operation;
}

function buildReleaseScoreSummary({
  agency,
  initialWorkstreams,
  deploymentContract,
  blockedDeployment,
  performanceContract,
  operationLifecycle,
  durableState,
  routes,
  memoryReadiness,
  memoryUplift,
}: {
  agency: PhaseContract;
  initialWorkstreams: Record<string, PhaseContract["workstreams"][number]>;
  deploymentContract: DeploymentContract;
  blockedDeployment: DeploymentContract["channels"];
  performanceContract: PerformanceContract;
  operationLifecycle: Record<string, Record<string, unknown>>;
  durableState: DurableStateEvidence;
  routes: string[];
  memoryReadiness: MemoryReadinessEvidence;
  memoryUplift: MemoryUpliftEvidence;
}): ReleaseScoreSummary {
  const finalWorkstreams = workstreamsById(agency);
  const expectedWorkstreams = [
    "strategy_brief",
    "legal_claims_precheck",
    "tech_execution_readiness",
    "media_channel_plan",
    "copy_message_house",
    "analytics_measurement_plan",
    "traffic_dependency_map",
    "content_asset_map",
    "timing_flighting_plan",
    "deployment_readiness_plan",
  ];
  const atlasQuality = {
    allExpectedWorkstreamsVisible: expectedWorkstreams.every((id) => Boolean(finalWorkstreams[id])),
    dependenciesBlockedInitially:
      initialWorkstreams.content_asset_map?.status === "blocked" &&
      initialWorkstreams.timing_flighting_plan?.status === "blocked" &&
      initialWorkstreams.deployment_readiness_plan?.status === "blocked",
    dependenciesCompleted: expectedWorkstreams.every((id) => finalWorkstreams[id]?.status === "completed"),
    gatePassed: agency.current_state.gate?.result === "pass",
    followUpMemoryUplift:
      memoryUplift.contextObservationIds.includes(memoryReadiness.observationId) &&
      memoryUplift.reusedLearnings.length > 0 &&
      memoryUplift.avoidedRejectedItems.length > 0 &&
      memoryUplift.workstreamMemoryRefs.length >= expectedWorkstreams.length,
    connectorHonesty:
      blockedDeployment.length > 0 &&
      blockedDeployment.every((channel) => Boolean(channel.company_signal_id) && !channel.tool_execution_id),
    measurementReady: Boolean(performanceContract.current_state.metric_snapshot_id),
  };
  const operationEntries = Object.values(operationLifecycle);
  const systemReliability = {
    operationsTerminal: operationEntries.every(
      (operation) => operation.status === "completed" && operation.terminal === true,
    ),
    durableWhiteboardReadable: durableState.whiteboardId.length > 0 && durableState.boardCardCount > 0,
    durableApprovalReadable: durableState.approval.status === "approved",
    durableDeploymentReadable:
      durableState.deployment.last_operation_id ===
      (deploymentContract.last_operation_id ?? deploymentContract.current_state?.last_operation_id),
    durablePerformanceReadable: Boolean(
      durableState.performance.metricSnapshotId && durableState.performance.evaluationId,
    ),
    memoryTraceable: memoryReadiness.contextObservationIds.includes(memoryReadiness.observationId),
    followUpOperationsTerminal: Object.values(memoryUplift.operations).every(
      (operation) => operation.status === "completed" && operation.terminal === true,
    ),
    followUpWhiteboardTraceable: Boolean(memoryUplift.threadId && memoryUplift.messageId && memoryUplift.whiteboardId),
  };
  const runtimeIntegrity = {
    noVerticalRoutes: routes.every((route) => !/\/api\/(?:marketing|atlas|legacy)(?:\/|$)/i.test(route)),
    genericWhiteboardRoutes: routes.some((route) => route.startsWith("/api/whiteboards/")),
    genericMemoryRoutes: routes.some((route) => route.startsWith("/api/memory/")),
    genericGraphRoutes: routes.some((route) => route.startsWith("/api/graphs/")),
    deploymentBlockersNotFakeSuccess: blockedDeployment.every((channel) => !channel.tool_execution_id),
  };
  const summary = {
    atlasQuality: { score: scoreChecks(atlasQuality), checks: atlasQuality },
    systemReliability: { score: scoreChecks(systemReliability), checks: systemReliability },
    runtimeIntegrity: { score: scoreChecks(runtimeIntegrity), checks: runtimeIntegrity },
  };
  return {
    ...summary,
    passed: [summary.atlasQuality, summary.systemReliability, summary.runtimeIntegrity].every(
      (section) => section.score === 100,
    ),
  };
}

function scoreChecks(checks: Record<string, boolean>): number {
  const values = Object.values(checks);
  return Math.round((values.filter(Boolean).length / values.length) * 100);
}

async function collectProjectionLagEvidence(
  request: APIRequestContext,
  fixture: LiveAtlasLegacyConsultFixture,
  apiCalls: ApiCall[],
): Promise<ProjectionLagEvidence> {
  const response = await rawGet(request, "/api/ops/projection-lag", fixture.accessToken, apiCalls);
  if (!response.ok()) {
    return {
      available: false,
      status: response.status(),
      error: await response.text(),
    };
  }
  const payload = await responseData<Omit<ProjectionLagEvidence, "available">>(response, "GET /api/ops/projection-lag");
  return {
    available: true,
    ...payload,
  };
}

async function collectWhiteboardBoardKafkaEvidence(
  request: APIRequestContext,
  fixture: LiveAtlasLegacyConsultFixture,
  whiteboardId: string,
  required: boolean,
  apiCalls: ApiCall[],
): Promise<WhiteboardBoardKafkaTransportEvidence> {
  const deadline = Date.now() + (required ? 90_000 : 1);
  let latest: WhiteboardBoardKafkaTransportEvidence | null = null;
  let latestError = "";
  let latestStatus = 0;
  do {
    const response = await rawGet(
      request,
      `/api/ops/transport-evidence?transport=whiteboard_board_kafka&whiteboard_id=${whiteboardId}`,
      fixture.accessToken,
      apiCalls,
    );
    latestStatus = response.status();
    if (response.ok()) {
      const payload = await responseData<{
        transport_evidence: Omit<WhiteboardBoardKafkaTransportEvidence, "available" | "required">;
      }>(response, "GET /api/ops/transport-evidence");
      latest = {
        ...payload.transport_evidence,
        required,
        available: true,
      };
      if (!required || whiteboardBoardKafkaEvidenceReady(latest)) {
        break;
      }
    } else {
      latestError = await response.text();
      if (!required) {
        break;
      }
    }
    await sleep(1_000);
  } while (Date.now() < deadline);

  if (!latest) {
    latest = unavailableWhiteboardBoardKafkaEvidence(required, latestStatus, latestError);
  }
  if (required) {
    expect(latest.available, latest.error ?? "whiteboard board Kafka evidence unavailable").toBe(true);
    expect(latest.authoritative_state_source).toBe("backend_db");
    expect(latest.enabled).toBe(true);
    expect(latest.outbox.published).toBeGreaterThan(0);
    expect(latest.receipts.handled + latest.receipts.ignored + latest.receipts.failed).toBeGreaterThan(0);
    expect(latest.dead_letters.active_count).toBe(0);
  }
  return latest;
}

function whiteboardBoardKafkaEvidenceReady(evidence: WhiteboardBoardKafkaTransportEvidence): boolean {
  return (
    evidence.available &&
    evidence.enabled &&
    evidence.authoritative_state_source === "backend_db" &&
    evidence.outbox.published > 0 &&
    evidence.receipts.handled + evidence.receipts.ignored + evidence.receipts.failed > 0 &&
    evidence.dead_letters.active_count === 0
  );
}

function unavailableWhiteboardBoardKafkaEvidence(
  required: boolean,
  status: number,
  error: string,
): WhiteboardBoardKafkaTransportEvidence {
  return {
    required,
    available: false,
    transport: "whiteboard_board_kafka",
    authoritative_state_source: "backend_db",
    enabled: false,
    topic: "",
    consumer_group: "",
    outbox: { pending: 0, published: 0, failed: 0, deferred: 0, total: 0, backlog: 0 },
    receipts: { handled: 0, ignored: 0, failed: 0, total: 0 },
    dead_letters: { active_count: 0, total: 0, recent: [] },
    recent_receipts: [],
    generated_at: new Date().toISOString(),
    status,
    error,
  };
}

async function persistAtlasAgencyReviewBoardEvaluation(
  request: APIRequestContext,
  fixture: LiveAtlasLegacyConsultFixture,
  whiteboardId: string,
  releaseScore: ReleaseScoreSummary,
  durableState: DurableStateEvidence,
  memoryUplift: MemoryUpliftEvidence,
  apiCalls: ApiCall[],
  testInfo: TestInfo,
): Promise<ReviewBoardEvaluationEvidence> {
  const scorecard = buildAtlasAgencyReviewBoardScorecard();
  const response = await postData<{
    evaluation: {
      id: string;
      status: string;
      score: number;
      grade: string;
      result: Record<string, unknown>;
      findings: Array<{ blocking?: boolean }>;
    };
  }>(
    request,
    "/api/evaluations/run",
    fixture.accessToken,
    {
      company_id: fixture.companyId,
      profile_id: "consulting_ops_demo.v1.quality_judge",
      content: JSON.stringify({
        release: "atlas_p2_review_packet",
        whiteboard_id: whiteboardId,
        release_score: releaseScore,
      }),
      input_refs: [
        { type: "work_whiteboard", id: whiteboardId },
        { type: "performance_evaluation", id: durableState.performance.evaluationId },
        { type: "memory_uplift_whiteboard", id: memoryUplift.whiteboardId },
      ],
      inputs: {
        submitted_scorecard: scorecard,
      },
    },
    idempotency(testInfo, `atlas-p2-review-board-${whiteboardId}`),
    apiCalls,
  );
  const evaluation = response.evaluation;
  expect(evaluation.id).toBeTruthy();
  expect(evaluation.status).toBe("PASS");
  expect(evaluation.result.schema_version).toBe("consulting_review_board_v1");
  expect(evaluation.result.decision).toBe("client_ready");
  const signalIds = Array.isArray(evaluation.result.signal_ids) ? evaluation.result.signal_ids.map(String) : [];
  expect(signalIds.length).toBeGreaterThan(0);
  return {
    evaluationId: evaluation.id,
    status: evaluation.status,
    score: evaluation.score,
    grade: evaluation.grade,
    schemaVersion: String(evaluation.result.schema_version),
    decision: String(evaluation.result.decision),
    approvalGate: evaluation.result.approval_gate as Record<string, unknown> | undefined,
    signalIds,
    findingCount: evaluation.findings.length,
    blockingFindingCount: evaluation.findings.filter((finding) => finding.blocking === true).length,
  };
}

function buildAtlasAgencyReviewBoardScorecard(): Record<string, unknown> {
  return {
    schema_version: "consulting_review_board_v1",
    decision: "client_ready",
    hard_fail: false,
    overall_average: 4.4,
    client_readiness_level: "client_ready",
    atlas: reviewBoardSection(
      [
        "Diagnostic depth",
        "Strategic reasoning",
        "Use of Legacy context",
        "Execution design",
        "Tool/capability honesty",
        "Client communication quality",
        "Operating-system maturity",
      ],
      "ATLAS",
    ),
    legacy: reviewBoardSection(
      [
        "Context completeness",
        "Commercial readiness",
        "Brand readiness",
        "Channel readiness",
        "Approval readiness",
        "Measurement readiness",
        "Operational maturity",
      ],
      "Legacy Eyewear",
    ),
    engagement: reviewBoardSection(
      [
        "Goal clarity",
        "Evidence quality",
        "Deliverable completeness",
        "Cross-company boundary correctness",
        "Client safety",
        "Execution continuity",
        "Reusability/history",
      ],
      "engagement",
    ),
    company_improvement_plan: [
      {
        target: "Legacy Eyewear",
        primitive: "CompanySignal",
        title: "Keep connector readiness explicit before launch",
        priority: "high",
        rationale: "Blocked provider paths should remain visible as readiness signals instead of simulated success.",
      },
      {
        target: "ATLAS",
        primitive: "OperationRecommendation",
        title: "Attach transport and projection evidence to every release packet",
        priority: "medium",
        rationale: "The review board needs backend-owned evidence for transport receipts and projection lag.",
      },
      {
        target: "engagement",
        primitive: "CompanySignal",
        title: "Carry approved follow-up learnings into the next cycle",
        priority: "medium",
        rationale: "The follow-up request reused prior approval memory and avoided unsupported channel claims.",
      },
    ],
    approval_gate: {
      client_deliverable_status: "approved_for_review",
      execution_status: "ready",
      reason: "Release packet is client-reviewable with explicit blocker and sandbox evidence.",
    },
  };
}

function reviewBoardSection(areas: string[], label: string): Record<string, unknown> {
  return {
    average: 4.4,
    scores: areas.map((area) => ({
      area,
      score: 4.4,
      rationale: `${label} ${area.toLowerCase()} evidence is present in the durable release packet.`,
      improvement: `Tighten ${area.toLowerCase()} evidence in the next release cycle.`,
    })),
    top_strengths: [
      `${label} evidence is backed by generic backend APIs and durable records.`,
      `${label} blocker handling stays honest about sandbox or missing provider readiness.`,
    ],
    required_improvements: [
      `${label} should keep shortening the path from evidence collection to client-ready summaries.`,
      `${label} should add more historical comparison once additional campaign cycles exist.`,
    ],
  };
}

function buildConnectorProviderEvidence(
  deploymentContract: DeploymentContract,
  performanceContract: PerformanceContract,
): Record<string, unknown> {
  return {
    realConnectorsEnabled: atlasP2RealConnectors,
    emailProvider: process.env.EMAIL_CONNECTOR_PROVIDER ?? "repo-default",
    socialProvider: process.env.SOCIAL_CONNECTOR_PROVIDER ?? "repo-default",
    deploymentChannels: deploymentContract.channels.map((channel) => ({
      id: channel.id,
      status: channel.status,
      hasToolExecution: Boolean(channel.tool_execution_id),
      blockedReasonCode: channel.blocked_reason_code,
      receiptMode: channel.receipt?.result?.mode,
      evidenceMode: channel.receipt?.result?.evidence_mode,
    })),
    performanceSources: performanceContract.sources.map((source) => ({
      id: source.id,
      status: source.status,
      hasToolExecution: Boolean(source.tool_execution_id),
      blockedReasonCode: source.blocked_reason_code,
    })),
  };
}

async function sleep(ms: number): Promise<void> {
  await new Promise((resolve) => setTimeout(resolve, ms));
}

async function completeAgencyPhaseInDependencyOrderThroughUi(
  page: Page,
  request: APIRequestContext,
  fixture: LiveAtlasLegacyConsultFixture,
  whiteboardId: string,
  phaseId: string,
  scorecard: Record<string, unknown>,
  apiCalls: ApiCall[],
): Promise<{
  whiteboard: WorkWhiteboard;
  contract: PhaseContract;
  afterFoundations: PhaseContract;
  afterContentTiming: PhaseContract;
  synthesisOperation: ProductOperation;
  evaluationOperation: ProductOperation;
}> {
  expect(Object.keys(scorecard).length).toBeGreaterThan(0);
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
  await openLiveTokenSession(page, request, fixture.accessToken, `/companies/${fixture.companyId}`);
  await page.getByTestId(`whiteboard-phase-${phaseId}`).scrollIntoViewIfNeeded();
  for (const workstreamId of foundationalBatch) {
    await completePhaseWorkstreamThroughUi(page, whiteboardId, phaseId, workstreamId, {
      summary: `${workstreamId} completed through the whiteboard UI for Legacy DEPP GOLD.`,
      context: {
        company: liveLegacyCompanyName,
        product: "Legacy DEPP GOLD",
        price: "599 MXN",
        budget: "10000 MXN",
        expected_gate_keys: Object.keys(scorecard),
      },
    });
  }
  const afterFoundations = await fetchPhaseContract(request, fixture, whiteboardId, phaseId, apiCalls);
  const foundationState = workstreamsById(afterFoundations);
  expect(foundationState.content_asset_map?.status).toBe("queued");
  expect(foundationState.timing_flighting_plan?.status).toBe("queued");
  expect(foundationState.deployment_readiness_plan?.status).toBe("blocked");

  for (const workstreamId of ["content_asset_map", "timing_flighting_plan"]) {
    await completePhaseWorkstreamThroughUi(page, whiteboardId, phaseId, workstreamId, {
      summary: `${workstreamId} completed through the whiteboard UI after foundational dependencies unblocked.`,
      context: {
        company: liveLegacyCompanyName,
        product: "Legacy DEPP GOLD",
        dependency_transition: "unblocked_after_foundational_batch",
      },
    });
  }
  const afterContentTiming = await fetchPhaseContract(request, fixture, whiteboardId, phaseId, apiCalls);
  expect(workstreamsById(afterContentTiming).deployment_readiness_plan?.status).toBe("queued");

  await completePhaseWorkstreamThroughUi(page, whiteboardId, phaseId, "deployment_readiness_plan", {
    summary: "Deployment readiness completed through the whiteboard UI after content and timing were ready.",
    context: {
      company: liveLegacyCompanyName,
      product: "Legacy DEPP GOLD",
      available_connectors: ["email_connector", "social_connector", "analytics_connector"],
      missing_connectors_create_blockers: true,
    },
  });

  const synthesisOperation = await synthesizePhaseThroughUi(page, request, fixture, whiteboardId, phaseId, apiCalls);
  const evaluationOperation = await evaluatePhaseThroughUi(page, request, fixture, whiteboardId, phaseId, apiCalls);
  const contract = await fetchPhaseContract(request, fixture, whiteboardId, phaseId, apiCalls);
  const whiteboard = await getData<{ whiteboard: WorkWhiteboard }>(
    request,
    `/api/whiteboards/${whiteboardId}`,
    fixture.accessToken,
    apiCalls,
  );
  return {
    whiteboard: whiteboard.whiteboard,
    contract,
    afterFoundations,
    afterContentTiming,
    synthesisOperation,
    evaluationOperation,
  };
}

async function completePhaseWorkstreamThroughUi(
  page: Page,
  whiteboardId: string,
  phaseId: string,
  workstreamId: string,
  result: { summary: string; context: Record<string, unknown> },
): Promise<void> {
  const card = page.getByTestId(`whiteboard-phase-workstream-${workstreamId}`);
  await card.scrollIntoViewIfNeeded();
  await expect(card).toBeVisible({ timeout: 30_000 });
  const completeButton = page.getByTestId(`whiteboard-phase-workstream-${workstreamId}-complete`);
  await expect(completeButton).toBeEnabled({ timeout: 60_000 });
  await page.getByTestId(`whiteboard-phase-workstream-${workstreamId}-summary`).fill(result.summary);
  await page
    .getByTestId(`whiteboard-phase-workstream-${workstreamId}-context`)
    .fill(JSON.stringify(result.context, null, 2));
  const responsePromise = waitForBackendPostResponse(
    page,
    `/api/whiteboards/${whiteboardId}/phases/${phaseId}/workstreams/${workstreamId}/complete`,
    60_000,
  );
  await completeButton.click();
  const response = await responsePromise;
  const payload = await responseData<PhaseActionResponse>(
    response,
    `POST /api/whiteboards/${whiteboardId}/phases/${phaseId}/workstreams/${workstreamId}/complete`,
  );
  expect(workstreamsById(payload.whiteboard_phase_contract)[workstreamId]?.status).toBe("completed");
  await expect(card).toContainText(/Completed/i, { timeout: 30_000 });
}

async function synthesizePhaseThroughUi(
  page: Page,
  request: APIRequestContext,
  fixture: LiveAtlasLegacyConsultFixture,
  whiteboardId: string,
  phaseId: string,
  apiCalls: ApiCall[],
): Promise<ProductOperation> {
  await page.getByTestId(`whiteboard-phase-${phaseId}`).scrollIntoViewIfNeeded();
  const synthesizeButton = page.getByTestId(`whiteboard-phase-synthesize-${phaseId}`);
  await expect(synthesizeButton).toBeEnabled({ timeout: 60_000 });
  const responsePromise = waitForBackendPostResponse(
    page,
    `/api/whiteboards/${whiteboardId}/phases/${phaseId}/synthesize`,
    60_000,
  );
  await synthesizeButton.click();
  const response = await responsePromise;
  const payload = await responseData<PhaseActionResponse>(
    response,
    `POST /api/whiteboards/${whiteboardId}/phases/${phaseId}/synthesize`,
  );
  const operation = expectOperation(payload, "phase_synthesize");
  await waitForOperationAndContract(
    request,
    fixture,
    whiteboardId,
    operation,
    () => fetchPhaseContract(request, fixture, whiteboardId, phaseId, apiCalls),
    apiCalls,
  );
  await expect(page.getByTestId(`whiteboard-phase-${phaseId}`)).toContainText(/Captured/i, { timeout: 30_000 });
  return operation;
}

async function evaluatePhaseThroughUi(
  page: Page,
  request: APIRequestContext,
  fixture: LiveAtlasLegacyConsultFixture,
  whiteboardId: string,
  phaseId: string,
  apiCalls: ApiCall[],
): Promise<ProductOperation> {
  await page.getByTestId(`whiteboard-phase-${phaseId}`).scrollIntoViewIfNeeded();
  const evaluateButton = page.getByTestId(`whiteboard-phase-evaluate-${phaseId}`);
  await expect(evaluateButton).toBeEnabled({ timeout: 60_000 });
  const responsePromise = waitForBackendPostResponse(
    page,
    `/api/whiteboards/${whiteboardId}/phases/${phaseId}/evaluate`,
    60_000,
  );
  await evaluateButton.click();
  const response = await responsePromise;
  const payload = await responseData<PhaseActionResponse>(
    response,
    `POST /api/whiteboards/${whiteboardId}/phases/${phaseId}/evaluate`,
  );
  const operation = expectOperation(payload, "phase_gate_evaluate");
  await waitForOperationAndContract(
    request,
    fixture,
    whiteboardId,
    operation,
    () => fetchPhaseContract(request, fixture, whiteboardId, phaseId, apiCalls),
    apiCalls,
  );
  await expect(page.getByTestId(`whiteboard-phase-${phaseId}`)).toContainText(/Pass|In Approval/i, {
    timeout: 30_000,
  });
  return operation;
}

async function completeAgencyPhaseInDependencyOrder(
  request: APIRequestContext,
  fixture: LiveAtlasLegacyConsultFixture,
  whiteboardId: string,
  phaseId: string,
  scorecard: Record<string, unknown>,
  testInfo: TestInfo,
  apiCalls: ApiCall[],
  workstreamResult?: (workstreamId: string) => Record<string, unknown>,
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
    await completePhaseWorkstream(
      request,
      fixture,
      whiteboardId,
      phaseId,
      workstreamId,
      testInfo,
      apiCalls,
      workstreamResult?.(workstreamId),
    );
  }
  const afterFoundations = await fetchPhaseContract(request, fixture, whiteboardId, phaseId, apiCalls);
  const foundationState = workstreamsById(afterFoundations);
  expect(foundationState.content_asset_map?.status).toBe("queued");
  expect(foundationState.timing_flighting_plan?.status).toBe("queued");
  expect(foundationState.deployment_readiness_plan?.status).toBe("blocked");

  for (const workstreamId of ["content_asset_map", "timing_flighting_plan"]) {
    await completePhaseWorkstream(
      request,
      fixture,
      whiteboardId,
      phaseId,
      workstreamId,
      testInfo,
      apiCalls,
      workstreamResult?.(workstreamId),
    );
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
    workstreamResult?.("deployment_readiness_plan"),
  );
  const synthesis = await postData<PhaseActionResponse>(
    request,
    `/api/whiteboards/${whiteboardId}/phases/${phaseId}/synthesize`,
    fixture.accessToken,
    {},
    idempotency(testInfo, `phase-synthesize-${phaseId}-${whiteboardId}`),
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
    idempotency(testInfo, `phase-evaluate-${phaseId}-${whiteboardId}`),
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
  result?: Record<string, unknown>,
): Promise<void> {
  await postData<{ whiteboard_phase_contract: PhaseContract }>(
    request,
    `/api/whiteboards/${whiteboardId}/phases/${phaseId}/workstreams/${workstreamId}/complete`,
    fixture.accessToken,
    {
      result: result ?? {
        summary: `${workstreamId} completed for Legacy DEPP GOLD.`,
        context: {
          company: liveLegacyCompanyName,
          product: "Legacy DEPP GOLD",
          price: "599 MXN",
          budget: "10000 MXN",
        },
      },
    },
    idempotency(testInfo, `phase-complete-${phaseId}-${whiteboardId}-${workstreamId}`),
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

async function reportPerformanceThroughUi(
  page: Page,
  request: APIRequestContext,
  fixture: LiveAtlasLegacyConsultFixture,
  whiteboardId: string,
  apiCalls: ApiCall[],
): Promise<{ performance_contract: PerformanceContract; whiteboard: WorkWhiteboard; operation: ProductOperation }> {
  await page.getByTestId("whiteboard-performance-section").scrollIntoViewIfNeeded();
  const reportButton = page.getByTestId("whiteboard-performance-report-button");
  await expect(reportButton).toBeEnabled({ timeout: 60_000 });
  const reportResponsePromise = waitForBackendPostResponse(
    page,
    `/api/whiteboards/${whiteboardId}/performance/report`,
    60_000,
  );
  await reportButton.click();
  const response = await reportResponsePromise;
  const payload = await responseData<PerformanceActionResponse>(
    response,
    `POST /api/whiteboards/${whiteboardId}/performance/report`,
  );
  const operation = expectOperation(payload, "performance_report");
  await waitForOperationAndContract(
    request,
    fixture,
    whiteboardId,
    operation,
    () => fetchPerformanceContract(request, fixture, whiteboardId, apiCalls),
    apiCalls,
  );
  await expect(page.getByTestId("whiteboard-performance-report")).not.toContainText(/Pending/i, { timeout: 30_000 });
  const performanceContract = await fetchPerformanceContract(request, fixture, whiteboardId, apiCalls);
  const whiteboard = await getData<{ whiteboard: WorkWhiteboard }>(
    request,
    `/api/whiteboards/${whiteboardId}`,
    fixture.accessToken,
    apiCalls,
  );
  return { performance_contract: performanceContract, whiteboard: whiteboard.whiteboard, operation };
}

async function evaluatePerformanceThroughUi(
  page: Page,
  request: APIRequestContext,
  fixture: LiveAtlasLegacyConsultFixture,
  whiteboardId: string,
  apiCalls: ApiCall[],
): Promise<{ performance_contract: PerformanceContract; whiteboard: WorkWhiteboard; operation: ProductOperation }> {
  await page.getByTestId("whiteboard-performance-section").scrollIntoViewIfNeeded();
  const evaluateButton = page.getByTestId("whiteboard-performance-evaluate-button");
  await expect(evaluateButton).toBeEnabled({ timeout: 60_000 });
  const evaluationResponsePromise = waitForBackendPostResponse(
    page,
    `/api/whiteboards/${whiteboardId}/performance/evaluate`,
    60_000,
  );
  await evaluateButton.click();
  const response = await evaluationResponsePromise;
  const payload = await responseData<PerformanceActionResponse>(
    response,
    `POST /api/whiteboards/${whiteboardId}/performance/evaluate`,
  );
  const operation = expectOperation(payload, "performance_evaluate");
  await waitForOperationAndContract(
    request,
    fixture,
    whiteboardId,
    operation,
    () => fetchPerformanceContract(request, fixture, whiteboardId, apiCalls),
    apiCalls,
  );
  await expect(page.getByTestId("whiteboard-performance-evaluation")).not.toContainText(/Pending/i, {
    timeout: 30_000,
  });
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
  memoryObservationIds: string[],
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
    ...memoryObservationIds.map((observationId) =>
      rawGet(request, `/api/memory/observations/${observationId}`, fixture.otherClientAccessToken, apiCalls),
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
  let routeState = liveApiRouteStates.get(page);
  const shouldInstallRoute = !routeState;
  if (!routeState) {
    routeState = { accessToken };
    liveApiRouteStates.set(page, routeState);
  }
  routeState.accessToken = accessToken;
  await page.context().clearCookies();
  if (shouldInstallRoute) {
    await page.route(liveApiRoutePattern, async (route) => {
      const requestUrl = new URL(route.request().url());
      const backendUrl = `${API_BASE_URL}${requestUrl.pathname}${requestUrl.search}`;
      const requestHeaders = route.request().headers();
      const browserAuthorization = requestHeaders.authorization ?? requestHeaders.Authorization;
      if (typeof browserAuthorization === "string" && browserAuthorization.toLowerCase().startsWith("bearer ")) {
        routeState.accessToken = browserAuthorization.slice("bearer ".length);
      }
      const response = await request.fetch(backendUrl, {
        method: route.request().method(),
        headers: {
          ...requestHeaders,
          Authorization: `Bearer ${routeState.accessToken}`,
        },
        data: route.request().postDataBuffer() ?? route.request().postData() ?? undefined,
        failOnStatusCode: false,
      });
      const body = await response.body();
      if (requestUrl.pathname === "/api/auth/refresh" && response.ok()) {
        routeState.accessToken = refreshedAccessTokenFromBody(body) ?? routeState.accessToken;
      }

      await route.fulfill({
        status: response.status(),
        headers: response.headers(),
        body,
      });
    });
  }
  await page.addInitScript((token) => {
    window.sessionStorage.setItem("__FORGEGRAPH_E2E_ACCESS_TOKEN__", token);
    (window as Window & { __FORGEGRAPH_E2E_ACCESS_TOKEN__?: string }).__FORGEGRAPH_E2E_ACCESS_TOKEN__ = token;
  }, accessToken);
  await page.goto(targetPath);
  await page.waitForLoadState("networkidle");
}

function refreshedAccessTokenFromBody(body: Buffer): string | null {
  try {
    const payload = JSON.parse(body.toString("utf8")) as { access?: unknown; data?: { access?: unknown } };
    const access = typeof payload.access === "string" ? payload.access : payload.data?.access;
    return typeof access === "string" && access.length > 0 ? access : null;
  } catch {
    return null;
  }
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
