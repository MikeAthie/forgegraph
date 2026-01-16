import { test, expect } from "@playwright/test";
import { createTestUser, ensureUserRegistered, login, type TestUser } from "./helpers";

let seededUser: TestUser;

const createGraphName = (prefix: string) => `${prefix} ${Date.now()}-${Math.random().toString(16).slice(2)}`;

test.beforeAll(async ({ request }, testInfo) => {
  seededUser = createTestUser(testInfo, "e2e-graphs");
  await ensureUserRegistered(request, seededUser);
});

test.describe("Graphs", () => {
  test.beforeEach(async ({ page }) => {
    await login(page, seededUser);
  });

  test("shows the graphs page", async ({ page }) => {
    await expect(page.getByRole("heading", { name: /^graphs$/i })).toBeVisible();
    await expect(page.getByRole("button", { name: /^new graph$/i })).toBeVisible();
  });

  test("validates create graph requires name", async ({ page }) => {
    await page.getByRole("button", { name: /^new graph$/i }).click();

    const dialog = page.getByRole("dialog");
    await expect(dialog).toBeVisible();

    await dialog.getByRole("button", { name: /^create$/i }).click();
    await expect(dialog.getByText(/name is required/i)).toBeVisible();
  });

  test("creates a graph and opens the detail view", async ({ page }) => {
    const graphName = createGraphName("E2E Graph");

    await page.getByRole("button", { name: /^new graph$/i }).click();

    const dialog = page.getByRole("dialog");
    await expect(dialog).toBeVisible();

    await page.locator("#create-graph-name").fill(graphName);
    await page.locator("#create-graph-description").fill("Created by Playwright.");
    await dialog.getByRole("button", { name: /^create$/i }).click();

    await expect(page).toHaveURL(/\/graphs\/[a-f0-9-]+/);
    await expect(page.getByRole("heading", { level: 1, name: graphName })).toBeVisible();
  });

  test("edits a graph from the list", async ({ page }) => {
    const graphName = createGraphName("E2E Graph Edit");

    await page.getByRole("button", { name: /^new graph$/i }).click();
    await page.locator("#create-graph-name").fill(graphName);
    await page.getByRole("dialog").getByRole("button", { name: /^create$/i }).click();

    await expect(page).toHaveURL(/\/graphs\/[a-f0-9-]+/);

    await page.goto("/graphs");
    await expect(page.getByRole("link", { name: graphName })).toBeVisible();

    const graphCard = page.locator('[data-slot="card"]').filter({ hasText: graphName });
    await graphCard.getByRole("button", { name: /^edit$/i }).click();

    const dialog = page.getByRole("dialog");
    await expect(dialog.getByText(/edit graph/i)).toBeVisible();

    const updatedName = createGraphName("E2E Graph Updated");
    await page.locator("#edit-graph-name").fill(updatedName);
    await page.locator("#edit-graph-description").fill("Updated by Playwright.");
    await dialog.getByRole("button", { name: /^save$/i }).click();

    await expect(page.getByRole("link", { name: updatedName })).toBeVisible();
  });

  test("deletes a graph with confirmation", async ({ page }) => {
    const graphName = createGraphName("E2E Graph Delete");

    await page.getByRole("button", { name: /^new graph$/i }).click();
    await page.locator("#create-graph-name").fill(graphName);
    await page.getByRole("dialog").getByRole("button", { name: /^create$/i }).click();

    await expect(page).toHaveURL(/\/graphs\/[a-f0-9-]+/);

    await page.goto("/graphs");
    const graphCard = page.locator('[data-slot="card"]').filter({ hasText: graphName });
    await expect(graphCard).toBeVisible();

    await graphCard.getByRole("button", { name: /^delete$/i }).click();

    const alertDialog = page.getByRole("alertdialog");
    await expect(alertDialog).toBeVisible();
    await alertDialog.getByRole("button", { name: /^delete$/i }).click();

    await expect(page.getByRole("link", { name: graphName })).not.toBeVisible();
  });
});
