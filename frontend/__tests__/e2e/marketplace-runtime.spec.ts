import { expect, test, type APIRequestContext, type Page } from "@playwright/test";

import { getPlaywrightRuntimeFixtureUser, login } from "./helpers";

const runtimeFixtureUser = getPlaywrightRuntimeFixtureUser();
const API_BASE_URL = (
  process.env.PLAYWRIGHT_API_URL ??
  process.env.NEXT_PUBLIC_API_URL ??
  "http://127.0.0.1:8000"
).replace(/\/$/, "");
const packageName = process.env.PLAYWRIGHT_RUNTIME_PACKAGE_NAME ?? "Playwright Runtime Health Check";
const toolName = process.env.PLAYWRIGHT_RUNTIME_TOOL_NAME ?? "playwright_runtime_health_check";

const GRAPH_URL_PATTERN = /\/graphs\/[a-f0-9-]+/;

const createGraphName = (prefix: string) => `${prefix} ${Date.now()}-${Math.random().toString(16).slice(2)}`;

async function expectGraphEditorOpen(page: Page) {
  await expect(page).toHaveURL(GRAPH_URL_PATTERN, { timeout: 15_000 });
}

async function getAccessToken(request: APIRequestContext) {
  const response = await request.post(`${API_BASE_URL}/api/auth/login`, {
    data: {
      email: runtimeFixtureUser.email,
      password: runtimeFixtureUser.password,
    },
  });
  expect(response.ok()).toBeTruthy();
  const body = (await response.json()) as { access?: string };
  expect(body.access).toBeTruthy();
  return body.access as string;
}

async function waitForRunTerminal(request: APIRequestContext, accessToken: string, runId: string) {
  const deadline = Date.now() + 30_000;
  while (Date.now() < deadline) {
    const response = await request.get(`${API_BASE_URL}/api/runs/${runId}`, {
      headers: { Authorization: `Bearer ${accessToken}` },
    });
    expect(response.ok()).toBeTruthy();
    const body = (await response.json()) as {
      data: { status: string; error_message?: string | null };
    };
    if (["succeeded", "failed", "canceled"].includes(body.data.status)) {
      return body.data;
    }
    await new Promise((resolve) => setTimeout(resolve, 500));
  }
  throw new Error(`Timed out waiting for run ${runId} to reach a terminal state.`);
}

async function addOutputNode(page: Page) {
  await page.getByRole("button", { name: /^output/i }).click();
  const dialog = page.getByRole("dialog", { name: /configure output node/i });
  await expect(dialog).toBeVisible();
  await dialog.getByRole("button", { name: /^add node$/i }).click();
  await expect(dialog).toBeHidden();
}

test.describe("Marketplace runtime E2E", () => {
  test.describe.configure({ mode: "serial" });

  test("installs a runtime package and executes it through the real engine path", async ({ page, request }) => {
    test.setTimeout(90_000);
    const accessToken = await getAccessToken(request);

    await login(page, runtimeFixtureUser);

    await page.goto("/admin/marketplace");
    await expect(page.getByRole("heading", { name: /^marketplace$/i })).toBeVisible();

    const packageCard = page.locator("div.rounded-lg.border").filter({ hasText: packageName }).first();
    await expect(packageCard).toBeVisible();
    await packageCard.getByRole("button", { name: /install|reinstall|update/i }).click();

    await expect
      .poll(async () => {
        return page.getByText(toolName).count();
      })
      .toBeGreaterThan(0);
    await page.waitForTimeout(2500);

    const graphName = createGraphName("Marketplace Runtime");

    await page.goto("/graphs");
    await page.getByRole("button", { name: /^new graph$/i }).click();
    await page.locator("#create-graph-name").fill(graphName);
    await page
      .getByRole("dialog")
      .getByRole("button", { name: /^create$/i })
      .click();

    await expectGraphEditorOpen(page);

    const quickAddButton = page.getByRole("button", {
      name: new RegExp(`Add ${packageName} integration node`, "i"),
    });
    await expect(quickAddButton).toBeVisible();
    await quickAddButton.click();

    const toolDialog = page.getByRole("dialog", { name: /configure tool node/i });
    if (await toolDialog.isVisible().catch(() => false)) {
      await toolDialog.getByRole("button", { name: /^add node$/i }).click();
      await expect(toolDialog).toBeHidden();
    }

    const toolNode = page.locator(".react-flow__node").filter({ hasText: packageName }).first();
    await expect(toolNode).toBeVisible();
    await toolNode.click();

    await addOutputNode(page);

    const outputNode = page.locator(".react-flow__node").filter({ hasText: "Output" }).first();
    await expect(outputNode).toBeVisible();

    const saveButton = page.getByRole("button", { name: /^save$/i });
    await expect(saveButton).toBeEnabled();
    await saveButton.click();

    const versionSelect = page.getByRole("combobox", { name: /^version$/i });
    await expect(versionSelect).toBeEnabled({ timeout: 30_000 });

    const runButton = page.getByRole("button", { name: /run workflow/i });
    await expect(runButton).toBeEnabled();
    await runButton.click();

    await expect(page).toHaveURL(/\/runs\/[a-f0-9-]+$/, { timeout: 15_000 });
    const runId = page.url().match(/\/runs\/([a-f0-9-]+)$/)?.[1];
    expect(runId).toBeTruthy();

    const runData = await waitForRunTerminal(request, accessToken, runId as string);
    expect(runData.status).toBe("succeeded");

    await page.reload();
    await expect(page.getByText(graphName)).toBeVisible();
    await expect(page.getByText(/succeeded/i).first()).toBeVisible();

    const toolRunButton = page.getByRole("button", { name: new RegExp(packageName, "i") }).first();
    await expect(toolRunButton).toBeVisible();
    await toolRunButton.click();

    await expect(page.getByText(/"tool":\s*"playwright_runtime_health_check"/i).first()).toBeVisible();
    await expect(page.getByText(/"status":\s*200/i).first()).toBeVisible();
    await expect(page.getByText(/"status":\s*"ok"/i).first()).toBeVisible();
  });
});
