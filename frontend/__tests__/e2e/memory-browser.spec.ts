import { expect, test } from "@playwright/test";

import { createObservationViaApi, createTestUser, ensureUserRegistered, getAccessToken, login } from "./helpers";

test.describe("Memory Browser", () => {
  test("shows curated observations seeded through the API", async ({ page, request }, testInfo) => {
    test.setTimeout(60_000);

    const user = createTestUser(testInfo, "memory-browser");
    await ensureUserRegistered(request, user);
    const accessToken = await getAccessToken(request, user);

    await createObservationViaApi(request, accessToken, {
      type: "customer_memory",
      title: "Jackie Memory Dossier",
      content: "Jackie prefers concise planning updates and values concrete next steps.",
      scope: "graph",
      graph_id: crypto.randomUUID(),
      topic_key: "jackie-memory",
      dedupe: true,
      update_topic: true,
    });

    await login(page, user);
    await page.goto("/memory");

    await expect(
      page.getByRole("heading", { name: /browse what the system decided was worth keeping/i }),
    ).toBeVisible();
    await expect(page.getByText(/Jackie Memory Dossier/i).first()).toBeVisible();

    await page.getByRole("searchbox", { name: /search observations/i }).fill("dossier");
    await expect(page.getByText(/Jackie Memory Dossier/i).first()).toBeVisible();

    await page.getByRole("button", { name: /Jackie Memory Dossier/i }).click();
    await expect(page.getByText(/Observation dossier/i)).toBeVisible();
    await expect(page.getByText(/concise planning updates and values concrete next steps/i).first()).toBeVisible();
    await expect(page.getByText(/Topic jackie-memory/i).nth(1)).toBeVisible();
  });
});
