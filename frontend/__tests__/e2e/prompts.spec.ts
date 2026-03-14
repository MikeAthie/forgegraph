import { test, expect, type Page } from "@playwright/test";
import { createTestUser, ensureUserRegistered, login, type TestUser } from "./helpers";

let primaryUser: TestUser;
let secondaryUser: TestUser;

const createPromptTitle = (prefix: string) => `${prefix} ${Date.now()}-${Math.random().toString(16).slice(2)}`;
const escapeRegExp = (value: string) => value.replace(/[.*+?^${}()|[\]\\]/g, "\\$&");

async function openPromptDetail(page: Page, title: string) {
  const exactTitle = new RegExp(`^${escapeRegExp(title)}$`, "i");
  const card = page
    .locator('[data-slot="card"]')
    .filter({ has: page.locator('[data-slot="card-title"]', { hasText: exactTitle }) })
    .first();
  await expect(card).toBeVisible();
  await card.getByRole("button", { name: /^view$/i }).click();
  await expect(page.getByRole("dialog")).toBeVisible();
}

async function logout(page: Page, email: string) {
  await page.getByRole("button", { name: new RegExp(email, "i") }).click();
  await page.getByRole("menuitem", { name: /sign out/i }).dispatchEvent("click");
  await page.waitForURL("/login");
}

test.beforeAll(async ({ request }, testInfo) => {
  primaryUser = createTestUser(testInfo, "e2e-prompts");
  secondaryUser = createTestUser(testInfo, "e2e-prompts-alt");
  await ensureUserRegistered(request, primaryUser);
  await ensureUserRegistered(request, secondaryUser);
});

test.describe("Prompts", () => {
  test.beforeEach(async ({ page }) => {
    await login(page, primaryUser);
    await page.getByRole("link", { name: /^prompts$/i }).click();
    await expect(page).toHaveURL("/prompts");
  });

  test("shows the prompts page", async ({ page }) => {
    await expect(page.getByRole("heading", { name: /^prompts$/i })).toBeVisible();
    await expect(page.getByRole("button", { name: /^new prompt$/i })).toBeVisible();
    await expect(page.getByRole("button", { name: /^my prompts$/i })).toBeVisible();
  });

  test("validates create prompt requires title", async ({ page }) => {
    await page.getByRole("button", { name: /^new prompt$/i }).click();

    const dialog = page.getByRole("dialog");
    await expect(dialog).toBeVisible();

    await dialog.getByRole("button", { name: /^create$/i }).click();
    await expect(dialog.getByText(/title is required/i)).toBeVisible();
  });

  test("creates a prompt and lists it", async ({ page }) => {
    const title = createPromptTitle("E2E Prompt");

    await page.getByRole("button", { name: /^new prompt$/i }).click();
    const dialog = page.getByRole("dialog");
    await expect(dialog).toBeVisible();

    await page.locator("#create-prompt-title").fill(title);
    await page.locator("#create-prompt-description").fill("Created by Playwright.");
    await page.locator("#create-prompt-content").fill("You are a helpful assistant.");
    await dialog.getByRole("button", { name: /^create$/i }).click();

    await expect(page.locator('[data-slot="card"]').filter({ hasText: title })).toBeVisible();
  });

  test("edits, publishes, and deletes a prompt", async ({ page }) => {
    const title = createPromptTitle("E2E Prompt Manage");

    await page.getByRole("button", { name: /^new prompt$/i }).click();
    await page.locator("#create-prompt-title").fill(title);
    await page.locator("#create-prompt-content").fill("Initial content.");
    await page
      .getByRole("dialog")
      .getByRole("button", { name: /^create$/i })
      .click();

    await expect(page.locator('[data-slot="card"]').filter({ hasText: title })).toBeVisible();

    await openPromptDetail(page, title);
    const dialog = page.getByRole("dialog");

    await dialog.getByRole("button", { name: /^edit$/i }).click();
    await expect(page.locator("#edit-prompt-title")).toBeVisible();

    const updatedTitle = createPromptTitle("E2E Prompt Updated");
    await page.locator("#edit-prompt-title").fill(updatedTitle);
    await page.locator("#edit-prompt-content").fill("Updated content.");
    await dialog.getByRole("button", { name: /^save$/i }).click();

    await expect(dialog.locator('[data-slot="dialog-title"]')).toHaveText(updatedTitle);

    await dialog.getByRole("button", { name: /^publish$/i }).click();
    await expect(dialog.getByText(/^public$/i)).toBeVisible();

    await dialog.getByRole("button", { name: /^delete$/i }).click();
    const alertDialog = page.getByRole("alertdialog");
    await expect(alertDialog).toBeVisible();
    await alertDialog.getByRole("button", { name: /^delete$/i }).click();

    await expect(page.locator('[data-slot="card"]').filter({ hasText: updatedTitle })).not.toBeVisible();
  });

  test("clones a public prompt from another user", async ({ page }) => {
    const title = createPromptTitle("E2E Prompt Clone Source");

    await page.getByRole("button", { name: /^new prompt$/i }).click();
    await page.locator("#create-prompt-title").fill(title);
    await page.locator("#create-prompt-content").fill("Clone me.");
    await page
      .getByRole("dialog")
      .getByRole("button", { name: /^create$/i })
      .click();

    await openPromptDetail(page, title);
    const dialog = page.getByRole("dialog");
    await dialog.getByRole("button", { name: /^publish$/i }).click();
    await expect(dialog.getByText(/^public$/i)).toBeVisible();
    await dialog
      .locator('[data-slot="dialog-footer"]')
      .getByRole("button", { name: /^close$/i })
      .click();

    await logout(page, primaryUser.email);

    await login(page, secondaryUser);
    await page.getByRole("link", { name: /^prompts$/i }).click();
    await expect(page).toHaveURL("/prompts");

    await openPromptDetail(page, title);
    const cloneDialog = page.getByRole("dialog");
    await expect(cloneDialog.getByRole("button", { name: /^clone$/i })).toBeVisible();
    await cloneDialog.getByRole("button", { name: /^clone$/i }).click();

    await expect(cloneDialog.locator('[data-slot="dialog-title"]')).toContainText("(Copy)");
    await expect(cloneDialog.getByRole("button", { name: /^edit$/i })).toBeVisible();
    const clonedTitle = (await cloneDialog.locator('[data-slot="dialog-title"]').innerText()).trim();
    await cloneDialog
      .locator('[data-slot="dialog-footer"]')
      .getByRole("button", { name: /^close$/i })
      .click();
    await expect(cloneDialog).toBeHidden();

    await page.getByRole("button", { name: /^my prompts$/i }).click();
    const exactClonedTitle = new RegExp(`^${escapeRegExp(clonedTitle)}$`, "i");
    await expect(
      page
        .locator('[data-slot="card"]')
        .filter({ has: page.locator('[data-slot="card-title"]', { hasText: exactClonedTitle }) }),
    ).toHaveCount(1);
  });
});
