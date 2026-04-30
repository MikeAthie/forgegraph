import { interactionApi, type InteractionEventResponse, type OperatingBrief } from "@/lib/api";

export const interactionRepository = {
  getCurrentBrief: async (companyId: string, operationId?: string | null): Promise<OperatingBrief> =>
    interactionApi.getCurrentBrief(companyId, operationId),

  submitInput: async (input: {
    companyId: string;
    operationId?: string | null;
    briefId?: string | null;
    text: string;
  }): Promise<InteractionEventResponse> =>
    interactionApi.submitEvent({
      company_id: input.companyId,
      operation_id: input.operationId ?? undefined,
      brief_id: input.briefId ?? undefined,
      input: input.text,
    }),
};

export type InteractionRepository = typeof interactionRepository;
