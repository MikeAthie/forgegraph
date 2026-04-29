import { accountingApi, type AccountingOverview, type CostLedgerEntry } from "@/lib/api";

import type { AccountingLedgerEntryVM, AccountingOverviewVM } from "../translation/viewModels";

function formatSourceLabel(entry: CostLedgerEntry): string {
  if (entry.agent_id) {
    return `Department ${entry.agent_id}`;
  }
  if (entry.task_id) {
    return `Task ${entry.task_id}`;
  }
  if (entry.execution_id) {
    return `Operation ${entry.execution_id}`;
  }
  return "Shared infrastructure";
}

function toAccountingOverviewVM(overview: AccountingOverview): AccountingOverviewVM {
  return {
    organizationId: overview.organization_id,
    totalCostUsd: overview.total_cost_usd,
    costByType: overview.cost_by_type.map((entry) => ({
      id: entry.cost_type,
      label: entry.cost_type,
      totalCostUsd: entry.total_cost_usd,
      entryCount: entry.entry_count,
    })),
    topDepartments: overview.top_agents.map((department) => ({
      id: department.id,
      displayName: department.display_name,
      status: department.status,
      totalCostUsd: department.total_cost_usd,
    })),
  };
}

function toAccountingLedgerEntryVM(entry: CostLedgerEntry): AccountingLedgerEntryVM {
  return {
    id: entry.id,
    sourceLabel: formatSourceLabel(entry),
    provider: entry.provider,
    model: entry.model,
    usageLabel: entry.cost_type,
    quantity: entry.quantity,
    costType: entry.cost_type,
    totalCostUsd: entry.total_cost_usd,
    occurredAt: entry.occurred_at,
  };
}

export const accountingRepository = {
  getOverview: async (): Promise<AccountingOverviewVM> => {
    const overview = await accountingApi.getOverview();
    return toAccountingOverviewVM(overview);
  },

  listLedger: async (): Promise<AccountingLedgerEntryVM[]> => {
    const entries = await accountingApi.listLedger();
    return entries.map(toAccountingLedgerEntryVM);
  },
};
