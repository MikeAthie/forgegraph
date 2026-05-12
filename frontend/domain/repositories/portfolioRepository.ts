import {
  portfolioApi,
  type CompanyAssignmentDTO,
  type CompanyAssignmentInput,
  type CompanyAssignmentPatchInput,
  type CredentialHealth,
  type CrossCompanyQueueType,
  type CrossCompanyQueues,
  type PortfolioHealth,
} from "@/lib/api";

export type PortfolioHomeVM = {
  health: PortfolioHealth;
  queues: CrossCompanyQueues;
};

export const portfolioRepository = {
  getHome: async (): Promise<PortfolioHomeVM> => {
    const [health, queues] = await Promise.all([portfolioApi.getHealth(), portfolioApi.getCrossCompanyQueues("all")]);
    return { health, queues };
  },

  getQueues: (type: CrossCompanyQueueType = "all"): Promise<CrossCompanyQueues> =>
    portfolioApi.getCrossCompanyQueues(type),

  getCredentialHealth: (): Promise<CredentialHealth> => portfolioApi.getCredentialHealth(),

  listCompanyAssignments: (companyId?: string): Promise<CompanyAssignmentDTO[]> =>
    portfolioApi.listCompanyAssignments(companyId),

  createCompanyAssignment: (input: CompanyAssignmentInput): Promise<CompanyAssignmentDTO> =>
    portfolioApi.createCompanyAssignment(input),

  patchCompanyAssignment: (assignmentId: string, input: CompanyAssignmentPatchInput): Promise<CompanyAssignmentDTO> =>
    portfolioApi.patchCompanyAssignment(assignmentId, input),
};
