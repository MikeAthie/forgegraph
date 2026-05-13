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
    serviceEngagementsApi.createEngagement(input),

  getEngagement: (engagementId: string): Promise<ServiceEngagementDTO> =>
    serviceEngagementsApi.getEngagement(engagementId),

  patchEngagement: (engagementId: string, input: ServiceEngagementPatchInput): Promise<ServiceEngagementDTO> =>
    serviceEngagementsApi.patchEngagement(engagementId, input),

  listDeliverables: (engagementId: string): Promise<ServiceDeliverableDTO[]> =>
    serviceEngagementsApi.listDeliverables(engagementId),

  createDeliverable: (engagementId: string, input: ServiceDeliverableInput): Promise<ServiceDeliverableDTO> =>
    serviceEngagementsApi.createDeliverable(engagementId, input),
};

type ServiceEngagementRepository = typeof serviceEngagementRepository;

export type { ServiceEngagementRepository };
