import { expect, test } from "@playwright/test";

import {
  createTestUser,
  ensureUserRegistered,
  login,
  proxyBackendApi,
  seedFrontendControlPlaneFixture,
} from "./helpers";

test.describe("Frontend Control Surface Live Backend", () => {
  test("renders overview state from backend projections", async ({ page, request }, testInfo) => {
    test.setTimeout(60_000);
    const user = createTestUser(testInfo, "live-overview");
    await ensureUserRegistered(request, user);
    seedFrontendControlPlaneFixture(user);
    await proxyBackendApi(page, request, user, [
      /\/api\/system-state\/overview(?:\?.*)?$/,
      /\/api\/decisions\/count(?:\?.*)?$/,
      /\/api\/approvals\/count(?:\?.*)?$/,
    ]);

    await login(page, user);
    await page.goto("/overview", { waitUntil: "domcontentloaded" });

    await expect(page.getByRole("heading", { name: /^command ops$/i }).first()).toBeVisible({ timeout: 15_000 });
    await expect(page.locator("a[href$='#active-departments']").filter({ hasText: /active agents/i })).toBeVisible({
      timeout: 15_000,
    });
    await expect(page.locator("a[href$='#usage-budget']").filter({ hasText: /cost today/i })).toBeVisible({
      timeout: 15_000,
    });
    await expect(page.getByRole("link", { name: /ops conductor/i }).first()).toBeVisible();
    await expect(page.getByRole("link", { name: /billing sentinel/i }).first()).toBeVisible();
    await expect(
      page.getByText(/ops conductor is waiting for a decision in vendor payment review/i).first(),
    ).toBeVisible();
  });

  test("renders live inbox state from backend approvals", async ({ page, request }, testInfo) => {
    const user = createTestUser(testInfo, "live-inbox");
    await ensureUserRegistered(request, user);
    const fixture = seedFrontendControlPlaneFixture(user);
    await proxyBackendApi(page, request, user, [
      /\/api\/approvals\/?(?:\?.*)?$/,
      /\/api\/approvals\/count(?:\?.*)?$/,
      /\/api\/decisions\/count(?:\?.*)?$/,
    ]);

    await login(page, user);
    await page.goto("/inbox", { waitUntil: "domcontentloaded" });

    await expect(page.getByRole("heading", { name: /decide with context, not with logs/i })).toBeVisible({
      timeout: 15_000,
    });
    await expect(page.getByText(fixture.approval.promptMessage, { exact: true }).first()).toBeVisible();
    await expect(page.getByRole("button", { name: new RegExp(fixture.approval.graphName, "i") })).toBeVisible();
  });

  test("renders execution trace from backend run detail", async ({ page, request }, testInfo) => {
    const user = createTestUser(testInfo, "live-trace");
    await ensureUserRegistered(request, user);
    const fixture = seedFrontendControlPlaneFixture(user);
    await proxyBackendApi(page, request, user, [
      new RegExp(`/api/runs/${fixture.runIds.failed}(?:\\?.*)?$`),
      /\/api\/decisions\/count(?:\?.*)?$/,
    ]);

    await login(page, user);
    await page.goto(`/executions/${fixture.runIds.failed}`, { waitUntil: "domcontentloaded" });

    await expect(page.getByRole("heading", { name: /operation detail/i }).first()).toBeVisible({ timeout: 15_000 });
    await expect(page.getByText(/operation could not continue|could not finish/i).first()).toBeVisible();
    await expect(page.getByRole("heading", { name: /department activity/i })).toBeVisible();
  });
});
