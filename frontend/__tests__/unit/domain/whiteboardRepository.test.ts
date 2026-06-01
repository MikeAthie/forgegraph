import { whiteboardRepository } from "@/domain/repositories/whiteboardRepository";
import { routingApi, tasksApi, whiteboardsApi } from "@/lib/api";

jest.mock("@/lib/api", () => ({
  routingApi: {
    listInbox: jest.fn(),
  },
  tasksApi: {
    list: jest.fn(),
  },
  whiteboardsApi: {
    attachBoardCardEvidence: jest.fn(),
    createBoardCard: jest.fn(),
    evaluatePerformance: jest.fn(),
    evaluatePhase: jest.fn(),
    executeDeploymentChannel: jest.fn(),
    get: jest.fn(),
    getBoard: jest.fn(),
    getDeployment: jest.fn(),
    getPerformance: jest.fn(),
    getPhase: jest.fn(),
    getPlanning: jest.fn(),
    getStrategy: jest.fn(),
    list: jest.fn(),
    patch: jest.fn(),
    patchBoardCard: jest.fn(),
    prepareDeployment: jest.fn(),
    readyForPlanning: jest.fn(),
    readyForStrategy: jest.fn(),
    reportPerformance: jest.fn(),
    startPerformance: jest.fn(),
    startPhase: jest.fn(),
    startPlanning: jest.fn(),
    startStrategy: jest.fn(),
    synthesizePlanning: jest.fn(),
    synthesizePhase: jest.fn(),
    synthesizeStrategy: jest.fn(),
  },
}));

describe("whiteboardRepository", () => {
  beforeEach(() => {
    jest.clearAllMocks();
    const whiteboard = { id: "whiteboard-1", company_id: "company-1" };
    const board = { whiteboard_id: "whiteboard-1", cards: [] };
    jest.mocked(whiteboardsApi.list).mockResolvedValue([whiteboard as never]);
    jest.mocked(whiteboardsApi.get).mockResolvedValue(whiteboard as never);
    jest.mocked(whiteboardsApi.patch).mockResolvedValue(whiteboard as never);
    jest.mocked(whiteboardsApi.getBoard).mockResolvedValue(board as never);
    jest.mocked(whiteboardsApi.createBoardCard).mockResolvedValue(board as never);
    jest.mocked(whiteboardsApi.patchBoardCard).mockResolvedValue(board as never);
    jest.mocked(whiteboardsApi.attachBoardCardEvidence).mockResolvedValue(board as never);
    jest.mocked(whiteboardsApi.readyForPlanning).mockResolvedValue(whiteboard as never);
    jest.mocked(whiteboardsApi.readyForStrategy).mockResolvedValue(whiteboard as never);
    jest.mocked(whiteboardsApi.getPhase).mockResolvedValue({ phase_id: "phase-1" } as never);
    jest.mocked(whiteboardsApi.startPhase).mockResolvedValue({ whiteboard } as never);
    jest.mocked(whiteboardsApi.synthesizePhase).mockResolvedValue({ whiteboard } as never);
    jest.mocked(whiteboardsApi.evaluatePhase).mockResolvedValue({ whiteboard } as never);
    jest.mocked(whiteboardsApi.getDeployment).mockResolvedValue({ whiteboard_id: "whiteboard-1" } as never);
    jest.mocked(whiteboardsApi.prepareDeployment).mockResolvedValue({ whiteboard } as never);
    jest.mocked(whiteboardsApi.executeDeploymentChannel).mockResolvedValue({ whiteboard } as never);
    jest.mocked(whiteboardsApi.getPerformance).mockResolvedValue({ whiteboard_id: "whiteboard-1" } as never);
    jest.mocked(whiteboardsApi.startPerformance).mockResolvedValue({ whiteboard } as never);
    jest.mocked(whiteboardsApi.reportPerformance).mockResolvedValue({ whiteboard } as never);
    jest.mocked(whiteboardsApi.evaluatePerformance).mockResolvedValue({ whiteboard } as never);
    jest.mocked(whiteboardsApi.startPlanning).mockResolvedValue({ whiteboard } as never);
    jest.mocked(whiteboardsApi.getPlanning).mockResolvedValue({ whiteboard_id: "whiteboard-1" } as never);
    jest.mocked(whiteboardsApi.synthesizePlanning).mockResolvedValue({ whiteboard } as never);
    jest.mocked(whiteboardsApi.startStrategy).mockResolvedValue({ whiteboard } as never);
    jest.mocked(whiteboardsApi.getStrategy).mockResolvedValue({ whiteboard_id: "whiteboard-1" } as never);
    jest.mocked(whiteboardsApi.synthesizeStrategy).mockResolvedValue({ whiteboard } as never);
  });

  it("uses whiteboardsApi for primary workboard flows", async () => {
    await whiteboardRepository.list({ companyId: "company-1", status: "onboarding" });
    await whiteboardRepository.get("whiteboard-1");
    await whiteboardRepository.patch("whiteboard-1", { objective: "Ship safely" });
    await whiteboardRepository.getBoard("whiteboard-1");
    await whiteboardRepository.createBoardCard("whiteboard-1", {
      department_id: "department-1",
      title: "Prepare handoff",
    });
    await whiteboardRepository.patchBoardCard("whiteboard-1", "card-1", {
      status: "in_progress",
    });
    await whiteboardRepository.attachBoardCardEvidence("whiteboard-1", "card-1", {
      summary: "Safe evidence reference",
    });
    await whiteboardRepository.readyForPlanning("whiteboard-1");
    await whiteboardRepository.getPhase("whiteboard-1", "phase-1");
    await whiteboardRepository.startPhase("whiteboard-1", "phase-1");
    await whiteboardRepository.synthesizePhase("whiteboard-1", "phase-1");
    await whiteboardRepository.evaluatePhase("whiteboard-1", "phase-1", { scores: {} });
    await whiteboardRepository.getDeployment("whiteboard-1");
    await whiteboardRepository.prepareDeployment("whiteboard-1");
    await whiteboardRepository.executeDeploymentChannel("whiteboard-1", "channel-1", {
      dry_run: true,
    });
    await whiteboardRepository.getPerformance("whiteboard-1");
    await whiteboardRepository.startPerformance("whiteboard-1");
    await whiteboardRepository.reportPerformance("whiteboard-1", "policy-1");
    await whiteboardRepository.evaluatePerformance("whiteboard-1", { scores: {} });
    await whiteboardRepository.startPlanning("whiteboard-1");
    await whiteboardRepository.getPlanning("whiteboard-1");
    await whiteboardRepository.synthesizePlanning("whiteboard-1", { scores: {} });
    await whiteboardRepository.startStrategy("whiteboard-1");
    await whiteboardRepository.getStrategy("whiteboard-1");
    await whiteboardRepository.synthesizeStrategy("whiteboard-1", { scores: {} });

    expect(whiteboardsApi.list).toHaveBeenCalledWith({
      company_id: "company-1",
      status: "onboarding",
    });
    expect(whiteboardsApi.getBoard).toHaveBeenCalledWith("whiteboard-1");
    expect(whiteboardsApi.createBoardCard).toHaveBeenCalledWith("whiteboard-1", {
      department_id: "department-1",
      title: "Prepare handoff",
    });
    expect(whiteboardsApi.patchBoardCard).toHaveBeenCalledWith("whiteboard-1", "card-1", {
      status: "in_progress",
    });
    expect(whiteboardsApi.attachBoardCardEvidence).toHaveBeenCalledWith("whiteboard-1", "card-1", {
      summary: "Safe evidence reference",
    });
    expect(whiteboardsApi.evaluatePhase).toHaveBeenCalledWith("whiteboard-1", "phase-1", {
      scores: {},
    });
    expect(whiteboardsApi.executeDeploymentChannel).toHaveBeenCalledWith(
      "whiteboard-1",
      "channel-1",
      { dry_run: true },
    );
    expect(whiteboardsApi.evaluatePerformance).toHaveBeenCalledWith("whiteboard-1", {
      scores: {},
    });
    expect(whiteboardsApi.readyForPlanning).toHaveBeenCalledWith("whiteboard-1");
    expect(whiteboardsApi.startPlanning).toHaveBeenCalledWith("whiteboard-1");
    expect(whiteboardsApi.getPlanning).toHaveBeenCalledWith("whiteboard-1");
    expect(whiteboardsApi.synthesizePlanning).toHaveBeenCalledWith("whiteboard-1", {
      scores: {},
    });
    expect(whiteboardsApi.synthesizeStrategy).toHaveBeenCalledWith("whiteboard-1", {
      scores: {},
    });
    expect(routingApi.listInbox).not.toHaveBeenCalled();
    expect(tasksApi.list).not.toHaveBeenCalled();
  });
});
