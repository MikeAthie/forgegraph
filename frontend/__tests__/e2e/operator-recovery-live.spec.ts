import { expect, test } from "@playwright/test";

import { apiBaseUrl, createTestUser, loginLive } from "./live-helpers";

const API_BASE_URL = apiBaseUrl();

test.describe("Operator recovery live flow", () => {
  test("loads the /ops console from backend-owned recovery APIs", async ({ page, request }, testInfo) => {
    test.setTimeout(90_000);

    const user = createTestUser(testInfo, "operator-recovery-live");
    const accessToken = await loginLive(page, request, user, "/ops");

    await expect(page.getByRole("heading", { level: 1, name: /operator recovery/i })).toBeVisible({ timeout: 30_000 });
    await expect(page.getByRole("heading", { name: /^dead letters$/i })).toBeVisible();
    await expect(page.getByRole("heading", { name: /^projection lag$/i })).toBeVisible();
    await expect(page.getByRole("heading", { name: /^event spool$/i })).toBeVisible();

    const [deadLetters, projectionLag, eventSpool] = await Promise.all([
      request.get(`${API_BASE_URL}/api/ops/dead-letters`, {
        headers: { Authorization: `Bearer ${accessToken}` },
      }),
      request.get(`${API_BASE_URL}/api/ops/projection-lag`, {
        headers: { Authorization: `Bearer ${accessToken}` },
      }),
      request.get(`${API_BASE_URL}/api/ops/event-spool`, {
        headers: { Authorization: `Bearer ${accessToken}` },
      }),
    ]);

    expect(deadLetters.ok()).toBeTruthy();
    expect(projectionLag.ok()).toBeTruthy();
    expect(eventSpool.ok()).toBeTruthy();

    const deadLetterBody = (await deadLetters.json()) as {
      data?: { items?: Array<{ id: string; actions: string[] }> };
    };
    await Promise.all((deadLetterBody.data?.items ?? []).map((item) => expect(page.getByText(item.id)).toBeVisible()));
  });
});
