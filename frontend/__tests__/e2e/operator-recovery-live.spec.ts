import { expect, test } from "@playwright/test";

import {
  apiBaseUrl,
  createGraphName,
  createHumanGateRunViaApi,
  createTestUser,
  loginLive,
  waitForRunStatus,
} from "./live-helpers";

const API_BASE_URL = apiBaseUrl();

test.describe("Operator recovery live flow", () => {
  test("inspects a stuck run and force-fails it through backend-owned operator controls", async ({
    page,
    request,
  }, testInfo) => {
    test.setTimeout(120_000);

    const user = createTestUser(testInfo, "operator-recovery-live");
    const accessToken = await loginLive(page, request, user, "/admin/operations");

    const graphName = createGraphName("Operator Recovery Live");
    const { runId } = await createHumanGateRunViaApi(request, accessToken, {
      graphName,
      promptMessage: "Operator recovery live test pause.",
      instructions: "Pause so the operator console can inspect and recover this run.",
    });
    await waitForRunStatus(request, accessToken, runId, "paused");

    await page.goto("/admin/operations");
    await expect(page.getByRole("heading", { name: /recovery controls/i })).toBeVisible({ timeout: 30_000 });
    await page.getByPlaceholder("Run ID").fill(runId);
    await page
      .getByPlaceholder(/operator reason required/i)
      .fill("Operator live recovery test force-failed an isolated paused run.");
    await page.getByRole("button", { name: /inspect run/i }).click();
    await expect(page.getByText(/blocked work/i)).toBeVisible({ timeout: 30_000 });
    await expect(page.getByText(/pending decisions/i)).toBeVisible();

    const forceFailResponse = page.waitForResponse(
      (response) =>
        response.url().includes(`/api/operator/runs/${runId}/force-fail`) &&
        response.request().method() === "POST",
    );
    await page.getByRole("button", { name: /force fail/i }).click();
    expect((await forceFailResponse).ok()).toBeTruthy();

    const operatorState = await request.get(`${API_BASE_URL}/api/operator/runs/${runId}/state`, {
      headers: { Authorization: `Bearer ${accessToken}` },
    });
    expect(operatorState.ok()).toBeTruthy();
    const body = (await operatorState.json()) as { data?: { run?: { status?: string }; tasks?: Array<{ status: string }> } };
    expect(body.data?.run?.status).toBe("failed");
    expect((body.data?.tasks ?? []).every((task) => ["failed", "completed", "dead_lettered", "cancelled"].includes(task.status))).toBeTruthy();
  });
});
