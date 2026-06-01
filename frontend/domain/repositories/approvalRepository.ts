import { approvalsApi, type ApprovalResolveResponse, type ResumeRunResponse } from "@/lib/api";
import { toApprovalVM, type ApprovalVM } from "@/domain/translation";
import { operationRepository } from "./operationRepository";
import { stableClientCommandId } from "@/lib/idempotency";

export const approvalRepository = {
  list: async (status?: string): Promise<ApprovalVM[]> => {
    const approvals = await approvalsApi.list(status);
    return approvals.map(toApprovalVM);
  },

  get: async (approvalId: string): Promise<ApprovalVM> => {
    const approval = await approvalsApi.get(approvalId);
    return toApprovalVM(approval);
  },

  decide: async (
    approval: ApprovalVM,
    approved: boolean,
    feedback?: string,
  ): Promise<ResumeRunResponse | ApprovalResolveResponse> => {
    if (approval.resolutionMode === "direct") {
      return approvalsApi.resolve(
        approval.id,
        { approved, notes: feedback },
        {
          idempotencyKey: stableClientCommandId("approval.resolve", approval.id, approved ? "approved" : "rejected"),
        },
      );
    }
    return operationRepository.resumeAfterApproval(approval.operationId, approval.departmentId, approved, feedback);
  },
};

type ApprovalRepository = typeof approvalRepository;
