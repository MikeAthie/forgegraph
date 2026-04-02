import { expect, test } from "@playwright/test";

import {
  createGraphName,
  ensureUserRegistered,
  expectGraphEditorOpen,
  gotoWithRetry,
  login,
  type TestUser,
  createTestUser,
} from "./helpers";

let seededUser: TestUser;

test.beforeAll(async ({ request }, testInfo) => {
  seededUser = createTestUser(testInfo, "graphs");
  await ensureUserRegistered(request, seededUser);
});

test.describe("Workflow Definitions", () => {
  test.beforeEach(async ({ page }) => {
    await login(page, seededUser);
  });

  test("shows the workflow workspace page", async ({ page }) => {
    await gotoWithRetry(page, "/workflows");

    await expect(page.getByRole("heading", { name: /definitions, revisions, and execution visibility/i })).toBeVisible();
    await expect(page.getByRole("link", { name: /open editor/i })).toBeVisible();
  });

  test("keeps the legacy /graphs route available", async ({ page }) => {
    await gotoWithRetry(page, "/graphs");

    await expect(page.getByRole("heading", { name: /manage definitions and revisions/i })).toBeVisible();
    await expect(page.getByRole("button", { name: /^new workflow$/i })).toBeVisible();
  });

  test("validates workflow creation requires a name", async ({ page }) => {
    await gotoWithRetry(page, "/graphs");
    await page.getByRole("button", { name: /^new workflow$/i }).click();

    const dialog = page.getByRole("dialog");
    await expect(dialog).toBeVisible();

    await dialog.getByRole("button", { name: /^create$/i }).click();
    await expect(dialog.getByText(/name is required/i)).toBeVisible();
  });

  test("creates a workflow and opens the editor", async ({ page }) => {
    const graphName = createGraphName("E2E Workflow");

    await gotoWithRetry(page, "/graphs");
    await page.getByRole("button", { name: /^new workflow$/i }).click();

    const dialog = page.getByRole("dialog");
    await expect(dialog).toBeVisible();

    await page.locator("#create-graph-name").fill(graphName);
    await page.locator("#create-graph-description").fill("Created by Playwright.");
    await dialog.getByRole("button", { name: /^create$/i }).click();

    await expectGraphEditorOpen(page);
    await expect(page.getByRole("heading", { name: graphName, exact: true })).toBeVisible();
    await expect(page.getByText(/workflow editor/i)).toBeVisible();
  });

  test("edits a workflow from the definitions list", async ({ page }) => {
    const graphName = createGraphName("E2E Workflow Edit");

    await gotoWithRetry(page, "/graphs");
    await page.getByRole("button", { name: /^new workflow$/i }).click();
    await page.locator("#create-graph-name").fill(graphName);
    await page.getByRole("dialog").getByRole("button", { name: /^create$/i }).click();

    await expectGraphEditorOpen(page);

    await gotoWithRetry(page, "/graphs");
    await expect(page.getByRole("link", { name: graphName })).toBeVisible();

    const graphCard = page.locator('[data-slot="card"]').filter({ hasText: graphName });
    await graphCard.getByRole("button", { name: /^edit$/i }).click();

    const dialog = page.getByRole("dialog");
    await expect(dialog.getByText(/edit workflow definition/i)).toBeVisible();

    const updatedName = createGraphName("E2E Workflow Updated");
    await page.locator("#edit-graph-name").fill(updatedName);
    await page.locator("#edit-graph-description").fill("Updated by Playwright.");
    await dialog.getByRole("button", { name: /^save$/i }).click();

    await expect(page.getByRole("link", { name: updatedName })).toBeVisible();
  });

  test("deletes a workflow definition with confirmation", async ({ page }) => {
    const graphName = createGraphName("E2E Workflow Delete");

    await gotoWithRetry(page, "/graphs");
    await page.getByRole("button", { name: /^new workflow$/i }).click();
    await page.locator("#create-graph-name").fill(graphName);
    await page.getByRole("dialog").getByRole("button", { name: /^create$/i }).click();

    await expectGraphEditorOpen(page);

    await gotoWithRetry(page, "/graphs");
    const graphCard = page.locator('[data-slot="card"]').filter({ hasText: graphName });
    await expect(graphCard).toBeVisible();

    await graphCard.getByRole("button", { name: /^delete$/i }).click();

    const alertDialog = page.getByRole("alertdialog");
    await expect(alertDialog).toBeVisible();
    await alertDialog.getByRole("button", { name: /^delete$/i }).click();

    await expect(page.getByRole("link", { name: graphName })).not.toBeVisible();
  });
});
