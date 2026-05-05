import { expect, test } from "@playwright/test";

import { apiBaseUrl, createTestUser, loginLive } from "./live-helpers";

const API_BASE_URL = apiBaseUrl();

test.describe("Operator recovery live flow", () => {
  test("loads the /ops console from backend-owned recovery APIs", async ({ page, request }, testInfo) => {
    test.setTimeout(90_000);

    const user = createTestUser(testInfo, "operator-recovery-live");
    const accessToken = await loginLive(page, request, user, "/ops");

    await expect(page.getByRole("heading", { name: /operator recovery/i })).toBeVisible({ timeout: 30_000 });
    await expect(page.getByText(/dead letters/i)).toBeVisible();
    await expect(page.getByText(/projection lag/i)).toBeVisible();
    await expect(page.getByText(/event spool/i)).toBeVisible();

    const deadLetters = await request.get(`${API_BASE_URL}/api/ops/dead-letters`, {
      headers: { Authorization: `Bearer ${accessToken}` },
    });
    const projectionLag = await request.get(`${API_BASE_URL}/api/ops/projection-lag`, {
      headers: { Authorization: `Bearer ${accessToken}` },
    });
    const eventSpool = await request.get(`${API_BASE_URL}/api/ops/event-spool`, {
      headers: { Authorization: `Bearer ${accessToken}` },
    });

    expect(deadLetters.ok()).toBeTruthy();
    expect(projectionLag.ok()).toBeTruthy();
    expect(eventSpool.ok()).toBeTruthy();

    const deadLetterBody = (await deadLetters.json()) as {
      data?: { items?: Array<{ id: string; actions: string[] }> };
    };
    for (const item of deadLetterBody.data?.items ?? []) {
      await expect(page.getByText(item.id)).toBeVisible();
    }
  });
});
