import { expect, type APIRequestContext, type Page, type TestInfo } from "@playwright/test";

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

export type RunSeedResult = {
  runId: string;
};

export type HumanGateRunSeedResult = {
  companyId: string;
  versionId: string;
  runId: string;
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

const TEST_PASSWORD = "ForgeGraphTest!12345";
const API_BASE_URL = (
  process.env.PLAYWRIGHT_API_URL ??
  process.env.NEXT_PUBLIC_API_URL ??
  "http://127.0.0.1:8002"
).replace(/\/$/, "");
const API_REQUEST_TIMEOUT_MS = positiveNumberFromEnv(
  "PLAYWRIGHT_API_REQUEST_TIMEOUT_MS",
  process.env.CI ? 60_000 : 30_000,
);
const LIVE_AUTH_TIMEOUT_MS = positiveNumberFromEnv("PLAYWRIGHT_LIVE_AUTH_TIMEOUT_MS", process.env.CI ? 60_000 : 30_000);
const ENGINE_START_RETRY_MS = positiveNumberFromEnv(
  "PLAYWRIGHT_ENGINE_START_RETRY_MS",
  process.env.CI ? 60_000 : 10_000,
);

function positiveNumberFromEnv(name: string, fallback: number): number {
  const rawValue = process.env[name];
  if (!rawValue) {
    return fallback;
  }

  const parsed = Number(rawValue);
  return Number.isFinite(parsed) && parsed > 0 ? parsed : fallback;
}

function sleep(ms: number): Promise<void> {
  return new Promise((resolve) => setTimeout(resolve, ms));
}

function isEngineUnavailable(status: number, body: string): boolean {
  return status === 503 && body.includes("ENGINE_UNAVAILABLE");
}

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

export async function ensureUserRegistered(request: APIRequestContext, user: TestUser): Promise<void> {
  const response = await request.post(`${API_BASE_URL}/api/auth/register`, {
    timeout: API_REQUEST_TIMEOUT_MS,
    data: { email: user.email, password: user.password },
  });

  if (response.ok() || response.status() === 400) {
    return;
  }

  throw new Error(`Failed to register test user (status ${response.status()}): ${await response.text()}`);
}

export async function getAccessToken(request: APIRequestContext, user: TestUser): Promise<string> {
  let lastBody = "";

  for (let attempt = 0; attempt < 5; attempt += 1) {
    const response = await request.post(`${API_BASE_URL}/api/auth/login`, {
      timeout: API_REQUEST_TIMEOUT_MS,
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

    lastBody = await response.text();
    if (response.status() !== 429 || attempt === 4) {
      throw new Error(`Failed to login test user (status ${response.status()}): ${lastBody}`);
    }

    const retryAfterSeconds = Number(response.headers()["retry-after"] ?? "2");
    const delayMs = Math.max(500, Math.min(5000, retryAfterSeconds * 1000 || 2000));
    await new Promise((resolve) => setTimeout(resolve, delayMs));
  }

  throw new Error(`Failed to login test user after retries: ${lastBody}`);
}

export async function loginLive(
  page: Page,
  request: APIRequestContext,
  user: TestUser,
  targetPath = "/companies",
): Promise<string> {
  await page.context().clearCookies();
  await ensureUserRegistered(request, user);

  await page.goto("/login");
  await page.getByRole("textbox", { name: /email address/i }).fill(user.email);
  await page.getByRole("textbox", { name: /password/i }).fill(user.password);
  const loginResponsePromise = page.waitForResponse(
    (response) => response.url().includes("/api/auth/login") && response.request().method() === "POST",
    { timeout: LIVE_AUTH_TIMEOUT_MS },
  );
  await page.getByRole("button", { name: /^sign in$/i }).click();
  const loginResponse = await loginResponsePromise;
  if (!loginResponse.ok()) {
    throw new Error(
      `Live login failed (status ${loginResponse.status()}) via ${loginResponse.url()}: ${await loginResponse.text()}`,
    );
  }
  await page.waitForURL(/\/companies(?:\?.*)?$/, { timeout: LIVE_AUTH_TIMEOUT_MS });

  let token: string | null = null;
  await expect
    .poll(
      async () => {
        token = await page.evaluate(() => window.sessionStorage.getItem("__FORGEGRAPH_E2E_ACCESS_TOKEN__"));
        return token;
      },
      {
        timeout: LIVE_AUTH_TIMEOUT_MS,
        message: "Timed out waiting for live login access token.",
      },
    )
    .toBeTruthy();
  if (!token) {
    throw new Error("Live login did not produce a browser access token.");
  }

  if (targetPath !== "/companies") {
    await page.goto(targetPath, { waitUntil: "domcontentloaded" });
  }
  return token;
}

export function createGraphName(prefix: string): string {
  return `${prefix} ${Date.now()}-${Math.random().toString(16).slice(2)}`;
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

export async function startRunViaApi(
  request: APIRequestContext,
  accessToken: string,
  options: {
    versionId: string;
    inputJson?: Record<string, unknown>;
  },
): Promise<RunSeedResult> {
  const deadline = Date.now() + ENGINE_START_RETRY_MS;
  let attempt = 0;

  while (true) {
    attempt += 1;
    const startResponse = await request.post(`${API_BASE_URL}/api/runs/start`, {
      timeout: API_REQUEST_TIMEOUT_MS,
      headers: { Authorization: `Bearer ${accessToken}` },
      data: {
        graph_version_id: options.versionId,
        input_json: options.inputJson ?? {},
      },
    });
    if (startResponse.ok()) {
      const startBody = (await startResponse.json()) as { data: { id: string } };
      return { runId: startBody.data.id };
    }

    const responseText = await startResponse.text();
    const hasRetryBudget = Date.now() < deadline;
    if (isEngineUnavailable(startResponse.status(), responseText) && hasRetryBudget) {
      await sleep(Math.min(5_000, 500 * 2 ** Math.min(attempt - 1, 4)));
      continue;
    }

    throw new Error(
      `Live run start failed with ${startResponse.status()} ${startResponse.statusText()} after ${attempt} attempt(s): ${responseText}`,
    );
  }
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

  const { runId } = await startRunViaApi(request, accessToken, {
    versionId,
    inputJson: {
      request: "Review and approve a controlled outbound refund test.",
    },
  });

  return {
    companyId,
    versionId,
    runId,
  };
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
        timeout: 60_000,
        message: `Timed out waiting for run ${runId} to reach a terminal state.`,
      },
    )
    .toMatch(/^(succeeded|failed|canceled)$/);

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

export function apiBaseUrl() {
  return API_BASE_URL;
}
