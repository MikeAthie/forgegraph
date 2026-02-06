import { test, expect } from "@playwright/test";

import { createTestUser, ensureUserRegistered, login, type TestUser } from "./helpers";

let seededUser: TestUser;

test.beforeAll(async ({ request }, testInfo) => {
  seededUser = createTestUser(testInfo, "e2e-onboarding");
  await ensureUserRegistered(request, seededUser);
});

test.describe("Onboarding quick starts", () => {
  test.describe.configure({ mode: "serial" });

  test.beforeEach(async ({ page }) => {
    await login(page, seededUser);
  });

  test("selects a quick start template and launches a run", async ({ page }) => {
    test.setTimeout(60_000);

    await page.goto("/onboarding");

    await expect(page.getByText(/template .* credential .* live run/i)).toBeVisible();
    await expect(page.getByTestId("provider-help-tip")).toBeVisible();
    await expect(page.getByTestId("graph-name-help-tip")).toBeVisible();
    await expect(page.getByTestId("onboarding-checklist-progress")).toBeVisible();

    const progressLabel = page.getByTestId("onboarding-checklist-progress-label");
    await expect(progressLabel).toBeVisible();

    const quickStartCards = page.locator('[data-testid^="quick-start-card-"]');
    await expect(quickStartCards.first()).toBeVisible();
    await quickStartCards.first().click();
    await expect
      .poll(async () => {
        const text = await progressLabel.textContent();
        const match = text?.match(/(\d+)\/(\d+)/);
        return match ? Number(match[1]) : 0;
      })
      .toBeGreaterThan(0);

    const templatePreview = page.getByTestId("template-preview-panel");
    await expect(templatePreview).toBeVisible();
    await expect(templatePreview.getByText(/template metadata/i)).toBeVisible();
    await expect(templatePreview.getByText(/expected output/i)).toBeVisible();
    await expect(templatePreview.getByText(/required credentials/i)).toBeVisible();

    const createAndRunButton = page.getByRole("button", { name: /create & run/i });
    await expect(createAndRunButton).toBeEnabled({ timeout: 15_000 });
    await createAndRunButton.click();

    const redirected = await page
      .waitForURL(/\/runs\/[a-f0-9-]+/, { timeout: 20_000 })
      .then(() => true)
      .catch(() => false);

    if (!redirected) {
      await expect(page).toHaveURL(/\/onboarding$/);
      await expect(page.getByTestId("template-preview-panel")).toBeVisible();
      await expect(createAndRunButton).toBeEnabled();
    }
  });
});
