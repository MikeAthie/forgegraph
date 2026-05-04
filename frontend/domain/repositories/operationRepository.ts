import { executionsApi, runsApi, tasksApi, type LLMMode, type ResumeRunResponse } from "@/lib/api";
import { buildCompanyProfile, buildOperationInput, type CompanyProfile } from "@/lib/company-workspace";
import {
  toOperationListVM,
  toOperationVM,
  toTaskVMFromRecord,
  type OperationLaunchInputVM,
  type OperationVM,
  type TaskVM,
} from "@/domain/translation";

const newClientActionId = (prefix: string): string => {
  const randomId =
    typeof crypto !== "undefined" && "randomUUID" in crypto
      ? crypto.randomUUID()
      : `${Date.now()}-${Math.random().toString(36).slice(2)}`;
  return `${prefix}:${randomId}`;
};

export const operationRepository = {
  list: async (): Promise<OperationVM[]> => {
    const operations = await runsApi.list();
    return operations
      .sort((left, right) => (right.started_at ?? "").localeCompare(left.started_at ?? ""))
      .map(toOperationListVM);
  },

  get: async (operationId: string): Promise<OperationVM> => {
    const operation = await runsApi.get(operationId);
    return toOperationVM(operation);
  },

  getBackendState: async (operationId: string): Promise<{ status: string; recoveryState?: string | null }> => {
    const operation = await runsApi.get(operationId);
    return {
      status: String(operation.status),
      recoveryState: operation.recovery_state ?? null,
    };
  },

  getLegacyExecution: async (operationId: string): Promise<OperationVM> => {
    const operation = await executionsApi.get(operationId);
    return toOperationVM(operation);
  },

  listTasks: async (): Promise<TaskVM[]> => {
    const tasks = await tasksApi.list();
    return tasks
      .sort((left, right) => (right.updated_at ?? "").localeCompare(left.updated_at ?? ""))
      .map(toTaskVMFromRecord);
  },

  launch: async (input: OperationLaunchInputVM): Promise<OperationVM> => {
    const profile = buildCompanyProfile({
      ...input.profile,
      objective: input.objective,
      autonomyMode: input.autonomyMode,
      aiAccessMode: input.aiAccessMode,
    });
    const operation = await runsApi.start(
      {
        graph_version_id: input.setupVersionId,
        llm_mode: input.aiAccessMode,
        provider: profile.intelligenceProvider,
        credential_id: profile.byokCredentialId ?? undefined,
        input_json: buildOperationInput(profile, input.operationBrief, input.operatingBrief),
      },
      {
        idempotencyKey: newClientActionId("operation.launch"),
      },
    );
    return toOperationVM(operation);
  },

  stop: async (operationId: string): Promise<OperationVM> => {
    const operation = await runsApi.cancel(operationId, {
      idempotencyKey: `operation.cancel:${operationId}`,
    });
    return toOperationVM(operation);
  },

  retry: async (
    operationId: string,
    input?: { aiAccessMode?: LLMMode; provider?: string; credentialId?: string | null },
  ): Promise<OperationVM> => {
    const operation = await runsApi.replay(
      operationId,
      {
        llm_mode: input?.aiAccessMode,
        provider: input?.provider,
        credential_id: input?.credentialId ?? undefined,
      },
      {
        idempotencyKey: newClientActionId(`operation.replay:${operationId}`),
      },
    );
    return toOperationVM(operation);
  },

  resumeAfterApproval: async (
    operationId: string,
    departmentId: string,
    approved: boolean,
    feedback?: string,
  ): Promise<ResumeRunResponse> =>
    runsApi.resume(
      operationId,
      {
        node_id: departmentId,
        input_json: {
          approved,
          feedback: feedback || undefined,
        },
      },
      {
        idempotencyKey: `operation.resume:${operationId}:${departmentId}:${approved ? "approved" : "rejected"}`,
      },
    ),
};

export type OperationRepository = typeof operationRepository;

export function getOperationAiAccess(profile: CompanyProfile) {
  return {
    aiAccessMode: profile.aiAccessMode,
    provider: profile.intelligenceProvider,
    credentialId: profile.byokCredentialId,
  };
}
