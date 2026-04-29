import { runsApi } from "@/lib/api";
import { toDeliverableVM, type DeliverableVM } from "@/domain/translation";

export const deliverableRepository = {
  getForOperation: async (operationId: string): Promise<DeliverableVM> => {
    const operation = await runsApi.get(operationId);
    return toDeliverableVM(operation);
  },

  listForCompany: async (companyId: string): Promise<DeliverableVM[]> => {
    const operations = await runsApi.list();
    const completed = operations
      .filter((operation) => operation.graph_id === companyId)
      .filter((operation) => String(operation.status).toLowerCase() === "succeeded")
      .slice(0, 3);
    const details = await Promise.all(completed.map((operation) => runsApi.get(operation.id)));
    return details.map(toDeliverableVM);
  },
};

export type DeliverableRepository = typeof deliverableRepository;
