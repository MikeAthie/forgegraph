import { execFileSync } from "child_process";
import path from "path";

import { expect, type APIRequestContext, type Locator, type Page, type TestInfo } from "@playwright/test";
import {
  buildCompanyGraphJson,
  buildCompanyProfile,
  type CompanyAIAccessMode,
  type CompanyAutonomyMode,
} from "../../lib/company-workspace";

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
  observationContextPaths?: string[];
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

export type CompanyOperatingModelVersionResponse = {
  data: {
    id: string;
    company_id: string;
    workflow_definition_id: string;
    version: number;
    model_json: GraphVersionResponse["data"]["graph_json"];
    checksum: string;
    created_at: string;
  };
};

export type RunDetailResponse = {
  status: string;
  error_message?: string | null;
  recovery_state?: string | null;
  timeline?: Array<{
    event_type: string;
    status?: string | null;
    message?: string | null;
    details?: Record<string, unknown> | null;
  }> | null;
};

export type MemoryObservationSeed = {
  type: string;
  content: string;
  scope: "graph" | "run" | "session";
  title?: string;
  graph_id?: string;
  run_id?: string;
  session_id?: string;
  topic_key?: string;
  dedupe?: boolean;
  update_topic?: boolean;
};

export type FrontendControlPlaneFixture = {
  organizationId: string;
  agentIds: {
    ops: string;
    finance: string;
  };
  runIds: {
    paused: string;
    running: string;
    failed: string;
  };
  approval: {
    id: string;
    runId: string;
    nodeId: string;
    nodeName: string;
    graphName: string;
    promptMessage: string;
    createdAt: string;
  };
};

export type CompanySeedOptions = {
  name: string;
  companyType?: string;
  objective: string;
  autonomyMode?: CompanyAutonomyMode;
  aiAccessMode?: CompanyAIAccessMode;
  operationBrief?: string;
};

export type CompanySeedResult = {
  companyId: string;
  versionId: string;
};

export type HumanGateRunSeedResult = {
  companyId: string;
  versionId: string;
  runId: string;
};

const TEST_PASSWORD = "ForgeGraphTest!12345";
const API_BASE_URL = (
  process.env.PLAYWRIGHT_API_URL ??
  process.env.NEXT_PUBLIC_API_URL ??
  "http://127.0.0.1:8000"
).replace(/\/$/, "");
const backendDir = path.join(__dirname, "..", "..", "..", "backend");
const managementEnv = {
  ...process.env,
  USE_SQLITE: process.env.USE_SQLITE ?? "false",
  SQLITE_DB_PATH: process.env.SQLITE_DB_PATH,
};

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
    email: process.env.PLAYWRIGHT_RUNTIME_FIXTURE_EMAIL ?? "playwright-runtime@example.com",
    password: process.env.PLAYWRIGHT_RUNTIME_FIXTURE_PASSWORD ?? TEST_PASSWORD,
  };
}

async function installAuthRouteMocks(
  page: Page,
  user: TestUser,
  accessToken: string,
  options?: {
    organizationId?: string | null;
    role?: "owner" | "admin" | "member" | "viewer";
    userId?: string;
  },
): Promise<void> {
  const createdAt = new Date().toISOString();
  await Promise.all([
    page.route("**/api/auth/me", (route) =>
      route.fulfill({
        status: 200,
        contentType: "application/json",
        body: JSON.stringify({
          id: options?.userId ?? "00000000-0000-0000-0000-00000000e2e1",
          email: user.email,
          created_at: createdAt,
          is_active: true,
          default_organization_id: options?.organizationId ?? null,
          organization_role: options?.role ?? "owner",
        }),
      }),
    ),
    page.route("**/api/auth/refresh", (route) =>
      route.fulfill({
        status: 200,
        contentType: "application/json",
        body: JSON.stringify({ access: accessToken }),
      }),
    ),
    page.addInitScript((token) => {
      window.sessionStorage.setItem("__FORGEGRAPH_E2E_ACCESS_TOKEN__", token);
      (window as Window & { __FORGEGRAPH_E2E_ACCESS_TOKEN__?: string }).__FORGEGRAPH_E2E_ACCESS_TOKEN__ = token;
    }, accessToken),
  ]);
}

async function gotoAndWaitForNetworkIdle(page: Page, targetPath: string): Promise<void> {
  await page.goto(targetPath);
  await page.waitForLoadState("networkidle");
}

async function runOrderedSteps(steps: Array<() => Promise<unknown>>): Promise<void> {
  await steps.reduce<Promise<unknown>>((chain, step) => chain.then(() => step()), Promise.resolve());
}

export async function ensureUserRegistered(request: APIRequestContext, user: TestUser): Promise<void> {
  const response = await request.post(`${API_BASE_URL}/api/auth/register`, {
    data: { email: user.email, password: user.password },
  });

  if (response.ok()) return;

  // If the user already exists, registration returns 400. That's fine for idempotency.
  if (response.status() === 400) return;

  const body = await response.text();
  throw new Error(`Failed to register test user via ${API_BASE_URL} (status ${response.status()}): ${body}`);
}

export async function login(page: Page, user: TestUser): Promise<void> {
  await page.context().clearCookies();

  const response = await page.context().request.post(`${API_BASE_URL}/api/auth/login`, {
    data: {
      email: user.email,
      password: user.password,
    },
  });

  if (!response.ok()) {
    const body = await response.text();
    throw new Error(`Failed to bootstrap authenticated session (status ${response.status()}): ${body}`);
  }

  const body = (await response.json()) as { access?: string };
  if (!body.access) {
    throw new Error("Login response did not include an access token.");
  }

  await installAuthRouteMocks(page, user, body.access);
  await runOrderedSteps([
    () => page.goto("/companies"),
    () => page.waitForURL(/\/companies(?:\?.*)?$/, { timeout: 20_000 }),
    () => page.waitForLoadState("networkidle"),
  ]);
}

export async function loginLive(
  page: Page,
  request: APIRequestContext,
  user: TestUser,
  targetPath = "/companies",
): Promise<string> {
  await Promise.all([page.context().clearCookies(), ensureUserRegistered(request, user)]);

  const loginResponsePromise = page.waitForResponse(
    (response) => response.url().includes("/api/auth/login") && response.request().method() === "POST",
    { timeout: 30_000 },
  );
  await runOrderedSteps([
    () => page.goto("/login"),
    () => page.getByRole("textbox", { name: /email address/i }).fill(user.email),
    () => page.getByRole("textbox", { name: /password/i }).fill(user.password),
    () => page.getByRole("button", { name: /^sign in$/i }).click(),
  ]);
  const loginResponse = await loginResponsePromise;
  if (!loginResponse.ok()) {
    throw new Error(
      `Live login failed (status ${loginResponse.status()}) via ${loginResponse.url()}: ${await loginResponse.text()}`,
    );
  }
  await runOrderedSteps([
    () => page.waitForURL(/\/companies(?:\?.*)?$/, { timeout: 30_000 }),
    () => page.waitForLoadState("networkidle"),
  ]);

  const token = await page.evaluate(() => window.sessionStorage.getItem("__FORGEGRAPH_E2E_ACCESS_TOKEN__"));
  if (!token) {
    throw new Error("Live login did not produce a browser access token.");
  }

  if (targetPath !== "/companies") {
    await page.goto(targetPath);
  }
  await page.waitForLoadState("networkidle");
  return token;
}

export async function openAuthenticatedPage(
  page: Page,
  user: TestUser,
  targetPath: string,
  options?: {
    organizationId?: string;
    role?: "owner" | "admin" | "member" | "viewer";
  },
): Promise<void> {
  await page.context().clearCookies();
  const e2eAccessToken = `e2e-${Date.now()}-${Math.random().toString(16).slice(2)}`;

  await installAuthRouteMocks(page, user, e2eAccessToken, {
    organizationId: options?.organizationId ?? null,
    role: options?.role ?? "owner",
    userId: "00000000-0000-0000-0000-00000000e2e9",
  });
  await gotoAndWaitForNetworkIdle(page, targetPath);
}

export async function openBackendAuthenticatedPage(
  page: Page,
  request: APIRequestContext,
  user: TestUser,
  targetPath: string,
): Promise<void> {
  await Promise.all([page.context().clearCookies(), ensureUserRegistered(request, user)])
    .then(() => getAccessToken(request, user))
    .then((token) =>
      installAuthRouteMocks(page, user, token, { userId: "00000000-0000-0000-0000-00000000e2eb" }).then(() =>
        gotoAndWaitForNetworkIdle(page, targetPath),
      ),
    );
}

export async function proxyBackendApi(
  page: Page,
  request: APIRequestContext,
  user: TestUser,
  patterns: RegExp[],
): Promise<void> {
  const token = await getAccessToken(request, user);

  await Promise.all(
    patterns.map((pattern) =>
      page.route(pattern, async (route) => {
        const requestUrl = new URL(route.request().url());
        const backendUrl = `${API_BASE_URL}${requestUrl.pathname}${requestUrl.search}`;
        const response = await request.fetch(backendUrl, {
          method: route.request().method(),
          headers: {
            ...route.request().headers(),
            Authorization: `Bearer ${token}`,
          },
          data: route.request().postDataBuffer() ?? route.request().postData() ?? undefined,
          failOnStatusCode: false,
        });

        await route.fulfill({
          status: response.status(),
          headers: response.headers(),
          body: await response.body(),
        });
      }),
    ),
  );
}

export async function gotoWithRetry(page: Page, url: string, attempts = 3, attempt = 0): Promise<void> {
  try {
    await page.goto(url);
  } catch (error) {
    const message = error instanceof Error ? error.message : String(error);
    if (message.split("interrupted by another navigation").length === 1 || attempt >= attempts - 1) {
      throw error;
    }
    await page.waitForLoadState("domcontentloaded").catch(() => undefined);
    await gotoWithRetry(page, url, attempts, attempt + 1);
  }
}

export function createGraphName(prefix: string): string {
  return `${prefix} ${Date.now()}-${Math.random().toString(16).slice(2)}`;
}

export async function getAccessToken(request: APIRequestContext, user: TestUser, attempt = 0): Promise<string> {
  const response = await request.post(`${API_BASE_URL}/api/auth/login`, {
    data: {
      email: user.email,
      password: user.password,
    },
  });

  if (response.ok()) {
    const body = (await response.json()) as { access?: string };
    expect(body.access).toBeTruthy();
    return body.access as string;
  }

  const body = await response.text();
  if (response.status() !== 429 || attempt >= 4) {
    throw new Error(`Failed to login test user (status ${response.status()}): ${body}`);
  }

  const retryAfterSeconds = Number(response.headers()["retry-after"] ?? "2");
  const delayMs = Math.max(500, Math.min(5000, retryAfterSeconds * 1000 || 2000));
  await new Promise((resolve) => setTimeout(resolve, delayMs));
  return getAccessToken(request, user, attempt + 1);
}

export async function createCompanyViaApi(
  request: APIRequestContext,
  accessToken: string,
  options: CompanySeedOptions,
): Promise<CompanySeedResult> {
  const profile = buildCompanyProfile({
    companyName: options.name,
    companyType: options.companyType ?? "General Company",
    objective: options.objective,
    autonomyMode: options.autonomyMode ?? "assisted",
    aiAccessMode: options.aiAccessMode ?? "managed",
  });

  const graphResponse = await request.post(`${API_BASE_URL}/api/graphs/`, {
    headers: { Authorization: `Bearer ${accessToken}` },
    data: {
      name: profile.companyName,
      description: profile.objective,
    },
  });
  expect(graphResponse.ok()).toBeTruthy();
  const graphBody = (await graphResponse.json()) as { data: { id: string } };
  const companyId = graphBody.data.id;

  const versionResponse = await request.post(`${API_BASE_URL}/api/graphs/${companyId}/versions`, {
    headers: { Authorization: `Bearer ${accessToken}` },
    data: {
      graph_json: buildCompanyGraphJson(profile),
    },
  });
  expect(versionResponse.ok()).toBeTruthy();
  const versionBody = (await versionResponse.json()) as { data: { id: string } };

  return {
    companyId,
    versionId: versionBody.data.id,
  };
}

export async function createCompanyViaCompanyApi(
  request: APIRequestContext,
  accessToken: string,
  options: CompanySeedOptions,
): Promise<CompanySeedResult> {
  const profile = buildCompanyProfile({
    companyName: options.name,
    companyType: options.companyType ?? "General Company",
    objective: options.objective,
    autonomyMode: options.autonomyMode ?? "assisted",
    aiAccessMode: options.aiAccessMode ?? "managed",
  });

  const companyResponse = await request.post(`${API_BASE_URL}/api/companies/`, {
    headers: { Authorization: `Bearer ${accessToken}` },
    data: {
      name: profile.companyName,
      description: profile.objective,
    },
  });
  expect(companyResponse.ok()).toBeTruthy();
  const companyBody = (await companyResponse.json()) as { data: { company_id: string; id: string } };
  const companyId = companyBody.data.company_id ?? companyBody.data.id;

  const versionResponse = await request.post(`${API_BASE_URL}/api/companies/${companyId}/operating-model-versions`, {
    headers: { Authorization: `Bearer ${accessToken}` },
    data: {
      model_json: buildCompanyGraphJson(profile),
    },
  });
  expect(versionResponse.ok()).toBeTruthy();
  const versionBody = (await versionResponse.json()) as CompanyOperatingModelVersionResponse;

  return {
    companyId,
    versionId: versionBody.data.id,
  };
}

export async function fetchLatestCompanyOperatingModelVersion(
  request: APIRequestContext,
  accessToken: string,
  companyId: string,
): Promise<GraphVersionResponse["data"]> {
  const response = await request.get(`${API_BASE_URL}/api/companies/${companyId}/operating-model-versions/latest`, {
    headers: { Authorization: `Bearer ${accessToken}` },
  });
  expect(response.ok()).toBeTruthy();
  const body = (await response.json()) as CompanyOperatingModelVersionResponse;
  return {
    id: body.data.id,
    version: body.data.version,
    graph_json: body.data.model_json,
  };
}

export async function createHumanGateRunViaApi(
  request: APIRequestContext,
  accessToken: string,
  options: {
    graphName: string;
    promptMessage: string;
    instructions?: string;
  },
): Promise<HumanGateRunSeedResult> {
  const graphResponse = await request.post(`${API_BASE_URL}/api/graphs/`, {
    headers: { Authorization: `Bearer ${accessToken}` },
    data: {
      name: options.graphName,
      description: "Live HITL approval/resume production gate harness.",
    },
  });
  expect(graphResponse.ok()).toBeTruthy();
  const graphBody = (await graphResponse.json()) as { data: { id: string } };
  const companyId = graphBody.data.id;

  const graphJson = {
    nodes: [
      {
        id: "finance_approval",
        type: "human_gate",
        name: "Finance approval",
        config: {
          prompt_message: options.promptMessage,
          approval_message: options.promptMessage,
          instructions: options.instructions ?? "",
          required_fields: [],
        },
      },
      {
        id: "final_output",
        type: "output",
        name: "Final Output",
        config: {
          output_mapping: {
            decision: "node.finance_approval.output",
            request: "input.request",
          },
        },
      },
    ],
    edges: [
      { id: "start-finance-approval", from: "START", to: "finance_approval" },
      { id: "finance-approval-final-output", from: "finance_approval", to: "final_output" },
      { id: "final-output-end", from: "final_output", to: "END" },
    ],
    metadata: {
      name: options.graphName,
      description: "Live HITL approval/resume production gate harness.",
      engine_contract_version: "2",
    },
    editor_state: {
      viewport: { x: 0, y: 0, zoom: 1 },
      nodePositions: {
        finance_approval: { x: 160, y: 120 },
        final_output: { x: 520, y: 120 },
      },
    },
  };

  const versionResponse = await request.post(`${API_BASE_URL}/api/graphs/${companyId}/versions`, {
    headers: { Authorization: `Bearer ${accessToken}` },
    data: {
      graph_json: graphJson,
    },
  });
  expect(versionResponse.ok()).toBeTruthy();
  const versionBody = (await versionResponse.json()) as { data: { id: string } };
  const versionId = versionBody.data.id;

  const startResponse = await request.post(`${API_BASE_URL}/api/runs/start`, {
    headers: { Authorization: `Bearer ${accessToken}` },
    data: {
      graph_version_id: versionId,
      input_json: {
        request: "Review and approve a controlled outbound refund test.",
      },
    },
  });
  expect(startResponse.ok()).toBeTruthy();
  const startBody = (await startResponse.json()) as { data: { id: string } };

  return {
    companyId,
    versionId,
    runId: startBody.data.id,
  };
}

export function seedFrontendControlPlaneFixture(user: TestUser): FrontendControlPlaneFixture {
  const raw = execFileSync(
    "python",
    ["manage.py", "seed_frontend_control_plane_fixture", "--email", user.email, "--password", user.password, "--json"],
    {
      cwd: backendDir,
      env: managementEnv,
      encoding: "utf8",
    },
  ).trim();

  return JSON.parse(raw) as FrontendControlPlaneFixture;
}

export async function createGraph(page: Page, graphName: string, description?: string): Promise<string> {
  await runOrderedSteps([
    () => gotoWithRetry(page, "/graphs"),
    () => page.getByRole("button", { name: /^new operating model$/i }).click(),
    () => page.locator("#create-graph-name").fill(graphName),
    () => (description ? page.locator("#create-graph-description").fill(description) : Promise.resolve()),
    () =>
      page
        .getByRole("dialog")
        .getByRole("button", { name: /^create$/i })
        .click(),
  ]);
  await expectGraphEditorOpen(page);
  return getGraphIdFromUrl(page);
}

export async function expectGraphEditorOpen(page: Page): Promise<void> {
  await expect(page).toHaveURL(/\/(?:graphs|workflows)\/[a-f0-9-]+/, { timeout: 15_000 });
  await expect(page.getByTestId("graph-canvas-panel")).toBeVisible();
}

export function getGraphIdFromUrl(page: Page): string {
  const graphId = page.url().match(/\/(?:graphs|workflows)\/([a-f0-9-]+)/)?.[1];
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

export async function addPaletteItem(page: Page, itemId: string): Promise<void> {
  await page.getByTestId(`palette-item-${itemId}`).click();
}

export async function addNodeFromPalette(
  page: Page,
  itemId: string,
  dialogName: RegExp,
  confirmName: RegExp = /^add node$/i,
): Promise<void> {
  const dialog = page.getByRole("dialog", { name: dialogName });
  await runOrderedSteps([
    () => addPaletteItem(page, itemId),
    () => expect(dialog).toBeVisible(),
    () => dialog.getByRole("button", { name: confirmName }).click(),
    () => expect(dialog).toBeHidden(),
  ]);
}

export async function addOutputNode(page: Page, label = "Output"): Promise<void> {
  const dialog = page.getByRole("dialog", { name: /configure output node/i });
  await runOrderedSteps([
    () => addPaletteItem(page, "output"),
    () => expect(dialog).toBeVisible(),
    () => (label !== "Output" ? dialog.locator("#node-label").fill(label) : Promise.resolve()),
    () => dialog.getByRole("button", { name: /^add node$/i }).click(),
    () => expect(dialog).toBeHidden(),
    () => fitGraphView(page),
  ]);
  const canvasNode = getGraphNodeByLabel(page, label);
  const inspectorName = page.getByRole("textbox", { name: /node name/i });
  const createdOnCanvas = await canvasNode.isVisible().catch(() => false);
  if (!createdOnCanvas) {
    await expect(inspectorName).toHaveValue(label);
  } else {
    await expect(canvasNode).toBeVisible();
  }
}

export async function addHumanGateNode(
  page: Page,
  options?: {
    label?: string;
    promptMessage?: string;
    instructions?: string;
  },
): Promise<void> {
  const label = options?.label ?? "Human Gate";
  const dialog = page.getByRole("dialog", { name: /configure human gate node/i });
  await runOrderedSteps([
    () => addPaletteItem(page, "human_gate"),
    () => expect(dialog).toBeVisible(),
    () => (label !== "Human Gate" ? dialog.locator("#node-label").fill(label) : Promise.resolve()),
    () => (options?.instructions ? dialog.locator("#instructions").fill(options.instructions) : Promise.resolve()),
    () => dialog.getByRole("button", { name: /^add node$/i }).click(),
    () => expect(dialog).toBeHidden(),
  ]);

  const node = getGraphNodeByLabel(page, label);

  const promptField = page.getByPlaceholder("Please review and approve this step...");
  await runOrderedSteps([
    () => expect(node).toBeVisible(),
    () => node.click(),
    () => expect(promptField).toBeVisible(),
    () => promptField.fill(options?.promptMessage ?? "Approve this execution step before it continues."),
  ]);
}

export async function addAgentNode(page: Page, options: AgentWorkflowOptions): Promise<void> {
  const dialog = page.getByRole("dialog", { name: /configure agent node/i });
  await runOrderedSteps([
    () => addPaletteItem(page, "agent"),
    () => expect(dialog).toBeVisible(),
    () => dialog.locator("#node-label").fill(options.agentLabel ?? "Jackie"),
    () => dialog.locator("#agent-instructions").fill(options.instructions),
    () => (options.provider ? dialog.locator("#agent-provider").selectOption(options.provider) : Promise.resolve()),
    () => (options.model ? dialog.locator("#agent-model").selectOption(options.model) : Promise.resolve()),
    () => dialog.locator("#agent-tools").fill(options.toolNames.join("\n")),
    () =>
      options.observationContextPaths?.length
        ? dialog.locator("#agent-observation-context-paths").fill(options.observationContextPaths.join("\n"))
        : Promise.resolve(),
    () =>
      options.approvalRequiredTools?.length
        ? dialog.locator("#agent-approval-tools").fill(options.approvalRequiredTools.join("\n"))
        : Promise.resolve(),
    () => dialog.getByRole("button", { name: /^add node$/i }).click(),
    () => expect(dialog).toBeHidden(),
    () => expect(getGraphNodeByLabel(page, options.agentLabel ?? "Jackie")).toBeVisible(),
  ]);
}

export async function addObservationContextNode(
  page: Page,
  label = "Observation Context",
  options?: {
    query?: string;
    limit?: number;
  },
): Promise<void> {
  const dialog = page.getByRole("dialog", {
    name: /configure observation context node/i,
  });
  await runOrderedSteps([
    () => addPaletteItem(page, "observation_context"),
    () => expect(dialog).toBeVisible(),
    () => (label !== "Observation Context" ? dialog.locator("#node-label").fill(label) : Promise.resolve()),
    () => (options?.query ? dialog.locator("#query-value").fill(options.query) : Promise.resolve()),
    () =>
      options?.limit ? dialog.locator("#observation-context-limit").fill(String(options.limit)) : Promise.resolve(),
    () => dialog.getByRole("button", { name: /^add node$/i }).click(),
    () => expect(dialog).toBeHidden(),
    () => expect(getGraphNodeByLabel(page, label)).toBeVisible(),
  ]);
}

export async function addObservationSaveNode(
  page: Page,
  label = "Observation Save",
  options?: {
    type?: string;
    scope?: "graph" | "run" | "session";
    content?: string;
    title?: string;
    topicKey?: string;
  },
): Promise<void> {
  const dialog = page.getByRole("dialog", {
    name: /configure observation save node/i,
  });
  await runOrderedSteps([
    () => addPaletteItem(page, "observation_save"),
    () => expect(dialog).toBeVisible(),
    () => (label !== "Observation Save" ? dialog.locator("#node-label").fill(label) : Promise.resolve()),
    () => dialog.locator("#observation-type").fill(options?.type ?? "customer_memory"),
    () => dialog.locator("#observation-scope").selectOption(options?.scope ?? "graph"),
    () => dialog.locator("#content-value").fill(options?.content ?? "Jackie prefers concise planning updates."),
    () => (options?.title ? dialog.locator("#title-value").fill(options.title) : Promise.resolve()),
    () => (options?.topicKey ? dialog.locator("#topic_key-value").fill(options.topicKey) : Promise.resolve()),
    () => dialog.getByRole("button", { name: /^add node$/i }).click(),
    () => expect(dialog).toBeHidden(),
    () => fitGraphView(page),
  ]);
  const canvasNode = getGraphNodeByLabel(page, label);
  const inspectorName = page.getByRole("textbox", { name: /node name/i });
  const createdOnCanvas = await canvasNode.isVisible().catch(() => false);
  if (!createdOnCanvas) {
    await expect(inspectorName).toHaveValue(label);
    return;
  }
  await expect(canvasNode).toBeVisible();
}

export async function addMemoryNode(page: Page, label = "Memory", options?: { key?: string }): Promise<void> {
  const dialog = page.getByRole("dialog", { name: /configure memory node/i });
  await runOrderedSteps([
    () => addPaletteItem(page, "memory"),
    () => expect(dialog).toBeVisible(),
    () => (label !== "Memory" ? dialog.locator("#node-label").fill(label) : Promise.resolve()),
    () => dialog.locator("#memory-key").fill(options?.key ?? "conversation_history"),
    () => dialog.getByRole("button", { name: /^add node$/i }).click(),
    () => expect(dialog).toBeHidden(),
    () => expect(getGraphNodeByLabel(page, label)).toBeVisible(),
  ]);
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
  await Promise.all([expect(sourceNode).toBeVisible(), expect(targetNode).toBeVisible()]);

  const sourceHandle = sourceNode.getByTestId(sourceHandleId);
  const targetHandle = targetNode.getByTestId(targetHandleId);
  await Promise.all([expect(sourceHandle).toBeVisible(), expect(targetHandle).toBeVisible()]);

  const [from, to] = await Promise.all([getCenter(sourceHandle), getCenter(targetHandle)]);

  try {
    await runOrderedSteps([
      () => sourceHandle.click(),
      () => targetHandle.click(),
      () => expect(edges).toHaveCount(beforeCount + 1, { timeout: 2_000 }),
    ]);
    return;
  } catch {
    await page.keyboard.press("Escape").catch(() => undefined);
  }

  await runOrderedSteps([
    () => page.mouse.move(from.x, from.y),
    () => page.mouse.down(),
    () => page.mouse.move(to.x, to.y, { steps: 20 }),
    () => page.mouse.up(),
  ]);

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

export async function fitGraphView(page: Page): Promise<void> {
  const fitViewButton = page.getByRole("button", { name: /^fit view$/i });
  await expect(fitViewButton).toBeVisible();
  await fitViewButton.click();
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
  const response = await request.get(`${API_BASE_URL}/api/graphs/${graphId}/versions/latest`, {
    headers: { Authorization: `Bearer ${accessToken}` },
  });
  expect(response.ok()).toBeTruthy();
  const body = (await response.json()) as GraphVersionResponse;
  return body.data;
}

export async function installRuntimePackage(page: Page, packageName: string, toolName?: string): Promise<void> {
  await gotoWithRetry(page, "/admin/marketplace");
  await expect(page.getByRole("heading", { name: /^marketplace$/i })).toBeVisible();

  const packageCard = page.locator("div.rounded-lg.border").filter({ hasText: packageName }).first();
  await expect(packageCard).toBeVisible();
  await packageCard.getByRole("button", { name: /install|reinstall|update/i }).click();

  if (toolName) {
    await expect.poll(async () => page.getByText(toolName).count()).toBeGreaterThan(0);
  }
}

export async function addMarketplaceToolNode(page: Page, packageSlug: string, nodeLabel: string): Promise<void> {
  const dialog = page.getByRole("dialog", { name: /configure tool node/i });
  await runOrderedSteps([
    () => addPaletteItem(page, `marketplace:${packageSlug}`),
    () => expect(dialog).toBeVisible(),
    () => (nodeLabel !== "Tool" ? dialog.locator("#node-label").fill(nodeLabel) : Promise.resolve()),
    () => dialog.getByRole("button", { name: /^add node$/i }).click(),
    () => expect(dialog).toBeHidden(),
    () => expect(getGraphNodeByLabel(page, nodeLabel)).toBeVisible(),
  ]);
}

export async function startRunFromEditor(page: Page): Promise<string> {
  const runButton = page.getByRole("button", { name: /run workflow/i });
  await runOrderedSteps([
    () => expect(runButton).toBeEnabled(),
    () => runButton.click(),
    () => expect(page).toHaveURL(/\/runs\/[a-f0-9-]+$/, { timeout: 15_000 }),
  ]);
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
  let latestRun: RunDetailResponse | null = null;

  await expect
    .poll(
      async () => {
        const response = await request.get(`${API_BASE_URL}/api/runs/${runId}`, {
          headers: { Authorization: `Bearer ${accessToken}` },
        });
        expect(response.ok()).toBeTruthy();
        const body = (await response.json()) as { data: RunDetailResponse };
        latestRun = body.data;
        return body.data.status;
      },
      {
        timeout: 30_000,
        message: `Timed out waiting for run ${runId} to reach a terminal state.`,
      },
    )
    .toMatch(/^(succeeded|failed|canceled)$/);

  if (!latestRun) {
    throw new Error(`Run ${runId} did not return detail during polling.`);
  }

  return latestRun;
}

export async function waitForRunStatus(
  request: APIRequestContext,
  accessToken: string,
  runId: string,
  expectedStatus: string,
): Promise<RunDetailResponse> {
  let latestRun: RunDetailResponse | null = null;

  await expect
    .poll(
      async () => {
        const response = await request.get(`${API_BASE_URL}/api/runs/${runId}`, {
          headers: { Authorization: `Bearer ${accessToken}` },
        });
        expect(response.ok()).toBeTruthy();
        const body = (await response.json()) as { data: RunDetailResponse };
        latestRun = body.data;
        return body.data.status;
      },
      {
        timeout: 30_000,
        message: `Timed out waiting for run ${runId} to reach status ${expectedStatus}.`,
      },
    )
    .toBe(expectedStatus);

  if (!latestRun) {
    throw new Error(`Run ${runId} did not return detail during polling.`);
  }

  return latestRun;
}

export async function createObservationViaApi(
  request: APIRequestContext,
  accessToken: string,
  observation: MemoryObservationSeed,
): Promise<{ id: string }> {
  const response = await request.post(`${API_BASE_URL}/api/memory/observations`, {
    headers: { Authorization: `Bearer ${accessToken}` },
    data: observation,
  });
  expect(response.ok()).toBeTruthy();
  const body = (await response.json()) as { data: { id: string } };
  return body.data;
}

export async function authorAgentWorkflow(
  page: Page,
  options: AgentWorkflowOptions,
): Promise<{ graphId: string; agentLabel: string; outputLabel: string }> {
  const agentLabel = options.agentLabel ?? "Jackie";
  const outputLabel = options.outputLabel ?? "Output";
  const graphId = await createGraph(page, options.graphName);

  await runOrderedSteps([
    () => addAgentNode(page, options),
    () => clearGraphSelection(page),
    () => addOutputNode(page, outputLabel),
    () => connectGraphNodes(page, agentLabel, outputLabel),
    () => saveGraph(page),
  ]);

  return { graphId, agentLabel, outputLabel };
}
