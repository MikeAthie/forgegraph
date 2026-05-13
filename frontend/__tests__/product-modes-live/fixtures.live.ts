import { expect, type APIRequestContext, type APIResponse, type Page, type TestInfo } from "@playwright/test";
import fs from "fs";
import os from "os";
import path from "path";

import {
  buildCompanyGraphJson,
  buildCompanyProfile,
  type CompanyDepartment,
  type CompanyProfile,
} from "../../lib/company-workspace";
import { createTestUser, ensureUserRegistered, getAccessToken, apiBaseUrl, type TestUser } from "../e2e/live-helpers";

const API_BASE_URL = apiBaseUrl();
const LIVE_LLM_PLACEHOLDER_KEYS = new Set(["", "playwright-openai-key", "test-openai-key", "sk-test"]);
const LIVE_LLM_MOCK_BASE_PATTERN = /127\.0\.0\.1:8011|localhost:8011|playwright-openai-mock/i;
const LOCAL_OPENAI_COMPATIBLE_BASE_PATTERN =
  /127\.0\.0\.1:12434|localhost:12434|host\.docker\.internal:12434|ollama|lmstudio|localai|vllm/i;
const LIVE_SQLITE_LOCK_RETRY_DELAYS_MS = [250, 500, 1_000, 2_000, 4_000];
const LIVE_SQLITE_SETUP_LOCK_TIMEOUT_MS = 120_000;
const LIVE_SQLITE_SETUP_LOCK_POLL_MS = 250;
const SQLITE_LOCK_PATTERNS = [
  /database is locked/i,
  /database table is locked/i,
  /database schema is locked/i,
  /sqlite_busy/i,
  /sqlite_locked/i,
];

export const liveLegacyCompanyName = "Legacy Eyewear";
export const forbiddenLegacyFunctionCompanies = [
  "Legacy Marketing",
  "Legacy Accounting",
  "Legacy Legal",
  "Legacy Consulting",
] as const;

export function liveProductModeRunNamespace(testInfo: TestInfo): string {
  return `product-mode-live-${liveProductModeRunIdSegment()}-w${testInfo.workerIndex}`;
}

export type LiveProductModeApiRequest = {
  method: string;
  url: string;
  pathname: string;
};

type LiveProvider = "openai" | "google" | "openrouter" | "anthropic";

type LiveLlmConfig = {
  provider: LiveProvider;
  llmMode: "managed" | "byok";
  model: string;
  apiKey?: string;
  apiKeyEnv?: string;
};

type ApiSuccess<T> = {
  data: T;
};

type GraphNode = {
  id: string;
  type: string;
  name?: string;
  config?: Record<string, unknown>;
};

type GraphJson = {
  nodes: GraphNode[];
  edges: Array<{ id?: string; from: string; to: string }>;
  metadata: Record<string, unknown>;
  editor_state?: Record<string, unknown>;
};

type PackSummary = {
  pack_id: string;
  display_name?: string;
};

type PackInstallation = {
  id: string;
  pack_id: string;
  role: "primary" | "addon";
  status: string;
  namespace: string;
};

type PeriodicReview = {
  id: string;
  display_name: string;
  current_due_period: {
    period_start: string;
    period_end: string;
  };
};

type MetricSnapshot = {
  id: string;
  company_id: string;
};

type WorkArtifact = {
  id: string;
  company_id: string;
  title: string;
  artifact_type: string;
  content?: unknown;
};

type ReportRun = {
  id: string;
  company_id: string;
  artifact: WorkArtifact | null;
  artifact_revision_id?: string | null;
  generated_sections?: unknown;
};

type StateProjection = {
  id: string;
  company_id: string;
  projection_type: string;
  display_label: string;
  summary?: string;
};

export type LiveRunDetail = {
  id: string;
  graph_id: string;
  status: string;
  output_json?: Record<string, unknown> | null;
  input_json?: Record<string, unknown> | null;
  error_message?: string | null;
  node_runs?: Array<{
    node_id: string;
    node_type: string;
    status: string;
    output_json?: Record<string, unknown> | null;
    error_message?: string | null;
  }>;
};

export type LiveLegacyProductModeFixture = {
  user: TestUser;
  accessToken: string;
  organizationId: string;
  companyId: string;
  versionId: string;
  llm: Omit<LiveLlmConfig, "apiKey"> & { credentialId?: string };
  installedPacks: PackInstallation[];
  programId: string | null;
  contextArtifact: WorkArtifact;
};

export type LiveLegacyIsolationFixture = LiveLegacyProductModeFixture & {
  atlasOperator: TestUser;
  legacyCustomer: TestUser;
  legacyCustomerAccessToken: string;
  otherClientUser: TestUser;
  otherClientAccessToken: string;
  otherClientCompanyId: string;
  otherClientCompanyName: string;
  report: LiveReportResult;
};

export type LiveReportResult = {
  review: PeriodicReview;
  metricSnapshot: MetricSnapshot;
  reportRun: ReportRun;
  serviceHistoryProjection: StateProjection | null;
  currentStateProjection: StateProjection | null;
};

export function liveLlmSkipReason(): string | null {
  if ((process.env.LIVE_LLM_E2E ?? "").toLowerCase() !== "true") {
    return "Set LIVE_LLM_E2E=true to run the opt-in live LLM product-mode suite.";
  }

  const resolved = resolveLiveLlmConfig();
  if (!resolved) {
    return [
      "Set real LLM credentials before running live product-mode E2E.",
      "Supported env names: OPENAI_API_KEY with a non-mock OPENAI_BASE_URL, local OpenAI-compatible LLM env,",
      "GEMINI_LEGACY, GEMINI_API_KEY, GOOGLE_API_KEY, OPENROUTER, OPENROUTER_API_KEY, or ANTHROPIC_API_KEY.",
    ].join(" ");
  }

  return null;
}

export function collectLiveProductModeApiRequests(page: Page): LiveProductModeApiRequest[] {
  const apiRequests: LiveProductModeApiRequest[] = [];
  page.on("request", (request) => {
    const url = new URL(request.url());
    if (!url.pathname.startsWith("/api/")) {
      return;
    }
    apiRequests.push({
      method: request.method(),
      url: request.url(),
      pathname: url.pathname,
    });
  });
  return apiRequests;
}

export function sawLiveApiPath(apiRequests: LiveProductModeApiRequest[], pathname: string): boolean {
  return apiRequests.some((request) => request.pathname === pathname);
}

export function sawLiveCompanyScopedQuery(
  apiRequests: LiveProductModeApiRequest[],
  pathname: string,
  companyId: string,
): boolean {
  return apiRequests.some((request) => {
    const url = new URL(request.url);
    return url.pathname === pathname && url.searchParams.get("company_id") === companyId;
  });
}

export function verticalLiveProductModeApiRequests(
  apiRequests: LiveProductModeApiRequest[],
  forbiddenPattern: RegExp = /\/api\/(?:marketing|growth-marketing|digital-marketing|marketing-campaigns)(?:\/|$)/i,
): LiveProductModeApiRequest[] {
  return apiRequests.filter((request) => forbiddenPattern.test(request.pathname));
}

export async function seedLiveLegacyProductMode(
  request: APIRequestContext,
  testInfo: TestInfo,
): Promise<LiveLegacyProductModeFixture> {
  return withLiveFixtureSetupLock(testInfo, () => seedLiveLegacyProductModeUnlocked(request, testInfo));
}

async function seedLiveLegacyProductModeUnlocked(
  request: APIRequestContext,
  testInfo: TestInfo,
): Promise<LiveLegacyProductModeFixture> {
  const llm = resolveLiveLlmConfig();
  if (!llm) {
    throw new Error(liveLlmSkipReason() ?? "Live LLM credentials are not configured.");
  }

  const namespace = liveProductModeRunNamespace(testInfo);
  const user = createTestUser(testInfo, `${namespace}-operator`);
  await ensureUserRegistered(request, user);
  const accessToken = await getAccessToken(request, user);
  const organizationId = await getDefaultOrganizationId(request, accessToken);
  const credentialId =
    llm.llmMode === "byok" ? await createLiveCredential(request, accessToken, llm, testInfo) : undefined;

  const { companyId, versionId } = await createLiveLegacyCompany(request, accessToken, {
    llm,
    credentialId,
    namespace,
    workerIndex: testInfo.workerIndex,
  });

  const availablePacks = await listAvailablePacks(request, accessToken);
  const installedPacks = await installAvailableLegacyPacks(request, accessToken, companyId, availablePacks, testInfo);
  expect(installedPacks.filter((pack) => pack.role === "primary")).toHaveLength(1);
  expect(installedPacks.filter((pack) => pack.role === "addon").length).toBeGreaterThanOrEqual(1);

  const programId = await createLegacyProgramIfPossible(request, accessToken, companyId, installedPacks, testInfo);
  const contextArtifact = await createLegacyContextArtifact(request, accessToken, companyId, programId, testInfo);

  return {
    user,
    accessToken,
    organizationId,
    companyId,
    versionId,
    llm: {
      provider: llm.provider,
      llmMode: llm.llmMode,
      model: llm.model,
      apiKeyEnv: llm.apiKeyEnv,
      credentialId,
    },
    installedPacks,
    programId,
    contextArtifact,
  };
}

export async function seedLiveLegacyIsolationProductMode(
  request: APIRequestContext,
  testInfo: TestInfo,
): Promise<LiveLegacyIsolationFixture> {
  return withLiveFixtureSetupLock(testInfo, async () => {
    const fixture = await seedLiveLegacyProductModeUnlocked(request, testInfo);
    const report = await createLiveReportFromSeededContext(request, fixture.accessToken, fixture, testInfo);
    const namespace = liveProductModeRunNamespace(testInfo);
    const legacyCustomer = await createRegisteredLiveUser(request, testInfo, `${namespace}-legacy-customer`);
    await addOrganizationMember(request, fixture.accessToken, legacyCustomer.user.email, "viewer");
    await switchDefaultOrganization(request, legacyCustomer.accessToken, fixture.organizationId);
    await createCompanyAssignment(request, fixture.accessToken, {
      companyId: fixture.companyId,
      email: legacyCustomer.user.email,
      role: "viewer",
    });

    const otherClient = await createRegisteredLiveUser(request, testInfo, `${namespace}-other-client`);
    const otherClientCompanyName = `Unrelated Client ${namespace}`;
    const otherClientCompanyId = await createOtherClientCompany(
      request,
      otherClient.accessToken,
      otherClientCompanyName,
      testInfo,
    );

    return {
      ...fixture,
      atlasOperator: fixture.user,
      legacyCustomer: legacyCustomer.user,
      legacyCustomerAccessToken: legacyCustomer.accessToken,
      otherClientUser: otherClient.user,
      otherClientAccessToken: otherClient.accessToken,
      otherClientCompanyId,
      otherClientCompanyName,
      report,
    };
  });
}

export async function waitForLiveRunTerminal(
  request: APIRequestContext,
  accessToken: string,
  runId: string,
  timeout = 180_000,
): Promise<LiveRunDetail> {
  let latestRun: LiveRunDetail | null = null;

  await expect
    .poll(
      async () => {
        const response = await request.get(`${API_BASE_URL}/api/runs/${runId}`, {
          headers: authHeaders(accessToken),
          timeout: 30_000,
        });
        expect(response.ok()).toBeTruthy();
        const body = (await response.json()) as ApiSuccess<LiveRunDetail>;
        latestRun = body.data;
        return body.data.status;
      },
      {
        timeout,
        intervals: [2_000, 3_000, 5_000],
        message: `Timed out waiting for live run ${runId} to reach a terminal state.`,
      },
    )
    .toMatch(/^(succeeded|failed|canceled)$/);

  if (!latestRun) {
    throw new Error(`Run ${runId} did not return detail during polling.`);
  }
  return latestRun;
}

export async function createLiveReportFromSeededContext(
  request: APIRequestContext,
  accessToken: string,
  fixture: LiveLegacyProductModeFixture,
  testInfo: TestInfo,
): Promise<LiveReportResult> {
  return createLiveReportFromSource(request, accessToken, fixture, testInfo, {
    id: fixture.contextArtifact.id,
    notes:
      "Seeded live product-mode isolation report for Legacy Eyewear using NC-29026 inventory and GAGA price-book context.",
  });
}

export async function createLiveReportFromCompletedRun(
  request: APIRequestContext,
  accessToken: string,
  fixture: LiveLegacyProductModeFixture,
  run: LiveRunDetail,
  testInfo: TestInfo,
): Promise<LiveReportResult> {
  return createLiveReportFromSource(request, accessToken, fixture, testInfo, {
    id: run.id,
    notes: `Live LLM operation ${run.id} completed for Legacy Eyewear using NC-29026 inventory and GAGA price-book context.`,
  });
}

async function createLiveReportFromSource(
  request: APIRequestContext,
  accessToken: string,
  fixture: LiveLegacyProductModeFixture,
  testInfo: TestInfo,
  source: { id: string; notes: string },
): Promise<LiveReportResult> {
  const review = await getPrimaryPeriodicReview(request, accessToken, fixture, testInfo);
  const metricSnapshot = await createMetricSnapshot(request, accessToken, fixture, review, testInfo);
  const reportRun = await runPeriodicReview(request, accessToken, review, metricSnapshot, source, testInfo);
  const serviceHistoryProjection = await findProjection(request, accessToken, fixture.companyId, "client_service_history");
  const currentStateProjection = await findProjection(request, accessToken, fixture.companyId, "currently_true_state");

  expect(reportRun.company_id).toBe(fixture.companyId);
  expect(reportRun.artifact?.company_id).toBe(fixture.companyId);
  expect(reportRun.artifact?.title).toBeTruthy();
  expect(reportRun.artifact_revision_id).toBeTruthy();

  return {
    review,
    metricSnapshot,
    reportRun,
    serviceHistoryProjection,
    currentStateProjection,
  };
}

async function createRegisteredLiveUser(
  request: APIRequestContext,
  testInfo: TestInfo,
  prefix: string,
): Promise<{ user: TestUser; accessToken: string }> {
  const user = createTestUser(testInfo, prefix);
  await ensureUserRegistered(request, user);
  return { user, accessToken: await getAccessToken(request, user) };
}

function resolveLiveLlmConfig(): LiveLlmConfig | null {
  const requestedProvider = normalizeProvider(process.env.LIVE_LLM_PROVIDER);
  if (requestedProvider) {
    return configForProvider(requestedProvider);
  }

  return (
    configForProvider("openai") ??
    configForProvider("google") ??
    configForProvider("openrouter") ??
    configForProvider("anthropic")
  );
}

function configForProvider(provider: LiveProvider): LiveLlmConfig | null {
  if (provider === "openai") {
    const apiKey = cleanEnv("OPENAI_API_KEY");
    const baseUrl = firstConfiguredBaseUrl([
      "OPENAI_BASE_URL",
      "OPENAI_API_BASE_URL",
      "LOCAL_LLM_BASE_URL",
      "PLAYWRIGHT_LOCAL_LLM_URL",
      "PLAYWRIGHT_DOCKER_LOCAL_LLM_URL",
    ]);
    const isLocalOpenAICompatible = Boolean(baseUrl && LOCAL_OPENAI_COMPATIBLE_BASE_PATTERN.test(baseUrl));
    if (!baseUrl || LIVE_LLM_MOCK_BASE_PATTERN.test(baseUrl) || (!isRealApiKey(apiKey) && !isLocalOpenAICompatible)) {
      return null;
    }
    return {
      provider,
      llmMode: "managed",
      model:
        cleanEnv("LIVE_LLM_MODEL") ||
        cleanEnv("OPENAI_MODEL") ||
        cleanEnv("PLAYWRIGHT_LOCAL_LLM_MODEL") ||
        "gpt-4.1-mini",
    };
  }

  if (provider === "google") {
    const found = firstEnv(["GEMINI_LEGACY", "GEMINI_API_KEY", "GOOGLE_API_KEY"]);
    if (!found) {
      return null;
    }
    return {
      provider,
      llmMode: "byok",
      model: cleanEnv("LIVE_LLM_MODEL") || cleanEnv("GEMINI_TEXT_MODEL") || "gemini-2.5-flash",
      apiKey: found.value,
      apiKeyEnv: found.name,
    };
  }

  if (provider === "openrouter") {
    const found = firstEnv(["OPENROUTER", "OPENROUTER_API_KEY"]);
    if (!found) {
      return null;
    }
    return {
      provider,
      llmMode: "byok",
      model: cleanEnv("LIVE_LLM_MODEL") || cleanEnv("OPENROUTER_MODEL") || "google/gemini-2.5-flash",
      apiKey: found.value,
      apiKeyEnv: found.name,
    };
  }

  const found = firstEnv(["ANTHROPIC_API_KEY"]);
  if (!found) {
    return null;
  }
  return {
    provider,
    llmMode: "byok",
    model: cleanEnv("LIVE_LLM_MODEL") || cleanEnv("ANTHROPIC_MODEL") || "claude-3-5-sonnet-latest",
    apiKey: found.value,
    apiKeyEnv: found.name,
  };
}

function normalizeProvider(value: string | undefined): LiveProvider | null {
  const normalized = (value ?? "").trim().toLowerCase();
  if (normalized === "openai" || normalized === "google" || normalized === "openrouter" || normalized === "anthropic") {
    return normalized;
  }
  return null;
}

function cleanEnv(name: string): string {
  return (process.env[name] ?? "").trim();
}

function firstEnv(names: string[]): { name: string; value: string } | null {
  for (const name of names) {
    const value = cleanEnv(name);
    if (isRealApiKey(value)) {
      return { name, value };
    }
  }
  return null;
}

function firstConfiguredBaseUrl(names: string[]): string {
  for (const name of names) {
    const value = cleanEnv(name);
    if (value) {
      return value;
    }
  }
  return "";
}

function isRealApiKey(value: string): boolean {
  const normalized = value.trim();
  if (LIVE_LLM_PLACEHOLDER_KEYS.has(normalized.toLowerCase())) {
    return false;
  }
  return normalized.length >= 8;
}

async function getDefaultOrganizationId(request: APIRequestContext, accessToken: string): Promise<string> {
  const orgResponse = await request.get(`${API_BASE_URL}/api/orgs/me`, {
    headers: authHeaders(accessToken),
  });
  if (orgResponse.ok()) {
    const body = (await orgResponse.json()) as {
      data?: { organization?: { id?: string } };
    };
    const organizationId = body.data?.organization?.id;
    if (organizationId) {
      return organizationId;
    }
  }

  const meResponse = await request.get(`${API_BASE_URL}/api/auth/me`, {
    headers: authHeaders(accessToken),
  });
  if (meResponse.ok()) {
    const body = (await meResponse.json()) as { default_organization_id?: string };
    if (body.default_organization_id) {
      return body.default_organization_id;
    }
  }

  throw new Error("Could not resolve the default organization for the live product-mode user.");
}

async function createLiveCredential(
  request: APIRequestContext,
  accessToken: string,
  llm: LiveLlmConfig,
  testInfo: TestInfo,
): Promise<string> {
  const response = await postJsonWithRetry(request, `${API_BASE_URL}/api/credentials/`, {
    headers: authHeaders(accessToken),
    data: {
      provider: llm.provider,
      name: `${liveProductModeRunNamespace(testInfo)}-${llm.provider}-${Date.now()}`,
      api_key: llm.apiKey,
    },
  });
  await expectApiOk(response, "create live LLM credential");
  const body = (await response.json()) as ApiSuccess<{ id: string }>;
  return body.data.id;
}

async function addOrganizationMember(
  request: APIRequestContext,
  accessToken: string,
  email: string,
  role: "owner" | "admin" | "member" | "viewer",
): Promise<void> {
  const response = await postJsonWithRetry(request, `${API_BASE_URL}/api/orgs/members`, {
    headers: authHeaders(accessToken),
    data: { email, role },
  });
  if (response.ok() || response.status() === 409) {
    return;
  }
  await expectApiOk(response, `add ${email} to live product-mode organization`);
}

async function switchDefaultOrganization(
  request: APIRequestContext,
  accessToken: string,
  organizationId: string,
): Promise<void> {
  const response = await request.patch(`${API_BASE_URL}/api/orgs/current`, {
    headers: authHeaders(accessToken),
    data: { organization_id: organizationId },
  });
  await expectApiOk(response, "switch live product-mode organization");
}

async function createCompanyAssignment(
  request: APIRequestContext,
  accessToken: string,
  input: {
    companyId: string;
    email: string;
    role: "viewer" | "member" | "admin";
  },
): Promise<void> {
  const response = await postJsonWithRetry(request, `${API_BASE_URL}/api/company-assignments`, {
    headers: authHeaders(accessToken),
    data: {
      company_id: input.companyId,
      email: input.email,
      role: input.role,
      status: "active",
    },
  });
  await expectApiOk(response, `assign ${input.email} to live product-mode company`);
}

async function createLiveLegacyCompany(
  request: APIRequestContext,
  accessToken: string,
  options: {
    llm: LiveLlmConfig;
    credentialId?: string;
    namespace: string;
    workerIndex: number;
  },
): Promise<{ companyId: string; versionId: string }> {
  const objective =
    "Run a live Legacy Eyewear operating review using one Company boundary, multiple installed capabilities, " +
    "inventory context, price-book context, brand guidelines, and business constraints.";
  const profile = buildCompanyProfile({
    companyName: liveLegacyCompanyName,
    companyType: "Eyewear Company",
    objective,
    autonomyMode: "assisted",
    aiAccessMode: options.llm.llmMode,
    intelligenceProvider: options.llm.provider,
    byokCredentialId: options.credentialId ?? null,
    departments: [legacyLiveDepartment()],
    skills: ["Reporting", "Planning", "Inventory review"],
  });

  const graphResponse = await postJsonWithRetry(request, `${API_BASE_URL}/api/graphs/`, {
    headers: authHeaders(accessToken),
    data: {
      name: liveLegacyCompanyName,
      description: `${objective} Playwright namespace: ${options.namespace}.`,
    },
  });
  await expectApiOk(graphResponse, "create live Legacy company");
  const graphBody = (await graphResponse.json()) as ApiSuccess<{ id: string }>;
  const companyId = graphBody.data.id;

  const versionResponse = await postJsonWithRetry(request, `${API_BASE_URL}/api/graphs/${companyId}/versions`, {
    headers: authHeaders(accessToken),
    data: {
      graph_json: buildLiveLegacyGraphJson(profile, options.llm, options.namespace, options.workerIndex),
    },
  });
  await expectApiOk(versionResponse, "create live Legacy graph version");
  const versionBody = (await versionResponse.json()) as ApiSuccess<{ id: string }>;

  return { companyId, versionId: versionBody.data.id };
}

async function createOtherClientCompany(
  request: APIRequestContext,
  accessToken: string,
  companyName: string,
  testInfo: TestInfo,
): Promise<string> {
  const objective =
    "Keep this unrelated client isolated from Legacy Eyewear while product-mode tests exercise concurrent access.";
  const profile = buildCompanyProfile({
    companyName,
    companyType: "Control Client",
    objective,
    autonomyMode: "assisted",
    aiAccessMode: "managed",
    departments: [
      {
        id: "control-client-ops",
        label: "Control Client Ops",
        responsibility: "Provides a separate company boundary for live product-mode isolation checks.",
        tools: ["Portfolio review"],
        category: "department",
      },
    ],
    skills: ["Portfolio review"],
  });

  const graphResponse = await postJsonWithRetry(request, `${API_BASE_URL}/api/graphs/`, {
    headers: authHeaders(accessToken),
    data: {
      name: companyName,
      description: objective,
    },
  });
  await expectApiOk(graphResponse, "create unrelated live product-mode company");
  const graphBody = (await graphResponse.json()) as ApiSuccess<{ id: string }>;
  const companyId = graphBody.data.id;
  const graphJson = buildCompanyGraphJson(profile) as GraphJson;
  graphJson.metadata = {
    ...(graphJson.metadata ?? {}),
    product_mode_live_e2e: {
      run_namespace: liveProductModeRunNamespace(testInfo),
      worker_index: testInfo.workerIndex,
      isolation_company: "unrelated_client",
    },
  };

  const versionResponse = await postJsonWithRetry(request, `${API_BASE_URL}/api/graphs/${companyId}/versions`, {
    headers: commandHeaders(accessToken, liveCommandKey(testInfo, "other-client", companyId)),
    data: {
      graph_json: graphJson,
    },
  });
  await expectApiOk(versionResponse, "create unrelated live product-mode graph version");
  return companyId;
}

function legacyLiveDepartment(): CompanyDepartment {
  return {
    id: "legacy-operator-review",
    label: "Operator Review",
    responsibility:
      "Produces a concise backend-owned operating artifact from Legacy Eyewear inventory, price, brand, and constraint context.",
    tools: ["Inventory review", "Price book review", "Reporting"],
    category: "department",
  };
}

function buildLiveLegacyGraphJson(
  profile: CompanyProfile,
  llm: LiveLlmConfig,
  namespace: string,
  workerIndex: number,
): GraphJson {
  return {
    nodes: [
      {
        id: "legacy_live_product_mode_prompt",
        type: "prompt",
        name: "Legacy Product Mode Review",
        config: {
          provider: llm.provider,
          model: llm.model,
          temperature: 0.2,
          max_tokens: 900,
          stream: false,
          system_prompt:
            "You are an operator inside ForgeGraph. Return concise product work only. " +
            "Use company-scoped context; do not invent separate function companies.",
          prompt_template:
            "Create a reviewable generic operating artifact for {{ input.company_name }}. " +
            "Use this operation brief as the seeded company context: {{ input.operation_brief }}. " +
            "Return a title, a short body, three concrete observations, and next actions. " +
            "Mention at least one seeded inventory or price-book detail when it is present.",
        },
      },
      {
        id: "final_deliverable",
        type: "output",
        name: "Final Deliverable",
        config: {
          output_mapping: {
            title: "input.operation_brief",
            deliverable: "node.legacy_live_product_mode_prompt.output.response",
            company_name: "input.company_name",
            company_context: "input.operation_brief",
            provider: "node.legacy_live_product_mode_prompt.output.provider",
            model: "node.legacy_live_product_mode_prompt.output.model",
          },
        },
      },
    ],
    edges: [
      { id: "start-legacy-product-mode-prompt", from: "START", to: "legacy_live_product_mode_prompt" },
      { id: "legacy-product-mode-prompt-output", from: "legacy_live_product_mode_prompt", to: "final_deliverable" },
      { id: "legacy-product-mode-output-end", from: "final_deliverable", to: "END" },
    ],
    metadata: {
      name: profile.companyName,
      description: profile.objective,
      company_profile: profile,
      product_mode_live_e2e: {
        run_namespace: namespace,
        worker_index: workerIndex,
        provider: llm.provider,
        llm_mode: llm.llmMode,
      },
    },
    editor_state: {
      viewport: { x: 0, y: 0, zoom: 1 },
      nodePositions: {
        legacy_live_product_mode_prompt: { x: 160, y: 120 },
        final_deliverable: { x: 520, y: 120 },
      },
    },
  };
}

async function listAvailablePacks(request: APIRequestContext, accessToken: string): Promise<PackSummary[]> {
  const response = await request.get(`${API_BASE_URL}/api/operating-model-packs`, {
    headers: authHeaders(accessToken),
  });
  await expectApiOk(response, "list operating model packs");
  const body = (await response.json()) as ApiSuccess<{ packs: PackSummary[] }>;
  return body.data.packs;
}

async function installAvailableLegacyPacks(
  request: APIRequestContext,
  accessToken: string,
  companyId: string,
  availablePacks: PackSummary[],
  testInfo: TestInfo,
): Promise<PackInstallation[]> {
  const availablePackIds = new Set(availablePacks.map((pack) => pack.pack_id));
  const primaryPackId =
    ["legacy_eyewear_core.v1", "generic_ops.v1", "digital_marketing_pro.v1", "legal_ops_demo.v1"].find((packId) =>
      availablePackIds.has(packId),
    ) ?? null;
  if (!primaryPackId) {
    throw new Error("No installable operating-model pack is available for the live product-mode fixture.");
  }

  const addOnPackIds = [
    "digital_marketing_pro.v1",
    "accounting_ops_demo.v1",
    "legal_ops_demo.v1",
    "consulting_ops_demo.v1",
  ].filter((packId) => packId !== primaryPackId && availablePackIds.has(packId));

  const installed: PackInstallation[] = [];
  installed.push(await installCompanyPack(request, accessToken, companyId, primaryPackId, "primary", testInfo));
  for (const addOnPackId of addOnPackIds) {
    installed.push(await installCompanyPack(request, accessToken, companyId, addOnPackId, "addon", testInfo));
  }
  return installed;
}

async function installCompanyPack(
  request: APIRequestContext,
  accessToken: string,
  companyId: string,
  packId: string,
  role: "primary" | "addon",
  testInfo: TestInfo,
): Promise<PackInstallation> {
  const response = await postJsonWithRetry(
    request,
    `${API_BASE_URL}/api/companies/${companyId}/packs/install`,
    {
      headers: commandHeaders(accessToken, liveCommandKey(testInfo, "install", companyId, packId)),
      data: {
        pack_id: packId,
        role,
        config: {
          skip_graph_version: true,
          selected_services: ["Legacy Eyewear shared operating context", "Backend-owned reporting"],
        },
      },
    },
  );
  await expectApiOk(response, `install ${packId}`);
  const body = (await response.json()) as ApiSuccess<{ installation: PackInstallation }>;
  return body.data.installation;
}

async function createLegacyProgramIfPossible(
  request: APIRequestContext,
  accessToken: string,
  companyId: string,
  installedPacks: PackInstallation[],
  testInfo: TestInfo,
): Promise<string | null> {
  const dmpInstalled = installedPacks.some((pack) => pack.pack_id === "digital_marketing_pro.v1");
  if (!dmpInstalled) {
    return null;
  }

  const response = await postJsonWithRetry(
    request,
    `${API_BASE_URL}/api/companies/${companyId}/programs`,
    {
      headers: commandHeaders(accessToken, liveCommandKey(testInfo, "program", companyId)),
      data: {
        template_id: "dmp.engagement",
        pack_id: "digital_marketing_pro.v1",
        title: "Legacy Eyewear shared operating program",
        objective: "Keep Legacy Eyewear inventory, pricing, service history, and reporting under one Company.",
        metadata: {
          product_mode_live: true,
          company_boundary: "single_company_multiple_pack_installations",
        },
      },
    },
  );
  await expectApiOk(response, "create Legacy product-mode program");
  const body = (await response.json()) as ApiSuccess<{ program: { id: string } }>;
  return body.data.program.id;
}

async function createLegacyContextArtifact(
  request: APIRequestContext,
  accessToken: string,
  companyId: string,
  programId: string | null,
  testInfo: TestInfo,
): Promise<WorkArtifact> {
  const response = await postJsonWithRetry(
    request,
    `${API_BASE_URL}/api/work-artifacts`,
    {
      headers: commandHeaders(accessToken, liveCommandKey(testInfo, "context-artifact", companyId)),
      data: {
        company_id: companyId,
        program_id: programId,
        title: "Legacy Eyewear shared company context",
        artifact_type: "company_context",
        content: legacySeededContext(),
        metadata: {
          product_mode_live: true,
          source: "playwright_live_fixture",
        },
      },
    },
  );
  await expectApiOk(response, "create Legacy context artifact");
  const body = (await response.json()) as ApiSuccess<{ artifact: WorkArtifact }>;
  return body.data.artifact;
}

async function getPrimaryPeriodicReview(
  request: APIRequestContext,
  accessToken: string,
  fixture: LiveLegacyProductModeFixture,
  testInfo: TestInfo,
): Promise<PeriodicReview> {
  const response = await request.get(`${API_BASE_URL}/api/periodic-reviews`, {
    headers: authHeaders(accessToken),
    params: { company_id: fixture.companyId },
  });
  await expectApiOk(response, "list periodic reviews");
  const body = (await response.json()) as ApiSuccess<{ periodic_reviews: PeriodicReview[] }>;
  const review = body.data.periodic_reviews[0];
  if (review) {
    return review;
  }

  const createResponse = await postJsonWithRetry(
    request,
    `${API_BASE_URL}/api/periodic-reviews`,
    {
      headers: commandHeaders(accessToken, liveCommandKey(testInfo, "review-definition", fixture.companyId)),
      data: {
        company_id: fixture.companyId,
        program_id: fixture.programId,
        template_id: "legacy_live_product_mode_review.v1",
        display_name: "Legacy Eyewear live product-mode review",
        cadence: "monthly",
        timezone: "UTC",
        evaluation_profile_id: "",
        report_template_id: "legacy_live_product_mode_report.v1",
        history_projection_type: "client_service_history",
        enabled: true,
        metadata: {
          product_mode_live: true,
          architecture_boundary: "Organization -> Company -> PackInstallation -> generic primitives",
          source: "playwright_live_fixture",
          report_template: {
            id: "legacy_live_product_mode_report.v1",
            artifact_schema_id: "periodic_report",
            sections: ["summary", "metric_snapshot", "next_actions"],
          },
        },
      },
    },
  );
  await expectApiOk(createResponse, "create periodic review definition");
  const createBody = (await createResponse.json()) as ApiSuccess<{ periodic_review: PeriodicReview }>;
  return createBody.data.periodic_review;
}

async function createMetricSnapshot(
  request: APIRequestContext,
  accessToken: string,
  fixture: LiveLegacyProductModeFixture,
  review: PeriodicReview,
  testInfo: TestInfo,
): Promise<MetricSnapshot> {
  const response = await postJsonWithRetry(
    request,
    `${API_BASE_URL}/api/metric-snapshots`,
    {
      headers: commandHeaders(accessToken, liveCommandKey(testInfo, "metrics", fixture.companyId)),
      data: {
        company_id: fixture.companyId,
        program_id: fixture.programId,
        review_definition_id: review.id,
        period_start: review.current_due_period.period_start,
        period_end: review.current_due_period.period_end,
        metric_values: {
          social_engagement_rate: 3.4,
          meta_tiktok_ctr: 1.6,
          google_search_ctr: 5.2,
          landing_page_conversion: 15.5,
          roas: 3.2,
          email_open_rate: 26,
          email_click_rate: 3.1,
          customer_retention_rate: 78,
        },
        metric_sources: {
          inventory: "Legacy Eyewear seeded context",
          price_book: "Legacy Eyewear seeded context",
          context_artifact_id: fixture.contextArtifact.id,
        },
        source_type: "seed",
        notes: "Live product-mode E2E metrics for Legacy Eyewear. Includes NC-29026, GAGA, and quiet-status brand context.",
      },
    },
  );
  await expectApiOk(response, "create metric snapshot");
  const body = (await response.json()) as ApiSuccess<{ metric_snapshot: MetricSnapshot }>;
  return body.data.metric_snapshot;
}

async function runPeriodicReview(
  request: APIRequestContext,
  accessToken: string,
  review: PeriodicReview,
  metricSnapshot: MetricSnapshot,
  source: { id: string; notes: string },
  testInfo: TestInfo,
): Promise<ReportRun> {
  const response = await postJsonWithRetry(
    request,
    `${API_BASE_URL}/api/periodic-reviews/${review.id}/run`,
    {
      headers: commandHeaders(accessToken, liveCommandKey(testInfo, "review", review.id, source.id)),
      data: {
        metric_snapshot_id: metricSnapshot.id,
        force: true,
        notes: source.notes,
      },
    },
  );
  await expectApiOk(response, "run periodic review");
  const body = (await response.json()) as ApiSuccess<{ report_run?: ReportRun }>;
  if (!body.data.report_run) {
    throw new Error("Periodic review did not return a generic report_run.");
  }
  return body.data.report_run;
}

async function findProjection(
  request: APIRequestContext,
  accessToken: string,
  companyId: string,
  projectionType: string,
): Promise<StateProjection | null> {
  const response = await request.get(`${API_BASE_URL}/api/state-projections`, {
    headers: authHeaders(accessToken),
    params: {
      company_id: companyId,
      projection_type: projectionType,
    },
  });
  await expectApiOk(response, `list ${projectionType} projections`);
  const body = (await response.json()) as ApiSuccess<{ state_projections: StateProjection[] }>;
  return body.data.state_projections[0] ?? null;
}

export function legacyLiveOperationBrief(): string {
  return [
    "Prepare a reviewable operating artifact for Legacy Eyewear.",
    "Seeded context: inventory SKU NC-29026 has scarce stock behavior; GAGA, HENDRIX, WINEHOUSE, WATSON, and MAVERICK are priority eyewear products.",
    "Price-book context: premium sunglasses and optical frames must preserve margin discipline before promotional decisions.",
    "Brand guidelines: quiet-status luxury, Mexico City operators, concise service language, no public side effects.",
    "Business constraints: keep marketing, accounting, legal, and consulting as capabilities inside the same Company, not separate Companies.",
  ].join(" ");
}

function legacySeededContext(): Record<string, unknown> {
  return {
    inventory: {
      scarce_sku: "NC-29026",
      active_stock_units: 62,
      priority_products: ["GAGA", "HENDRIX", "WINEHOUSE", "WATSON", "MAVERICK"],
    },
    price_book: {
      posture: "premium_margin_discipline",
      discounting: "approval_required_before_live_offer",
    },
    brand_guidelines: {
      voice: "quiet-status luxury",
      market: "Mexico City",
      constraints: ["no live checkout", "no public outreach", "no procurement side effects"],
    },
    architecture_boundary: "Organization -> Company -> PackInstallation -> generic primitives",
  };
}

function liveCommandKey(testInfo: TestInfo, action: string, ...parts: string[]): string {
  return [liveProductModeRunNamespace(testInfo), safeNamespaceSegment(action), ...parts.map(safeNamespaceSegment)].join(
    ":",
  );
}

function safeNamespaceSegment(value: string): string {
  return (
    value
      .replace(/[^a-z0-9_.-]+/gi, "-")
      .replace(/^-+|-+$/g, "")
      .toLowerCase()
      .slice(0, 72) || "local"
  );
}

function authHeaders(accessToken: string): Record<string, string> {
  return { Authorization: `Bearer ${accessToken}` };
}

function commandHeaders(accessToken: string, idempotencyKey: string): Record<string, string> {
  return {
    ...authHeaders(accessToken),
    "Idempotency-Key": idempotencyKey,
  };
}

async function postJsonWithRetry(
  request: APIRequestContext,
  url: string,
  options: Parameters<APIRequestContext["post"]>[1],
): Promise<APIResponse> {
  let response: APIResponse | null = null;
  for (let attempt = 0; attempt <= LIVE_SQLITE_LOCK_RETRY_DELAYS_MS.length; attempt += 1) {
    response = await request.post(url, options);
    if (response.ok() || response.status() < 500 || attempt === LIVE_SQLITE_LOCK_RETRY_DELAYS_MS.length) {
      return response;
    }
    const responseText = await response.text();
    if (!isTransientSqliteLockResponse(response, responseText)) {
      return response;
    }
    await sleep(LIVE_SQLITE_LOCK_RETRY_DELAYS_MS[attempt]);
  }
  if (!response) {
    throw new Error(`POST ${url} did not return a response.`);
  }
  return response;
}

function isTransientSqliteLockResponse(response: APIResponse, responseText: string): boolean {
  if (response.status() < 500 || response.status() > 599) {
    return false;
  }
  return SQLITE_LOCK_PATTERNS.some((pattern) => pattern.test(responseText));
}

async function withLiveFixtureSetupLock<T>(testInfo: TestInfo, action: () => Promise<T>): Promise<T> {
  if ((process.env.USE_SQLITE ?? "").toLowerCase() !== "true") {
    return action();
  }

  const lockPath = path.join(
    os.tmpdir(),
    `forgegraph-product-mode-live-${liveProductModeRunIdSegment()}-sqlite-setup.lock`,
  );
  const startedAt = Date.now();
  let lockHandle: fs.promises.FileHandle | null = null;

  while (!lockHandle) {
    try {
      lockHandle = await fs.promises.open(lockPath, "wx");
      await lockHandle.writeFile(
        JSON.stringify({
          pid: process.pid,
          namespace: liveProductModeRunNamespace(testInfo),
          createdAt: new Date().toISOString(),
        }),
      );
    } catch (error) {
      if (!isFileAlreadyExistsError(error)) {
        throw error;
      }
      const removedStaleLock = await removeStaleLiveFixtureLock(lockPath);
      if (removedStaleLock) {
        continue;
      }
      if (Date.now() - startedAt > LIVE_SQLITE_SETUP_LOCK_TIMEOUT_MS) {
        throw new Error(`Timed out waiting for live SQLite fixture setup lock: ${lockPath}`);
      }
      await sleep(LIVE_SQLITE_SETUP_LOCK_POLL_MS);
    }
  }

  try {
    return await action();
  } finally {
    await lockHandle.close();
    await fs.promises.rm(lockPath, { force: true });
  }
}

async function removeStaleLiveFixtureLock(lockPath: string): Promise<boolean> {
  try {
    const stat = await fs.promises.stat(lockPath);
    const lockAgeMs = Date.now() - stat.mtimeMs;
    if (lockAgeMs > LIVE_SQLITE_SETUP_LOCK_TIMEOUT_MS) {
      await fs.promises.rm(lockPath, { force: true });
      return true;
    }
    return false;
  } catch (error) {
    if (!isFileNotFoundError(error)) {
      throw error;
    }
    return false;
  }
}

function isFileAlreadyExistsError(error: unknown): boolean {
  return typeof error === "object" && error !== null && "code" in error && error.code === "EEXIST";
}

function isFileNotFoundError(error: unknown): boolean {
  return typeof error === "object" && error !== null && "code" in error && error.code === "ENOENT";
}

function liveProductModeRunIdSegment(): string {
  return safeNamespaceSegment(process.env.PLAYWRIGHT_RUN_ID ?? "local");
}

function sleep(ms: number): Promise<void> {
  return new Promise((resolve) => setTimeout(resolve, ms));
}

async function expectApiOk(response: APIResponse, action: string): Promise<void> {
  if (response.ok()) {
    return;
  }
  throw new Error(`${action} failed with ${response.status()} ${response.statusText()}: ${await response.text()}`);
}
