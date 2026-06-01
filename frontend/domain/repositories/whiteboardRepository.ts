import {
  type WorkWhiteboardDTO,
  type WorkWhiteboardBoardCardCreateInput,
  type WorkWhiteboardBoardCardPatchInput,
  type WorkWhiteboardBoardEvidenceInput,
  type WorkWhiteboardBoardSnapshotDTO,
  type WorkWhiteboardDeploymentContractDTO,
  type WorkWhiteboardDeploymentExecuteInput,
  type WorkWhiteboardDeploymentResponse,
  type WorkWhiteboardPerformanceContractDTO,
  type WorkWhiteboardPerformanceEvaluationInput,
  type WorkWhiteboardPerformanceResponse,
  type WorkWhiteboardPerformanceStartInput,
  type WorkWhiteboardPhaseContractDTO,
  type WorkWhiteboardPhaseEvaluationInput,
  type WorkWhiteboardPhaseResponse,
  type WorkWhiteboardProductOperationDTO,
  type WorkWhiteboardPatchInput,
  type WorkWhiteboardPlanningDTO,
  type WorkWhiteboardPlanningResponse,
  type WorkWhiteboardPlanningSynthesisInput,
  type WorkWhiteboardStrategyDTO,
  type WorkWhiteboardStrategyResponse,
  type WorkWhiteboardStrategySynthesisInput,
  whiteboardsApi,
} from "@/lib/api";

export const whiteboardRepository = {
  list: (params: { companyId: string; status?: string }): Promise<WorkWhiteboardDTO[]> =>
    whiteboardsApi.list({ company_id: params.companyId, status: params.status }),

  get: (whiteboardId: string): Promise<WorkWhiteboardDTO> => whiteboardsApi.get(whiteboardId),

  getOperation: (whiteboardId: string, operationId: string): Promise<WorkWhiteboardProductOperationDTO> =>
    whiteboardsApi.getOperation(whiteboardId, operationId),

  patch: (whiteboardId: string, input: WorkWhiteboardPatchInput): Promise<WorkWhiteboardDTO> =>
    whiteboardsApi.patch(whiteboardId, input),

  getBoard: (whiteboardId: string): Promise<WorkWhiteboardBoardSnapshotDTO> => whiteboardsApi.getBoard(whiteboardId),

  createBoardCard: (
    whiteboardId: string,
    input: WorkWhiteboardBoardCardCreateInput,
  ): Promise<WorkWhiteboardBoardSnapshotDTO> => whiteboardsApi.createBoardCard(whiteboardId, input),

  patchBoardCard: (
    whiteboardId: string,
    cardId: string,
    input: WorkWhiteboardBoardCardPatchInput,
  ): Promise<WorkWhiteboardBoardSnapshotDTO> => whiteboardsApi.patchBoardCard(whiteboardId, cardId, input),

  attachBoardCardEvidence: (
    whiteboardId: string,
    cardId: string,
    input: WorkWhiteboardBoardEvidenceInput,
  ): Promise<WorkWhiteboardBoardSnapshotDTO> => whiteboardsApi.attachBoardCardEvidence(whiteboardId, cardId, input),

  readyForPlanning: (whiteboardId: string): Promise<WorkWhiteboardDTO> => whiteboardsApi.readyForPlanning(whiteboardId),

  // Compatibility helper for legacy strategy-named API consumers.
  readyForStrategy: (whiteboardId: string): Promise<WorkWhiteboardDTO> => whiteboardsApi.readyForStrategy(whiteboardId),

  getPhase: (whiteboardId: string, phaseId: string): Promise<WorkWhiteboardPhaseContractDTO> =>
    whiteboardsApi.getPhase(whiteboardId, phaseId),

  startPhase: (whiteboardId: string, phaseId: string): Promise<WorkWhiteboardPhaseResponse> =>
    whiteboardsApi.startPhase(whiteboardId, phaseId),

  synthesizePhase: (whiteboardId: string, phaseId: string): Promise<WorkWhiteboardPhaseResponse> =>
    whiteboardsApi.synthesizePhase(whiteboardId, phaseId),

  evaluatePhase: (
    whiteboardId: string,
    phaseId: string,
    input: WorkWhiteboardPhaseEvaluationInput,
  ): Promise<WorkWhiteboardPhaseResponse> => whiteboardsApi.evaluatePhase(whiteboardId, phaseId, input),

  getDeployment: (whiteboardId: string): Promise<WorkWhiteboardDeploymentContractDTO> =>
    whiteboardsApi.getDeployment(whiteboardId),

  prepareDeployment: (whiteboardId: string): Promise<WorkWhiteboardDeploymentResponse> =>
    whiteboardsApi.prepareDeployment(whiteboardId),

  executeDeploymentChannel: (
    whiteboardId: string,
    channelId: string,
    input: WorkWhiteboardDeploymentExecuteInput,
  ): Promise<WorkWhiteboardDeploymentResponse> =>
    whiteboardsApi.executeDeploymentChannel(whiteboardId, channelId, input),

  getPerformance: (whiteboardId: string): Promise<WorkWhiteboardPerformanceContractDTO> =>
    whiteboardsApi.getPerformance(whiteboardId),

  startPerformance: (
    whiteboardId: string,
    input?: WorkWhiteboardPerformanceStartInput,
  ): Promise<WorkWhiteboardPerformanceResponse> => whiteboardsApi.startPerformance(whiteboardId, input ?? {}),

  reportPerformance: (whiteboardId: string, policyId = ""): Promise<WorkWhiteboardPerformanceResponse> =>
    whiteboardsApi.reportPerformance(whiteboardId, policyId),

  evaluatePerformance: (
    whiteboardId: string,
    input?: WorkWhiteboardPerformanceEvaluationInput,
  ): Promise<WorkWhiteboardPerformanceResponse> => whiteboardsApi.evaluatePerformance(whiteboardId, input ?? {}),

  startPlanning: (whiteboardId: string): Promise<WorkWhiteboardPlanningResponse> =>
    whiteboardsApi.startPlanning(whiteboardId),

  getPlanning: (whiteboardId: string): Promise<WorkWhiteboardPlanningDTO> => whiteboardsApi.getPlanning(whiteboardId),

  synthesizePlanning: (
    whiteboardId: string,
    input: WorkWhiteboardPlanningSynthesisInput,
  ): Promise<WorkWhiteboardPlanningResponse> => whiteboardsApi.synthesizePlanning(whiteboardId, input),

  // Compatibility helpers for legacy strategy-named API consumers.
  startStrategy: (whiteboardId: string): Promise<WorkWhiteboardStrategyResponse> =>
    whiteboardsApi.startStrategy(whiteboardId),

  getStrategy: (whiteboardId: string): Promise<WorkWhiteboardStrategyDTO> => whiteboardsApi.getStrategy(whiteboardId),

  synthesizeStrategy: (
    whiteboardId: string,
    input: WorkWhiteboardStrategySynthesisInput,
  ): Promise<WorkWhiteboardStrategyResponse> => whiteboardsApi.synthesizeStrategy(whiteboardId, input),
};

export type WhiteboardRepository = typeof whiteboardRepository;
