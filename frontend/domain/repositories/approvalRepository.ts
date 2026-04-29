import { approvalsApi } from "@/lib/api";
import { toApprovalVM, type ApprovalVM } from "@/domain/translation";
import { operationRepository } from "./operationRepository";

export const approvalRepository = {
  list: async (status?: string): Promise<ApprovalVM[]> => {
    const approvals = await approvalsApi.list(status);
    return approvals.map(toApprovalVM);
  },

  get: async (approvalId: string): Promise<ApprovalVM> => {
    const approval = await approvalsApi.get(approvalId);
    return toApprovalVM(approval);
  },

  decide: async (approval: ApprovalVM, approved: boolean, feedback?: string): Promise<{ resumed: boolean }> =>
    operationRepository.resumeAfterApproval(approval.operationId, approval.departmentId, approved, feedback),
};

export type ApprovalRepository = typeof approvalRepository;
