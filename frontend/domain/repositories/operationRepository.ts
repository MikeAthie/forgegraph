import { executionsApi, runsApi, tasksApi, type LLMMode } from "@/lib/api";
import { buildCompanyProfile, buildOperationInput, type CompanyProfile } from "@/lib/company-workspace";
import {
  toOperationListVM,
  toOperationVM,
  toTaskVMFromRecord,
  type OperationLaunchInputVM,
  type OperationVM,
  type TaskVM,
} from "@/domain/translation";

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
    const operation = await runsApi.start({
      graph_version_id: input.setupVersionId,
      llm_mode: input.aiAccessMode,
      provider: profile.intelligenceProvider,
      credential_id: profile.byokCredentialId ?? undefined,
      input_json: buildOperationInput(profile, input.operationBrief, input.operatingBrief),
    });
    return toOperationVM(operation);
  },

  stop: async (operationId: string): Promise<OperationVM> => {
    const operation = await runsApi.cancel(operationId);
    return toOperationVM(operation);
  },

  retry: async (
    operationId: string,
    input?: { aiAccessMode?: LLMMode; provider?: string; credentialId?: string | null },
  ): Promise<OperationVM> => {
    const operation = await runsApi.replay(operationId, {
      llm_mode: input?.aiAccessMode,
      provider: input?.provider,
      credential_id: input?.credentialId ?? undefined,
    });
    return toOperationVM(operation);
  },

  resumeAfterApproval: async (
    operationId: string,
    departmentId: string,
    approved: boolean,
    feedback?: string,
  ): Promise<{ resumed: boolean }> =>
    runsApi.resume(operationId, {
      node_id: departmentId,
      input_json: {
        approved,
        feedback: feedback || undefined,
      },
    }),
};

export type OperationRepository = typeof operationRepository;

export function getOperationAiAccess(profile: CompanyProfile) {
  return {
    aiAccessMode: profile.aiAccessMode,
    provider: profile.intelligenceProvider,
    credentialId: profile.byokCredentialId,
  };
}
