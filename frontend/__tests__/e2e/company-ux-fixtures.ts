import type { Page, Route } from "@playwright/test";

import type {
  ApprovalTask,
  CompanyDTO,
  CompanyOperatingModelVersionDTO,
  GraphDetail,
  GraphListItem,
  NodeRunItem,
  OperatingBrief,
  RunDetail,
  RunListItem,
  RunStatus,
} from "../../lib/api";
import { NODE_TYPES, type GraphJson } from "../../lib/graph-types";

function apiSuccess<T>(data: T) {
  return {
    data,
    meta: {
      requestId: "playwright-company-ux",
      timestamp: "2026-04-26T12:00:00.000Z",
    },
  };
}

type MinimalGraphVersion = {
  id: string;
  version: number;
  graph_json: GraphJson;
};

function buildDemoOperatingModelPack() {
  return {
    pack_id: "company_ops_demo.v1",
    base_pack_id: "company_ops_demo",
    version: "1.0.0",
    display_name: "Company Ops Demo",
    description: "A generic company operating model pack for workspace tests.",
    company_type_label: "Company",
    checksum: "playwright",
    manifest: {},
    files: {
      programs: {
        program_templates: [
          {
            id: "demo.program",
            display_label: "Program",
            title_template: "{{ company_name }} Operating Program",
            objective_template: "Run a generic company operating program.",
            default_current_stage_id: "stage_01",
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
        categories: ["company", "customer", "operations"],
      },
      artifacts: {
        artifact_schemas: [
          { id: "brief", label: "Brief" },
          { id: "report", label: "Report" },
        ],
      },
      evaluations: {
        profiles: [{ id: "demo.quick_check", label: "Quick Check", mode: "quick" }],
      },
      policies: {
        policy_packs: [
          {
            id: "demo.policy",
            label: "Company Policy",
            rules: [{ id: "demo.publish", action_type: "publish", risk_floor: "MEDIUM" }],
          },
        ],
      },
      dashboards: {
        panels: [
          { id: "demo.overview", label: "Overview" },
          { id: "demo.programs", label: "Programs" },
        ],
      },
    },
  };
}

export type MockCompanyOperation = {
  id: string;
  status: RunStatus;
  startedAt: string;
  endedAt?: string | null;
  operationBrief?: string;
  deliverable?: string;
  errorMessage?: string;
  currentNodeId?: string | null;
  failedNodeId?: string | null;
  llmMode?: "managed" | "byok";
  provider?: string;
};

export type CompanyWorkspaceMockState = {
  companyId: string;
  companyName: string;
  graphVersion: MinimalGraphVersion;
  operations: MockCompanyOperation[];
  brief?: OperatingBrief;
  pendingApprovalCount?: number;
  approvals?: ApprovalTask[];
  onStart?: (input: Record<string, unknown>, state: CompanyWorkspaceMockState) => MockCompanyOperation;
  onReplay?: (
    runId: string,
    input: Record<string, unknown>,
    state: CompanyWorkspaceMockState,
  ) => MockCompanyOperation | void;
};

function buildDefaultApprovals(state: CompanyWorkspaceMockState): ApprovalTask[] {
  const count = state.pendingApprovalCount ?? 0;
  if (count === 0) {
    return [];
  }

  const candidateRuns = state.operations.slice(0, count);
  return candidateRuns.map((operation, index) => ({
    id: `approval-${index + 1}`,
    run_id: operation.id,
    run_name: `Operation ${operation.id.slice(0, 8)}`,
    graph_name: state.companyName,
    node_id: operation.currentNodeId ?? getDepartmentNodes(state.graphVersion.graph_json)[0]?.id ?? "approval-required",
    node_name:
      getNodeLabel(
        operation.currentNodeId ?? getDepartmentNodes(state.graphVersion.graph_json)[0]?.id ?? "approval-required",
        state.graphVersion.graph_json,
      ) ?? "Approval Required",
    status: "pending",
    prompt_message: "Approval required before this company operation can continue.",
    payload: {
      prompt_message: "Approval required before this company operation can continue.",
      required_fields: ["notes"],
    },
    result: null,
    created_at: "2026-04-26T11:00:00.000Z",
    resolved_at: null,
  }));
}

function getDepartmentNodes(graphJson: GraphJson) {
  return graphJson.nodes.filter((node) => node.type !== NODE_TYPES.OUTPUT);
}

function getNodeLabel(nodeId: string, graphJson: GraphJson): string | undefined {
  return graphJson.nodes.find((node) => node.id === nodeId)?.name;
}

function buildNodeRuns(operation: MockCompanyOperation, graphJson: GraphJson): NodeRunItem[] {
  const nodes = getDepartmentNodes(graphJson);
  if (operation.status === "pending") {
    return [];
  }

  const resolvedCurrentNodeId = operation.currentNodeId ?? nodes[0]?.id ?? null;
  const resolvedFailedNodeId = operation.failedNodeId ?? resolvedCurrentNodeId;
  const currentIndex = nodes.findIndex((node) => node.id === resolvedCurrentNodeId);
  const failedIndex = nodes.findIndex((node) => node.id === resolvedFailedNodeId);

  return nodes.flatMap((node, index) => {
    const baseRun: NodeRunItem = {
      id: `${operation.id}-node-${index + 1}`,
      node_id: node.id,
      node_type: node.type,
      status: "pending",
      attempt: 1,
      started_at: operation.startedAt,
      ended_at: null,
      duration_ms: index === 0 ? 12000 : 18000,
      input_json: {
        operation_brief: operation.operationBrief ?? "Run the next company operation.",
      },
      output_json: null,
      error_json: null,
      agent_trace: null,
      memory_activity: null,
    };

    if (operation.status === "running") {
      if (index < (currentIndex >= 0 ? currentIndex : 0)) {
        return [
          {
            ...baseRun,
            status: "succeeded",
            ended_at: "2026-04-26T11:05:00.000Z",
            output_json: {
              deliverable: `${node.name ?? "Department"} handed work forward.`,
            },
          },
        ];
      }
      if (index === (currentIndex >= 0 ? currentIndex : 0)) {
        return [
          {
            ...baseRun,
            status: "running",
          },
        ];
      }
      return [];
    }

    if (operation.status === "failed") {
      if (index < (failedIndex >= 0 ? failedIndex : 0)) {
        return [
          {
            ...baseRun,
            status: "succeeded",
            ended_at: "2026-04-26T11:07:00.000Z",
            output_json: {
              deliverable: `${node.name ?? "Department"} completed its work.`,
            },
          },
        ];
      }
      if (index === (failedIndex >= 0 ? failedIndex : 0)) {
        return [
          {
            ...baseRun,
            status: "failed",
            ended_at: operation.endedAt ?? "2026-04-26T11:10:00.000Z",
            error_json: {
              message: operation.errorMessage ?? "Department task failed.",
            },
          },
        ];
      }
      return [];
    }

    if (operation.status === "paused") {
      if (index < (currentIndex >= 0 ? currentIndex : 0)) {
        return [
          {
            ...baseRun,
            status: "succeeded",
            ended_at: "2026-04-26T11:07:00.000Z",
            output_json: {
              deliverable: `${node.name ?? "Department"} completed its work.`,
            },
          },
        ];
      }
      if (index === (currentIndex >= 0 ? currentIndex : 0)) {
        return [
          {
            ...baseRun,
            status: "pending",
          },
        ];
      }
      return [];
    }

    return [
      {
        ...baseRun,
        status: "succeeded",
        ended_at: operation.endedAt ?? "2026-04-26T11:12:00.000Z",
        output_json: {
          deliverable:
            index === nodes.length - 1
              ? (operation.deliverable ?? "Deliverable ready for review.")
              : `${node.name ?? "Department"} completed its work.`,
        },
      },
    ];
  });
}

function buildRunListItem(state: CompanyWorkspaceMockState, operation: MockCompanyOperation): RunListItem {
  return {
    id: operation.id,
    graph_id: state.companyId,
    graph_name: state.companyName,
    graph_version_id: state.graphVersion.id,
    graph_version: state.graphVersion.version,
    status: operation.status,
    queue_status:
      operation.status === "pending"
        ? "queued"
        : operation.status === "paused"
          ? "paused"
          : operation.status === "succeeded"
            ? "completed"
            : operation.status,
    queue_attempts: 1,
    queue_available_at: null,
    started_at: operation.startedAt,
    ended_at: operation.endedAt ?? null,
    duration_ms: operation.endedAt ? 120000 : 45000,
    llm_access: {
      llm_mode: operation.llmMode ?? "managed",
      provider: operation.provider ?? "openai",
      credential_id: operation.llmMode === "byok" ? "credential-1" : null,
      api_key_present: operation.llmMode === "byok",
    },
    memory_activity: {
      has_activity: false,
      save_node_count: 0,
      saved_observation_count: 0,
      retrieval_node_count: 0,
      retrieved_observation_count: 0,
      influenced_node_count: 0,
      influenced_observation_count: 0,
      degraded: false,
    },
  };
}

function buildGraphListItem(state: CompanyWorkspaceMockState): GraphListItem {
  return {
    id: state.companyId,
    name: state.companyName,
    description: String(state.graphVersion.graph_json.metadata?.description ?? ""),
    created_at: "2026-04-26T08:00:00.000Z",
    updated_at: "2026-04-26T12:00:00.000Z",
    version_count: state.graphVersion.version,
    latest_version: state.graphVersion.version,
  };
}

function buildGraphDetail(state: CompanyWorkspaceMockState): GraphDetail {
  return {
    id: state.companyId,
    owner_id: "playwright-company-owner",
    name: state.companyName,
    description: String(state.graphVersion.graph_json.metadata?.description ?? ""),
    created_at: "2026-04-26T08:00:00.000Z",
    updated_at: "2026-04-26T12:00:00.000Z",
    versions: [
      {
        id: state.graphVersion.id,
        version: state.graphVersion.version,
        checksum: `checksum-${state.graphVersion.id}`,
        created_at: "2026-04-26T08:05:00.000Z",
      },
    ],
  };
}

function buildCompanyListItem(state: CompanyWorkspaceMockState): CompanyDTO {
  return {
    id: state.companyId,
    company_id: state.companyId,
    workflow_definition_id: state.companyId,
    storage_model: "Graph",
    organization_id: "playwright-company-org",
    name: state.companyName,
    description: String(state.graphVersion.graph_json.metadata?.description ?? ""),
    created_at: "2026-04-26T08:00:00.000Z",
    updated_at: "2026-04-26T12:00:00.000Z",
    setup_version_count: state.graphVersion.version,
    latest_setup_version: state.graphVersion.version,
  };
}

function buildCompanyOperatingModelVersion(state: CompanyWorkspaceMockState): CompanyOperatingModelVersionDTO {
  return {
    id: state.graphVersion.id,
    company_id: state.companyId,
    workflow_definition_id: state.companyId,
    version: state.graphVersion.version,
    model_json: state.graphVersion.graph_json,
    checksum: `checksum-${state.graphVersion.id}`,
    created_at: "2026-04-26T08:05:00.000Z",
  };
}

function buildDefaultOperatingBrief(state: CompanyWorkspaceMockState, operationId?: string | null): OperatingBrief {
  const profile = state.graphVersion.graph_json.metadata?.company_profile;
  const objective =
    profile && typeof profile === "object" && "objective" in profile
      ? String((profile as Record<string, unknown>).objective ?? "")
      : String(state.graphVersion.graph_json.metadata?.description ?? "");

  return {
    id: null,
    organization_id: "playwright-company-org",
    company_id: state.companyId,
    operation_id: operationId ?? null,
    objective: objective || null,
    deliverable: null,
    constraints: [],
    success_criteria: [],
    stakeholders: [],
    dependencies: [],
    assumptions: [],
    clarifications: [],
    priority_frame: {
      speed: 0.5,
      cost: 0.5,
      quality: 0.5,
      risk: 0.5,
    },
    autonomy_mode: "assisted",
    created_at: null,
    updated_at: null,
  };
}

function mutateOperatingBrief(
  state: CompanyWorkspaceMockState,
  text: string,
  operationId?: string | null,
): OperatingBrief {
  const lower = text.toLowerCase();
  const current = state.brief ?? buildDefaultOperatingBrief(state, operationId);
  const brief: OperatingBrief = {
    ...current,
    id: current.id ?? "playwright-operating-brief",
    operation_id: operationId ?? current.operation_id,
    constraints: [...current.constraints],
    success_criteria: [...current.success_criteria],
    stakeholders: [...current.stakeholders],
    dependencies: [...current.dependencies],
    assumptions: [...current.assumptions],
    clarifications: [...current.clarifications],
    priority_frame: { ...current.priority_frame },
    updated_at: "2026-04-26T12:00:00.000Z",
  };

  if (!brief.objective && text.trim()) {
    brief.objective = text.trim();
    brief.deliverable = text.replace(/^(build|create|launch)\s+/i, "").trim() || null;
  }
  if (lower.includes("enterprise")) {
    brief.stakeholders = Array.from(new Set([...brief.stakeholders, "Enterprise clients"]));
  }
  if (lower.includes("paid ads")) {
    brief.constraints = Array.from(new Set([...brief.constraints, "Cannot use paid ads"]));
  }
  if (lower.includes("speed")) {
    brief.priority_frame = { ...brief.priority_frame, speed: 0.9, cost: lower.includes("cost") ? 0.3 : 0.5 };
  }
  brief.assumptions = [
    ...brief.assumptions,
    {
      field: "context",
      value: text,
      confidence: 0.7,
      created_at: "2026-04-26T12:00:00.000Z",
    },
  ];
  state.brief = brief;
  return brief;
}

function buildRunDetail(state: CompanyWorkspaceMockState, operation: MockCompanyOperation): RunDetail {
  const nodeRuns = buildNodeRuns(operation, state.graphVersion.graph_json);
  const pausedNodeId =
    operation.status === "paused"
      ? (operation.currentNodeId ?? getDepartmentNodes(state.graphVersion.graph_json)[0]?.id ?? null)
      : null;

  return {
    id: operation.id,
    owner_id: "playwright-company-owner",
    thread_id: null,
    graph_id: state.companyId,
    graph_name: state.companyName,
    graph_version_id: state.graphVersion.id,
    graph_version: state.graphVersion.version,
    status: operation.status,
    queue_status:
      operation.status === "pending"
        ? "queued"
        : operation.status === "paused"
          ? "paused"
          : operation.status === "succeeded"
            ? "completed"
            : operation.status,
    queue_attempts: 1,
    queue_available_at: null,
    started_at: operation.startedAt,
    ended_at: operation.endedAt ?? null,
    input_json: {
      company_name: state.companyName,
      objective: state.graphVersion.graph_json.metadata?.description ?? "",
      operation_brief: operation.operationBrief ?? "Run the next company operation.",
    },
    output_json:
      operation.status === "succeeded"
        ? {
            deliverable: operation.deliverable ?? "Deliverable ready for review.",
          }
        : null,
    error_message: operation.errorMessage ?? "",
    duration_ms: operation.endedAt ? 120000 : 45000,
    node_runs: nodeRuns,
    agent_events: [],
    memory_activity: null,
    llm_access: {
      llm_mode: operation.llmMode ?? "managed",
      provider: operation.provider ?? "openai",
      credential_id: operation.llmMode === "byok" ? "credential-1" : null,
      api_key_present: operation.llmMode === "byok",
    },
    paused_node_id: pausedNodeId,
    pause_payload: pausedNodeId
      ? {
          node_id: pausedNodeId,
          node_name: getNodeLabel(pausedNodeId, state.graphVersion.graph_json) ?? "Approval Required",
          prompt_message: "Approval required before this company operation can continue.",
          required_fields: ["notes"],
        }
      : null,
  };
}

function createOperationId() {
  const suffix = Math.random().toString(16).slice(2, 14).padEnd(12, "0");
  return `aaaaaaaa-aaaa-4aaa-8aaa-${suffix}`;
}

function toInputRecord(value: unknown): Record<string, unknown> {
  if (!value || typeof value !== "object" || Array.isArray(value)) {
    return {};
  }
  return value as Record<string, unknown>;
}

export async function installCompanyWorkspaceMocks(page: Page, state: CompanyWorkspaceMockState): Promise<void> {
  const demoPack = buildDemoOperatingModelPack();
  const routePromises: Array<ReturnType<Page["route"]>> = [];
  const route = (...args: Parameters<Page["route"]>) => {
    routePromises.push(page.route(...args));
  };

  route(/\/api\/graphs\/?(?:\?.*)?$/, async (route: Route) => {
    if (route.request().method() !== "GET") {
      await route.continue();
      return;
    }

    await route.fulfill({
      status: 200,
      contentType: "application/json",
      body: JSON.stringify(apiSuccess([buildGraphListItem(state)])),
    });
  });

  route(new RegExp(`/api/graphs/${state.companyId}/versions/latest(?:\\?.*)?$`), async (route: Route) => {
    await route.fulfill({
      status: 200,
      contentType: "application/json",
      body: JSON.stringify(apiSuccess(state.graphVersion)),
    });
  });

  route(new RegExp(`/api/graphs/${state.companyId}(?:\\?.*)?$`), async (route: Route) => {
    if (route.request().method() !== "GET") {
      await route.continue();
      return;
    }

    await route.fulfill({
      status: 200,
      contentType: "application/json",
      body: JSON.stringify(apiSuccess(buildGraphDetail(state))),
    });
  });

  route(/\/api\/companies\/?(?:\?.*)?$/, async (route: Route) => {
    if (route.request().method() !== "GET") {
      await route.continue();
      return;
    }

    await route.fulfill({
      status: 200,
      contentType: "application/json",
      body: JSON.stringify(apiSuccess([buildCompanyListItem(state)])),
    });
  });

  route(
    new RegExp(`/api/companies/${state.companyId}/operating-model-versions/latest(?:\\?.*)?$`),
    async (route: Route) => {
      await route.fulfill({
        status: 200,
        contentType: "application/json",
        body: JSON.stringify(apiSuccess(buildCompanyOperatingModelVersion(state))),
      });
    },
  );

  route(new RegExp(`/api/companies/${state.companyId}(?:\\?.*)?$`), async (route: Route) => {
    if (route.request().method() !== "GET") {
      await route.continue();
      return;
    }

    await route.fulfill({
      status: 200,
      contentType: "application/json",
      body: JSON.stringify(apiSuccess(buildCompanyListItem(state))),
    });
  });

  route(/\/api\/decisions\/count(?:\?.*)?$/, async (route: Route) => {
    await route.fulfill({
      status: 200,
      contentType: "application/json",
      body: JSON.stringify(apiSuccess({ count: state.pendingApprovalCount ?? 0 })),
    });
  });

  route(/\/api\/approvals\/count(?:\?.*)?$/, async (route: Route) => {
    await route.fulfill({
      status: 200,
      contentType: "application/json",
      body: JSON.stringify(apiSuccess({ count: state.pendingApprovalCount ?? 0 })),
    });
  });

  route(/\/api\/approvals\/?(?:\?.*)?$/, async (route: Route) => {
    if (route.request().method() !== "GET") {
      await route.continue();
      return;
    }

    const approvals = state.approvals ?? buildDefaultApprovals(state);
    await route.fulfill({
      status: 200,
      contentType: "application/json",
      body: JSON.stringify(apiSuccess(approvals)),
    });
  });

  route(/\/api\/operating-model-packs\/?(?:\?.*)?$/, async (route: Route) => {
    await route.fulfill({
      status: 200,
      contentType: "application/json",
      body: JSON.stringify(apiSuccess({ packs: [demoPack] })),
    });
  });

  route(new RegExp(`/api/companies/${state.companyId}/operating-model(?:\\?.*)?$`), async (route: Route) => {
    await route.fulfill({
      status: 200,
      contentType: "application/json",
      body: JSON.stringify(
        apiSuccess({
          operating_model: {
            company_id: state.companyId,
            installed_packs: [],
            programs: [],
            evaluation_profiles: [],
            policy_packs: [],
            signal_taxonomies: [],
          },
        }),
      ),
    });
  });

  route(new RegExp(`/api/companies/${state.companyId}/programs(?:\\?.*)?$`), async (route: Route) => {
    if (route.request().method() !== "GET") {
      await route.continue();
      return;
    }

    await route.fulfill({
      status: 200,
      contentType: "application/json",
      body: JSON.stringify(apiSuccess({ programs: [] })),
    });
  });

  route(/\/api\/assertions(?:\?.*)?$/, async (route: Route) => {
    if (route.request().method() !== "GET") {
      await route.continue();
      return;
    }

    await route.fulfill({
      status: 200,
      contentType: "application/json",
      body: JSON.stringify(apiSuccess({ assertions: [] })),
    });
  });

  route(/\/api\/work-artifacts(?:\?.*)?$/, async (route: Route) => {
    if (route.request().method() !== "GET") {
      await route.continue();
      return;
    }

    await route.fulfill({
      status: 200,
      contentType: "application/json",
      body: JSON.stringify(apiSuccess({ artifacts: [] })),
    });
  });

  route(/\/api\/state-projections(?:\?.*)?$/, async (route: Route) => {
    await route.fulfill({
      status: 200,
      contentType: "application/json",
      body: JSON.stringify(apiSuccess({ state_projections: [] })),
    });
  });

  route(/\/api\/interaction\/briefs\/current(?:\?.*)?$/, async (route: Route) => {
    const url = new URL(route.request().url());
    const operationId = url.searchParams.get("operation_id");
    const brief = state.brief ?? buildDefaultOperatingBrief(state, operationId);
    await route.fulfill({
      status: 200,
      contentType: "application/json",
      body: JSON.stringify(apiSuccess({ brief })),
    });
  });

  route(/\/api\/interaction\/events(?:\?.*)?$/, async (route: Route) => {
    const input = toInputRecord(route.request().postDataJSON());
    const text = String(input.input ?? "");
    const operationId = typeof input.operation_id === "string" ? input.operation_id : null;
    const brief = mutateOperatingBrief(state, text, operationId);
    const lower = text.toLowerCase();
    const affectedFields = [
      ...(lower.includes("enterprise") ? ["stakeholders"] : []),
      ...(lower.includes("paid ads") ? ["constraints"] : []),
      ...(lower.includes("speed") ? ["priority_frame"] : []),
    ];

    await route.fulfill({
      status: 201,
      contentType: "application/json",
      body: JSON.stringify(
        apiSuccess({
          brief,
          event: {
            id: "playwright-interaction-event",
            brief_id: brief.id ?? "playwright-operating-brief",
            company_id: state.companyId,
            operation_id: operationId,
            sequence: 1,
            type: lower.includes("paid ads") ? "CONSTRAINT" : lower.includes("speed") ? "PRIORITY_SHIFT" : "MODIFY",
            actor: "user",
            timestamp: "2026-04-26T12:00:00.000Z",
            raw_input: text,
            delta: {},
            affected_fields: affectedFields,
            interpretation: {},
            pm_action: "ASSUME_AND_CONTINUE",
            plan_implications: {
              execution_ready: false,
              requires_plan_revision: Boolean(operationId),
              active_operation_id: operationId,
              should_interrupt_active_operation: false,
              affected_fields: affectedFields,
              blocking_clarifications: [],
              summary: "Brief updated; assumptions were recorded so work can continue without restarting.",
            },
            created_at: "2026-04-26T12:00:00.000Z",
          },
          interpretation: {
            intent_classification: lower.includes("paid ads")
              ? "CONSTRAINT"
              : lower.includes("speed")
                ? "PRIORITY_SHIFT"
                : "MODIFY",
            affected_fields: affectedFields,
            confidence: 0.8,
            rationale: "Mocked interaction interpretation.",
          },
          pm_action: {
            action: "ASSUME_AND_CONTINUE",
            rationale: "Mocked interaction decision.",
          },
          plan_implications: {
            execution_ready: false,
            requires_plan_revision: Boolean(operationId),
            active_operation_id: operationId,
            should_interrupt_active_operation: false,
            affected_fields: affectedFields,
            blocking_clarifications: [],
            summary: "Brief updated; assumptions were recorded so work can continue without restarting.",
          },
        }),
      ),
    });
  });

  route(/\/api\/runs\/start(?:\?.*)?$/, async (route: Route) => {
    const input = toInputRecord(route.request().postDataJSON());
    const operation = state.onStart?.(input, state) ?? {
      id: createOperationId(),
      status: "running",
      startedAt: "2026-04-26T11:15:00.000Z",
      operationBrief: String(
        input.input_json && typeof input.input_json === "object"
          ? ((input.input_json as Record<string, unknown>).operation_brief ?? "Run the next company operation.")
          : "Run the next company operation.",
      ),
      currentNodeId: getDepartmentNodes(state.graphVersion.graph_json)[0]?.id ?? null,
      llmMode: input.llm_mode === "byok" ? "byok" : "managed",
    };

    state.operations = [operation, ...state.operations.filter((existing) => existing.id !== operation.id)];

    await route.fulfill({
      status: 200,
      contentType: "application/json",
      body: JSON.stringify(apiSuccess(buildRunDetail(state, operation))),
    });
  });

  route(/\/api\/runs\/[^/]+\/replay(?:\?.*)?$/, async (route: Route) => {
    const runId = route.request().url().split("/api/runs/")[1]?.split("/replay")[0] ?? "";
    const input = toInputRecord(route.request().postDataJSON());
    const replayResult = state.onReplay?.(runId, input, state);
    const operation = replayResult ??
      state.operations.find((existing) => existing.id === runId) ?? {
        id: runId,
        status: "running",
        startedAt: "2026-04-26T11:18:00.000Z",
        currentNodeId: getDepartmentNodes(state.graphVersion.graph_json)[0]?.id ?? null,
        llmMode: input.llm_mode === "byok" ? "byok" : "managed",
      };

    state.operations = [
      operation,
      ...state.operations.filter((existing) => existing.id !== runId && existing.id !== operation.id),
    ];

    await route.fulfill({
      status: 200,
      contentType: "application/json",
      body: JSON.stringify(apiSuccess(buildRunDetail(state, operation))),
    });
  });

  route(/\/api\/runs\/(?!start(?:\?|$))[^/]+(?:\?.*)?$/, async (route: Route) => {
    const runId = route.request().url().split("/api/runs/")[1]?.split("?")[0] ?? "";
    const operation = state.operations.find((existing) => existing.id === runId);

    if (!operation) {
      await route.fulfill({
        status: 404,
        contentType: "application/json",
        body: JSON.stringify({
          error: {
            code: "NOT_FOUND",
            message: "Operation not found.",
          },
          meta: {
            requestId: "playwright-company-ux-missing",
            timestamp: "2026-04-26T12:00:00.000Z",
          },
        }),
      });
      return;
    }

    await route.fulfill({
      status: 200,
      contentType: "application/json",
      body: JSON.stringify(apiSuccess(buildRunDetail(state, operation))),
    });
  });

  route(/\/api\/runs\/?(?:\?.*)?$/, async (route: Route) => {
    if (route.request().method() !== "GET") {
      await route.continue();
      return;
    }

    const runs = state.operations.map((operation) => buildRunListItem(state, operation));
    await route.fulfill({
      status: 200,
      contentType: "application/json",
      body: JSON.stringify(apiSuccess(runs)),
    });
  });
  await Promise.all(routePromises);
}
