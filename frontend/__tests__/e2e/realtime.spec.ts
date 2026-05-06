import { expect, test, type APIRequestContext } from "@playwright/test";

import {
  createTestUser,
  ensureUserRegistered,
  getAccessToken,
  login,
  seedFrontendControlPlaneFixture,
} from "./helpers";

async function waitForRunWebSocketSubscription(request: APIRequestContext, accessToken: string, runId: string) {
  const apiBase = (process.env.PLAYWRIGHT_API_URL ?? "http://127.0.0.1:8002").replace(/\/$/, "");
  await expect
    .poll(
      async () => {
        const response = await request.get(`${apiBase}/api/operator/ws/subscribers`, {
          headers: { Authorization: `Bearer ${accessToken}` },
        });
        if (!response.ok()) {
          return 0;
        }
        const body = (await response.json()) as {
          data?: { by_run?: Array<{ run_id?: string; connections?: number }> };
          by_run?: Array<{ run_id?: string; connections?: number }>;
        };
        const snapshot = body.data ?? body;
        const runSubscription = snapshot.by_run?.find((item) => item.run_id === runId);
        return runSubscription?.connections ?? 0;
      },
      { timeout: 30_000 },
    )
    .toBeGreaterThan(0);
}

test.describe("Realtime Monitoring Contract", () => {
  test("updates observable state without a refresh when backend events arrive", async ({ page, request }, testInfo) => {
    test.setTimeout(60_000);
    const user = createTestUser(testInfo, "realtime");
    await ensureUserRegistered(request, user);
    const fixture = seedFrontendControlPlaneFixture(user);
    const accessToken = await getAccessToken(request, user);

    await login(page, user);
    const initialRunResponse = page.waitForResponse(
      (response) =>
        response.request().method() === "GET" &&
        response.url().includes(`/api/runs/${fixture.runIds.running}`) &&
        response.status() === 200,
    );
    const runSocket = page.waitForEvent("websocket", { timeout: 15_000 });
    await page.goto(`/runs/${fixture.runIds.running}`);
    await initialRunResponse;
    await runSocket;
    await waitForRunWebSocketSubscription(request, accessToken, fixture.runIds.running);

    await expect(page.getByRole("heading", { name: /operation detail/i }).first()).toBeVisible();
    await expect(page.getByRole("heading", { name: /invoice monitoring/i, level: 2 })).toBeVisible();

    const endedAt = new Date().toISOString();
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
            ended_at: endedAt,
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
            ended_at: endedAt,
            output_json: { summary: "Budget watch completed cleanly." },
          },
        },
      },
    );
    expect(nodeUpdate.ok()).toBeTruthy();

    await expect(page.getByText(/^completed$/i).first()).toBeVisible();
    await expect(page.getByText(/budget watch completed cleanly/i).first()).toBeVisible();
  });
});
