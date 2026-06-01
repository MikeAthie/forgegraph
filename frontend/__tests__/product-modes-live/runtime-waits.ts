import { expect, type APIResponse, type Page } from "@playwright/test";

type PhaseWithWorkstreams = {
  workstreams: Array<{ status: string }>;
};

type PerformanceWithMetricSnapshot = {
  current_state: {
    metric_snapshot_id?: string;
  };
};

export async function waitForBackendPostResponse(
  page: Page,
  pathPart: string,
  timeout = 60_000,
): Promise<APIResponse> {
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
