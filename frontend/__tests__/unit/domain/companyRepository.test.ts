import { companyRepository } from "@/domain/repositories/companyRepository";
import { buildCompanyProfile } from "@/lib/company-workspace";
import { companyBlueprintsApi, graphsApi } from "@/lib/api";

jest.mock("@/lib/api", () => ({
  approvalsApi: {
    list: jest.fn().mockResolvedValue([]),
  },
  companyBlueprintsApi: {
    createCompany: jest.fn(),
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

  it("keeps the generic graph creation path when no operating model pack is selected", async () => {
    jest.mocked(graphsApi.create).mockResolvedValue({
      id: "company-2",
      name: "Generic Company",
      description: "Operate generically.",
      created_at: "2026-05-12T00:00:00Z",
      updated_at: "2026-05-12T00:00:00Z",
      version_count: 0,
      latest_version: null,
    });
    jest.mocked(graphsApi.createVersion).mockResolvedValue({
      id: "version-2",
      version: 1,
      graph_json: { nodes: [], edges: [], metadata: {} },
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
    expect(graphsApi.create).toHaveBeenCalledWith({
      name: "Generic Company",
      description: "Operate generically.",
    });
    expect(companyBlueprintsApi.createCompany).not.toHaveBeenCalled();
  });
});
