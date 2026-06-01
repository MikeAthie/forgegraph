import { approvalsApi, companiesApi, companyBlueprintsApi, credentialsApi, runsApi } from "@/lib/api";
import {
  buildCompanyGraphJson,
  buildCompanyProfile,
  buildOperationInput,
  type CompanyProfile,
} from "@/lib/company-workspace";
import {
  toCompanyVM,
  toOperationListVM,
  toOperationVM,
  type CompanyCreateInputVM,
  type CompanyUpdateInputVM,
  type CompanyVM,
  type CompanyWorkspaceVM,
  type OperationVM,
} from "@/domain/translation";
import { operationRepository } from "./operationRepository";

function sortOperations<T extends { startedAt: string | null }>(operations: T[]): T[] {
  return operations.toSorted((left, right) => (right.startedAt ?? "").localeCompare(left.startedAt ?? ""));
}

export const companyRepository = {
  list: async (): Promise<CompanyVM[]> => {
    const [companies, operations, approvals] = await Promise.all([
      companiesApi.list(),
      runsApi.list(),
      approvalsApi.list("pending"),
    ]);
    const setupVersions = await Promise.all(
      companies.map((company) => companiesApi.getLatestOperatingModelVersion(company.id)),
    );

    return companies.map((company, index) => {
      const companyOperations = operations
        .flatMap((operation) => (operation.graph_id === company.id ? [operation] : []))
        .toSorted((left, right) => (right.started_at ?? "").localeCompare(left.started_at ?? ""))
        .map(toOperationListVM);
      const operationIds = new Set(companyOperations.map((operation) => operation.id));
      const pendingApprovalCount = approvals.filter((approval) => operationIds.has(approval.run_id)).length;
      return toCompanyVM(company, setupVersions[index] ?? null, companyOperations, pendingApprovalCount);
    });
  },

  getWorkspace: async (companyId: string): Promise<CompanyWorkspaceVM> => {
    const [company, setupVersion, operations, approvals] = await Promise.all([
      companiesApi.get(companyId),
      companiesApi.getLatestOperatingModelVersion(companyId),
      runsApi.list(),
      approvalsApi.list("pending"),
    ]);

    const companyOperationList = operations
      .filter((operation) => operation.graph_id === companyId)
      .sort((left, right) => (right.started_at ?? "").localeCompare(left.started_at ?? ""));
    const operationIds = new Set(companyOperationList.map((operation) => operation.id));
    const detailedOperationIds: string[] = [];
    companyOperationList.forEach((operation, index) => {
      if (
        index < 4 ||
        String(operation.status).toLowerCase() === "running" ||
        String(operation.status).toLowerCase() === "failed"
      ) {
        detailedOperationIds.push(operation.id);
      }
    });
    const detailedOperations = await Promise.all(detailedOperationIds.map((operationId) => runsApi.get(operationId)));
    const detailById = new Map(
      detailedOperations.map((operation) => [operation.id, toOperationVM(operation, setupVersion?.model_json ?? null)]),
    );
    const translatedOperations = sortOperations(
      companyOperationList.slice(0, 6).map((operation) => detailById.get(operation.id) ?? toOperationListVM(operation)),
    );
    const pendingApprovalCount = approvals.filter((approval) => operationIds.has(approval.run_id)).length;

    return {
      company: toCompanyVM(company, setupVersion, translatedOperations, pendingApprovalCount),
      operations: translatedOperations,
      pendingApprovalCount,
    };
  },

  create: async (input: CompanyCreateInputVM): Promise<{ companyId: string; firstOperation: OperationVM | null }> => {
    let credentialId: string | null = null;
    if (input.profile.aiAccessMode === "byok" && input.byokApiKey?.trim()) {
      const credential = await credentialsApi.create({
        provider: "openai",
        name: `${input.profile.companyName.trim()} BYOK`,
        api_key: input.byokApiKey.trim(),
      });
      credentialId = credential.id;
    }

    const profile = buildCompanyProfile({
      ...input.profile,
      byokCredentialId: credentialId,
    });
    if (input.operatingModelPackId) {
      const created = await companyBlueprintsApi.createCompany(
        {
          company_name: profile.companyName,
          objective: profile.objective,
          blueprint_id: input.operatingModelPackId,
          services: profile.skills,
          regions: [],
          autonomy_mode: profile.autonomyMode,
          ai_access_mode: profile.aiAccessMode,
          intelligence_provider: profile.intelligenceProvider,
          launch_first_operation: input.launchFirstOperation,
          operation_brief: input.operationBrief,
          credential_id: credentialId,
        },
        { idempotencyKey: makeClientIdempotencyKey("company-from-blueprint") },
      );
      if (!created.first_operation_id) {
        return { companyId: created.company_id, firstOperation: null };
      }
      const operation = await runsApi.get(created.first_operation_id);
      return {
        companyId: created.company_id,
        firstOperation: toOperationVM(operation, created.graph_json),
      };
    }

    const company = await companiesApi.create({
      name: profile.companyName,
      description: profile.objective,
    });
    const setup = await companiesApi.createOperatingModelVersion(company.id, {
      model_json: buildCompanyGraphJson(profile),
    });
    if (!setup.id) {
      throw new Error("Graph version creation did not return an id.");
    }

    if (!input.launchFirstOperation) {
      return { companyId: company.id, firstOperation: null };
    }

    const operation = await runsApi.start({
      graph_version_id: setup.id,
      llm_mode: profile.aiAccessMode,
      provider: profile.intelligenceProvider,
      credential_id: credentialId ?? undefined,
      input_json: buildOperationInput(profile, input.operationBrief),
    });

    return { companyId: company.id, firstOperation: toOperationVM(operation, setup.model_json) };
  },

  saveSettings: async (input: CompanyUpdateInputVM): Promise<void> => {
    const nextProfile: CompanyProfile = buildCompanyProfile({
      ...input.currentProfile,
      objective: input.objective,
      autonomyMode: input.autonomyMode,
      aiAccessMode: input.aiAccessMode,
      companyStatus: input.paused ? "Paused by operator" : "Ready to launch",
    });

    await companiesApi.update(input.companyId, {
      name: nextProfile.companyName,
      description: nextProfile.objective,
    });
    await companiesApi.createOperatingModelVersion(input.companyId, {
      model_json: buildCompanyGraphJson(nextProfile),
    });
  },

  setPaused: async (input: CompanyUpdateInputVM): Promise<void> => {
    await companyRepository.saveSettings(input);
  },

  launchOperation: operationRepository.launch,
  retryOperation: operationRepository.retry,
};

function makeClientIdempotencyKey(prefix: string): string {
  const randomId =
    typeof globalThis.crypto?.randomUUID === "function"
      ? globalThis.crypto.randomUUID()
      : `${Date.now()}-${Math.random().toString(36).slice(2)}`;
  return `${prefix}:${randomId}`;
}

type CompanyRepository = typeof companyRepository;
