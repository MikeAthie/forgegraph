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
    const user = createTestUser(testInfo, "live-overview");
    await ensureUserRegistered(request, user);
    seedFrontendControlPlaneFixture(user);
    await proxyBackendApi(page, request, user, [
      /\/api\/system-state\/overview(?:\?.*)?$/,
      /\/api\/decisions\/count(?:\?.*)?$/,
      /\/api\/approvals\/count(?:\?.*)?$/,
    ]);

    await login(page, user);

    await expect(page.getByRole("heading", { name: /organization overview/i })).toBeVisible();
    await expect(page.getByRole("heading", { name: /^active agents$/i })).toBeVisible();
    await expect(page.getByText(/^token cost today$/i)).toBeVisible();
    await expect(page.getByRole("link", { name: /ops conductor/i })).toBeVisible();
    await expect(page.getByRole("link", { name: /billing sentinel/i })).toBeVisible();
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
    await page.goto("/inbox");
    await page.waitForLoadState("networkidle");

    await expect(page.getByRole("heading", { name: /review consequential agent decisions/i })).toBeVisible();
    await expect(page.getByText(fixture.approval.promptMessage, { exact: true })).toBeVisible();
    await expect(page.getByRole("button", { name: new RegExp(fixture.approval.graphName, "i") })).toBeVisible();
  });

  test("renders execution trace from backend run detail", async ({ page, request }, testInfo) => {
    const user = createTestUser(testInfo, "live-trace");
    await ensureUserRegistered(request, user);
    const fixture = seedFrontendControlPlaneFixture(user);
    await proxyBackendApi(page, request, user, [
      new RegExp(`/api/executions/${fixture.runIds.failed}(?:\\?.*)?$`),
      /\/api\/decisions\/count(?:\?.*)?$/,
    ]);

    await login(page, user);
    await page.goto(`/executions/${fixture.runIds.failed}`);
    await page.waitForLoadState("networkidle");

    await expect(page.getByRole("heading", { name: /structured execution trace/i })).toBeVisible();
    await expect(page.getByRole("button", { name: /write_ticket/i })).toBeVisible();
    await expect(page.getByText(/escalation api rejected the payload/i)).toBeVisible();
  });
});
