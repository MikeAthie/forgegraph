import { expect, type APIResponse, type Page } from "@playwright/test";

type PhaseWithWorkstreams = {
  workstreams: Array<{ status: string }>;
};

type ContractWithRevision = {
  contract_revision?: number;
  current_state?: {
    contract_revision?: number;
  };
};

type OperationWithStatus = {
  status: string;
};

type PerformanceWithMetricSnapshot = {
  current_state: {
    metric_snapshot_id?: string;
  };
};

export async function waitForBackendPostResponse(page: Page, pathPart: string, timeout = 60_000): Promise<APIResponse> {
  const response = await page.waitForResponse(
    (candidate) => candidate.url().includes(pathPart) && candidate.request().method() === "POST",
    { timeout },
  );
  expect(response.ok()).toBeTruthy();
  return response;
}

export async function waitForPhaseWorkstreamMaterialization(
  fetchContract: () => Promise<PhaseWithWorkstreams>,
  timeout = 30_000,
): Promise<void> {
  await expect
    .poll(
      async () => {
        const contract = await fetchContract();
        return contract.workstreams.some((workstream) => workstream.status !== "not_started");
      },
      { timeout },
    )
    .toBe(true);
}

export async function waitForOperation(
  fetchOperation: () => Promise<OperationWithStatus>,
  terminalStates: string[] = ["completed"],
  timeout = 60_000,
): Promise<void> {
  await expect
    .poll(
      async () => {
        const operation = await fetchOperation();
        return terminalStates.includes(operation.status);
      },
      { timeout },
    )
    .toBe(true);
}

export async function waitForContractRevision(
  fetchContract: () => Promise<ContractWithRevision>,
  minimumRevision: number,
  timeout = 60_000,
): Promise<void> {
  await expect
    .poll(
      async () => {
        const contract = await fetchContract();
        return contract.contract_revision ?? contract.current_state?.contract_revision ?? 0;
      },
      { timeout },
    )
    .toBeGreaterThanOrEqual(minimumRevision);
}

export async function waitForPerformanceMetricSnapshot(
  fetchContract: () => Promise<PerformanceWithMetricSnapshot>,
  timeout = 30_000,
): Promise<void> {
  await expect
    .poll(
      async () => {
        const contract = await fetchContract();
        return contract.current_state.metric_snapshot_id ?? "";
      },
      { timeout },
    )
    .not.toBe("");
}
