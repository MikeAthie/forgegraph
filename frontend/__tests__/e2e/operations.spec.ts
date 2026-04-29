import { expect, test } from "@playwright/test";

import { createTestUser, ensureUserRegistered, openAuthenticatedPage } from "./helpers";
import { mockOperationApis, pausedOperationId, succeededOperationId } from "./fixtures/operationApis";

test.describe("Operation Visibility", () => {
  test("shows a seeded operation in the visibility screen and opens detail", async ({ page, request }, testInfo) => {
    const user = createTestUser(testInfo, "operations");
    await ensureUserRegistered(request, user);
    await mockOperationApis(page);

    await openAuthenticatedPage(page, user, "/runs");

    await expect(page.getByRole("heading", { name: /recent company operations/i })).toBeVisible();
    await expect(page.getByRole("button", { name: /revenue operating pulse/i })).toBeVisible();

    const operationDetailHref = await page.getByRole("link", { name: /open operation detail/i }).getAttribute("href");
    expect(operationDetailHref).toBe(`/runs/${succeededOperationId}`);
    await page.goto(operationDetailHref!);

    await expect(page).toHaveURL(new RegExp(`/runs/${succeededOperationId}$`));
    await expect(page.getByText(/operation detail/i)).toBeVisible();
    await expect(page.getByRole("heading", { name: /department activity/i })).toBeVisible();
    await expect(page.getByRole("heading", { name: /operation state/i })).toBeVisible();
    await expect(page.getByText(/revenue pulse is ready for review/i).first()).toBeVisible();
  });

  test("shows paused operations with approval context", async ({ page, request }, testInfo) => {
    const user = createTestUser(testInfo, "operations-paused");
    await ensureUserRegistered(request, user);
    await mockOperationApis(page);

    await openAuthenticatedPage(page, user, `/runs/${pausedOperationId}`);

    await expect(page.getByText(/approval is waiting/i)).toBeVisible();
    await expect(page.getByRole("link", { name: /open approvals/i })).toBeVisible();
  });

  test("surfaces status badges across operations", async ({ page, request }, testInfo) => {
    const user = createTestUser(testInfo, "operations-status");
    await ensureUserRegistered(request, user);
    await mockOperationApis(page);

    await openAuthenticatedPage(page, user, "/runs");

    await expect(page.getByRole("heading", { name: /recent company operations/i })).toBeVisible();
    await expect(page.getByText(/^completed$/i).first()).toBeVisible();
    await expect(page.getByText(/^failed$/i).first()).toBeVisible();
  });

  test("shows an empty state when no operations exist", async ({ page, request }, testInfo) => {
    const user = createTestUser(testInfo, "operations-empty");
    await ensureUserRegistered(request, user);
    await mockOperationApis(page, { operations: [] });

    await openAuthenticatedPage(page, user, "/runs");

    await expect(page.getByText(/no operations available/i)).toBeVisible();
  });

  test("shows a translated error for a non-existent operation", async ({ page, request }, testInfo) => {
    const user = createTestUser(testInfo, "operations-missing");
    await ensureUserRegistered(request, user);
    const missingOperationId = "00000000-0000-0000-0000-000000000000";
    await mockOperationApis(page, { missingOperationId });

    await openAuthenticatedPage(page, user, `/runs/${missingOperationId}`);

    await expect(page.getByText(/operation could not continue/i)).toBeVisible();
  });
});
