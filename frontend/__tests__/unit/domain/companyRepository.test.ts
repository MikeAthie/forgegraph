import { companyRepository } from "@/domain/repositories/companyRepository";
import { buildCompanyProfile } from "@/lib/company-workspace";
import { companiesApi, companyBlueprintsApi, companyOpsApi, graphsApi } from "@/lib/api";

jest.mock("@/lib/api", () => ({
  approvalsApi: {
    list: jest.fn().mockResolvedValue([]),
  },
  companyBlueprintsApi: {
    createCompany: jest.fn(),
  },
  companyOpsApi: {
    getAgencyHealth: jest.fn(),
  },
  companiesApi: {
    create: jest.fn(),
    createOperatingModelVersion: jest.fn(),
    get: jest.fn(),
    getLatestOperatingModelVersion: jest.fn(),
    list: jest.fn(),
    update: jest.fn(),
  },
  credentialsApi: {
    create: jest.fn(),
  },
  executionsApi: {},
  graphsApi: {
    create: jest.fn(),
    createVersion: jest.fn(),
    get: jest.fn(),
    getLatestVersion: jest.fn(),
    list: jest.fn(),
    update: jest.fn(),
  },
  runsApi: {
    get: jest.fn(),
    list: jest.fn(),
    start: jest.fn(),
  },
  tasksApi: {
    list: jest.fn(),
  },
}));

describe("companyRepository.create", () => {
  beforeEach(() => {
    jest.clearAllMocks();
  });

  it("creates pack-backed companies through the company blueprint control-plane endpoint", async () => {
    jest.mocked(companyBlueprintsApi.createCompany).mockResolvedValue({
      company_id: "company-1",
      graph_version_id: "version-1",
      graph_json: { nodes: [], edges: [], metadata: {} },
      template_ids: ["operating_model_pack:digital_marketing_pro.v1"],
      department_groups: [],
      first_operation_id: null,
      idempotent_replay: false,
    });

    const profile = buildCompanyProfile({
      companyName: "ATLAS MARKETING",
      companyType: "Growth & Marketing",
      objective: "Run a pack-backed company.",
      skills: ["Campaign planning"],
    });

    const result = await companyRepository.create({
      profile,
      operationBrief: "Prepare the first engagement.",
      launchFirstOperation: false,
      operatingModelPackId: "digital_marketing_pro.v1",
    });

    expect(result).toEqual({ companyId: "company-1", firstOperation: null });
    expect(companyBlueprintsApi.createCompany).toHaveBeenCalledWith(
      expect.objectContaining({
        company_name: "ATLAS MARKETING",
        blueprint_id: "digital_marketing_pro.v1",
        services: ["Campaign planning"],
        launch_first_operation: false,
      }),
      expect.objectContaining({
        idempotencyKey: expect.stringContaining("company-from-blueprint:"),
      }),
    );
    expect(graphsApi.create).not.toHaveBeenCalled();
  });

  it("creates generic companies through the company alias API when no operating model pack is selected", async () => {
    jest.mocked(companiesApi.create).mockResolvedValue({
      id: "company-2",
      company_id: "company-2",
      workflow_definition_id: "company-2",
      storage_model: "Graph",
      name: "Generic Company",
      description: "Operate generically.",
      created_at: "2026-05-12T00:00:00Z",
      updated_at: "2026-05-12T00:00:00Z",
      setup_version_count: 0,
      latest_setup_version: null,
    });
    jest.mocked(companiesApi.createOperatingModelVersion).mockResolvedValue({
      id: "version-2",
      company_id: "company-2",
      workflow_definition_id: "company-2",
      version: 1,
      model_json: { nodes: [], edges: [], metadata: {} },
      checksum: "checksum",
      created_at: "2026-05-12T00:00:00Z",
    });

    const profile = buildCompanyProfile({
      companyName: "Generic Company",
      objective: "Operate generically.",
    });

    const result = await companyRepository.create({
      profile,
      operationBrief: "Start.",
      launchFirstOperation: false,
    });

    expect(result).toEqual({ companyId: "company-2", firstOperation: null });
    expect(companiesApi.create).toHaveBeenCalledWith({
      name: "Generic Company",
      description: "Operate generically.",
    });
    expect(companiesApi.createOperatingModelVersion).toHaveBeenCalledWith("company-2", {
      model_json: expect.objectContaining({
        nodes: expect.any(Array),
        edges: expect.any(Array),
      }),
    });
    expect(companyBlueprintsApi.createCompany).not.toHaveBeenCalled();
    expect(graphsApi.create).not.toHaveBeenCalled();
    expect(graphsApi.createVersion).not.toHaveBeenCalled();
  });
});

describe("companyRepository.getAgencyHealth", () => {
  beforeEach(() => {
    jest.clearAllMocks();
  });

  it("loads backend-owned agency health and returns a sanitized view model", async () => {
    jest.mocked(companyOpsApi.getAgencyHealth).mockResolvedValue({
      company_id: "company-1",
      generated_at: "2026-06-04T12:00:00Z",
      profile: {
        company_id: "company-1",
        name: "Atlas Agency",
        description: "Run managed services.",
        client_stage: "in_progress",
        active_service_engagement: null,
        commercial: {
          metadata: { api_key: "sk-secret" },
        },
      },
      health: {
        score: 72,
        status: "monitor",
        dimensions: [
          {
            slug: "connector_readiness",
            label: "Connector readiness",
            score: 45,
            status: "attention",
            weight: 20,
            owner_department_slug: "channel_execution",
            summary: "Required connector gaps are lowering account health.",
            internal_trace_id: "trace-1",
          },
        ],
      },
      onboarding_items: [
        {
          slug: "connector_setup",
          label: "Connector setup",
          status: "blocked",
          owner_department_slug: "channel_execution",
          message: "Required connectors are missing.",
          secret_token: "sk-secret",
        },
      ],
      connector_readiness: {
        status: "blocked",
        summary: {
          total: 1,
          required: 1,
          ready: 0,
          missing: 1,
          degraded: 0,
          disabled: 0,
        },
        connectors: [
          {
            slug: "whatsapp",
            label: "WhatsApp",
            category: "messaging",
            required: true,
            status: "missing",
            readiness: "action_required",
            owner_department_slug: "channel_execution",
            source: "gateway_connection",
            last_seen_at: null,
            last_health_check_at: null,
            message: "WhatsApp is not connected.",
            oauth_client_secret: "sk-secret",
          },
        ],
      },
      recurring_reporting: { metadata: { api_key: "sk-secret" } },
      growth_signals: { metadata: { api_key: "sk-secret" } },
      risks: [
        {
          slug: "missing_required_connectors",
          label: "Required connectors missing",
          severity: "high",
          owner_department_slug: "channel_execution",
          summary: "1 required connector(s) are not ready.",
          metadata: { api_key: "sk-secret" },
        },
      ],
      opportunities: [],
      next_actions: [
        {
          slug: "configure_whatsapp",
          label: "Configure WhatsApp",
          priority: "high",
          owner_department_slug: "channel_execution",
          reason: "WhatsApp is not connected.",
        },
      ],
    } as never);

    const result = await companyRepository.getAgencyHealth("company-1");

    expect(companyOpsApi.getAgencyHealth).toHaveBeenCalledWith("company-1");
    expect(result.companyId).toBe("company-1");
    expect(result.health.dimensions[0]).toEqual({
      slug: "connector_readiness",
      label: "Connector readiness",
      score: 45,
      status: "attention",
      weight: 20,
      ownerDepartmentSlug: "channel_execution",
      summary: "Required connector gaps are lowering account health.",
    });
    expect(result.connectorReadiness.connectors[0]).toEqual({
      slug: "whatsapp",
      label: "WhatsApp",
      category: "messaging",
      required: true,
      status: "missing",
      readiness: "action_required",
      ownerDepartmentSlug: "channel_execution",
      source: "gateway_connection",
      lastSeenAt: null,
      lastHealthCheckAt: null,
      message: "WhatsApp is not connected.",
    });
    expect(JSON.stringify(result)).not.toContain("sk-secret");
    expect(result).not.toHaveProperty("growthSignals");
    expect(result).not.toHaveProperty("recurringReporting");
  });
});
