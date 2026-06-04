import {
  serviceEngagementsApi,
  type ServiceCatalogInput,
  type ServiceCatalogItemDTO,
  type ServiceCatalogPatchInput,
  type ServiceDeliverableDTO,
  type ServiceDeliverableInput,
  type ServiceEngagementDTO,
  type ServiceEngagementInput,
  type ServiceEngagementPatchInput,
} from "@/lib/api";

export const serviceEngagementRepository = {
  listCatalog: (params?: { status?: string; visibility?: string }): Promise<ServiceCatalogItemDTO[]> =>
    serviceEngagementsApi.listCatalog(params),

  createCatalogItem: (input: ServiceCatalogInput): Promise<ServiceCatalogItemDTO> =>
    serviceEngagementsApi.createCatalogItem(input),

  getCatalogItem: (serviceId: string): Promise<ServiceCatalogItemDTO> =>
    serviceEngagementsApi.getCatalogItem(serviceId),

  patchCatalogItem: (serviceId: string, input: ServiceCatalogPatchInput): Promise<ServiceCatalogItemDTO> =>
    serviceEngagementsApi.patchCatalogItem(serviceId, input),

  listEngagements: (params?: { company_id?: string; status?: string }): Promise<ServiceEngagementDTO[]> =>
    serviceEngagementsApi.listEngagements(params),

  createEngagement: (input: ServiceEngagementInput): Promise<ServiceEngagementDTO> =>
    serviceEngagementsApi.createEngagement(input, {
      idempotencyKey: makeClientIdempotencyKey("service-engagement-create"),
    }),

  getEngagement: (engagementId: string): Promise<ServiceEngagementDTO> =>
    serviceEngagementsApi.getEngagement(engagementId),

  patchEngagement: (engagementId: string, input: ServiceEngagementPatchInput): Promise<ServiceEngagementDTO> =>
    serviceEngagementsApi.patchEngagement(engagementId, input, {
      idempotencyKey: makeClientIdempotencyKey(`service-engagement-update:${engagementId}`),
    }),

  listDeliverables: (engagementId: string): Promise<ServiceDeliverableDTO[]> =>
    serviceEngagementsApi.listDeliverables(engagementId),

  createDeliverable: (engagementId: string, input: ServiceDeliverableInput): Promise<ServiceDeliverableDTO> =>
    serviceEngagementsApi.createDeliverable(engagementId, input, {
      idempotencyKey: makeClientIdempotencyKey(`service-deliverable-create:${engagementId}`),
    }),
};

type ServiceEngagementRepository = typeof serviceEngagementRepository;

export type { ServiceEngagementRepository };

function makeClientIdempotencyKey(prefix: string): string {
  const randomId =
    typeof globalThis.crypto?.randomUUID === "function"
      ? globalThis.crypto.randomUUID()
      : `${Date.now()}-${Math.random().toString(36).slice(2)}`;
  return `${prefix}:${randomId}`;
}
