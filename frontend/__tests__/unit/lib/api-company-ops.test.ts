const apiGet = jest.fn();
const authPost = jest.fn();

jest.mock("axios", () => {
  const create = jest.fn(() => ({
    get: apiGet,
    post: authPost,
    interceptors: {
      request: { use: jest.fn() },
      response: { use: jest.fn() },
    },
  }));

  return {
    __esModule: true,
    default: { create },
  };
});

describe("companyOpsApi", () => {
  beforeEach(() => {
    jest.clearAllMocks();
  });

  it("loads agency health through the company-ops agency-health endpoint", async () => {
    const { companyOpsApi } = await import("@/lib/api");
    const agencyHealth = {
      company_id: "company-1",
      generated_at: "2026-06-04T12:00:00Z",
      health: { score: 80, status: "healthy", dimensions: [] },
      onboarding_items: [],
      connector_readiness: { status: "ready", summary: {}, connectors: [] },
    };
    apiGet.mockResolvedValueOnce({
      data: {
        data: {
          agency_health: agencyHealth,
        },
      },
    });

    await expect(companyOpsApi.getAgencyHealth("company-1")).resolves.toBe(agencyHealth);

    expect(apiGet).toHaveBeenCalledWith("/api/company-ops/agency-health", {
      params: { company_id: "company-1" },
    });
  });
});
