import { expect, test, type APIRequestContext, type Page, type TestInfo } from "@playwright/test";

import { buildMarketingSimulationGraph } from "./fixtures/marketing-simulation-graph";
import { createGraph, createGraphName, createTestUser, expectGraphEditorOpen } from "./helpers";

const API_BASE_URL = (
  process.env.PLAYWRIGHT_API_URL ??
  process.env.NEXT_PUBLIC_API_URL ??
  "http://127.0.0.1:8000"
).replace(/\/$/, "");

type MarketingRunDetail = {
  id: string;
  status: string;
  status_history: string[];
  backend_attempt_id: string;
  error_message?: string | null;
  output_json?: {
    goal?: string;
    strategy?: Record<string, unknown>;
    content_assets?: Array<Record<string, unknown>>;
    distribution_plan?: Record<string, unknown>;
    analytics?: Record<string, unknown>;
    iteration?: number;
  } | null;
  timeline: Array<Record<string, unknown>>;
  node_runs: Array<{
    node_id: string;
    attempt: number;
    status: string;
    input_json?: Record<string, unknown> | null;
    output_json?: Record<string, unknown> | null;
    error_json?: Record<string, unknown> | null;
    started_at?: string | null;
  }>;
};

async function registerViaUi(page: Page, email: string, password: string): Promise<void> {
  await page.goto("/register");
  await page.locator("#email").fill(email);
  await page.locator("#password").fill(password);
  await page.locator("#confirmPassword").fill(password);
  await page.getByRole("button", { name: /^create account$/i }).click();
  await expect(page).toHaveURL(/\/login\?registered=true$/, { timeout: 20_000 });
}

async function loginViaUi(page: Page, email: string, password: string): Promise<void> {
  await page.goto("/login");
  await page.locator("#email").fill(email);
  await page.locator("#password").fill(password);
  await page.getByRole("button", { name: /^sign in$/i }).click();
  await expect(page).toHaveURL(/\/overview(?:\?.*)?$/, { timeout: 20_000 });
  await page.waitForLoadState("networkidle");
}

async function proxyFrontendApiRequests(page: Page, request: APIRequestContext): Promise<void> {
  await page.route("**/api/**", async (route) => {
    const requestUrl = new URL(route.request().url());
    const backendUrl = `${API_BASE_URL}${requestUrl.pathname}${requestUrl.search}`;
    const response = await request.fetch(backendUrl, {
      method: route.request().method(),
      headers: route.request().headers(),
      data: route.request().postDataBuffer() ?? route.request().postData() ?? undefined,
      failOnStatusCode: false,
    });

    await route.fulfill({
      status: response.status(),
      headers: response.headers(),
      body: await response.body(),
    });
  });
}

async function getUiAccessToken(page: Page): Promise<string> {
  const token = await page.evaluate(() => window.sessionStorage.getItem("__FORGEGRAPH_E2E_ACCESS_TOKEN__"));
  expect(token).toBeTruthy();
  return token as string;
}

async function assertOrganizationExists(
  request: APIRequestContext,
  accessToken: string,
): Promise<{ id: string; name: string }> {
  const response = await request.get(`${API_BASE_URL}/api/orgs/me`, {
    headers: { Authorization: `Bearer ${accessToken}` },
  });
  expect(response.ok()).toBeTruthy();
  const body = (await response.json()) as {
    data: { organization: { id: string; name: string } };
  };
  expect(body.data.organization.id).toBeTruthy();
  expect(body.data.organization.name).toBeTruthy();
  return body.data.organization;
}

async function createGraphVersion(request: APIRequestContext, accessToken: string, graphId: string): Promise<string> {
  const response = await request.post(`${API_BASE_URL}/api/graphs/${graphId}/versions`, {
    headers: { Authorization: `Bearer ${accessToken}` },
    data: {
      graph_json: buildMarketingSimulationGraph(),
    },
  });
  expect(response.ok()).toBeTruthy();
  const body = (await response.json()) as { data: { id: string } };
  expect(body.data.id).toBeTruthy();
  return body.data.id;
}

async function startRunFromGraphEditor(page: Page): Promise<string> {
  const runButton = page.getByRole("button", { name: /run workflow/i });
  await expect(runButton).toBeEnabled();
  await runButton.click();
  await expect(page).toHaveURL(/\/runs\/[a-f0-9-]+$/, { timeout: 20_000 });
  const runId = page.url().match(/\/runs\/([a-f0-9-]+)$/)?.[1];
  if (!runId) {
    throw new Error(`Could not determine run id from URL: ${page.url()}`);
  }
  return runId;
}

async function pollRunDetail(
  request: APIRequestContext,
  accessToken: string,
  runId: string,
): Promise<MarketingRunDetail> {
  let latestRun: MarketingRunDetail | null = null;

  await expect
    .poll(
      async () => {
        const response = await request.get(`${API_BASE_URL}/api/runs/${runId}`, {
          headers: { Authorization: `Bearer ${accessToken}` },
        });
        expect(response.ok()).toBeTruthy();
        const body = (await response.json()) as { data: MarketingRunDetail };
        latestRun = body.data;
        return body.data.status;
      },
      {
        timeout: 240_000,
        message: `Timed out waiting for run ${runId} to complete.`,
      },
    )
    .toMatch(/^(succeeded|failed|canceled)$/);

  if (!latestRun) {
    throw new Error(`Run ${runId} did not return any detail payload.`);
  }

  return latestRun;
}

function getInputExecutionState(nodeRun: MarketingRunDetail["node_runs"][number]): unknown {
  return nodeRun.input_json?.vars && typeof nodeRun.input_json.vars === "object"
    ? (nodeRun.input_json.vars as { execution_state?: unknown }).execution_state
    : undefined;
}

function getOutputExecutionState(nodeRun: MarketingRunDetail["node_runs"][number]): unknown {
  const output = nodeRun.output_json?.output;
  if (output && typeof output === "object") {
    if ("state" in output) {
      return (output as { state?: unknown }).state;
    }
    if ("structured_response" in output) {
      return (output as { structured_response?: unknown }).structured_response;
    }
  }
  return undefined;
}

function attachRunArtifacts(testInfo: TestInfo, run: MarketingRunDetail): Promise<void[]> {
  return Promise.all([
    testInfo.attach("marketing-run-detail.json", {
      body: Buffer.from(JSON.stringify(run, null, 2), "utf8"),
      contentType: "application/json",
    }),
    testInfo.attach("marketing-execution-trace.json", {
      body: Buffer.from(JSON.stringify(run.timeline, null, 2), "utf8"),
      contentType: "application/json",
    }),
    testInfo.attach("marketing-node-runs.json", {
      body: Buffer.from(JSON.stringify(run.node_runs, null, 2), "utf8"),
      contentType: "application/json",
    }),
  ]);
}

test.describe("Marketing Simulation Replay", () => {
  test.describe.configure({ mode: "serial" });

  test("runs the replayable marketing company end-to-end", async ({ page, request }, testInfo) => {
    test.setTimeout(300_000);
    const user = createTestUser(testInfo, "marketing-sim");

    await proxyFrontendApiRequests(page, request);
    await registerViaUi(page, user.email, user.password);
    await loginViaUi(page, user.email, user.password);

    const accessToken = await getUiAccessToken(page);
    const organization = await assertOrganizationExists(request, accessToken);
    expect(organization.id).toBeTruthy();

    const graphName = createGraphName("Marketing Company Simulation");
    const graphId = await createGraph(page, graphName, "Replayable deterministic marketing run.");
    const versionId = await createGraphVersion(request, accessToken, graphId);
    expect(versionId).toBeTruthy();

    await page.reload();
    await expectGraphEditorOpen(page);

    const runId = await startRunFromGraphEditor(page);
    const run = await pollRunDetail(request, accessToken, runId);
    await attachRunArtifacts(testInfo, run);

    console.log(
      JSON.stringify(
        {
          run_id: runId,
          backend_attempt_id: run.backend_attempt_id,
          status_history: run.status_history,
          timeline_events: run.timeline.length,
          node_runs: run.node_runs.length,
        },
        null,
        2,
      ),
    );

    if (run.status !== "succeeded") {
      throw new Error(
        `Marketing simulation run ${runId} ended with ${run.status}: ${run.error_message ?? "unknown error"}`,
      );
    }

    const runningIndex = run.status_history.indexOf("running");
    const succeededIndex = run.status_history.indexOf("succeeded");
    expect(run.status_history[0]).toBe("pending");
    expect(runningIndex).toBeGreaterThan(0);
    expect(succeededIndex).toBeGreaterThan(runningIndex);

    expect(run.backend_attempt_id).toBeTruthy();
    expect(run.output_json?.strategy).toBeTruthy();
    expect(run.output_json?.content_assets?.length ?? 0).toBeGreaterThan(0);
    expect(run.output_json?.distribution_plan).toBeTruthy();
    expect(run.output_json?.analytics).toBeTruthy();
    expect(run.output_json?.iteration).toBe(2);

    const seenAttempts = new Set<string>();
    for (const nodeRun of run.node_runs) {
      const key = `${nodeRun.node_id}#${nodeRun.attempt}`;
      expect(seenAttempts.has(key), `Duplicate node execution detected for ${key}`).toBeFalsy();
      seenAttempts.add(key);
    }

    const llmNodeIds = new Set([
      "strategy_agent",
      "content_copywriter_specialist",
      "content_editor_specialist",
      "distribution_agent",
    ]);
    const statefulNodeIds = new Set([
      "merge_strategy_state",
      "merge_copywriter_asset",
      "merge_editor_asset",
      "content_agent",
      "merge_distribution_state",
      "analytics_agent",
      "decision_node",
    ]);
    const statefulNodeRuns = run.node_runs.filter((nodeRun) => statefulNodeIds.has(nodeRun.node_id));
    let previousExecutionState: unknown = undefined;
    for (const nodeRun of statefulNodeRuns) {
      const inputExecutionState = getInputExecutionState(nodeRun);
      expect(
        inputExecutionState,
        `Missing execution_state input for ${nodeRun.node_id}#${nodeRun.attempt}`,
      ).toBeTruthy();
      if (previousExecutionState !== undefined) {
        expect(inputExecutionState).toEqual(previousExecutionState);
      }
      previousExecutionState = getOutputExecutionState(nodeRun) ?? inputExecutionState;
    }

    const llmNodeRuns = run.node_runs.filter((nodeRun) => llmNodeIds.has(nodeRun.node_id));
    expect(llmNodeRuns.length).toBeGreaterThan(0);
    for (const nodeRun of llmNodeRuns) {
      expect(
        getInputExecutionState(nodeRun),
        `Missing execution_state input for prompt node ${nodeRun.node_id}#${nodeRun.attempt}`,
      ).toBeTruthy();
      const output = nodeRun.output_json?.output;
      expect(
        output && typeof output === "object",
        `Missing prompt output for ${nodeRun.node_id}#${nodeRun.attempt}`,
      ).toBeTruthy();
      const promptOutput = output as {
        prompt?: unknown;
        response?: unknown;
        provider?: unknown;
        model?: unknown;
        usage?: { total_tokens?: unknown };
        structured_response?: unknown;
        schema_validation?: { valid?: unknown };
        state_output_key?: unknown;
      };
      expect(promptOutput.provider).toBe("openai");
      expect(typeof promptOutput.model).toBe("string");
      expect(typeof promptOutput.prompt).toBe("string");
      expect(typeof promptOutput.response).toBe("string");
      expect(
        promptOutput.structured_response,
        `Missing structured_response for ${nodeRun.node_id}#${nodeRun.attempt}`,
      ).toBeTruthy();
      expect(promptOutput.schema_validation?.valid).toBe(true);
      expect(Number(promptOutput.usage?.total_tokens ?? 0)).toBeGreaterThan(0);
      expect(typeof promptOutput.state_output_key).toBe("string");
    }
  });

  test("captures deterministic failure state loudly", async ({ page, request }, testInfo) => {
    test.setTimeout(300_000);
    const user = createTestUser(testInfo, "marketing-fail");

    await proxyFrontendApiRequests(page, request);
    await registerViaUi(page, user.email, user.password);
    await loginViaUi(page, user.email, user.password);

    const accessToken = await getUiAccessToken(page);
    const graphId = await createGraph(
      page,
      createGraphName("Marketing Company Failure Simulation"),
      "Failure visibility harness.",
    );
    const versionId = await createGraphVersion(request, accessToken, graphId);

    const startResponse = await request.post(`${API_BASE_URL}/api/runs/start`, {
      headers: { Authorization: `Bearer ${accessToken}` },
      data: {
        graph_version_id: versionId,
        input_json: {
          goal: "Force a visible content failure.",
          force_content_failure: true,
        },
      },
    });
    expect(startResponse.ok()).toBeTruthy();
    const startBody = (await startResponse.json()) as { data: { id: string } };
    const runId = startBody.data.id;

    const run = await pollRunDetail(request, accessToken, runId);
    await attachRunArtifacts(testInfo, run);

    console.error(
      JSON.stringify(
        {
          run_id: runId,
          status: run.status,
          error_message: run.error_message,
          failed_nodes: run.node_runs
            .filter((nodeRun) => nodeRun.status === "failed")
            .map((nodeRun) => ({
              node_id: nodeRun.node_id,
              attempt: nodeRun.attempt,
              error_json: nodeRun.error_json,
            })),
        },
        null,
        2,
      ),
    );

    expect(run.status).toBe("failed");
    const failedNode = run.node_runs.find((nodeRun) => nodeRun.status === "failed");
    expect(failedNode?.node_id).toContain("content");
    expect(JSON.stringify(failedNode?.error_json ?? {})).toContain("simulated");
  });
});
