import {
  expect,
  type APIRequestContext,
  type Locator,
  type Page,
  type TestInfo,
} from "@playwright/test";

export type TestUser = {
  email: string;
  password: string;
};

export type AgentWorkflowOptions = {
  graphName: string;
  agentLabel?: string;
  outputLabel?: string;
  instructions: string;
  toolNames: string[];
  provider?: string;
  model?: string;
  approvalRequiredTools?: string[];
};

export type GraphVersionResponse = {
  data: {
    id: string;
    version: number;
    graph_json: {
      nodes: Array<{
        id: string;
        type: string;
        name?: string;
        config?: Record<string, unknown>;
      }>;
      edges: Array<{
        id?: string;
        from: string;
        to: string;
        label?: string | null;
        condition?: string | null;
      }>;
    };
  };
};

export type RunDetailResponse = {
  status: string;
  error_message?: string | null;
};

const TEST_PASSWORD = "ForgeGraphTest!12345";
const API_BASE_URL = (
  process.env.PLAYWRIGHT_API_URL ??
  process.env.NEXT_PUBLIC_API_URL ??
  "http://127.0.0.1:8000"
).replace(/\/$/, "");

export function createTestUser(testInfo: TestInfo, prefix = "e2e"): TestUser {
  const runId = `${Date.now()}-${Math.random().toString(16).slice(2)}`;
  const projectName = testInfo?.project?.name ?? "default";
  const project = projectName.replace(/[^a-z0-9]+/gi, "-").toLowerCase();
  const safePrefix = prefix
    .replace(/[^a-z0-9]+/gi, "-")
    .toLowerCase()
    .replace(/empty/g, "blank");
  return {
    email: `${safePrefix}-${project}-${runId}@example.com`,
    password: TEST_PASSWORD,
  };
}

export function getPlaywrightRuntimeFixtureUser(): TestUser {
  return {
    email:
      process.env.PLAYWRIGHT_RUNTIME_FIXTURE_EMAIL ??
      "playwright-runtime@example.com",
    password: process.env.PLAYWRIGHT_RUNTIME_FIXTURE_PASSWORD ?? TEST_PASSWORD,
  };
}

export async function ensureUserRegistered(
  request: APIRequestContext,
  user: TestUser,
): Promise<void> {
  const response = await request.post(`${API_BASE_URL}/api/auth/register`, {
    data: { email: user.email, password: user.password },
  });

  if (response.ok()) return;

  // If the user already exists, registration returns 400. That's fine for idempotency.
  if (response.status() === 400) return;

  const body = await response.text();
  throw new Error(
    `Failed to register test user (status ${response.status()}): ${body}`,
  );
}

export async function login(page: Page, user: TestUser): Promise<void> {
  await page.goto("/login");
  await page.locator("#email").fill(user.email);
  await page.locator("#password").fill(user.password);
  await page.getByRole("button", { name: /^sign in$/i }).click();
  await page.waitForURL(/\/graphs(?:\?.*)?$/, { timeout: 20_000 });
  await page.waitForLoadState("networkidle");
}

export async function gotoWithRetry(
  page: Page,
  url: string,
  attempts = 3,
): Promise<void> {
  let lastError: unknown;

  for (let attempt = 0; attempt < attempts; attempt += 1) {
    try {
      await page.goto(url);
      return;
    } catch (error) {
      lastError = error;
      const message = error instanceof Error ? error.message : String(error);
      if (!message.includes("interrupted by another navigation")) {
        throw error;
      }
      await page.waitForTimeout(250);
    }
  }

  throw lastError;
}

export function createGraphName(prefix: string): string {
  return `${prefix} ${Date.now()}-${Math.random().toString(16).slice(2)}`;
}

export async function getAccessToken(
  request: APIRequestContext,
  user: TestUser,
): Promise<string> {
  const response = await request.post(`${API_BASE_URL}/api/auth/login`, {
    data: {
      email: user.email,
      password: user.password,
    },
  });
  expect(response.ok()).toBeTruthy();
  const body = (await response.json()) as { access?: string };
  expect(body.access).toBeTruthy();
  return body.access as string;
}

export async function createGraph(
  page: Page,
  graphName: string,
  description?: string,
): Promise<string> {
  await page.goto("/graphs");
  await page.getByRole("button", { name: /^new graph$/i }).click();
  await page.locator("#create-graph-name").fill(graphName);
  if (description) {
    await page.locator("#create-graph-description").fill(description);
  }
  await page
    .getByRole("dialog")
    .getByRole("button", { name: /^create$/i })
    .click();
  await expectGraphEditorOpen(page);
  return getGraphIdFromUrl(page);
}

export async function expectGraphEditorOpen(page: Page): Promise<void> {
  await expect(page).toHaveURL(/\/graphs\/[a-f0-9-]+/, { timeout: 15_000 });
  await expect(page.getByTestId("graph-canvas-panel")).toBeVisible();
}

export function getGraphIdFromUrl(page: Page): string {
  const graphId = page.url().match(/\/graphs\/([a-f0-9-]+)/)?.[1];
  if (!graphId) {
    throw new Error(`Could not determine graph id from URL: ${page.url()}`);
  }
  return graphId;
}

export function getGraphNodeByLabel(page: Page, label: string): Locator {
  return page
    .getByTestId("graph-node")
    .filter({
      has: page.getByTestId("graph-node-label").filter({ hasText: label }),
    })
    .first();
}

export async function addPaletteItem(
  page: Page,
  itemId: string,
): Promise<void> {
  await page.getByTestId(`palette-item-${itemId}`).click();
}

export async function addNodeFromPalette(
  page: Page,
  itemId: string,
  dialogName: RegExp,
  confirmName: RegExp = /^add node$/i,
): Promise<void> {
  await addPaletteItem(page, itemId);
  const dialog = page.getByRole("dialog", { name: dialogName });
  await expect(dialog).toBeVisible();
  await dialog.getByRole("button", { name: confirmName }).click();
  await expect(dialog).toBeHidden();
}

export async function addOutputNode(
  page: Page,
  label = "Output",
): Promise<void> {
  await addPaletteItem(page, "output");
  const dialog = page.getByRole("dialog", { name: /configure output node/i });
  await expect(dialog).toBeVisible();
  if (label !== "Output") {
    await dialog.locator("#node-label").fill(label);
  }
  await dialog.getByRole("button", { name: /^add node$/i }).click();
  await expect(dialog).toBeHidden();
  const canvasNode = getGraphNodeByLabel(page, label);
  const inspectorName = page.getByRole("textbox", { name: /node name/i });
  const createdOnCanvas = await canvasNode.isVisible().catch(() => false);
  if (!createdOnCanvas) {
    await expect(inspectorName).toHaveValue(label);
  } else {
    await expect(canvasNode).toBeVisible();
  }
}

export async function addAgentNode(
  page: Page,
  options: AgentWorkflowOptions,
): Promise<void> {
  await addPaletteItem(page, "agent");
  const dialog = page.getByRole("dialog", { name: /configure agent node/i });
  await expect(dialog).toBeVisible();

  await dialog.locator("#node-label").fill(options.agentLabel ?? "Jackie");
  await dialog.locator("#agent-instructions").fill(options.instructions);

  if (options.provider) {
    await dialog.locator("#agent-provider").selectOption(options.provider);
  }
  if (options.model) {
    await dialog.locator("#agent-model").selectOption(options.model);
  }

  await dialog.locator("#agent-tools").fill(options.toolNames.join("\n"));

  if (options.approvalRequiredTools?.length) {
    await dialog
      .locator("#agent-approval-tools")
      .fill(options.approvalRequiredTools.join("\n"));
  }

  await dialog.getByRole("button", { name: /^add node$/i }).click();
  await expect(dialog).toBeHidden();
  await expect(
    getGraphNodeByLabel(page, options.agentLabel ?? "Jackie"),
  ).toBeVisible();
}

export async function addMemoryNode(
  page: Page,
  label = "Memory",
  options?: { key?: string },
): Promise<void> {
  await addPaletteItem(page, "memory");
  const dialog = page.getByRole("dialog", { name: /configure memory node/i });
  await expect(dialog).toBeVisible();
  if (label !== "Memory") {
    await dialog.locator("#node-label").fill(label);
  }
  await dialog
    .locator("#memory-key")
    .fill(options?.key ?? "conversation_history");
  await dialog.getByRole("button", { name: /^add node$/i }).click();
  await expect(dialog).toBeHidden();
  await expect(getGraphNodeByLabel(page, label)).toBeVisible();
}

async function getCenter(locator: Locator): Promise<{ x: number; y: number }> {
  const box = await locator.boundingBox();
  if (!box) {
    throw new Error("Could not determine element bounding box");
  }
  return { x: box.x + box.width / 2, y: box.y + box.height / 2 };
}

export async function connectGraphNodes(
  page: Page,
  sourceLabel: string,
  targetLabel: string,
  sourceHandleId = "node-handle-source-default",
  targetHandleId = "node-handle-target-default",
): Promise<void> {
  const edges = page.locator('[data-testid^="rf__edge-"]');
  const beforeCount = await edges.count();

  const sourceNode = getGraphNodeByLabel(page, sourceLabel);
  const targetNode = getGraphNodeByLabel(page, targetLabel);
  await expect(sourceNode).toBeVisible();
  await expect(targetNode).toBeVisible();

  const sourceHandle = sourceNode.getByTestId(sourceHandleId);
  const targetHandle = targetNode.getByTestId(targetHandleId);
  await expect(sourceHandle).toBeVisible();
  await expect(targetHandle).toBeVisible();

  const from = await getCenter(sourceHandle);
  const to = await getCenter(targetHandle);

  try {
    await sourceHandle.click();
    await targetHandle.click();
    await expect(edges).toHaveCount(beforeCount + 1, { timeout: 2_000 });
    return;
  } catch {
    await page.keyboard.press("Escape").catch(() => undefined);
  }

  await page.mouse.move(from.x, from.y);
  await page.mouse.down();
  await page.mouse.move(to.x, to.y, { steps: 20 });
  await page.mouse.up();

  await expect(edges).toHaveCount(beforeCount + 1);
}

export async function clearGraphSelection(page: Page): Promise<void> {
  const canvas = page.getByTestId("graph-canvas-panel");
  await expect(canvas).toBeVisible();
  const box = await canvas.boundingBox();
  if (!box) {
    throw new Error("Could not determine graph canvas bounds");
  }
  await page.mouse.click(box.x + 24, box.y + 24);
}

export async function saveGraph(page: Page): Promise<void> {
  const saveButton = page.getByRole("button", { name: /^save$/i });
  await expect(saveButton).toBeEnabled();
  await saveButton.click();
  const versionSelect = page.getByRole("combobox", { name: /^version$/i });
  await expect(versionSelect).toBeEnabled({ timeout: 30_000 });
}

export async function fetchLatestGraphVersion(
  request: APIRequestContext,
  accessToken: string,
  graphId: string,
): Promise<GraphVersionResponse["data"]> {
  const response = await request.get(
    `${API_BASE_URL}/api/graphs/${graphId}/versions/latest`,
    {
      headers: { Authorization: `Bearer ${accessToken}` },
    },
  );
  expect(response.ok()).toBeTruthy();
  const body = (await response.json()) as GraphVersionResponse;
  return body.data;
}

export async function installRuntimePackage(
  page: Page,
  packageName: string,
  toolName?: string,
): Promise<void> {
  await page.goto("/admin/marketplace");
  await expect(
    page.getByRole("heading", { name: /^marketplace$/i }),
  ).toBeVisible();

  const packageCard = page
    .locator("div.rounded-lg.border")
    .filter({ hasText: packageName })
    .first();
  await expect(packageCard).toBeVisible();
  await packageCard
    .getByRole("button", { name: /install|reinstall|update/i })
    .click();

  if (toolName) {
    await expect
      .poll(async () => page.getByText(toolName).count())
      .toBeGreaterThan(0);
  }
}

export async function addMarketplaceToolNode(
  page: Page,
  packageSlug: string,
  nodeLabel: string,
): Promise<void> {
  await addPaletteItem(page, `marketplace:${packageSlug}`);
  const dialog = page.getByRole("dialog", { name: /configure tool node/i });
  await expect(dialog).toBeVisible();
  if (nodeLabel !== "Tool") {
    await dialog.locator("#node-label").fill(nodeLabel);
  }
  await dialog.getByRole("button", { name: /^add node$/i }).click();
  await expect(dialog).toBeHidden();
  await expect(getGraphNodeByLabel(page, nodeLabel)).toBeVisible();
}

export async function startRunFromEditor(page: Page): Promise<string> {
  const runButton = page.getByRole("button", { name: /run workflow/i });
  await expect(runButton).toBeEnabled();
  await runButton.click();
  await expect(page).toHaveURL(/\/runs\/[a-f0-9-]+$/, { timeout: 15_000 });
  const runId = page.url().match(/\/runs\/([a-f0-9-]+)$/)?.[1];
  if (!runId) {
    throw new Error(`Could not determine run id from URL: ${page.url()}`);
  }
  return runId;
}

export async function waitForRunTerminal(
  request: APIRequestContext,
  accessToken: string,
  runId: string,
): Promise<RunDetailResponse> {
  const deadline = Date.now() + 30_000;
  while (Date.now() < deadline) {
    const response = await request.get(`${API_BASE_URL}/api/runs/${runId}`, {
      headers: { Authorization: `Bearer ${accessToken}` },
    });
    expect(response.ok()).toBeTruthy();
    const body = (await response.json()) as { data: RunDetailResponse };
    if (["succeeded", "failed", "canceled"].includes(body.data.status)) {
      return body.data;
    }
    await new Promise((resolve) => setTimeout(resolve, 500));
  }
  throw new Error(
    `Timed out waiting for run ${runId} to reach a terminal state.`,
  );
}

export async function authorAgentWorkflow(
  page: Page,
  options: AgentWorkflowOptions,
): Promise<{ graphId: string; agentLabel: string; outputLabel: string }> {
  const agentLabel = options.agentLabel ?? "Jackie";
  const outputLabel = options.outputLabel ?? "Output";
  const graphId = await createGraph(page, options.graphName);

  await addAgentNode(page, options);
  await clearGraphSelection(page);
  await addOutputNode(page, outputLabel);
  await connectGraphNodes(page, agentLabel, outputLabel);
  await saveGraph(page);

  return { graphId, agentLabel, outputLabel };
}
