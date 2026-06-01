import {
  communicationApi,
  type CommunicationMessageDTO,
  type CommunicationMessageInput,
  type CommunicationRouteRequestResponse,
  type CommunicationThreadDTO,
  type CommunicationThreadInput,
} from "@/lib/api";
import { newClientCommandId, stableClientCommandId } from "@/lib/idempotency";

export const communicationRepository = {
  listThreads: (params: {
    companyId: string;
    status?: string;
    serviceEngagementId?: string;
    operationId?: string;
  }): Promise<CommunicationThreadDTO[]> =>
    communicationApi.listThreads({
      company_id: params.companyId,
      status: params.status,
      service_engagement_id: params.serviceEngagementId,
      operation_id: params.operationId,
    }),

  createThread: (input: CommunicationThreadInput): Promise<CommunicationThreadDTO> =>
    communicationApi.createThread(input, {
      idempotencyKey: stableClientCommandId(
        "communication.thread.create",
        input.company_id,
        input.source_key || input.title,
      ),
    }),

  listMessages: (threadId: string): Promise<CommunicationMessageDTO[]> => communicationApi.listMessages(threadId),

  createMessage: (threadId: string, input: CommunicationMessageInput): Promise<CommunicationMessageDTO> =>
    communicationApi.createMessage(threadId, input, {
      idempotencyKey: newClientCommandId("communication.message.create"),
    }),

  routeRequest: (messageId: string): Promise<CommunicationRouteRequestResponse> =>
    communicationApi.routeRequest(messageId, {
      idempotencyKey: stableClientCommandId("communication.message.route_request", messageId),
    }),
};

type CommunicationRepository = typeof communicationRepository;

export type { CommunicationRepository };
