import { expect, test } from "@playwright/test";

import {
  createTestUser,
  ensureUserRegistered,
  getAccessToken,
  login,
  proxyBackendApi,
  seedFrontendControlPlaneFixture,
} from "./helpers";

test.describe("Realtime Monitoring Contract", () => {
  test("updates observable state without a refresh when backend events arrive", async ({ page, request }, testInfo) => {
    const user = createTestUser(testInfo, "realtime");
    await ensureUserRegistered(request, user);
    const fixture = seedFrontendControlPlaneFixture(user);
    const accessToken = await getAccessToken(request, user);
    await proxyBackendApi(page, request, user, [
      new RegExp(`/api/runs/${fixture.runIds.running}(?:\\?.*)?$`),
      /\/api\/decisions\/count(?:\?.*)?$/,
    ]);

    await login(page, user);
    await page.goto(`/runs/${fixture.runIds.running}`);
    await page.waitForLoadState("networkidle");

    await expect(page.getByRole("heading", { name: /structured execution trace/i })).toBeVisible();
    await expect(page.getByText(/^live updates$/i)).toBeVisible();
    await expect(page.getByText(/invoice monitoring/i)).toBeVisible();

    const runUpdate = await request.post(
      `${process.env.PLAYWRIGHT_API_URL}/api/runs/${fixture.runIds.running}/events`,
      {
        headers: {
          Authorization: `Bearer ${accessToken}`,
        },
        data: {
          event_type: "run.updated",
          run: {
            status: "succeeded",
            ended_at: "2026-04-01T12:05:00.000Z",
            output_json: { summary: "Budget watch completed cleanly." },
            error_message: "",
          },
        },
      },
    );
    expect(runUpdate.ok()).toBeTruthy();

    const nodeUpdate = await request.post(
      `${process.env.PLAYWRIGHT_API_URL}/api/runs/${fixture.runIds.running}/events`,
      {
        headers: {
          Authorization: `Bearer ${accessToken}`,
        },
        data: {
          event_type: "node_run.updated",
          node_run: {
            id: "99999999-9999-9999-9999-999999999999",
            node_id: "finance_agent",
            node_type: "agent",
            status: "succeeded",
            attempt: 1,
            ended_at: "2026-04-01T12:05:00.000Z",
            output_json: { summary: "Budget watch completed cleanly." },
          },
        },
      },
    );
    expect(nodeUpdate.ok()).toBeTruthy();

    await expect(page.getByText(/^succeeded$/i).first()).toBeVisible();
    await expect(page.getByText(/budget watch completed cleanly/i).first()).toBeVisible();
  });
});
