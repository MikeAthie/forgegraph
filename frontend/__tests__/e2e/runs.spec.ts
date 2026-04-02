import { execFileSync } from "child_process";
import path from "path";

import { expect, test, type APIRequestContext } from "@playwright/test";

import {
  createGraphName,
  createTestUser,
  ensureUserRegistered,
  getAccessToken,
  gotoWithRetry,
  login,
  type TestUser,
} from "./helpers";

let seededUser: TestUser;

const API_BASE_URL = (process.env.PLAYWRIGHT_API_URL ?? "http://127.0.0.1:8000").replace(/\/$/, "");
const backendDir = path.join(__dirname, "..", "..", "..", "backend");
const managementEnv = {
  ...process.env,
  USE_SQLITE: process.env.USE_SQLITE ?? "false",
  SQLITE_DB_PATH: process.env.SQLITE_DB_PATH,
};

async function createGraphVersion(
  request: APIRequestContext,
  accessToken: string,
  options: {
    graphName: string;
    description: string;
    graphJson: {
      nodes: Array<{ id: string; type: string; name: string; config: Record<string, unknown> }>;
      edges: Array<{ id: string; from: string; to: string }>;
    };
  },
): Promise<string> {
  const createGraphResponse = await request.post(`${API_BASE_URL}/api/graphs/`, {
    headers: { Authorization: `Bearer ${accessToken}` },
    data: { name: options.graphName, description: options.description },
  });
  expect(createGraphResponse.ok()).toBeTruthy();
  const createdGraph = (await createGraphResponse.json()) as { data: { id: string } };

  const createVersionResponse = await request.post(`${API_BASE_URL}/api/graphs/${createdGraph.data.id}/versions`, {
    headers: { Authorization: `Bearer ${accessToken}` },
    data: { graph_json: options.graphJson },
  });
  expect(createVersionResponse.ok()).toBeTruthy();
  const createdVersion = (await createVersionResponse.json()) as { data: { id: string } };
  return createdVersion.data.id;
}

async function waitForRunId(request: APIRequestContext, token: string, graphVersionId: string) {
  const deadline = Date.now() + 10_000;
  while (Date.now() < deadline) {
    const response = await request.get(`${API_BASE_URL}/api/runs/`, {
      headers: { Authorization: `Bearer ${token}` },
    });
    if (!response.ok()) {
      const body = await response.text();
      throw new Error(`Failed to list runs (status ${response.status()}): ${body}`);
    }
    const json = (await response.json()) as {
      data: Array<{ id: string; graph_version_id: string }>;
    };
    const match = json.data.find((run) => run.graph_version_id === graphVersionId);
    if (match) {
      return match.id;
    }
    await new Promise((resolve) => setTimeout(resolve, 300));
  }
  throw new Error("Timed out waiting for seeded execution to appear in /api/runs/.");
}

function seedRunTrace(graphVersionId: string, ...args: string[]) {
  execFileSync("python", ["manage.py", "seed_run_trace", graphVersionId, ...args], {
    cwd: backendDir,
    env: managementEnv,
    stdio: "inherit",
  });
}

test.beforeAll(async ({ request }, testInfo) => {
  seededUser = createTestUser(testInfo, "executions");
  await ensureUserRegistered(request, seededUser);
});

test.describe("Execution Visibility", () => {
  test("shows a seeded execution in the visibility screen and opens detail", async ({ page, request }) => {
    const accessToken = await getAccessToken(request, seededUser);
    const graphName = createGraphName("E2E Execution");
    const graphVersionId = await createGraphVersion(request, accessToken, {
      graphName,
      description: "Created by Playwright (execution visibility).",
      graphJson: {
        nodes: [
          { id: "start", type: "prompt", name: "Start", config: {} },
          { id: "end", type: "output", name: "End", config: {} },
        ],
        edges: [
          { id: "e0", from: "START", to: "start" },
          { id: "e1", from: "start", to: "end" },
        ],
      },
    });

    seedRunTrace(graphVersionId, "--run-status", "succeeded");
    const runId = await waitForRunId(request, accessToken, graphVersionId);

    await login(page, seededUser);
    await gotoWithRetry(page, "/runs");

    await expect(page.getByRole("heading", { name: /distributed trace for humans/i })).toBeVisible();
    await expect(page.getByText(graphName).first()).toBeVisible();

    const executionDetailHref = await page.getByRole("link", { name: /open execution detail/i }).getAttribute("href");
    expect(executionDetailHref).toBe(`/executions/${runId}`);
    await page.goto(executionDetailHref!);

    await expect(page).toHaveURL(new RegExp(`/executions/${runId}$`));
    await expect(page.getByRole("heading", { name: /structured execution trace/i })).toBeVisible();
    await expect(page.getByText(/execution flow/i)).toBeVisible();
    await expect(page.getByText(/execution state/i)).toBeVisible();
    await expect(page.getByText(/"ok": true/i).first()).toBeVisible();
  });

  test("shows paused executions with human gate context", async ({ page, request }) => {
    const accessToken = await getAccessToken(request, seededUser);
    const graphName = createGraphName("E2E Human Gate");
    const graphVersionId = await createGraphVersion(request, accessToken, {
      graphName,
      description: "Created by Playwright (paused execution).",
      graphJson: {
        nodes: [
          { id: "start", type: "prompt", name: "Start", config: {} },
          {
            id: "gate",
            type: "human_gate",
            name: "Human Gate",
            config: { prompt_message: "Please review this run.", required_fields: ["ticket"] },
          },
          { id: "end", type: "output", name: "End", config: {} },
        ],
        edges: [
          { id: "e0", from: "START", to: "start" },
          { id: "e1", from: "start", to: "gate" },
          { id: "e2", from: "gate", to: "end" },
        ],
      },
    });

    seedRunTrace(graphVersionId, "--run-status", "paused", "--paused-node-id", "gate");
    const runId = await waitForRunId(request, accessToken, graphVersionId);

    await login(page, seededUser);
    await page.goto(`/executions/${runId}`);

    await expect(page.getByRole("heading", { name: /structured execution trace/i })).toBeVisible();
    await expect(page.getByRole("heading", { name: /^human gate$/i })).toBeVisible();
    await expect(page.getByText("Please review this run.", { exact: true })).toBeVisible();
  });

  test("surfaces status badges across executions", async ({ page, request }) => {
    const accessToken = await getAccessToken(request, seededUser);
    const graphName = createGraphName("E2E Execution Status");
    const graphVersionId = await createGraphVersion(request, accessToken, {
      graphName,
      description: "Created by Playwright (execution statuses).",
      graphJson: {
        nodes: [
          { id: "node_1", type: "prompt", name: "Node", config: {} },
          { id: "output", type: "output", name: "Output", config: {} },
        ],
        edges: [
          { id: "e0", from: "START", to: "node_1" },
          { id: "e1", from: "node_1", to: "output" },
        ],
      },
    });

    seedRunTrace(graphVersionId, "--run-status", "succeeded");
    seedRunTrace(graphVersionId, "--run-status", "failed");

    await login(page, seededUser);
    await gotoWithRetry(page, "/executions");

    await expect(page.getByRole("heading", { name: /distributed trace for humans/i })).toBeVisible();
    await expect(page.getByText(/succeeded/i).first()).toBeVisible();
    await expect(page.getByText(/failed/i).first()).toBeVisible();
  });

  test("shows an empty state when no executions exist", async ({ page, request }, testInfo) => {
    const freshUser = createTestUser(testInfo, "executions-empty");
    await ensureUserRegistered(request, freshUser);

    await login(page, freshUser);
    await gotoWithRetry(page, "/executions");

    await expect(page.getByText(/no executions available/i)).toBeVisible();
  });

  test("shows an error for a non-existent execution", async ({ page }) => {
    await login(page, seededUser);
    await page.goto("/executions/00000000-0000-0000-0000-000000000000");

    await expect(page.getByText(/failed to load execution detail|not found/i)).toBeVisible();
  });
});
