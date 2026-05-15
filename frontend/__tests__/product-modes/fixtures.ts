import type { Page, Route } from "@playwright/test";

import { installCompanyWorkspaceMocks, type CompanyWorkspaceMockState } from "../e2e/company-ux-fixtures";
import type {
  AssertionRecordDTO,
  CommunicationMessageDTO,
  CommunicationThreadDTO,
  CompanyOperatingModelDTO,
  CompanyProgramDTO,
  CrossCompanyQueues,
  MetricSnapshotDTO,
  OperatingModelInstallation,
  OperatingModelPack,
  PeriodicReviewDTO,
  PortfolioHealth,
  ReportRunDTO,
  StateProjectionDTO,
  WorkArtifactDTO,
  WorkWhiteboardDTO,
} from "../../lib/api";

export const legacyMultiPackIds = {
  primary: "legacy-eyewear-core.v1",
  accounting: "legacy-eyewear-accounting.v1",
  legal: "legacy-eyewear-legal.v1",
  consulting: "legacy-eyewear-consulting.v1",
  program: "legacy-eyewear-program",
  artifact: "legacy-eyewear-service-report",
  projection: "legacy-eyewear-current-state",
  serviceHistory: "legacy-eyewear-service-history",
  report: "legacy-eyewear-q2-report",
  metricSnapshot: "legacy-eyewear-q2-metrics",
  periodicReview: "legacy-eyewear-quarterly-review",
  communicationThread: "legacy-eyewear-consult-thread",
  signal: "legacy-eyewear-missing-whatsapp-signal",
  whiteboard: "legacy-eyewear-work-whiteboard",
} as const;

export type ProductModeMockState = CompanyWorkspaceMockState & {
  availablePacks: OperatingModelPack[];
  installedPacks: OperatingModelInstallation[];
  operatingModel?: CompanyOperatingModelDTO;
  programs?: CompanyProgramDTO[];
  assertions?: AssertionRecordDTO[];
  artifacts?: WorkArtifactDTO[];
  stateProjections?: StateProjectionDTO[];
  periodicReviews?: PeriodicReviewDTO[];
  metricSnapshots?: MetricSnapshotDTO[];
  reportRuns?: ReportRunDTO[];
  communicationThreads?: CommunicationThreadDTO[];
  communicationMessages?: Record<string, CommunicationMessageDTO[]>;
  whiteboards?: WorkWhiteboardDTO[];
};

export function collectProductModeApiRequests(page: Page): string[] {
  const apiRequests: string[] = [];
  page.on("request", (request) => {
    const url = new URL(request.url());
    if (url.pathname.startsWith("/api/")) {
      apiRequests.push(request.url());
    }
  });
  return apiRequests;
}

export function sawProductModeApiPath(apiRequests: string[], pathname: string): boolean {
  return apiRequests.some((requestUrl) => new URL(requestUrl).pathname === pathname);
}

export function sawCompanyScopedProductModeQuery(
  apiRequests: string[],
  pathname: string,
  companyId: string,
): boolean {
  return apiRequests.some((requestUrl) => {
    const url = new URL(requestUrl);
    return url.pathname === pathname && url.searchParams.get("company_id") === companyId;
  });
}

export function verticalProductModeApiRequests(
  apiRequests: string[],
  forbiddenPattern: RegExp = /\/api\/marketing(?:\/|$)/,
): string[] {
  return apiRequests.filter((requestUrl) => forbiddenPattern.test(new URL(requestUrl).pathname));
}

function apiSuccess<T>(data: T) {
  return {
    data,
    meta: {
      requestId: "playwright-product-modes",
      timestamp: "2026-05-12T12:00:00.000Z",
    },
  };
}

function escapeRegExp(value: string): string {
  return value.replace(/[.*+?^${}()|[\]\\]/g, "\\$&");
}

function scopedByCompany<T extends { company_id: string }>(items: T[], route: Route): T[] {
  const url = new URL(route.request().url());
  const companyId = url.searchParams.get("company_id");
  return companyId ? items.filter((item) => item.company_id === companyId) : items;
}

async function fulfillJson(route: Route, data: unknown): Promise<void> {
  await route.fulfill({
    status: 200,
    contentType: "application/json",
    body: JSON.stringify(apiSuccess(data)),
  });
}

function buildCompanyOperatingModel(state: ProductModeMockState): CompanyOperatingModelDTO {
  return {
    company_id: state.companyId,
    installed_packs: state.installedPacks,
    programs: state.programs ?? [],
    evaluation_profiles: [
      {
        profile_id: "legacy.performance-readout",
        display_name: "Performance Readout",
        mode: "periodic_review",
      },
    ],
    policy_packs: [
      {
        policy_pack_id: "legacy.service-policy",
        display_name: "Legacy Service Policy",
      },
    ],
    signal_taxonomies: [
      {
        taxonomy_id: "legacy.service-signals",
        display_name: "Service Signals",
      },
    ],
    periodic_reviews: (state.periodicReviews ?? []).map((review) => ({
      id: review.id,
      template_id: review.template_id,
      display_name: review.display_name,
      cadence: review.cadence,
      evaluation_profile_id: review.evaluation_profile_id,
      report_template_id: review.report_template_id,
      history_projection_type: review.history_projection_type,
      enabled: review.enabled,
    })),
  };
}

function buildProductModePortfolioHealth(state: ProductModeMockState): PortfolioHealth {
  const activePackCount = state.installedPacks.filter((pack) => pack.status === "active").length;
  const archivedPackCount = state.installedPacks.filter((pack) => pack.status === "archived").length;
  const primaryPack = state.installedPacks.find((pack) => pack.role === "primary") ?? null;
  const activeOperationsCount = state.operations.filter((operation) => operation.status === "running").length;
  const failedOperationsCount = state.operations.filter((operation) => operation.status === "failed").length;
  const pendingApprovalCount = state.pendingApprovalCount ?? state.approvals?.length ?? 0;

  return {
    organization_id: "playwright-product-modes-org",
    source: "computed",
    generated_at: "2026-05-12T12:00:00.000Z",
    summary: {
      total_companies: 1,
      healthy: failedOperationsCount || pendingApprovalCount ? 0 : 1,
      attention: pendingApprovalCount ? 1 : 0,
      blocked: failedOperationsCount ? 1 : 0,
      active_operations: activeOperationsCount,
      pending_approvals: pendingApprovalCount,
      metric_gaps: 0,
      credential_blockers: 0,
    },
    companies: [
      {
        company_id: state.companyId,
        company_name: state.companyName,
        company_description: String(state.graphVersion.graph_json.metadata?.description ?? ""),
        health_status: failedOperationsCount ? "blocked" : pendingApprovalCount ? "attention" : "healthy",
        health_score: failedOperationsCount ? 45 : pendingApprovalCount ? 70 : 95,
        primary_pack: primaryPack
          ? {
              installation_id: primaryPack.id,
              pack_id: primaryPack.pack_id,
              namespace: primaryPack.namespace,
              release_version: primaryPack.version,
            }
          : null,
        pack_counts: {
          active: activePackCount,
          primary: state.installedPacks.filter((pack) => pack.role === "primary").length,
          addon: state.installedPacks.filter((pack) => pack.role === "addon").length,
          disabled: state.installedPacks.filter((pack) => pack.status === "disabled").length,
          archived: archivedPackCount,
        },
        active_operations_count: activeOperationsCount,
        failed_operations_count: failedOperationsCount,
        pending_approval_count: pendingApprovalCount,
        pending_decision_count: 0,
        pending_task_count: 0,
        enabled_review_count: state.periodicReviews?.filter((review) => review.enabled).length ?? 0,
        report_run_count: state.reportRuns?.length ?? 0,
        metric_gap_count: 0,
        signal_summary: {
          total: 0,
          new: 0,
          qualified: 0,
          latest_at: null,
        },
        credential_health: {
          company_id: state.companyId,
          status: "healthy",
          scope: "company",
          healthy_count: 0,
          expired_count: 0,
          revoked_count: 0,
          provider_counts: {},
        },
      },
    ],
  };
}

function buildProductModeCrossCompanyQueues(): CrossCompanyQueues {
  return {
    type: "all",
    source: "computed",
    generated_at: "2026-05-12T12:00:00.000Z",
    counts: {
      reviews: 0,
      approvals: 0,
      metric_gaps: 0,
      credentials: 0,
      tasks: 0,
    },
    queues: {
      reviews: [],
      approvals: [],
      metric_gaps: [],
      credentials: [],
      tasks: [],
    },
  };
}

export async function installProductModeMocks(page: Page, state: ProductModeMockState): Promise<void> {
  await installCompanyWorkspaceMocks(page, state);

  const companyPath = escapeRegExp(state.companyId);
  const routePromises: Array<ReturnType<Page["route"]>> = [];
  const route = (...args: Parameters<Page["route"]>) => {
    routePromises.push(page.route(...args));
  };

  route(/\/api\/operating-model-packs\/?(?:\?.*)?$/, async (route: Route) => {
    if (route.request().method() !== "GET") {
      await route.continue();
      return;
    }
    await fulfillJson(route, { packs: state.availablePacks });
  });

  route(new RegExp(`/api/companies/${companyPath}/packs(?:\\?.*)?$`), async (route: Route) => {
    if (route.request().method() !== "GET") {
      await route.continue();
      return;
    }
    await fulfillJson(route, { packs: state.installedPacks });
  });

  route(new RegExp(`/api/companies/${companyPath}/operating-model(?:\\?.*)?$`), async (route: Route) => {
    if (route.request().method() !== "GET") {
      await route.continue();
      return;
    }
    await fulfillJson(route, { operating_model: state.operatingModel ?? buildCompanyOperatingModel(state) });
  });

  route(new RegExp(`/api/companies/${companyPath}/programs(?:\\?.*)?$`), async (route: Route) => {
    if (route.request().method() !== "GET") {
      await route.continue();
      return;
    }
    await fulfillJson(route, { programs: state.programs ?? [] });
  });

  route(/\/api\/portfolio-health(?:\?.*)?$/, async (route: Route) => {
    if (route.request().method() !== "GET") {
      await route.continue();
      return;
    }
    await fulfillJson(route, buildProductModePortfolioHealth(state));
  });

  route(/\/api\/cross-company-queues(?:\?.*)?$/, async (route: Route) => {
    if (route.request().method() !== "GET") {
      await route.continue();
      return;
    }
    await fulfillJson(route, buildProductModeCrossCompanyQueues());
  });

  route(/\/api\/assertions(?:\?.*)?$/, async (route: Route) => {
    if (route.request().method() !== "GET") {
      await route.continue();
      return;
    }
    await fulfillJson(route, { assertions: scopedByCompany(state.assertions ?? [], route) });
  });

  route(/\/api\/work-artifacts(?:\?.*)?$/, async (route: Route) => {
    if (route.request().method() !== "GET") {
      await route.continue();
      return;
    }
    await fulfillJson(route, { artifacts: scopedByCompany(state.artifacts ?? [], route) });
  });

  route(/\/api\/state-projections(?:\?.*)?$/, async (route: Route) => {
    if (route.request().method() !== "GET") {
      await route.continue();
      return;
    }
    const url = new URL(route.request().url());
    const projectionType = url.searchParams.get("projection_type");
    const programId = url.searchParams.get("program_id");
    const projections = scopedByCompany(state.stateProjections ?? [], route).filter(
      (projection) =>
        (!projectionType || projection.projection_type === projectionType) &&
        (!programId || projection.program_id === programId),
    );
    await fulfillJson(route, { state_projections: projections });
  });

  route(/\/api\/periodic-reviews(?:\?.*)?$/, async (route: Route) => {
    if (route.request().method() !== "GET") {
      await route.continue();
      return;
    }
    await fulfillJson(route, { periodic_reviews: scopedByCompany(state.periodicReviews ?? [], route) });
  });

  route(/\/api\/metric-snapshots(?:\?.*)?$/, async (route: Route) => {
    if (route.request().method() !== "GET") {
      await route.continue();
      return;
    }
    await fulfillJson(route, { metric_snapshots: scopedByCompany(state.metricSnapshots ?? [], route) });
  });

  route(/\/api\/report-runs(?:\?.*)?$/, async (route: Route) => {
    if (route.request().method() !== "GET") {
      await route.continue();
      return;
    }
    await fulfillJson(route, { report_runs: scopedByCompany(state.reportRuns ?? [], route) });
  });

  route(/\/api\/communication\/threads(?:\?.*)?$/, async (route: Route) => {
    if (route.request().method() !== "GET") {
      await route.continue();
      return;
    }
    const url = new URL(route.request().url());
    const companyId = url.searchParams.get("company_id");
    const threads = companyId
      ? (state.communicationThreads ?? []).filter((thread) => thread.company_id === companyId)
      : (state.communicationThreads ?? []);
    await fulfillJson(route, { threads });
  });

  route(/\/api\/whiteboards(?:\?.*)?$/, async (route: Route) => {
    if (route.request().method() !== "GET") {
      await route.continue();
      return;
    }
    await fulfillJson(route, { whiteboards: scopedByCompany(state.whiteboards ?? [], route) });
  });

  route(/\/api\/whiteboards\/[^/]+\/deployment(?:\/prepare)?(?:\?.*)?$/, async (route: Route) => {
    const url = new URL(route.request().url());
    const match = url.pathname.match(/\/api\/whiteboards\/([^/]+)\/deployment(?:\/prepare)?$/);
    const whiteboardId = match?.[1] ?? "";
    const whiteboard = (state.whiteboards ?? []).find((item) => item.id === whiteboardId);
    if (!whiteboard?.deployment_contract) {
      await route.fulfill({
        status: 404,
        contentType: "application/json",
        body: JSON.stringify({ error: { code: "NOT_FOUND", message: "Deployment contract was not found." } }),
      });
      return;
    }
    await fulfillJson(route, {
      deployment_contract: whiteboard.deployment_contract,
      whiteboard,
    });
  });

  route(/\/api\/whiteboards\/[^/]+\/deployment\/[^/]+\/execute(?:\?.*)?$/, async (route: Route) => {
    const url = new URL(route.request().url());
    const match = url.pathname.match(/\/api\/whiteboards\/([^/]+)\/deployment\/([^/]+)\/execute$/);
    const whiteboardId = match?.[1] ?? "";
    const channelId = match?.[2] ?? "";
    const whiteboard = (state.whiteboards ?? []).find((item) => item.id === whiteboardId);
    const channel = whiteboard?.deployment_contract?.channels.find((item) => item.id === channelId);
    if (!whiteboard?.deployment_contract || !channel) {
      await route.fulfill({
        status: 404,
        contentType: "application/json",
        body: JSON.stringify({ error: { code: "NOT_FOUND", message: "Deployment channel was not found." } }),
      });
      return;
    }
    await fulfillJson(route, {
      deployment_channel: channel,
      deployment_contract: whiteboard.deployment_contract,
      whiteboard,
    });
  });

  route(/\/api\/whiteboards\/[^/]+\/performance(?:\/(?:start|report|evaluate))?(?:\?.*)?$/, async (route: Route) => {
    const url = new URL(route.request().url());
    const match = url.pathname.match(/\/api\/whiteboards\/([^/]+)\/performance(?:\/(?:start|report|evaluate))?$/);
    const whiteboardId = match?.[1] ?? "";
    const whiteboard = (state.whiteboards ?? []).find((item) => item.id === whiteboardId);
    if (!whiteboard?.performance_contract) {
      await route.fulfill({
        status: 404,
        contentType: "application/json",
        body: JSON.stringify({ error: { code: "NOT_FOUND", message: "Performance contract was not found." } }),
      });
      return;
    }
    await fulfillJson(route, {
      performance_contract: whiteboard.performance_contract,
      whiteboard,
    });
  });

  route(/\/api\/communication\/threads\/[^/]+\/messages(?:\?.*)?$/, async (route: Route) => {
    const url = new URL(route.request().url());
    const match = url.pathname.match(/\/api\/communication\/threads\/([^/]+)\/messages$/);
    const threadId = match?.[1] ?? "";
    if (route.request().method() === "GET") {
      await fulfillJson(route, { messages: state.communicationMessages?.[threadId] ?? [] });
      return;
    }
    if (route.request().method() === "POST") {
      const posted = JSON.parse(route.request().postData() || "{}") as Partial<CommunicationMessageDTO>;
      const message: CommunicationMessageDTO = {
        id: `mock-message-${Date.now()}`,
        thread_id: threadId,
        organization_id: "playwright-product-modes-org",
        company_id: state.companyId,
        sender_kind: "user",
        sender_user_id: "playwright-user",
        sender_agent_id: null,
        sender_company_id: null,
        sender_organization_id: null,
        message_kind: String(posted.message_kind || "note"),
        body: String(posted.body || ""),
        body_format: String(posted.body_format || "markdown"),
        visibility: String(posted.visibility || "customer"),
        redacted: false,
        redacted_at: null,
        metadata: {},
        attachments: [],
        created_at: "2026-05-12T12:10:00.000Z",
        updated_at: "2026-05-12T12:10:00.000Z",
      };
      await route.fulfill({
        status: 201,
        contentType: "application/json",
        body: JSON.stringify(apiSuccess({ message })),
      });
      return;
    }
    await route.continue();
  });

  await Promise.all(routePromises);
}

function buildPack(input: {
  id: string;
  baseId: string;
  name: string;
  description: string;
  files?: Record<string, unknown>;
}): OperatingModelPack {
  return {
    pack_id: input.id,
    base_pack_id: input.baseId,
    version: "1.0.0",
    display_name: input.name,
    description: input.description,
    company_type_label: "Company",
    checksum: `playwright-${input.id}`,
    manifest: {},
    files: input.files ?? {},
  };
}

function buildInstallation(
  companyId: string,
  pack: OperatingModelPack,
  role: "primary" | "addon",
  index: number,
): OperatingModelInstallation {
  return {
    id: `${pack.pack_id}.installation`,
    company_id: companyId,
    pack_id: pack.pack_id,
    base_pack_id: pack.base_pack_id,
    role,
    namespace: `legacy.${role}.${index}`,
    status: "active",
    display_name: pack.display_name,
    version: pack.version,
    checksum: pack.checksum,
    company_type_label: pack.company_type_label,
    config: {},
    public_config: {},
    dashboard: {},
    active_since: "2026-05-01T08:00:00.000Z",
    archived_at: null,
    config_revision_count: role === "primary" ? 3 : 1,
    namespace_claim_count: role === "primary" ? 9 : 4,
    installed_at: "2026-05-01T08:00:00.000Z",
    updated_at: "2026-05-12T12:00:00.000Z",
  };
}

function buildArtifact(companyId: string, programId: string, id: string, title: string): WorkArtifactDTO {
  return {
    id,
    company_id: companyId,
    title,
    artifact_type: "service_report",
    program_id: programId,
    status: "accepted",
    metadata: {},
    canonical_revision_id: `${id}-rev-1`,
    revisions: [
      {
        id: `${id}-rev-1`,
        asset_id: id,
        version_number: 1,
        label: "v1",
        content_uri: `memory://${id}`,
        content_hash: `hash-${id}`,
        mime_type: "text/markdown",
        metadata: {},
        created_at: "2026-05-08T17:00:00.000Z",
      },
    ],
    created_at: "2026-05-08T17:00:00.000Z",
    updated_at: "2026-05-10T17:00:00.000Z",
  };
}

export function buildLegacyMultiPackProductModeState(base: CompanyWorkspaceMockState): ProductModeMockState {
  const programId = legacyMultiPackIds.program;
  const primaryPack = buildPack({
    id: legacyMultiPackIds.primary,
    baseId: "legacy-eyewear-core",
    name: "Legacy Eyewear Core",
    description: "Primary operating model for Legacy Eyewear company work.",
    files: {
      programs: {
        program_templates: [
          {
            id: "legacy-eyewear.service-program",
            display_label: "Service Program",
            title_template: "{{ company_name }} Service Program",
            objective_template: "Coordinate service delivery, reporting, and follow-up inside one Company.",
            default_current_stage_id: "stage-intake",
          },
        ],
      },
      operations: {
        operation_templates: [
          {
            id: "legacy-eyewear.frame-inventory-check",
            label: "Frame Inventory Check",
            description: "Review eyewear inventory and customer commitments.",
            outputs: ["service_report"],
            tool_ids: [],
            stage_ids: ["stage-intake"],
            module_ids: ["legacy-eyewear.fulfillment"],
          },
          {
            id: "legacy-eyewear.quarterly-review",
            label: "Quarterly Review",
            description: "Prepare company-scoped performance and service history.",
            outputs: ["service_report"],
            tool_ids: [],
            stage_ids: ["stage-review"],
            module_ids: ["legacy-eyewear.reporting"],
          },
        ],
      },
      modules: {
        modules: [
          {
            id: "legacy-eyewear.fulfillment",
            label: "Fulfillment",
            description: "Keeps product and service commitments together under the same Company.",
            department_id: "operations",
            capabilities: ["inventory", "service"],
            operation_template_ids: ["legacy-eyewear.frame-inventory-check"],
            artifact_schema_ids: ["service_report"],
            stage_ids: ["stage-intake"],
          },
          {
            id: "legacy-eyewear.reporting",
            label: "Reporting",
            description: "Publishes periodic company reports without creating a second company.",
            department_id: "operations",
            capabilities: ["reporting", "history"],
            operation_template_ids: ["legacy-eyewear.quarterly-review"],
            artifact_schema_ids: ["service_report"],
            stage_ids: ["stage-review"],
          },
        ],
      },
      service_model: {
        service_sections: [
          {
            id: "legacy-eyewear.service-history",
            label: "Service History",
            description: "History and outputs stay attached to the Legacy Eyewear Company.",
            operation_template_ids: ["legacy-eyewear.quarterly-review"],
            artifact_schema_ids: ["service_report"],
            items: ["reports", "projections", "artifacts"],
          },
        ],
      },
      assertions: {
        assertion_labels: {
          FACT: "Fact",
          OPINION: "Opinion",
          ASSUMPTION: "Assumption",
          QUESTION: "Question",
        },
        categories: ["company", "service", "inventory"],
      },
      artifacts: {
        artifact_schemas: [
          {
            id: "service_report",
            label: "Service Report",
            description: "Company-scoped report artifact.",
            produced_by_operations: ["legacy-eyewear.quarterly-review"],
            state_projection_behavior: "append_to_history",
          },
        ],
      },
      evaluations: {
        profiles: [{ id: "legacy.performance-readout", label: "Performance Readout", mode: "periodic_review" }],
      },
      policies: {
        policy_packs: [
          {
            id: "legacy.service-policy",
            label: "Legacy Service Policy",
            rules: [{ id: "legacy.publish", action_type: "publish_report", risk_floor: "LOW" }],
          },
        ],
      },
      dashboards: {
        panels: [
          { id: "legacy.overview", label: "Overview" },
          { id: "legacy.history", label: "History" },
        ],
      },
    },
  });
  const accountingPack = buildPack({
    id: legacyMultiPackIds.accounting,
    baseId: "legacy-eyewear-accounting",
    name: "Accounting Add-on",
    description: "Adds financial reconciliation capability to the same Legacy Eyewear Company.",
  });
  const legalPack = buildPack({
    id: legacyMultiPackIds.legal,
    baseId: "legacy-eyewear-legal",
    name: "Legal Add-on",
    description: "Adds review capability without creating a separate legal company.",
  });
  const consultingPack = buildPack({
    id: legacyMultiPackIds.consulting,
    baseId: "legacy-eyewear-consulting",
    name: "Consulting Add-on",
    description: "Adds advisory delivery capability inside the same Company boundary.",
  });
  const availablePacks = [primaryPack, accountingPack, legalPack, consultingPack];
  const installedPacks = availablePacks.map((pack, index) =>
    buildInstallation(base.companyId, pack, index === 0 ? "primary" : "addon", index + 1),
  );
  const programs: CompanyProgramDTO[] = [
    {
      id: programId,
      company_id: base.companyId,
      pack_id: primaryPack.pack_id,
      template_id: "legacy-eyewear.service-program",
      display_label: "Service Program",
      title: "Legacy Eyewear Service Program",
      objective: "Keep service, reporting, and add-on capability work inside the Legacy Eyewear Company.",
      status: "active",
      current_stage_id: "stage-review",
      metadata: {},
      stages: [
        {
          id: "legacy-eyewear-stage-intake",
          program_id: programId,
          stage_id: "stage-intake",
          label: "Intake",
          sequence: 1,
          status: "completed",
          state: {
            template: {
              expected_artifact_schema_ids: ["service_report"],
            },
          },
          operation_template_ids: ["legacy-eyewear.frame-inventory-check"],
          started_at: "2026-05-01T08:00:00.000Z",
          completed_at: "2026-05-02T08:00:00.000Z",
          updated_at: "2026-05-02T08:00:00.000Z",
        },
        {
          id: "legacy-eyewear-stage-review",
          program_id: programId,
          stage_id: "stage-review",
          label: "Review",
          sequence: 2,
          status: "active",
          state: {
            template: {
              expected_artifact_schema_ids: ["service_report"],
            },
          },
          operation_template_ids: ["legacy-eyewear.quarterly-review"],
          started_at: "2026-05-03T08:00:00.000Z",
          completed_at: null,
          updated_at: "2026-05-10T08:00:00.000Z",
        },
      ],
      created_at: "2026-05-01T08:00:00.000Z",
      updated_at: "2026-05-10T08:00:00.000Z",
    },
  ];
  const artifact = buildArtifact(
    base.companyId,
    programId,
    legacyMultiPackIds.artifact,
    "Legacy Eyewear service report",
  );
  const reportArtifact = buildArtifact(
    base.companyId,
    programId,
    `${legacyMultiPackIds.report}-artifact`,
    "Legacy Eyewear quarterly report",
  );
  const periodicReviews: PeriodicReviewDTO[] = [
    {
      id: legacyMultiPackIds.periodicReview,
      company_id: base.companyId,
      program_id: programId,
      pack_id: primaryPack.pack_id,
      template_id: "legacy-eyewear.quarterly-review",
      display_name: "Quarterly Service Review",
      cadence: "quarterly",
      timezone: "UTC",
      evaluation_profile_id: "legacy.performance-readout",
      report_template_id: "legacy-eyewear.service-report",
      history_projection_type: "client_service_history",
      enabled: true,
      metadata: {},
      created_at: "2026-05-01T08:00:00.000Z",
      updated_at: "2026-05-10T08:00:00.000Z",
    },
  ];
  const metricSnapshots: MetricSnapshotDTO[] = [
    {
      id: legacyMultiPackIds.metricSnapshot,
      company_id: base.companyId,
      program_id: programId,
      review_definition_id: legacyMultiPackIds.periodicReview,
      period_start: "2026-04-01",
      period_end: "2026-06-30",
      metric_values: {
        service_orders: 42,
        fulfillment_quality: 0.96,
      },
      metric_sources: {},
      source_type: "fixture",
      notes: "Seeded for product-mode smoke.",
      created_at: "2026-05-09T12:00:00.000Z",
    },
  ];
  const reportRuns: ReportRunDTO[] = [
    {
      id: legacyMultiPackIds.report,
      company_id: base.companyId,
      program_id: programId,
      review_definition_id: legacyMultiPackIds.periodicReview,
      metric_snapshot_id: legacyMultiPackIds.metricSnapshot,
      report_template_id: "legacy-eyewear.service-report",
      period_start: "2026-04-01",
      period_end: "2026-06-30",
      evaluation_run_ids: [],
      artifact: reportArtifact,
      artifact_revision_id: reportArtifact.canonical_revision_id,
      generated_sections: {
        summary: "Legacy Eyewear report generated under the same Company.",
      },
      source_refs: [],
      created_at: "2026-05-10T18:00:00.000Z",
    },
  ];
  const stateProjections: StateProjectionDTO[] = [
    {
      id: legacyMultiPackIds.projection,
      company_id: base.companyId,
      program_id: programId,
      projection_type: "currently_true_state",
      display_label: "Current State",
      source_refs: [{ artifact_id: artifact.id }],
      json_state: {
        company_id: base.companyId,
        company_name: base.companyName,
        installed_pack_count: installedPacks.length,
        primary_pack_id: primaryPack.pack_id,
        addon_pack_ids: installedPacks.filter((pack) => pack.role === "addon").map((pack) => pack.pack_id),
      },
      markdown_summary:
        "Legacy Eyewear is one Company with a primary pack plus accounting, legal, and consulting add-on packs.",
      generated_by: "playwright-product-modes",
      created_at: "2026-05-10T12:00:00.000Z",
      updated_at: "2026-05-10T12:00:00.000Z",
    },
    {
      id: legacyMultiPackIds.serviceHistory,
      company_id: base.companyId,
      program_id: programId,
      projection_type: "client_service_history",
      display_label: "Service History",
      source_refs: [{ artifact_id: artifact.id }, { report_run_id: legacyMultiPackIds.report }],
      json_state: {
        company_id: base.companyId,
        service_artifacts: [{ artifact_id: artifact.id, title: artifact.title }],
        report_runs: [{ report_run_id: legacyMultiPackIds.report, title: reportArtifact.title }],
        next_actions: [{ operation_template_id: "legacy-eyewear.quarterly-review", reason: "Continue review" }],
      },
      markdown_summary:
        "Legacy Eyewear service history keeps artifacts, reports, and projections under the same Company.",
      generated_by: "playwright-product-modes",
      created_at: "2026-05-10T12:00:00.000Z",
      updated_at: "2026-05-10T12:00:00.000Z",
    },
  ];
  const communicationThread: CommunicationThreadDTO = {
    id: legacyMultiPackIds.communicationThread,
    organization_id: "playwright-product-modes-org",
    company_id: base.companyId,
    service_engagement_id: null,
    operation_id: base.operations[0]?.id ?? null,
    approval_task_id: null,
    artifact_id: artifact.id,
    report_run_id: legacyMultiPackIds.report,
    title: "Legacy Eyewear consult",
    thread_type: "service_engagement",
    visibility_mode: "mixed",
    status: "open",
    source_key: "service_engagement:legacy-eyewear:primary",
    metadata: {},
    can_send_internal: false,
    created_by_user_id: null,
    created_by_agent_id: null,
    created_at: "2026-05-12T12:00:00.000Z",
    updated_at: "2026-05-12T12:05:00.000Z",
  };
  const communicationMessages: CommunicationMessageDTO[] = [
    {
      id: "legacy-whatsapp-question",
      thread_id: communicationThread.id,
      organization_id: communicationThread.organization_id,
      company_id: base.companyId,
      sender_kind: "user",
      sender_user_id: "legacy-owner",
      sender_agent_id: null,
      sender_company_id: null,
      sender_organization_id: null,
      message_kind: "request",
      body: "Can you explain why WhatsApp is recommended if the connector is missing?",
      body_format: "markdown",
      visibility: "customer",
      redacted: false,
      redacted_at: null,
      metadata: {},
      attachments: [],
      created_at: "2026-05-12T12:00:00.000Z",
      updated_at: "2026-05-12T12:00:00.000Z",
    },
    {
      id: "atlas-whatsapp-reply",
      thread_id: communicationThread.id,
      organization_id: communicationThread.organization_id,
      company_id: base.companyId,
      sender_kind: "user",
      sender_user_id: "atlas-operator",
      sender_agent_id: null,
      sender_company_id: null,
      sender_organization_id: null,
      message_kind: "response",
      body:
        "WhatsApp is recommended as a manual first step. Automation requires connecting a WhatsApp/Twilio/Brevo capability.",
      body_format: "markdown",
      visibility: "customer",
      redacted: false,
      redacted_at: null,
      metadata: {},
      attachments: [],
      created_at: "2026-05-12T12:03:00.000Z",
      updated_at: "2026-05-12T12:03:00.000Z",
    },
  ];
  const whiteboard: WorkWhiteboardDTO = {
    id: legacyMultiPackIds.whiteboard,
    organization_id: "playwright-product-modes-org",
    company_id: base.companyId,
    service_engagement_id: null,
    communication_thread_id: communicationThread.id,
    source_message_id: "legacy-whatsapp-question",
    status: "in_approval",
    request_type: "campaign",
    client_name: base.companyName,
    request_summary:
      "Legacy asked why WhatsApp is recommended while the connector is missing; onboarding is collecting launch context before strategy.",
    objective: "Clarify the manual-first launch path before strategy.",
    budget_limit: "$5000",
    timeline: "next week",
    constraints: { legal: "No unsupported performance claims." },
    target_audience: { segment: "premium eyewear shoppers" },
    brand_context: { brand_voice: "precise" },
    product_context: { offer: "DEPP GOLD launch consult" },
    channel_context: { requested_channels: ["whatsapp"], connectors: ["email"] },
    known_facts: { approval_owner: "Legacy owner", success_metrics: "consult replies", inventory: "launch batch" },
    missing_fields: [],
    completion_score: 100,
    redis_snapshot_key: "forgegraph:whiteboard:legacy-eyewear-work-whiteboard",
    assumptions: ["Internal readiness depends on connector configuration."],
    metadata: { source: "playwright-product-modes" },
    routing_records: [
      {
        id: "legacy-whiteboard-deployment-task",
        department_id: "deployment-ops",
        department_name: "Deployment Ops",
        status: "queued",
        priority: "normal",
        reason: "Fill missing whiteboard context: connector_readiness.",
        created_at: "2026-05-12T12:06:00.000Z",
      },
      {
        id: "legacy-whiteboard-content-task",
        department_id: "content-creative",
        department_name: "Content/Creative",
        status: "queued",
        priority: "normal",
        reason: "Strategy gate passed. Content/Creative can begin content planning.",
        created_at: "2026-05-12T12:22:00.000Z",
      },
      {
        id: "legacy-whiteboard-client-services-approval",
        department_id: "client-services",
        department_name: "Client Services",
        status: "queued",
        priority: "normal",
        reason: "Content production gate passed. Client approval can begin.",
        created_at: "2026-05-12T12:23:00.000Z",
      },
    ],
    phase_contracts: [
      {
        whiteboard_id: legacyMultiPackIds.whiteboard,
        phase_id: "atlas_agency_ops.v1.content_production",
        source_policy_id: "atlas_agency_ops.v1.content_production",
        pack_id: "atlas_agency_ops.v1",
        phase_name: "Content Production",
        workstreams: [
          "copywriting",
          "social_content",
          "email_sequence",
          "whatsapp_script",
          "landing_page_copy",
          "ad_copy",
          "visual_concepts",
          "video_storyboard",
        ].map((workstream, index) => ({
          id: workstream,
          name: workstream.replaceAll("_", " ").replace(/\b\w/g, (letter) => letter.toUpperCase()),
          status: "completed",
          required: true,
          output_type: "asset",
          department_id: index < 3 ? "content" : "creative",
          department_name: index < 3 ? "Content" : "Creative",
          run_id: `legacy-phase-run-${index + 1}`,
          task_lifecycle_id: `legacy-phase-lifecycle-${index + 1}`,
          asset_id: `legacy-phase-asset-${index + 1}`,
          asset_version_id: `legacy-phase-asset-version-${index + 1}`,
          reason: `Complete configured workstream: ${workstream.replaceAll("_", " ")}.`,
          created_at: "2026-05-12T12:12:00.000Z",
          updated_at: "2026-05-12T12:20:00.000Z",
        })),
        gate: {
          gate_id: "atlas_agency_ops.v1.content_quality_gate",
          result: "pass",
          criteria: [
            { key: "brand_alignment", value_type: "number", operator: ">=", threshold: 90 },
            { key: "strategy_alignment", value_type: "number", operator: ">=", threshold: 90 },
            { key: "channel_fit", value_type: "number", operator: ">=", threshold: 90 },
            { key: "claim_support", value_type: "enum", operator: "in", expected: ["pass", 100] },
            { key: "legal_compliance", value_type: "enum", operator: "in", expected: ["pass", 100] },
            { key: "format_compliance", value_type: "number", operator: ">=", threshold: 95 },
            { key: "execution_readiness", value_type: "number", operator: ">=", threshold: 85 },
          ],
          approval_required: true,
          latest_evaluation: {
            evaluation_id: "legacy-content-quality-gate",
            status: "PASS",
            result: "pass",
            score: 100,
            grade: "A",
            evaluated_at: "2026-05-12T12:22:00.000Z",
          },
        },
        current_state: {
          status: "passed",
          all_workstreams_completed: true,
          synthesis: {
            asset_id: "legacy-content-synthesis",
            asset_version_id: "legacy-content-synthesis-v1",
            created_at: "2026-05-12T12:21:00.000Z",
          },
          gate: {
            evaluation_id: "legacy-content-quality-gate",
            status: "PASS",
            result: "pass",
            score: 100,
            grade: "A",
            evaluated_at: "2026-05-12T12:22:00.000Z",
          },
          applied_actions: { approval_task_id: "legacy-content-approval" },
        },
        allowed_actions: [],
      },
    ],
    deployment_contract: {
      whiteboard_id: legacyMultiPackIds.whiteboard,
      policy_id: "atlas_agency_ops.v1.launch_deployment",
      source_policy_id: "atlas_agency_ops.v1.launch_deployment",
      pack_id: "atlas_agency_ops.v1",
      status: "partial",
      channels: [
        {
          id: "email",
          display_name: "Email",
          status: "executed",
          blocked_reason: "",
          blocked_reason_code: "",
          tool_execution_id: "legacy-email-sandbox-tool-execution",
          company_signal_id: "",
          routing_record_id: "",
          approval_task_id: "legacy-content-approval",
          asset_id: "legacy-phase-asset-3",
          asset_version_id: "legacy-phase-asset-version-3",
          allowed_actions: [],
          department: "crm",
          department_name: "CRM",
          required_connector: "email_service_connector",
          tool_id: "dmp.email_draft_send_schedule",
          asset_types: ["asset", "publication_draft"],
          risk_level: "medium",
          receipt: {
            tool_execution_id: "legacy-email-sandbox-tool-execution",
            tool_id: "dmp.email_draft_send_schedule",
            dry_run: true,
            status: "succeeded",
            completed_at: "2026-05-12T12:30:00.000Z",
            result: {
              provider: "local_capture",
              mode: "sandbox",
              status: "captured",
              message_id: "fg-email-sandbox-legacy",
              recipient_count: 0,
              recipient_domains: [],
            },
          },
        },
        ...["whatsapp", "instagram", "facebook", "tiktok", "landing_page"].map((channel) => ({
          id: channel,
          display_name: channel.replaceAll("_", " ").replace(/\b\w/g, (letter) => letter.toUpperCase()),
          status: "blocked",
          blocked_reason: "Required connector is not available for this company.",
          blocked_reason_code: "connector_missing",
          tool_execution_id: "",
          company_signal_id: `legacy-deployment-signal-${channel}`,
          routing_record_id: `legacy-deployment-routing-${channel}`,
          approval_task_id: "legacy-content-approval",
          asset_id: "",
          asset_version_id: "",
          allowed_actions: [],
          department: channel === "landing_page" ? "web" : "social",
          department_name: channel === "landing_page" ? "Web" : "Social",
          required_connector: `${channel}_connector`,
          tool_id: `${channel}.publish`,
          asset_types: ["publication_draft"],
          risk_level: "high",
        })),
      ],
      current_state: {
        status: "partial",
        updated_at: "2026-05-12T12:30:00.000Z",
        prepared_at: "2026-05-12T12:30:00.000Z",
      },
      allowed_actions: [],
    },
    performance_contract: {
      whiteboard_id: legacyMultiPackIds.whiteboard,
      policy_id: "atlas_agency_ops.v1.launch_performance_review",
      source_policy_id: "atlas_agency_ops.v1.launch_performance_review",
      pack_id: "atlas_agency_ops.v1",
      status: "partial",
      cadence: "weekly",
      sources: [
        {
          id: "email",
          display_name: "Email",
          status: "collected",
          blocked_reason: "",
          blocked_reason_code: "",
          tool_execution_id: "legacy-email-performance-tool-execution",
          company_signal_id: "",
          routing_record_id: "",
          operation_id: "legacy-email-performance-run",
          metrics: {
            open_rate: 0.42,
            click_rate: 0.11,
            execution_completeness: 86,
          },
          department: "crm",
          department_name: "CRM",
          required_connector: "email_service_connector",
          tool_id: "dmp.email_draft_send_schedule",
          metric_keys: ["open_rate", "click_rate", "execution_completeness"],
          receipt: {
            tool_execution_id: "legacy-email-performance-tool-execution",
            tool_id: "dmp.email_draft_send_schedule",
            dry_run: true,
            status: "succeeded",
            completed_at: "2026-05-19T09:00:00.000Z",
            result: {
              provider: "local_capture",
              mode: "sandbox",
              status: "captured",
            },
          },
        },
        ...["whatsapp", "social", "landing_page"].map((source) => ({
          id: source,
          display_name: source.replaceAll("_", " ").replace(/\b\w/g, (letter) => letter.toUpperCase()),
          status: "blocked",
          blocked_reason: "Required metric connector is not available for this company.",
          blocked_reason_code: "missing_metric_connector",
          tool_execution_id: "",
          company_signal_id: `legacy-performance-signal-${source}`,
          routing_record_id: `legacy-performance-routing-${source}`,
          operation_id: "",
          metrics: {},
          department: source === "landing_page" ? "analytics" : "deployment-ops",
          department_name: source === "landing_page" ? "Analytics" : "Deployment Ops",
          required_connector: `${source}_analytics_connector`,
          tool_id: `${source}.metrics`,
          metric_keys: ["configured_metric"],
        })),
      ],
      current_state: {
        status: "evaluated",
        metric_snapshot_id: "legacy-performance-metric-snapshot",
        report_run_id: "legacy-performance-report-run",
        evaluation_id: "legacy-performance-evaluation",
        period_start: "2026-05-04",
        period_end: "2026-05-10",
        updated_at: "2026-05-19T09:05:00.000Z",
      },
      allowed_actions: [],
    },
    can_update: true,
    created_at: "2026-05-12T12:05:00.000Z",
    updated_at: "2026-05-12T12:06:00.000Z",
  };
  const state: ProductModeMockState = {
    ...base,
    pendingApprovalCount: base.pendingApprovalCount ?? 0,
    availablePacks,
    installedPacks,
    programs,
    assertions: [],
    artifacts: [artifact],
    periodicReviews,
    metricSnapshots,
    reportRuns,
    stateProjections,
    communicationThreads: [communicationThread],
    communicationMessages: {
      [communicationThread.id]: communicationMessages,
    },
    whiteboards: [whiteboard],
  };
  return {
    ...state,
    operatingModel: buildCompanyOperatingModel(state),
  };
}
