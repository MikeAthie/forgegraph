import { test, expect, type APIRequestContext } from "@playwright/test";
import path from "path";
import { execFileSync } from "child_process";

import { createTestUser, ensureUserRegistered, gotoWithRetry, login, type TestUser } from "./helpers";

let seededUser: TestUser;

const API_BASE_URL = (process.env.PLAYWRIGHT_API_URL ?? "http://127.0.0.1:8000").replace(/\/$/, "");

const createGraphName = (prefix: string) => `${prefix} ${Date.now()}-${Math.random().toString(16).slice(2)}`;

async function getAccessToken(request: APIRequestContext, user: TestUser): Promise<string> {
  const response = await request.post(`${API_BASE_URL}/api/auth/login`, {
    data: { email: user.email, password: user.password },
  });
  expect(response.ok()).toBeTruthy();
  const json = (await response.json()) as { access?: string };
  if (!json.access) {
    throw new Error(`Login did not return access token: ${JSON.stringify(json)}`);
  }
  return json.access;
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
    if (match) return match.id;
    await new Promise((resolve) => setTimeout(resolve, 300));
  }
  throw new Error("Timed out waiting for seeded run to appear in /api/runs/.");
}

test.beforeAll(async ({ request }, testInfo) => {
  seededUser = createTestUser(testInfo, "e2e-runs");
  await ensureUserRegistered(request, seededUser);
});

test.describe("Runs", () => {
  test("shows a seeded run trace in the UI", async ({ page, request }) => {
    const accessToken = await getAccessToken(request, seededUser);

    const graphName = createGraphName("E2E Run Graph");
    const createGraphResponse = await request.post(`${API_BASE_URL}/api/graphs/`, {
      headers: { Authorization: `Bearer ${accessToken}` },
      data: { name: graphName, description: "Created by Playwright (runs)." },
    });
    expect(createGraphResponse.ok()).toBeTruthy();
    const createdGraph = (await createGraphResponse.json()) as { data: { id: string } };
    const graphId = createdGraph.data.id;

    const graphJson = {
      nodes: [
        { id: "start", type: "prompt", name: "Start", config: {} },
        { id: "end", type: "output", name: "End", config: {} },
      ],
      edges: [{ id: "e1", from: "start", to: "end" }],
    };

    const createVersionResponse = await request.post(`${API_BASE_URL}/api/graphs/${graphId}/versions`, {
      headers: { Authorization: `Bearer ${accessToken}` },
      data: { graph_json: graphJson },
    });
    expect(createVersionResponse.ok()).toBeTruthy();
    const createdVersion = (await createVersionResponse.json()) as { data: { id: string } };
    const graphVersionId = createdVersion.data.id;

    const backendDir = path.join(__dirname, "..", "..", "..", "backend");
    execFileSync(
      "python",
      ["manage.py", "seed_run_trace", graphVersionId, "--run-status", "succeeded"],
      {
        cwd: backendDir,
        env: { ...process.env, USE_SQLITE: process.env.USE_SQLITE ?? "true" },
        stdio: "inherit",
      },
    );

    const runId = await waitForRunId(request, accessToken, graphVersionId);

    await login(page, seededUser);
    await gotoWithRetry(page, "/runs");

    await expect(page.getByRole("heading", { name: /^runs$/i })).toBeVisible();

    const runRow = page.locator("tr").filter({ hasText: graphName }).first();
    await expect(runRow).toBeVisible();
    await runRow.getByRole("link", { name: /^view$/i }).click();

    await expect(page).toHaveURL(new RegExp(`/runs/${runId}$`));

    await expect(page.getByText("Nodes")).toBeVisible();
    await expect(page.getByRole("button", { name: /start/i })).toBeVisible();
    await expect(page.getByText(/"ok": true/i)).toBeVisible();
  });

  test("shows a paused run with Human Gate approval UI", async ({ page, request }) => {
    const accessToken = await getAccessToken(request, seededUser);

    const graphName = createGraphName("E2E Paused Run Graph");
    const createGraphResponse = await request.post(`${API_BASE_URL}/api/graphs/`, {
      headers: { Authorization: `Bearer ${accessToken}` },
      data: { name: graphName, description: "Created by Playwright (paused run)." },
    });
    expect(createGraphResponse.ok()).toBeTruthy();
    const createdGraph = (await createGraphResponse.json()) as { data: { id: string } };
    const graphId = createdGraph.data.id;

    const graphJson = {
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
        { id: "e1", from: "start", to: "gate" },
        { id: "e2", from: "gate", to: "end" },
      ],
    };

    const createVersionResponse = await request.post(`${API_BASE_URL}/api/graphs/${graphId}/versions`, {
      headers: { Authorization: `Bearer ${accessToken}` },
      data: { graph_json: graphJson },
    });
    expect(createVersionResponse.ok()).toBeTruthy();
    const createdVersion = (await createVersionResponse.json()) as { data: { id: string } };
    const graphVersionId = createdVersion.data.id;

    const backendDir = path.join(__dirname, "..", "..", "..", "backend");
    execFileSync(
      "python",
      ["manage.py", "seed_run_trace", graphVersionId, "--run-status", "paused", "--paused-node-id", "gate"],
      {
        cwd: backendDir,
        env: { ...process.env, USE_SQLITE: process.env.USE_SQLITE ?? "true" },
        stdio: "inherit",
      },
    );

    const runId = await waitForRunId(request, accessToken, graphVersionId);

    await login(page, seededUser);
    await gotoWithRetry(page, "/runs");

    const runRow = page.locator("tr").filter({ hasText: graphName }).first();
    await expect(runRow).toBeVisible();
    await runRow.getByRole("link", { name: /^view$/i }).click();

    await expect(page).toHaveURL(new RegExp(`/runs/${runId}$`));

    // Human Gate approval UI should render for paused runs.
    await expect(page.getByText(/waiting for approval/i)).toBeVisible();
    await expect(page.getByText("Please review this run.")).toBeVisible();
    await expect(page.getByText(/paused at node/i)).toBeVisible();
    await expect(page.getByText(/^ticket$/i)).toBeVisible();
    await expect(page.getByRole("button", { name: /^approve$/i })).toBeVisible();
    await expect(page.getByRole("button", { name: /^reject$/i })).toBeVisible();
  });

  test("displays run list with status badges", async ({ page, request }) => {
    const accessToken = await getAccessToken(request, seededUser);

    // Create multiple runs with different statuses
    const graphName = createGraphName("E2E Status Graph");
    const createGraphResponse = await request.post(`${API_BASE_URL}/api/graphs/`, {
      headers: { Authorization: `Bearer ${accessToken}` },
      data: { name: graphName, description: "Test status badges" },
    });
    expect(createGraphResponse.ok()).toBeTruthy();
    const createdGraph = (await createGraphResponse.json()) as { data: { id: string } };
    const graphId = createdGraph.data.id;

    const graphJson = {
      nodes: [{ id: "node_1", type: "prompt", name: "Node", config: {} }],
      edges: [],
    };

    const createVersionResponse = await request.post(`${API_BASE_URL}/api/graphs/${graphId}/versions`, {
      headers: { Authorization: `Bearer ${accessToken}` },
      data: { graph_json: graphJson },
    });
    expect(createVersionResponse.ok()).toBeTruthy();
    const createdVersion = (await createVersionResponse.json()) as { data: { id: string } };
    const graphVersionId = createdVersion.data.id;

    // Seed succeeded run
    const backendDir = path.join(__dirname, "..", "..", "..", "backend");
    execFileSync("python", ["manage.py", "seed_run_trace", graphVersionId, "--run-status", "succeeded"], {
      cwd: backendDir,
      env: { ...process.env, USE_SQLITE: process.env.USE_SQLITE ?? "true" },
      stdio: "inherit",
    });

    // Seed failed run
    execFileSync("python", ["manage.py", "seed_run_trace", graphVersionId, "--run-status", "failed"], {
      cwd: backendDir,
      env: { ...process.env, USE_SQLITE: process.env.USE_SQLITE ?? "true" },
      stdio: "inherit",
    });

    await login(page, seededUser);
    await gotoWithRetry(page, "/runs");

    await expect(page.getByRole("heading", { name: /^runs$/i })).toBeVisible();

    // Check for status badges
    await expect(page.locator("text=/succeeded/i").first()).toBeVisible();
    await expect(page.locator("text=/failed/i").first()).toBeVisible();
  });

  test("navigates from run list to run detail", async ({ page, request }) => {
    const accessToken = await getAccessToken(request, seededUser);

    const graphName = createGraphName("E2E Navigation Graph");
    const createGraphResponse = await request.post(`${API_BASE_URL}/api/graphs/`, {
      headers: { Authorization: `Bearer ${accessToken}` },
      data: { name: graphName, description: "Test navigation" },
    });
    expect(createGraphResponse.ok()).toBeTruthy();
    const createdGraph = (await createGraphResponse.json()) as { data: { id: string } };
    const graphId = createdGraph.data.id;

    const graphJson = {
      nodes: [{ id: "node_1", type: "prompt", name: "Test Node", config: {} }],
      edges: [],
    };

    const createVersionResponse = await request.post(`${API_BASE_URL}/api/graphs/${graphId}/versions`, {
      headers: { Authorization: `Bearer ${accessToken}` },
      data: { graph_json: graphJson },
    });
    expect(createVersionResponse.ok()).toBeTruthy();
    const createdVersion = (await createVersionResponse.json()) as { data: { id: string } };
    const graphVersionId = createdVersion.data.id;

    const backendDir = path.join(__dirname, "..", "..", "..", "backend");
    execFileSync("python", ["manage.py", "seed_run_trace", graphVersionId, "--run-status", "succeeded"], {
      cwd: backendDir,
      env: { ...process.env, USE_SQLITE: process.env.USE_SQLITE ?? "true" },
      stdio: "inherit",
    });

    const runId = await waitForRunId(request, accessToken, graphVersionId);

    await login(page, seededUser);
    await gotoWithRetry(page, "/runs");

    // Click on the table row
    const runRow = page.locator("tr").filter({ hasText: graphName }).first();
    await expect(runRow).toBeVisible();
    await runRow.click();

    // Should navigate to run detail
    await expect(page).toHaveURL(new RegExp(`/runs/${runId}$`));
    await expect(page.getByText(graphName)).toBeVisible();
  });

  test("displays node runs with input/output details", async ({ page, request }) => {
    const accessToken = await getAccessToken(request, seededUser);

    const graphName = createGraphName("E2E Details Graph");
    const createGraphResponse = await request.post(`${API_BASE_URL}/api/graphs/`, {
      headers: { Authorization: `Bearer ${accessToken}` },
      data: { name: graphName, description: "Test node details" },
    });
    expect(createGraphResponse.ok()).toBeTruthy();
    const createdGraph = (await createGraphResponse.json()) as { data: { id: string } };
    const graphId = createdGraph.data.id;

    const graphJson = {
      nodes: [
        { id: "node_1", type: "prompt", name: "First Node", config: {} },
        { id: "node_2", type: "http", name: "Second Node", config: {} },
      ],
      edges: [{ id: "e1", from: "node_1", to: "node_2" }],
    };

    const createVersionResponse = await request.post(`${API_BASE_URL}/api/graphs/${graphId}/versions`, {
      headers: { Authorization: `Bearer ${accessToken}` },
      data: { graph_json: graphJson },
    });
    expect(createVersionResponse.ok()).toBeTruthy();
    const createdVersion = (await createVersionResponse.json()) as { data: { id: string } };
    const graphVersionId = createdVersion.data.id;

    const backendDir = path.join(__dirname, "..", "..", "..", "backend");
    execFileSync("python", ["manage.py", "seed_run_trace", graphVersionId, "--run-status", "succeeded"], {
      cwd: backendDir,
      env: { ...process.env, USE_SQLITE: process.env.USE_SQLITE ?? "true" },
      stdio: "inherit",
    });

    const runId = await waitForRunId(request, accessToken, graphVersionId);

    await login(page, seededUser);
    await page.goto(`/runs/${runId}`);

    await expect(page.getByText(graphName)).toBeVisible();

    // Check that both nodes are visible
    await expect(page.getByRole("button", { name: /First Node/i })).toBeVisible();
    await expect(page.getByRole("button", { name: /Second Node/i })).toBeVisible();

    // Click to expand first node
    const firstNodeButton = page.getByRole("button", { name: /First Node/i });
    await firstNodeButton.click();

    // Should show JSON output
    await expect(page.getByText(/"ok": true/i).first()).toBeVisible();
  });

  test("displays error message for failed runs", async ({ page, request }) => {
    const accessToken = await getAccessToken(request, seededUser);

    const graphName = createGraphName("E2E Failed Graph");
    const createGraphResponse = await request.post(`${API_BASE_URL}/api/graphs/`, {
      headers: { Authorization: `Bearer ${accessToken}` },
      data: { name: graphName, description: "Test failed run" },
    });
    expect(createGraphResponse.ok()).toBeTruthy();
    const createdGraph = (await createGraphResponse.json()) as { data: { id: string } };
    const graphId = createdGraph.data.id;

    const graphJson = {
      nodes: [{ id: "node_1", type: "prompt", name: "Failing Node", config: {} }],
      edges: [],
    };

    const createVersionResponse = await request.post(`${API_BASE_URL}/api/graphs/${graphId}/versions`, {
      headers: { Authorization: `Bearer ${accessToken}` },
      data: { graph_json: graphJson },
    });
    expect(createVersionResponse.ok()).toBeTruthy();
    const createdVersion = (await createVersionResponse.json()) as { data: { id: string } };
    const graphVersionId = createdVersion.data.id;

    const backendDir = path.join(__dirname, "..", "..", "..", "backend");
    execFileSync("python", ["manage.py", "seed_run_trace", graphVersionId, "--run-status", "failed"], {
      cwd: backendDir,
      env: { ...process.env, USE_SQLITE: process.env.USE_SQLITE ?? "true" },
      stdio: "inherit",
    });

    const runId = await waitForRunId(request, accessToken, graphVersionId);

    await login(page, seededUser);
    await page.goto(`/runs/${runId}`);

    // Should show failed status
    await expect(page.getByText(/failed/i)).toBeVisible();

    // Should show error message (seeded runs typically have an error message for failed status)
    await expect(page.getByText(/error|failed/i)).toBeVisible();
  });

  test("shows empty state when no runs exist", async ({ page, request }) => {
    // Create a fresh user with no runs
    const freshUser = createTestUser({ title: "Fresh User" } as any, "e2e-empty");
    await ensureUserRegistered(request, freshUser);

    await login(page, freshUser);
    await gotoWithRetry(page, "/runs");

    await expect(page.getByRole("heading", { name: /^runs$/i })).toBeVisible();
    await expect(page.getByText(/no runs yet|empty|get started/i)).toBeVisible();
  });

  test("displays run duration for completed runs", async ({ page, request }) => {
    const accessToken = await getAccessToken(request, seededUser);

    const graphName = createGraphName("E2E Duration Graph");
    const createGraphResponse = await request.post(`${API_BASE_URL}/api/graphs/`, {
      headers: { Authorization: `Bearer ${accessToken}` },
      data: { name: graphName, description: "Test duration display" },
    });
    expect(createGraphResponse.ok()).toBeTruthy();
    const createdGraph = (await createGraphResponse.json()) as { data: { id: string } };
    const graphId = createdGraph.data.id;

    const graphJson = {
      nodes: [{ id: "node_1", type: "prompt", name: "Node", config: {} }],
      edges: [],
    };

    const createVersionResponse = await request.post(`${API_BASE_URL}/api/graphs/${graphId}/versions`, {
      headers: { Authorization: `Bearer ${accessToken}` },
      data: { graph_json: graphJson },
    });
    expect(createVersionResponse.ok()).toBeTruthy();
    const createdVersion = (await createVersionResponse.json()) as { data: { id: string } };
    const graphVersionId = createdVersion.data.id;

    const backendDir = path.join(__dirname, "..", "..", "..", "backend");
    execFileSync("python", ["manage.py", "seed_run_trace", graphVersionId, "--run-status", "succeeded"], {
      cwd: backendDir,
      env: { ...process.env, USE_SQLITE: process.env.USE_SQLITE ?? "true" },
      stdio: "inherit",
    });

    await login(page, seededUser);
    await gotoWithRetry(page, "/runs");

    // Should display some duration (ms, s, m, etc.)
    await expect(page.locator("text=/\\d+\\s*(ms|s|m|h)/").first()).toBeVisible();
  });

  test("displays node retry attempts", async ({ page, request }) => {
    const accessToken = await getAccessToken(request, seededUser);

    const graphName = createGraphName("E2E Retry Graph");
    const createGraphResponse = await request.post(`${API_BASE_URL}/api/graphs/`, {
      headers: { Authorization: `Bearer ${accessToken}` },
      data: { name: graphName, description: "Test retry attempts" },
    });
    expect(createGraphResponse.ok()).toBeTruthy();
    const createdGraph = (await createGraphResponse.json()) as { data: { id: string } };
    const graphId = createdGraph.data.id;

    const graphJson = {
      nodes: [
        { id: "node_1", type: "http", name: "Retrying Node", config: {} },
        { id: "end", type: "output", name: "End", config: {} },
      ],
      edges: [{ id: "e1", from: "node_1", to: "end" }],
    };

    const createVersionResponse = await request.post(`${API_BASE_URL}/api/graphs/${graphId}/versions`, {
      headers: { Authorization: `Bearer ${accessToken}` },
      data: { graph_json: graphJson },
    });
    expect(createVersionResponse.ok()).toBeTruthy();
    const createdVersion = (await createVersionResponse.json()) as { data: { id: string } };
    const graphVersionId = createdVersion.data.id;

    // Seed a run (avoid depending on the Go engine for this UI-only assertion)
    const backendDir = path.join(__dirname, "..", "..", "..", "backend");
    execFileSync(
      "python",
      ["manage.py", "seed_run_trace", graphVersionId, "--run-status", "succeeded"],
      {
        cwd: backendDir,
        env: { ...process.env, USE_SQLITE: process.env.USE_SQLITE ?? "true" },
        stdio: "inherit",
      },
    );

    const runId = await waitForRunId(request, accessToken, graphVersionId);

    // Manually create node runs with retry attempts
    await request.post(`${API_BASE_URL}/api/runs/${runId}/events`, {
      headers: { Authorization: `Bearer ${accessToken}` },
      data: {
        event_type: "node_run.updated",
        node_run: {
          node_id: "node_1",
          node_type: "http",
          status: "failed",
          attempt: 1,
          error_json: { message: "Timeout" },
        },
      },
    });

    await request.post(`${API_BASE_URL}/api/runs/${runId}/events`, {
      headers: { Authorization: `Bearer ${accessToken}` },
      data: {
        event_type: "node_run.updated",
        node_run: {
          node_id: "node_1",
          node_type: "http",
          status: "succeeded",
          attempt: 2,
          output_json: { ok: true },
        },
      },
    });

    await request.post(`${API_BASE_URL}/api/runs/${runId}/events`, {
      headers: { Authorization: `Bearer ${accessToken}` },
      data: {
        event_type: "run.updated",
        run: { status: "succeeded" },
      },
    });

    await login(page, seededUser);
    await page.goto(`/runs/${runId}`);

    await expect(page.getByText(graphName).first()).toBeVisible({ timeout: 10_000 });

    // Should show both attempts
    await expect(
      page.getByRole("button", { name: /Retrying Node.*attempt 1/i }),
    ).toBeVisible();
    await expect(
      page.getByRole("button", { name: /Retrying Node.*attempt 2/i }),
    ).toBeVisible();
  });

  test("handles 404 for non-existent run", async ({ page }) => {
    await login(page, seededUser);
    const fakeRunId = "00000000-0000-0000-0000-000000000000";
    await page.goto(`/runs/${fakeRunId}`);

    // Should show 404 or not found message
    await expect(page.getByText(/not found|404|does not exist/i)).toBeVisible();
  });

  test("displays final output for completed runs", async ({ page, request }) => {
    const accessToken = await getAccessToken(request, seededUser);

    const graphName = createGraphName("E2E Output Graph");
    const createGraphResponse = await request.post(`${API_BASE_URL}/api/graphs/`, {
      headers: { Authorization: `Bearer ${accessToken}` },
      data: { name: graphName, description: "Test final output" },
    });
    expect(createGraphResponse.ok()).toBeTruthy();
    const createdGraph = (await createGraphResponse.json()) as { data: { id: string } };
    const graphId = createdGraph.data.id;

    const graphJson = {
      nodes: [{ id: "node_1", type: "output", name: "Output", config: {} }],
      edges: [],
    };

    const createVersionResponse = await request.post(`${API_BASE_URL}/api/graphs/${graphId}/versions`, {
      headers: { Authorization: `Bearer ${accessToken}` },
      data: { graph_json: graphJson },
    });
    expect(createVersionResponse.ok()).toBeTruthy();
    const createdVersion = (await createVersionResponse.json()) as { data: { id: string } };
    const graphVersionId = createdVersion.data.id;

    const backendDir = path.join(__dirname, "..", "..", "..", "backend");
    execFileSync("python", ["manage.py", "seed_run_trace", graphVersionId, "--run-status", "succeeded"], {
      cwd: backendDir,
      env: { ...process.env, USE_SQLITE: process.env.USE_SQLITE ?? "true" },
      stdio: "inherit",
    });

    const runId = await waitForRunId(request, accessToken, graphVersionId);

    await login(page, seededUser);
    await page.goto(`/runs/${runId}`);

    await expect(page.getByText(graphName)).toBeVisible();

    // Should show output section with JSON
    await expect(page.getByText(/output|result/i)).toBeVisible();
    await expect(page.getByText(/"ok": true/i)).toBeVisible();
  });
});
