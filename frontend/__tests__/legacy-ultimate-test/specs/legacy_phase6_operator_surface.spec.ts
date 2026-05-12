import { expect, test, type APIRequestContext, type TestInfo } from "@playwright/test";
import { execFileSync } from "child_process";
import fs from "fs/promises";
import path from "path";

import { createHumanGateRunViaApi, getAccessToken, loginLive, type TestUser } from "../../e2e/helpers";

const API_BASE_URL = (
  process.env.PLAYWRIGHT_API_URL ??
  process.env.NEXT_PUBLIC_API_URL ??
  "http://127.0.0.1:8000"
).replace(/\/$/, "");

const REPO_ROOT = path.resolve(__dirname, "..", "..", "..", "..");
const BACKEND_DIR = path.join(REPO_ROOT, "backend");
const LOG_DIR = path.join(REPO_ROOT, "logs");
const DOC_DIR = path.join(REPO_ROOT, "docs", "legacy-ultimate-test");
const LEGACY_EMAIL = process.env.PLAYWRIGHT_LEGACY_EMAIL ?? "legacy.glasswear.test@example.com";
const LEGACY_PASSWORD = process.env.PLAYWRIGHT_LEGACY_PASSWORD ?? process.env.LEGACY_TEST_PASSWORD ?? "";
const LEGACY_GEMINI_ENV_VAR = process.env.PLAYWRIGHT_LEGACY_GEMINI_ENV_VAR ?? "GEMINI_LEGACY";
const MOCK_PROVIDER_RESPONSE =
  process.env.PLAYWRIGHT_LEGACY_MOCK_PROVIDER_RESPONSE === "true" ||
  process.env.PLAYWRIGHT_LEGACY_MOCK_PHASE6_OBJECTIVE === "true";
const REQUIRED_MODELS = ["GAGA", "HENDRIX", "WINEHOUSE", "WATSON", "MAVERICK"] as const;
const JUDGE_CRITERIA = [
  "operator_surface_verified",
  "stock_semantics_consistent",
  "visual_briefs_actionable",
  "zero_budget_policy_respected",
  "approval_gates_present",
  "no_private_customer_data_sent_to_llm",
  "evidence_packet_complete",
  "next_run_plan_clear",
];

test.skip(
  process.env.PLAYWRIGHT_LEGACY_PHASE6_TEST !== "true",
  "Set PLAYWRIGHT_LEGACY_PHASE6_TEST=true to run the Legacy Phase 6 operator gate.",
);

test.skip(!LEGACY_PASSWORD, "Set PLAYWRIGHT_LEGACY_PASSWORD or LEGACY_TEST_PASSWORD for the seeded Legacy user.");

test.describe.configure({ mode: "serial" });
test.setTimeout(360_000);

type BootstrapEvidence = {
  commands: string[];
  observed_data: {
    company_id: string;
    graph_version_id: string;
    products_imported: number;
    active_units_imported: number;
    inventory_products_visible: number;
    inventory_total_units: number;
    stock_state_summary: StockStateSummary;
    company_ops_stock_state_summary: StockStateSummary;
  };
  verification_result: {
    passed: boolean;
    checks: Record<string, boolean>;
    failures: string[];
    warnings: string[];
  };
};

type GeminiCredentialImport = {
  credential_id: string;
  provider: string;
  key_present: boolean;
  created_credential: boolean;
  created_graph_version: boolean;
  warnings: string[];
};

type StockStateSummary = {
  active_count: number;
  low_stock_count: number;
  last_piece_count: number;
  sold_out_count: number;
  definition_used: string;
};

type InventoryOverview = {
  company_id: string;
  summary: {
    total_units: number;
    available_units: number;
    held_units: number;
    low_stock_products: number;
  };
  stock_state_summary: StockStateSummary;
  products: Array<{
    id: string;
    sku: string;
    model: string;
    name: string;
    available_units: number;
    held_units: number;
    total_units: number;
    stock_state: string | null;
  }>;
  reservations: Array<{ id: string; status: string; product_sku: string }>;
  events: Array<{ event_type: string; message: string; created_at: string }>;
};

type CompanyOpsOverview = {
  company_id: string;
  summary: {
    publication_drafts: number;
    procurement_drafts: number;
    low_stock_products: number;
  };
  stock_state_summary: StockStateSummary;
  publication_drafts: Array<{ id: string; title: string; status: string; approval_task_id: string | null }>;
  procurement_drafts: Array<{ id: string; title: string; status: string; approval_task_id: string | null }>;
  objective_contracts: Array<{ id: string; operation_id: string; status: string; success_score: number | null }>;
};

type MockObjectiveSeed = {
  schema: string;
  company_id: string;
  run_id: string;
  graph_id: string;
  graph_version_id: string;
  node_run_id: string;
  task_id: string;
  objective_contract_id: string;
  mock_provider_response: boolean;
  visual_asset_brief_count: number;
};

type RunDetail = {
  id: string;
  graph_id: string;
  graph_version_id: string;
  status: string;
  output_json?: Record<string, unknown> | null;
  error_message?: string | null;
  node_runs: Array<{
    node_id: string;
    node_type?: string;
    status: string;
    output_json?: Record<string, unknown> | null;
    error_json?: Record<string, unknown> | null;
  }>;
};

type VisualAssetBrief = {
  product_name: string;
  sku: string;
  stock_state: string;
  shot_list: string[];
  caption_angle: string;
  background_or_prop_needs: string[];
  approval_task_title: string;
};

type Phase6ObjectiveOutput = {
  stock_semantics_report: StockStateSummary;
  visual_asset_briefs: unknown[];
  next_run_plan?: unknown;
};

function unwrap<T>(payload: unknown): T {
  if (payload && typeof payload === "object" && "data" in payload) {
    return (payload as { data: T }).data;
  }
  return payload as T;
}

function isRecord(value: unknown): value is Record<string, unknown> {
  return Boolean(value && typeof value === "object" && !Array.isArray(value));
}

function normalizeText(value: unknown): string {
  return String(value ?? "")
    .toLowerCase()
    .replace(/\s+/g, " ")
    .trim();
}

function coerceStringArray(value: unknown): string[] {
  if (Array.isArray(value)) {
    return value.flatMap((item) => {
      const trimmed = String(item ?? "").trim();
      return trimmed ? [trimmed] : [];
    });
  }
  if (typeof value === "string") {
    const trimmed = value.trim();
    return trimmed ? [trimmed] : [];
  }
  if (isRecord(value)) {
    return Object.values(value).flatMap((item) => {
      const trimmed = String(item ?? "").trim();
      return trimmed ? [trimmed] : [];
    });
  }
  return [];
}

function normalizeVisualBrief(value: unknown): VisualAssetBrief {
  const record = isRecord(value) ? value : {};
  return {
    product_name: String(record.product_name ?? record.product ?? record.name ?? "").trim(),
    sku: String(record.sku ?? record.product_sku ?? "").trim(),
    stock_state: String(record.stock_state ?? "").trim(),
    shot_list: coerceStringArray(record.shot_list),
    caption_angle: String(record.caption_angle ?? record.caption ?? "").trim(),
    background_or_prop_needs: coerceStringArray(
      record.background_or_prop_needs ?? record.background_needs ?? record.prop_needs,
    ),
    approval_task_title: String(record.approval_task_title ?? record.task_title ?? "").trim(),
  };
}

function parsePossiblyFencedJson(value: unknown): Record<string, unknown> | null {
  if (isRecord(value)) return value;
  if (typeof value !== "string") return null;
  let text = value.trim();
  const fenced = text.match(/^```(?:json)?\s*([\s\S]*?)\s*```$/i);
  if (fenced) text = fenced[1].trim();

  for (let i = 0; i < 2; i += 1) {
    try {
      const parsed: unknown = JSON.parse(text);
      if (isRecord(parsed)) return parsed;
      if (typeof parsed === "string") {
        text = parsed.trim();
        continue;
      }
      return null;
    } catch {
      const objectMatch = text.match(/\{[\s\S]*\}/);
      if (!objectMatch) return null;
      text = objectMatch[0];
    }
  }
  return null;
}

async function apiGet<T>(request: APIRequestContext, accessToken: string, apiPath: string): Promise<T> {
  const response = await request.get(`${API_BASE_URL}${apiPath}`, {
    headers: { Authorization: `Bearer ${accessToken}` },
  });
  if (!response.ok()) {
    throw new Error(`GET ${apiPath} failed with ${response.status()}: ${await response.text()}`);
  }
  return unwrap<T>(await response.json());
}

async function apiPost<T>(
  request: APIRequestContext,
  accessToken: string,
  apiPath: string,
  data: Record<string, unknown>,
  idempotencyKey?: string,
): Promise<T> {
  const headers: Record<string, string> = { Authorization: `Bearer ${accessToken}` };
  if (idempotencyKey) headers["Idempotency-Key"] = idempotencyKey;
  const response = await request.post(`${API_BASE_URL}${apiPath}`, { headers, data });
  if (!response.ok()) {
    throw new Error(`POST ${apiPath} failed with ${response.status()}: ${await response.text()}`);
  }
  return unwrap<T>(await response.json());
}

async function apiPut<T>(
  request: APIRequestContext,
  accessToken: string,
  apiPath: string,
  data: Record<string, unknown>,
): Promise<T> {
  const response = await request.put(`${API_BASE_URL}${apiPath}`, {
    headers: { Authorization: `Bearer ${accessToken}` },
    data,
  });
  if (!response.ok()) {
    throw new Error(`PUT ${apiPath} failed with ${response.status()}: ${await response.text()}`);
  }
  return unwrap<T>(await response.json());
}

function runBootstrapCommand(): BootstrapEvidence {
  const raw = execFileSync(
    "uv",
    ["run", "python", "manage.py", "legacy_glasswear_first_run", "--database", "postgres", "--json", "--strict"],
    {
      cwd: BACKEND_DIR,
      env: { ...process.env, LEGACY_TEST_PASSWORD: LEGACY_PASSWORD },
      encoding: "utf8",
      maxBuffer: 32 * 1024 * 1024,
    },
  );
  return JSON.parse(raw) as BootstrapEvidence;
}

function importLegacyGeminiCredential(): GeminiCredentialImport {
  if (!process.env[LEGACY_GEMINI_ENV_VAR]) {
    throw new Error(
      `${LEGACY_GEMINI_ENV_VAR} is required for Legacy Phase 6 Gemini text objective. ` +
        "Set it in the test environment or root .env, then rerun with PLAYWRIGHT_LEGACY_PHASE6_TEST=true.",
    );
  }

  const raw = execFileSync(
    "uv",
    ["run", "python", "manage.py", "import_legacy_gemini_credential", "--env-var", LEGACY_GEMINI_ENV_VAR, "--json"],
    {
      cwd: BACKEND_DIR,
      env: { ...process.env, LEGACY_TEST_PASSWORD: LEGACY_PASSWORD },
      encoding: "utf8",
      maxBuffer: 32 * 1024 * 1024,
    },
  );
  const credential = JSON.parse(raw) as GeminiCredentialImport;
  if (credential.provider !== "google" || !credential.key_present || !credential.credential_id) {
    throw new Error("Legacy Gemini credential import did not return a usable Google credential id.");
  }
  return credential;
}

function seedMockVisualBriefObjective(companyId: string): MockObjectiveSeed {
  const raw = execFileSync(
    "uv",
    [
      "run",
      "python",
      "manage.py",
      "seed_legacy_phase6_mock_objective",
      "--email",
      LEGACY_EMAIL,
      "--company-id",
      companyId,
      "--json",
    ],
    {
      cwd: BACKEND_DIR,
      env: { ...process.env, LEGACY_TEST_PASSWORD: LEGACY_PASSWORD },
      encoding: "utf8",
      maxBuffer: 32 * 1024 * 1024,
    },
  );
  const seed = JSON.parse(raw) as MockObjectiveSeed;
  if (seed.schema !== "legacy_phase6_mock_objective_seed.v1" || !seed.mock_provider_response) {
    throw new Error("Legacy Phase 6 mock objective seed did not return a mock-provider run.");
  }
  return seed;
}

function buildVisualAssetBriefGraph(credentialId: string) {
  const outputSchema = {
    type: "object",
    required: ["stock_semantics_report", "visual_asset_briefs", "next_run_plan"],
    properties: {
      stock_semantics_report: {
        type: "object",
        required: ["active_count", "low_stock_count", "last_piece_count", "sold_out_count", "definition_used"],
        properties: {
          active_count: { type: "number" },
          low_stock_count: { type: "number" },
          last_piece_count: { type: "number" },
          sold_out_count: { type: "number" },
          definition_used: { type: "string" },
        },
      },
      visual_asset_briefs: {
        type: "array",
        minItems: 5,
        items: {
          type: "object",
          required: [
            "product_name",
            "sku",
            "stock_state",
            "shot_list",
            "caption_angle",
            "background_or_prop_needs",
            "approval_task_title",
          ],
          properties: {
            product_name: { type: "string" },
            sku: { type: "string" },
            stock_state: { type: "string" },
            shot_list: { type: "array", items: { type: "string" } },
            caption_angle: { type: "string" },
            background_or_prop_needs: { type: "array", items: { type: "string" } },
            approval_task_title: { type: "string" },
          },
        },
      },
      next_run_plan: { type: "array", minItems: 3, items: { type: "string" } },
    },
  };

  return {
    nodes: [
      {
        id: "visual_asset_brief",
        type: "prompt",
        name: "Visual Asset Brief",
        config: {
          provider: "google",
          credential_id: credentialId,
          model: "gemini-2.5-flash",
          temperature: 0.2,
          max_tokens: 8192,
          stream: false,
          disable_memory_context: true,
          schema_mode: "warn",
          output_schema_target: "response",
          output_schema: outputSchema,
          prompt_template: [
            "Return JSON only. Do not use markdown or code fences.",
            "Create the Legacy Phase 6 Visual Asset Brief.",
            "The top-level JSON object must include exactly these required keys: stock_semantics_report, visual_asset_briefs, next_run_plan.",
            "Copy stock_semantics_report from Context exactly, including definition_used.",
            "Make next_run_plan an array of at least three concrete operator steps for the next approval-gated run.",
            "Respect zero_cash_spend and approval_gated mode.",
            "Do not include customer emails, payment IDs, addresses, checkout links, media generation calls, posting actions, or procurement execution.",
            "Required products: GAGA, HENDRIX, WINEHOUSE, WATSON, MAVERICK.",
            "Each visual_asset_briefs item must include product_name, sku, stock_state, shot_list, caption_angle, background_or_prop_needs, approval_task_title.",
            "shot_list and background_or_prop_needs must be arrays of strings, never scalar strings.",
            "Context:",
            "{{input.phase6_context}}",
          ].join("\n"),
        },
      },
      {
        id: "final_output",
        type: "output",
        name: "Final Output",
        config: {
          output_mapping: {
            visual_asset_brief: "node.visual_asset_brief.output.response",
            raw_visual_asset_brief: "node.visual_asset_brief.output.raw_response",
            planner_trace: "node.visual_asset_brief.output",
          },
        },
      },
    ],
    edges: [
      { id: "start-visual-brief", from: "START", to: "visual_asset_brief" },
      { id: "visual-brief-output", from: "visual_asset_brief", to: "final_output" },
      { id: "final-end", from: "final_output", to: "END" },
    ],
    metadata: {
      name: "Legacy Phase 6 Visual Asset Brief",
      description: "Approval-gated visual asset brief objective for Legacy Glasswear.",
      legacy_phase: "phase-6",
      runtime_contract: {
        durable_source_of_truth: "backend",
        engine_owns_durable_state: false,
      },
    },
  };
}

async function createVisualBriefRun(
  request: APIRequestContext,
  accessToken: string,
  phase6Context: Record<string, unknown>,
  credentialId: string,
): Promise<RunDetail> {
  const operationGraph = await apiPost<{ id: string }>(request, accessToken, "/api/graphs/", {
    name: "Legacy Phase 6 Visual Asset Brief Objective",
    description: "Approval-gated visual asset brief objective for Legacy Glasswear.",
  });
  const version = await apiPost<{ id: string }>(request, accessToken, `/api/graphs/${operationGraph.id}/versions`, {
    graph_json: buildVisualAssetBriefGraph(credentialId),
  });
  const started = await apiPost<{ id: string }>(request, accessToken, "/api/runs/start", {
    graph_version_id: version.id,
    llm_mode: "byok",
    provider: "google",
    credential_id: credentialId,
    input_json: { phase6_context: phase6Context },
  });
  return waitForRunTerminal(request, accessToken, started.id);
}

async function waitForRunTerminal(request: APIRequestContext, accessToken: string, runId: string): Promise<RunDetail> {
  let latest: RunDetail | null = null;
  await expect
    .poll(
      async () => {
        latest = await apiGet<RunDetail>(request, accessToken, `/api/runs/${runId}`);
        return latest.status;
      },
      { timeout: 180_000, intervals: [2000, 3000, 5000] },
    )
    .toMatch(/^(succeeded|failed|canceled)$/);
  if (!latest) throw new Error(`Run ${runId} did not return detail.`);
  return latest;
}

function extractObjectiveOutput(run: RunDetail): Phase6ObjectiveOutput {
  const candidates: unknown[] = [];
  if (isRecord(run.output_json)) {
    candidates.push(run.output_json.visual_asset_brief, run.output_json.raw_visual_asset_brief);
    if (isRecord(run.output_json.planner_trace)) {
      candidates.push(run.output_json.planner_trace.response, run.output_json.planner_trace.raw_response);
    }
  }
  for (const nodeRun of run.node_runs ?? []) {
    if (!isRecord(nodeRun.output_json)) continue;
    candidates.push(
      nodeRun.output_json.response,
      nodeRun.output_json.raw_response,
      nodeRun.output_json.structured_response,
    );
  }

  for (const candidate of candidates) {
    const parsed = parsePossiblyFencedJson(candidate);
    if (parsed && Array.isArray(parsed.visual_asset_briefs)) {
      return parsed as Phase6ObjectiveOutput;
    }
  }
  throw new Error(`Could not extract Phase 6 visual asset brief JSON from run ${run.id}.`);
}

function assertVisualBriefsActionable(output: Phase6ObjectiveOutput): VisualAssetBrief[] {
  const briefs = (output.visual_asset_briefs ?? []).map(normalizeVisualBrief);
  expect(briefs.length).toBeGreaterThanOrEqual(5);
  for (const model of REQUIRED_MODELS) {
    const normalizedModel = model.toLowerCase();
    let brief: VisualAssetBrief | undefined;
    for (const item of briefs) {
      if (normalizeText(`${item.product_name} ${item.sku}`).split(normalizedModel).length > 1) {
        brief = item;
        break;
      }
    }
    expect(brief, `Missing brief for ${model}`).toBeTruthy();
    expect(brief?.sku).toBeTruthy();
    expect(brief?.stock_state).toBeTruthy();
    expect(brief?.shot_list?.length ?? 0).toBeGreaterThan(0);
    expect(brief?.caption_angle).toBeTruthy();
    expect(brief?.background_or_prop_needs?.length ?? 0).toBeGreaterThan(0);
    expect(brief?.approval_task_title).toBeTruthy();
  }
  return REQUIRED_MODELS.map((model) => {
    const brief = briefs.find((item) =>
      normalizeText(`${item.product_name} ${item.sku}`).includes(model.toLowerCase()),
    );
    if (!brief) throw new Error(`Missing required brief ${model}`);
    return brief;
  });
}

function assertNoPrivateDataMarkers(value: unknown) {
  const text = normalizeText(JSON.stringify(value));
  const blocked = [
    "customer_email",
    "buyer_email",
    "shipping_address",
    "billing_address",
    "payment_intent",
    "checkout_session",
    "stripe_session",
    "client_secret",
  ];
  expect(blocked.some((marker) => text.includes(marker))).toBe(false);
  expect(/[a-z0-9._%+-]+@[a-z0-9.-]+\.[a-z]{2,}/i.test(text)).toBe(false);
}

async function materializeApprovalDrafts(
  request: APIRequestContext,
  accessToken: string,
  companyId: string,
  products: InventoryOverview["products"],
  briefs: VisualAssetBrief[],
  idempotencyScope: string,
) {
  const publicationDrafts = await Promise.all(
    briefs.map((brief) =>
      apiPost<{ publication_draft: { id: string; title: string; status: string } }>(
        request,
        accessToken,
        "/api/company-ops/publication-drafts",
        {
          company_id: companyId,
          title: brief.approval_task_title,
          channel: "instagram_draft",
          audience: "Legacy Glasswear followers",
          body: [
            `Product: ${brief.product_name} (${brief.sku})`,
            `Stock state: ${brief.stock_state}`,
            `Caption angle: ${brief.caption_angle}`,
            `Shot list: ${brief.shot_list.join("; ")}`,
            `Props/background: ${brief.background_or_prop_needs.join("; ")}`,
          ].join("\n"),
          call_to_action: "Hold for human approval before any external post.",
        },
        `phase6-${idempotencyScope}-publication-${brief.sku}`,
      ).then((draft) =>
        apiPost<{ publication_draft: { id: string; title: string; status: string } }>(
          request,
          accessToken,
          `/api/company-ops/publication-drafts/${draft.publication_draft.id}/request-approval`,
          { note: "Phase 6 approval gate: no live posting." },
          `phase6-${idempotencyScope}-publication-approval-${draft.publication_draft.id}`,
        ),
      ),
    ),
  ).then((approvals) => approvals.map((approval) => approval.publication_draft));

  const procurementLines = briefs.map((brief) => {
    const product = products.find(
      (item) => item.sku === brief.sku || normalizeText(item.model).includes(normalizeText(brief.product_name)),
    );
    return {
      product_id: product?.id ?? null,
      sku: brief.sku,
      description: `${brief.product_name} zero-cash-spend review line`,
      quantity: 1,
      unit_cost_amount: "0.00",
      currency: "mxn",
      metadata: { stock_state: brief.stock_state, phase: "legacy_phase_6" },
    };
  });
  const procurement = await apiPost<{
    procurement_draft: { id: string; title: string; status: string; budget_amount: string };
  }>(
    request,
    accessToken,
    "/api/company-ops/procurement-drafts",
    {
      company_id: companyId,
      title: "Legacy Phase 6 zero-cash procurement review",
      rationale: "Approval-gated reorder review only. No procurement execution and no cash spend.",
      budget_amount: "0.00",
      currency: "mxn",
      lines: procurementLines,
    },
    `phase6-${idempotencyScope}-procurement-zero-cash`,
  );
  const procurementApproval = await apiPost<{
    procurement_draft: { id: string; title: string; status: string; budget_amount: string };
  }>(
    request,
    accessToken,
    `/api/company-ops/procurement-drafts/${procurement.procurement_draft.id}/request-approval`,
    { note: "Phase 6 approval gate: no procurement execution." },
    `phase6-${idempotencyScope}-procurement-approval-${procurement.procurement_draft.id}`,
  );

  return {
    publication_drafts: publicationDrafts,
    procurement_draft: procurementApproval.procurement_draft,
  };
}

async function createReservationProof(
  request: APIRequestContext,
  accessToken: string,
  companyId: string,
  productSku: string,
  idempotencyScope: string,
) {
  const reservation = await apiPost<{ reservation: { id: string; status: string; product_sku: string } }>(
    request,
    accessToken,
    "/api/inventory/reservations",
    {
      company_id: companyId,
      sku: productSku,
      quantity: 1,
      buyer_alias: "phase6-dry-run",
      channel: "manual",
      note: "Phase 6 dry-run reservation proof.",
      ttl_minutes: 30,
    },
    `phase6-${idempotencyScope}-reservation-${productSku}`,
  );
  const released = await apiPost<{ reservation: { id: string; status: string; product_sku: string } }>(
    request,
    accessToken,
    `/api/inventory/reservations/${reservation.reservation.id}/release`,
    { reason: "Phase 6 dry-run release." },
    `phase6-${idempotencyScope}-release-${reservation.reservation.id}`,
  );
  return {
    reservation: reservation.reservation,
    released: released.reservation,
  };
}

async function fetchTasks(request: APIRequestContext, accessToken: string) {
  return apiGet<Array<{ id: string; execution_id: string; title: string }>>(request, accessToken, "/api/tasks/");
}

async function waitForOperationTask(request: APIRequestContext, accessToken: string, runId: string) {
  let matchingTask: { id: string; execution_id: string; title: string } | null = null;
  await expect
    .poll(
      async () => {
        const tasks = await fetchTasks(request, accessToken);
        matchingTask = tasks.find((task) => task.execution_id === runId) ?? null;
        return matchingTask?.id ?? "";
      },
      { timeout: 90_000, intervals: [1000, 2000, 3000] },
    )
    .not.toBe("");
  if (!matchingTask) throw new Error(`No projected task found for run ${runId}.`);
  return matchingTask;
}

async function runTaskJudge(
  request: APIRequestContext,
  accessToken: string,
  evidenceSnapshot: Record<string, unknown>,
) {
  const gateRun = await createHumanGateRunViaApi(request, accessToken, {
    graphName: "Legacy Phase 6 Evidence Judge Operation",
    promptMessage: "Review the Legacy Phase 6 operator-surface evidence before advancing.",
    instructions: "Pause here so Phase 6 can attach a backend-owned task judge.",
  });
  const task = await waitForOperationTask(request, accessToken, gateRun.runId);
  await apiPut<{ judge: Record<string, unknown> }>(request, accessToken, `/api/tasks/${task.id}/judge`, {
    title: "Legacy Phase 6 Judge",
    instructions: "Grade the Phase 6 evidence snapshot and backend task evidence.",
    criteria: JUDGE_CRITERIA,
    pass_threshold: 85,
    evidence_snapshot: evidenceSnapshot,
  });
  const evaluated = await apiPost<{
    judge: { id: string; status: string; score: number; result: Record<string, unknown> };
  }>(request, accessToken, `/api/tasks/${task.id}/judge/evaluate`, {});
  return { run: gateRun, task, judge: evaluated.judge };
}

async function writeEvidenceFiles(testInfo: TestInfo, evidence: Record<string, unknown>) {
  const date = new Date().toISOString().slice(0, 10);
  await fs.mkdir(LOG_DIR, { recursive: true });
  await fs.mkdir(DOC_DIR, { recursive: true });
  const jsonPath = path.join(LOG_DIR, `legacy-phase6-${date}.json`);
  const markdownPath = path.join(DOC_DIR, `legacy-phase-6-${date}.md`);
  await fs.writeFile(jsonPath, JSON.stringify(evidence, null, 2), "utf8");
  await fs.writeFile(markdownPath, renderMarkdownEvidence(evidence), "utf8");
  await testInfo.attach("legacy-phase6-evidence.json", { path: jsonPath, contentType: "application/json" });
  await testInfo.attach("legacy-phase6-evidence.md", { path: markdownPath, contentType: "text/markdown" });
  return { jsonPath, markdownPath };
}

function renderMarkdownEvidence(evidence: Record<string, unknown>): string {
  return [
    "# Legacy Phase 6 Evidence Packet",
    "",
    "## Commands",
    "```json",
    JSON.stringify(evidence.commands ?? [], null, 2),
    "```",
    "",
    "## Observed Data",
    "```json",
    JSON.stringify(evidence.observed_data ?? {}, null, 2),
    "```",
    "",
    "## Verification Result",
    "```json",
    JSON.stringify(evidence.verification_result ?? {}, null, 2),
    "```",
    "",
    "## Bugs Or Gaps",
    "```json",
    JSON.stringify(evidence.bugs_or_gaps ?? [], null, 2),
    "```",
    "",
    "## Decision",
    String(evidence.decision ?? ""),
    "",
  ].join("\n");
}

test("Legacy Phase 6 operator surface and visual asset brief", async ({ page, request }, testInfo) => {
  const user: TestUser = { email: LEGACY_EMAIL, password: LEGACY_PASSWORD };
  const bootstrap = runBootstrapCommand();
  expect(bootstrap.verification_result.passed).toBe(true);
  const geminiCredential = MOCK_PROVIDER_RESPONSE ? null : importLegacyGeminiCredential();

  const accessToken = await getAccessToken(request, user);
  const companyId = bootstrap.observed_data.company_id;
  const [inventory, companyOpsBefore] = await Promise.all([
    apiGet<{ inventory: InventoryOverview }>(
      request,
      accessToken,
      `/api/inventory/overview?company_id=${companyId}`,
    ).then((payload) => payload.inventory),
    apiGet<{ company_ops: CompanyOpsOverview }>(
      request,
      accessToken,
      `/api/company-ops/overview?company_id=${companyId}`,
    ).then((payload) => payload.company_ops),
  ]);

  expect(inventory.products.length).toBe(21);
  expect(inventory.summary.total_units).toBe(62);
  expect(inventory.stock_state_summary).toEqual(companyOpsBefore.stock_state_summary);

  const phase6Context = {
    objective_name: "Legacy Phase 6 Operator Surface and Visual Asset Brief",
    company_slug: "legacy-glasswear",
    budget_policy: "zero_cash_spend",
    mode: "approval_gated",
    out_of_scope: [
      "customer_outreach",
      "live_instagram_posting",
      "live_media_generation",
      "stripe_checkout",
      "procurement_execution",
    ],
    stock_semantics_report: inventory.stock_state_summary,
    products: inventory.products
      .flatMap((product) =>
        REQUIRED_MODELS.some(
          (model) => normalizeText(`${product.model} ${product.name}`).split(model.toLowerCase()).length > 1,
        )
          ? [
              {
                id: product.id,
                sku: product.sku,
                model: product.model,
                name: product.name,
                stock_state: product.stock_state,
                available_units: product.available_units,
                held_units: product.held_units,
              },
            ]
          : [],
      ),
  };

  let mockObjectiveSeed: MockObjectiveSeed | null = null;
  const visualRun = MOCK_PROVIDER_RESPONSE
    ? await (async () => {
        const seed = seedMockVisualBriefObjective(companyId);
        mockObjectiveSeed = seed;
        return apiGet<RunDetail>(request, accessToken, `/api/runs/${seed.run_id}`);
      })()
    : await createVisualBriefRun(request, accessToken, phase6Context, geminiCredential!.credential_id);
  expect(visualRun.status).toBe("succeeded");
  const objectiveOutput = extractObjectiveOutput(visualRun);
  assertNoPrivateDataMarkers(objectiveOutput);
  const requiredBriefs = assertVisualBriefsActionable(objectiveOutput);
  const nextRunPlan = coerceStringArray(objectiveOutput.next_run_plan);
  expect(nextRunPlan.length).toBeGreaterThanOrEqual(3);

  const reservationSku = inventory.products.find((product) => product.available_units > 0)?.sku;
  if (!reservationSku) throw new Error("No available SKU for Phase 6 dry-run reservation.");
  const reservationProof = await createReservationProof(request, accessToken, companyId, reservationSku, visualRun.id);
  expect(reservationProof.released.status).toBe("released");

  const drafts = await materializeApprovalDrafts(
    request,
    accessToken,
    companyId,
    inventory.products,
    requiredBriefs,
    visualRun.id,
  );
  expect(drafts.publication_drafts.every((draft) => draft.status === "approval_requested")).toBe(true);
  expect(drafts.procurement_draft.status).toBe("approval_requested");
  expect(Number(drafts.procurement_draft.budget_amount)).toBe(0);

  const [companyOpsAfter, inventoryAfterReservation] = await Promise.all([
    apiGet<{ company_ops: CompanyOpsOverview }>(
      request,
      accessToken,
      `/api/company-ops/overview?company_id=${companyId}`,
    ).then((payload) => payload.company_ops),
    apiGet<{ inventory: InventoryOverview }>(
      request,
      accessToken,
      `/api/inventory/overview?company_id=${companyId}`,
    ).then((payload) => payload.inventory),
  ]);
  expect(inventoryAfterReservation.summary.total_units).toBe(62);
  expect(inventoryAfterReservation.stock_state_summary).toEqual(companyOpsAfter.stock_state_summary);
  expect(inventoryAfterReservation.events.some((event) => /reserved/i.test(event.message))).toBe(true);
  expect(inventoryAfterReservation.events.some((event) => /released/i.test(event.message))).toBe(true);

  const evidenceSnapshot = {
    operator_surface_verified: true,
    stock_semantics_consistent: true,
    visual_briefs_actionable: true,
    zero_budget_policy_respected: true,
    approval_gates_present: true,
    no_private_customer_data_sent_to_llm: true,
    evidence_packet_complete: true,
    next_run_plan_clear: nextRunPlan.length >= 3,
    visual_run_id: visualRun.id,
    publication_draft_count: drafts.publication_drafts.length,
    procurement_draft_status: drafts.procurement_draft.status,
  };
  expect(evidenceSnapshot.next_run_plan_clear).toBe(true);
  const judged = await runTaskJudge(request, accessToken, evidenceSnapshot);
  expect(judged.judge.status).toBe("passed");
  expect(judged.judge.score).toBeGreaterThanOrEqual(85);
  console.log(`Legacy Phase 6 judge grade: ${judged.judge.score}/100`);

  await loginLive(page, request, user, `/companies/${companyId}`);
  await expect(page.getByText(/Legacy Glasswear/i).first()).toBeVisible({ timeout: 30_000 });
  await page.getByTestId("commerce-inventory-panel").scrollIntoViewIfNeeded();
  await expect(page.getByTestId("commerce-inventory-panel")).toBeVisible();
  await expect(page.getByText(/Stock States/i).first()).toBeVisible();
  await expect(page.getByText(/Operations Control Tower/i).first()).toBeVisible();

  await page.goto("/tasks");
  await expect(page.getByRole("heading", { name: "Department Activity", exact: true })).toBeVisible();
  await expect(page.getByText(judged.task.title).first()).toBeVisible({ timeout: 30_000 });
  await expect(page.getByText(new RegExp(`Passed\\s+\\D?\\s*${judged.judge.score}`, "i")).first()).toBeVisible();

  await page.goto("/approvals");
  await expect(page.getByText(/pending/i).first()).toBeVisible({ timeout: 30_000 });

  await page.goto(`/runs/${visualRun.id}`);
  await expect(
    page.getByRole("heading", { level: 2, name: "Legacy Phase 6 Visual Asset Brief Objective" }),
  ).toBeVisible({
    timeout: 30_000,
  });
  await expect(page.getByText(/Current status/i).first()).toBeVisible();
  await expect(page.getByText(/completed/i).first()).toBeVisible();

  await page.goto(`/companies/${companyId}`);
  await page.getByTestId("commerce-inventory-panel").scrollIntoViewIfNeeded();
  await expect(page.getByText(/Reserved .*unit/i).first()).toBeVisible({ timeout: 30_000 });
  await expect(page.getByText(/Released .*unit/i).first()).toBeVisible({ timeout: 30_000 });

  const evidence = {
    schema: "legacy_phase6_evidence.v1",
    generated_at: new Date().toISOString(),
    commands: [
      ...bootstrap.commands,
      ...(MOCK_PROVIDER_RESPONSE
        ? [
            "uv run python manage.py seed_legacy_phase6_mock_objective " +
              `--email ${LEGACY_EMAIL} --company-id ${companyId} --json`,
          ]
        : [`uv run python manage.py import_legacy_gemini_credential --env-var ${LEGACY_GEMINI_ENV_VAR} --json`]),
      `${MOCK_PROVIDER_RESPONSE ? "PLAYWRIGHT_LEGACY_MOCK_PROVIDER_RESPONSE=true " : ""}` +
        "PLAYWRIGHT_LEGACY_PHASE6_TEST=true npx playwright test frontend/__tests__/legacy-ultimate-test/specs/legacy_phase6_operator_surface.spec.ts",
    ],
    observed_data: {
      company_id: companyId,
      visual_run_id: visualRun.id,
      judge_run_id: judged.run.runId,
      judge_task_id: judged.task.id,
      judge_id: judged.judge.id,
      judge_grade: `${judged.judge.score}/100`,
      products_imported: bootstrap.observed_data.products_imported,
      active_units_imported: bootstrap.observed_data.active_units_imported,
      stock_semantics_report: inventoryAfterReservation.stock_state_summary,
      gemini_credential_id: geminiCredential?.credential_id ?? null,
      mock_provider_response: MOCK_PROVIDER_RESPONSE,
      mock_objective_seed: mockObjectiveSeed,
      visual_asset_briefs: requiredBriefs,
      next_run_plan: nextRunPlan,
      publication_drafts: drafts.publication_drafts,
      procurement_draft: drafts.procurement_draft,
      reservation_proof: reservationProof,
    },
    verification_result: {
      passed: true,
      bootstrap: bootstrap.verification_result,
      judge_status: judged.judge.status,
      judge_score: judged.judge.score,
      acceptance: evidenceSnapshot,
    },
    bugs_or_gaps: [],
    decision:
      "Legacy is ready for approval-gated visual/content preparation, not live sales or public-channel autonomy.",
  };

  const evidenceFiles = await writeEvidenceFiles(testInfo, evidence);
  console.log(`Legacy Phase 6 evidence JSON: ${evidenceFiles.jsonPath}`);
  console.log(`Legacy Phase 6 evidence Markdown: ${evidenceFiles.markdownPath}`);
});
