import { expect, test } from "@playwright/test";

import {
  createTestUser,
  loginLive,
} from "./live-helpers";

test.describe("Production launch live OS surfaces", () => {
  test("loads operator surfaces from the live backend stack", async ({ page, request }, testInfo) => {
    test.setTimeout(120_000);

    const user = createTestUser(testInfo, "production-launch-live");
    await loginLive(page, request, user, "/overview");

    const surfaces: Array<[string, RegExp]> = [
      ["/overview", /Command Ops|System health/i],
      ["/departments", /How the company thinks|Departments/i],
      ["/tasks", /Department activity at a glance|Activity queue/i],
      ["/approvals", /Approval posture|Decide with context/i],
      ["/runs", /Recent company operations|Operation list/i],
      ["/memory", /Browse the knowledge layer|Memory inspection/i],
      ["/accounting", /Economic state of the AI organization|Accounting/i],
      ["/settings", /Configure the operating environment|Settings posture/i],
    ];

    for (const [route, expectedText] of surfaces) {
      await page.goto(route);
      await expect(page.getByText(expectedText).first()).toBeVisible({ timeout: 30_000 });
    }
  });

  test("keeps protected OS surfaces behind backend authentication", async ({ browser }) => {
    const context = await browser.newContext();
    const unauthenticatedPage = await context.newPage();
    await unauthenticatedPage.goto("/overview");
    await expect(unauthenticatedPage).toHaveURL(/\/login(?:\?.*)?$/, { timeout: 30_000 });
    await context.close();
  });
});
