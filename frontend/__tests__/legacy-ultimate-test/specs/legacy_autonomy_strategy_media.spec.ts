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
const LEGACY_PASSWORD =
  process.env.PLAYWRIGHT_LEGACY_PASSWORD ?? process.env.LEGACY_TEST_PASSWORD ?? "ForgeGraphLegacy!2026";
const LEGACY_GEMINI_ENV_VAR = process.env.PLAYWRIGHT_LEGACY_GEMINI_ENV_VAR ?? "GEMINI_LEGACY";
const LEGACY_OPENROUTER_ENV_VAR = process.env.PLAYWRIGHT_LEGACY_OPENROUTER_ENV_VAR ?? "OPENROUTER";
const GEMINI_TEXT_MODEL = process.env.PLAYWRIGHT_LEGACY_GEMINI_TEXT_MODEL ?? "gemini-2.5-flash";
const OPENROUTER_TEXT_MODEL = process.env.PLAYWRIGHT_LEGACY_OPENROUTER_TEXT_MODEL ?? "google/gemini-2.5-flash";
const FORCE_GEMINI_TEXT_LIMIT = process.env.PLAYWRIGHT_LEGACY_FORCE_GEMINI_TEXT_LIMIT === "true";
const AUTONOMY_TEXT_MAX_TOKENS = Number(process.env.PLAYWRIGHT_LEGACY_AUTONOMY_TEXT_MAX_TOKENS ?? 8192);
const JUDGE_TIMEOUT_MS = Number(process.env.PLAYWRIGHT_LEGACY_JUDGE_TIMEOUT_MS ?? 120_000);
const JUDGE_MAX_TOKENS = Number(process.env.PLAYWRIGHT_LEGACY_JUDGE_MAX_TOKENS ?? 1800);
const PUBLICATION_CHANNELS = new Set(["instagram", "facebook"]);

const LIMIT_SIGNATURES = [
  "429",
  "too many requests",
  "resource_exhausted",
  "quota",
  "rate limit",
  "rate_limited",
  "token limit",
  "max token",
  "max_tokens",
  "max output",
  "context limit",
  "context_length",
  'finishreason":"max_tokens',
  "finishreason: max_tokens",
  "only available on paid plans",
  "upgrade your account",
];

const PRIVATE_DATA_MARKERS = [
  "customer_email",
  "buyer_email",
  "shipping_address",
  "billing_address",
  "payment_intent",
  "checkout_session",
  "stripe_session",
  "client_secret",
  "sk_live",
  "sk_test",
];

const AI_JUDGE_PROMPT = [
  "You are a strict evaluator for the Legacy Glasswear autonomous company test.",
  "Grade whether one operator request was routed to the Strategy Department, converted into a coherent strategy, transformed into approval-gated Instagram/Facebook media packages, and persisted through backend-owned evidence.",
  "The strategy must define the commercial creative objective before media generation: product-specific description, desired ad composition, CTA/offer policy, language, and approval-safe publication intent.",
  "The backend must remain the durable source of truth. Media, publication drafts, approvals, and judge evidence must not be treated as engine/client-owned state.",
  "Return JSON only with this exact shape:",
  '{"verdict":"pass|partial|fail","score":number,"reasoning":"string","criteria":{"routing_correctness":number,"strategy_quality":number,"creative_objective_quality":number,"media_alignment":number,"backend_ownership":number,"approval_safety":number,"privacy_safety":number,"operator_visibility":number,"autonomy_evidence":number},"concerns":["string"],"recommended_next_test":"string"}',
  "Score each number from 0 to 100.",
].join("\n");

const BACKEND_JUDGE_CRITERIA = [
  "ai_judge_passed",
  "routing_correctness",
  "strategy_quality",
  "creative_objective_quality",
  "media_alignment",
  "backend_ownership",
  "approval_safety",
  "privacy_safety",
  "operator_visibility",
  "autonomy_evidence",
  "provider_fallback_recorded",
];

test.skip(
  process.env.PLAYWRIGHT_LEGACY_AUTONOMY_TEST !== "true",
  "Set PLAYWRIGHT_LEGACY_AUTONOMY_TEST=true to run the Legacy Phase 7 autonomy strategy/media test.",
);

test.describe.configure({ mode: "serial" });
test.setTimeout(480_000);

type BootstrapEvidence = {
  commands: string[];
  observed_data: {
    company_id: string;
    graph_version_id: string;
    products_imported: number;
    active_units_imported: number;
  };
  verification_result: { passed: boolean; checks: Record<string, boolean>; failures: string[]; warnings: string[] };
};

type CredentialImport = {
  credential_id: string;
  provider: string;
  key_present: boolean;
  created_credential: boolean;
  created_graph_version: boolean;
  warnings: string[];
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

type InventoryOverview = {
  company_id: string;
  summary: { total_units: number; available_units: number };
  products: Array<{
    id: string;
    sku: string;
    model: string;
    name: string;
    variant: string;
    color: string;
    photo_url: string;
    price_mxn?: string;
    currency?: string;
    visual_description?: string;
    visual_traits?: string[];
    visual_reference_source?: string;
    available_units: number;
    stock_state: string | null;
  }>;
};

type MediaGenerationJob = {
  id: string;
  provider: string;
  model: string;
  modality: string;
  prompt: string;
  status: string;
  output_asset_id: string | null;
  output_asset_version_id: string | null;
  error_code: string;
  error_message: string;
};

type MediaFallbackResult = {
  primary_job: MediaGenerationJob;
  fallback_job: MediaGenerationJob | null;
  selected_job: MediaGenerationJob;
  fallback_used: boolean;
  fallback_reason: string;
};

type PublicationDraft = {
  id: string;
  title: string;
  channel: string;
  status: string;
  approval_task_id: string | null;
  asset_id?: string | null;
  asset_version_id?: string | null;
  media_job_id?: string | null;
};

type AutonomyOutput = {
  route: Record<string, unknown>;
  strategy: Record<string, unknown>;
  contentPlan: Record<string, unknown>;
};

type AutonomyRunResult = {
  output: AutonomyOutput;
  primaryRun: RunDetail;
  fallbackRun: RunDetail | null;
  finalRun: RunDetail;
  fallbackUsed: boolean;
  fallbackReason: string;
  finalProvider: "google" | "openrouter";
};

type AIJudgeResult = {
  verdict: "pass" | "partial" | "fail";
  score: number;
  reasoning: string;
  criteria: {
    routing_correctness: number;
    strategy_quality: number;
    creative_objective_quality: number;
    media_alignment: number;
    backend_ownership: number;
    approval_safety: number;
    privacy_safety: number;
    operator_visibility: number;
    autonomy_evidence: number;
  };
  concerns: string[];
  recommended_next_test: string;
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

function stringArray(value: unknown): string[] {
  if (Array.isArray(value)) {
    return value.flatMap((item) => {
      const trimmed = String(item ?? "").trim();
      return trimmed ? [trimmed] : [];
    });
  }
  if (typeof value === "string" && value.trim()) return [value.trim()];
  return [];
}

function mxnPriceLabel(value: unknown): string {
  const text = String(value ?? "").trim();
  if (!text) return "";
  const amount = Number(text.replace(/,/g, ""));
  if (!Number.isFinite(amount)) return text;
  return `MXN $${Math.round(amount)}`;
}

function buildProductVisualContext(product: InventoryOverview["products"][number]): Record<string, unknown> {
  const photoUrl = String(product.photo_url ?? "").trim();
  const color = String(product.color ?? "").trim();
  const priceMxn = String(product.price_mxn ?? "").trim();
  const priceLabel = mxnPriceLabel(priceMxn);
  const visualDescription = String(product.visual_description ?? "").trim();
  const visualTraits = stringArray(product.visual_traits);
  const knownVisualTraits = [
    color ? `frame color from inventory: ${color}` : "frame color is not available",
    photoUrl ? `product reference image: ${photoUrl}` : "no product photo_url or reference image is available",
    visualDescription ? `catalog visual description: ${visualDescription}` : "",
    ...visualTraits.map((trait) => `catalog visual trait: ${trait}`),
    "commercial model names and SKUs are labels, not visual descriptions of frame geometry",
  ].flatMap((item) => (item ? [item] : []));

  return {
    sku: product.sku,
    model: product.model,
    name: product.name,
    variant: product.variant,
    color,
    stock_state: product.stock_state,
    available_units: product.available_units,
    pricing: {
      price_mxn: priceMxn,
      display_price: priceLabel,
      currency: product.currency ?? "mxn",
      offer_policy:
        "Use backend inventory pricing for offer copy. If changing the price or discount, mark it as a proposed offer requiring human approval.",
    },
    visual_reference: photoUrl
      ? {
          available: true,
          type: "photo_url",
          uri: photoUrl,
          source: product.visual_reference_source ?? "",
          visual_description: visualDescription,
          visual_traits: visualTraits,
          fidelity_policy:
            "Use the product reference image and catalog visual description for product-accurate generation.",
        }
      : {
          available: false,
          type: "missing",
          visual_description: visualDescription,
          visual_traits: visualTraits,
          fidelity_policy:
            "Do not claim exact product likeness. Generate only concept drafts from known color and campaign context, or request product photos before final publication.",
        },
    known_visual_traits: knownVisualTraits,
  };
}

function parsePossiblyFencedJson(value: unknown): Record<string, unknown> | null {
  if (isRecord(value)) return value;
  if (typeof value !== "string") return null;
  let text = value.trim();
  const fenced = text.match(/^```(?:json)?\s*([\s\S]*?)\s*```$/i);
  if (fenced) text = fenced[1].trim();

  for (let attempt = 0; attempt < 3; attempt += 1) {
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

function importLegacyGeminiCredential(): CredentialImport {
  if (!process.env[LEGACY_GEMINI_ENV_VAR]) {
    throw new Error(`${LEGACY_GEMINI_ENV_VAR} is required for the Legacy autonomy Gemini primary provider.`);
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
  const credential = JSON.parse(raw) as CredentialImport;
  if (credential.provider !== "google" || !credential.key_present || !credential.credential_id) {
    throw new Error("Legacy Gemini credential import did not return a usable Google credential id.");
  }
  return credential;
}

function importLegacyOpenRouterCredential(): CredentialImport {
  if (!process.env[LEGACY_OPENROUTER_ENV_VAR] && !process.env.OPENROUTER_API_KEY) {
    throw new Error(
      `${LEGACY_OPENROUTER_ENV_VAR} or OPENROUTER_API_KEY is required for the Legacy autonomy fallback provider.`,
    );
  }
  const raw = execFileSync(
    "uv",
    [
      "run",
      "python",
      "manage.py",
      "import_legacy_openrouter_credential",
      "--env-var",
      LEGACY_OPENROUTER_ENV_VAR,
      "--json",
    ],
    {
      cwd: BACKEND_DIR,
      env: { ...process.env, LEGACY_TEST_PASSWORD: LEGACY_PASSWORD },
      encoding: "utf8",
      maxBuffer: 32 * 1024 * 1024,
    },
  );
  const credential = JSON.parse(raw) as CredentialImport;
  if (credential.provider !== "openrouter" || !credential.key_present || !credential.credential_id) {
    throw new Error("Legacy OpenRouter credential import did not return a usable OpenRouter credential id.");
  }
  return credential;
}

function buildAutonomyGraph(config: {
  provider: "google" | "openrouter";
  credentialId: string;
  model: string;
  maxTokens: number;
}) {
  const routeOutputSchema = {
    type: "object",
    required: [
      "selected_department",
      "operation_type",
      "routing_rationale",
      "participating_departments",
      "constraints",
    ],
    properties: {
      selected_department: { type: "string" },
      operation_type: { type: "string" },
      routing_rationale: { type: "string" },
      participating_departments: { type: "array", items: { type: "string" } },
      constraints: { type: "array", items: { type: "string" } },
    },
  };
  const strategyOutputSchema = {
    type: "object",
    required: [
      "positioning",
      "audience",
      "product_focus",
      "chosen_channels",
      "tradeoffs",
      "success_metrics",
      "creative_objective",
      "media_plan",
      "privacy_boundaries",
      "approval_policy",
    ],
    properties: {
      positioning: { type: "string" },
      audience: { type: "string" },
      product_focus: {
        type: "array",
        minItems: 1,
        items: {
          type: "object",
          required: ["sku", "reason"],
          properties: {
            sku: { type: "string" },
            reason: { type: "string" },
          },
        },
      },
      chosen_channels: { type: "array", minItems: 1, items: { type: "string" } },
      tradeoffs: { type: "array", minItems: 1, items: { type: "string" } },
      success_metrics: { type: "array", minItems: 1, items: { type: "string" } },
      creative_objective: {
        type: "object",
        required: [
          "desired_ad_result",
          "product_description_policy",
          "composition",
          "cta_policy",
          "offer_policy",
          "copy_language",
          "approval_gate",
        ],
        properties: {
          desired_ad_result: { type: "string" },
          product_description_policy: { type: "string" },
          composition: { type: "string" },
          cta_policy: { type: "string" },
          offer_policy: { type: "string" },
          copy_language: { type: "string" },
          approval_gate: { type: "string" },
        },
      },
      media_plan: {
        type: "array",
        minItems: 1,
        items: {
          type: "object",
          required: ["channel", "asset_type", "brief", "media_prompt"],
          properties: {
            channel: { type: "string" },
            asset_type: { type: "string" },
            brief: { type: "string" },
            media_prompt: { type: "string" },
          },
        },
      },
      privacy_boundaries: { type: "array", minItems: 1, items: { type: "string" } },
      approval_policy: { type: "string" },
    },
  };
  const contentOutputSchema = {
    type: "object",
    required: ["media_briefs", "post_packages", "video_deferred_reason"],
    properties: {
      media_briefs: {
        type: "array",
        minItems: 1,
        items: {
          type: "object",
          required: [
            "channel",
            "asset_type",
            "product_sku",
            "brief",
            "media_prompt",
            "visual_fidelity_note",
            "creative_objective_applied",
          ],
          properties: {
            channel: { type: "string" },
            asset_type: { type: "string" },
            product_sku: { type: "string" },
            brief: { type: "string" },
            media_prompt: { type: "string" },
            visual_fidelity_note: { type: "string" },
            creative_objective_applied: { type: "string" },
          },
        },
      },
      post_packages: {
        type: "array",
        minItems: 1,
        items: {
          type: "object",
          required: ["channel", "caption", "cta", "product_sku", "media_prompt", "approval_required"],
          properties: {
            channel: { type: "string" },
            caption: { type: "string" },
            cta: { type: "string" },
            product_sku: { type: "string" },
            media_prompt: { type: "string" },
            approval_required: { type: "boolean" },
          },
        },
      },
      video_deferred_reason: { type: "string" },
    },
  };

  const promptConfig = {
    provider: config.provider,
    credential_id: config.credentialId,
    model: config.model,
    temperature: 0.2,
    max_tokens: config.maxTokens,
    stream: false,
    disable_memory_context: true,
    schema_mode: "warn",
    output_schema_target: "response",
  };

  return {
    nodes: [
      {
        id: "routing_department",
        type: "prompt",
        name: "Routing Department",
        config: {
          ...promptConfig,
          output_key: "route",
          output_schema: routeOutputSchema,
          prompt_template: [
            "Return JSON only. Do not use markdown.",
            "You are Legacy Glasswear's Routing Department.",
            "Route this operator request to the single ideal department that determines strategy before content execution.",
            "Required JSON shape:",
            '{"selected_department":"Strategy Department","operation_type":"content_drop_planning","routing_rationale":"string","participating_departments":["Strategy Department","Content Studio","Social Desk"],"constraints":["string"]}',
            "Rules: Routing does not execute downstream work. Keep all durable state backend-owned. Do not include customer PII, payment data, addresses, or checkout links.",
            "Operator request:",
            "{{input.operator_request}}",
            "Company context:",
            "{{input.company_context}}",
          ].join("\n"),
        },
      },
      {
        id: "strategy_department",
        type: "prompt",
        name: "Strategy Department",
        config: {
          ...promptConfig,
          output_key: "strategy",
          output_schema: strategyOutputSchema,
          prompt_template: [
            "Return JSON only. Do not use markdown.",
            "You are Legacy Glasswear's Strategy Department.",
            "Use the route and backend context to decide the campaign strategy and selected channels.",
            "Required JSON shape:",
            '{"positioning":"string","audience":"string","product_focus":[{"sku":"string","reason":"string"}],"chosen_channels":["instagram","facebook"],"tradeoffs":["string"],"success_metrics":["string"],"creative_objective":{"desired_ad_result":"string","product_description_policy":"string","composition":"string","cta_policy":"string","offer_policy":"string","copy_language":"string","approval_gate":"string"},"media_plan":[{"channel":"instagram|facebook","asset_type":"image|video","brief":"string","media_prompt":"string"}],"privacy_boundaries":["string"],"approval_policy":"string"}',
            "The top-level JSON object must include every required key exactly once, including privacy_boundaries and approval_policy.",
            "Define creative_objective as the upstream target for the media work, not as a finished asset. It must describe the intended polished social ad result: product-specific visual description, product name/copy treatment, CTA/offer policy, language, channel composition, and approval gate.",
            "Use backend inventory pricing in company_context.inventory[*].pricing for offer copy. Do not invent discounts, checkout links, or unapproved prices.",
            "Set approval_policy to one sentence that explicitly says human approval or review is required before publication.",
            "Set privacy_boundaries to concrete data classes excluded from prompts, outputs, and publication drafts.",
            "Product model names and SKUs are labels, not visual references. If product photos or visual references are missing, treat model-specific image generation as concept drafting only and include that tradeoff.",
            "Prefer products with visual_reference.available=true for image media because those can produce more product-accurate drafts.",
            "Choose Instagram, Facebook, or both based on the strategy. Approval is required before any external publication.",
            "Route:",
            "{{node.routing_department.output.response}}",
            "Company context:",
            "{{input.company_context}}",
          ].join("\n"),
        },
      },
      {
        id: "strategy_policy_defaults",
        type: "transform",
        name: "Backend Strategy Policy Defaults",
        config: {
          expression_type: "static",
          output_key: "strategy_policy_defaults",
          value: {
            privacy_boundaries: [
              "Exclude customer emails, shipping addresses, billing addresses, payment identifiers, checkout links, and private order data from prompts, media, captions, and approval notes.",
              "Use product, inventory, styling, and campaign context only.",
            ],
            approval_policy:
              "Human approval review is required before any Instagram, Facebook, or external publication action.",
          },
        },
      },
      {
        id: "strategy_contract_guard",
        type: "transform",
        name: "Backend Strategy Contract Guard",
        config: {
          expression_type: "state_patch",
          expression: "vars.strategy_policy_defaults",
          output_key: "strategy",
          state_source: "vars.strategy",
          patch_mode: "deep_merge",
        },
      },
      {
        id: "content_studio",
        type: "prompt",
        name: "Content Studio",
        config: {
          ...promptConfig,
          output_key: "content_plan",
          output_schema: contentOutputSchema,
          prompt_template: [
            "Return JSON only. Do not use markdown.",
            "You are Legacy Glasswear's Content Studio. Convert the strategy into approval-gated media briefs and social packages.",
            "Required JSON shape:",
            '{"media_briefs":[{"channel":"instagram|facebook","asset_type":"image|video","product_sku":"string","brief":"string","media_prompt":"string","visual_fidelity_note":"string","creative_objective_applied":"string"}],"post_packages":[{"channel":"instagram|facebook","caption":"string","cta":"string","product_sku":"string","media_prompt":"string","approval_required":true}],"video_deferred_reason":"string"}',
            "At least one image media brief is required. If video is useful but not necessary, defer it with a reason.",
            "No live posting, no checkout links, no customer PII, no payment data.",
            "Carry strategy.creative_objective into the media work. Every image media_prompt must aim for a polished social ad draft with product-accurate eyewear, the selected product name, a clear CTA/offer direction, and a channel-ready composition. Include visible copy only as draft copy requiring approval.",
            "Use backend pricing from company_context.inventory[*].pricing when writing offer copy, and state any proposed offer is approval-required.",
            "Do not use a product name or SKU as if it describes frame appearance.",
            "Every image media_prompt must include known visual traits from company_context.inventory, such as frame color or a product photo reference.",
            "If visual_reference.available is true, include the photo_url and catalog visual description in the media_prompt.",
            "If no product photo/reference exists, phrase the media_prompt as a concept draft, not an exact product rendering, and do not invent precise frame geometry.",
            "Each visual_fidelity_note must state whether a product photo/reference exists and whether the draft is product-accurate or conceptual.",
            "Validated strategy JSON:",
            "{{node.strategy_contract_guard.output.state}}",
            "Company context with inventory visual references:",
            "{{input.company_context}}",
          ].join("\n"),
        },
      },
      {
        id: "final_output",
        type: "output",
        name: "Final Output",
        config: {
          output_mapping: {
            route: "node.routing_department.output.response",
            strategy: "node.strategy_contract_guard.output.state",
            content_plan: "node.content_studio.output.response",
            routing_trace: "node.routing_department.output",
            strategy_trace: "node.strategy_department.output",
            strategy_contract_guard: "node.strategy_contract_guard.output",
            content_trace: "node.content_studio.output",
          },
        },
      },
    ],
    edges: [
      { id: "start-routing", from: "START", to: "routing_department" },
      { id: "routing-strategy", from: "routing_department", to: "strategy_department" },
      { id: "strategy-policy-defaults", from: "strategy_department", to: "strategy_policy_defaults" },
      { id: "strategy-contract-guard", from: "strategy_policy_defaults", to: "strategy_contract_guard" },
      { id: "strategy-content", from: "strategy_contract_guard", to: "content_studio" },
      { id: "content-output", from: "content_studio", to: "final_output" },
      { id: "output-end", from: "final_output", to: "END" },
    ],
    metadata: {
      name: "Legacy Phase 7 Autonomy Strategy Media",
      legacy_phase: "phase-7-autonomy-strategy-media",
      runtime_contract: {
        durable_source_of_truth: "backend",
        engine_owns_durable_state: false,
        events_are_authoritative: false,
      },
    },
  };
}

async function createAutonomyRun(
  request: APIRequestContext,
  accessToken: string,
  input: Record<string, unknown>,
  provider: "google" | "openrouter",
  credentialId: string,
  model: string,
  maxTokens: number,
): Promise<RunDetail> {
  const graph = await apiPost<{ id: string }>(request, accessToken, "/api/graphs/", {
    name: `Legacy Phase 7 Autonomy ${provider}`,
    description: "One-request Legacy autonomy strategy and media planning test.",
  });
  const version = await apiPost<{ id: string }>(request, accessToken, `/api/graphs/${graph.id}/versions`, {
    graph_json: buildAutonomyGraph({ provider, credentialId, model, maxTokens }),
  });
  const started = await apiPost<{ id: string }>(request, accessToken, "/api/runs/start", {
    graph_version_id: version.id,
    llm_mode: "byok",
    provider,
    credential_id: credentialId,
    input_json: input,
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

function parseNodeOrOutput(run: RunDetail, outputKey: string, nodeId: string): Record<string, unknown> {
  const output = isRecord(run.output_json) ? run.output_json : {};
  const node = run.node_runs.find((item) => item.node_id === nodeId);
  const candidates = [
    output[outputKey],
    isRecord(node?.output_json) ? node?.output_json.response : null,
    isRecord(node?.output_json) ? node?.output_json.raw_response : null,
    isRecord(node?.output_json) ? node?.output_json.structured_response : null,
  ];
  for (const candidate of candidates) {
    const parsed = parsePossiblyFencedJson(candidate);
    if (parsed) return parsed;
  }
  throw new Error(`Could not parse ${outputKey} JSON from run ${run.id}.`);
}

function extractAutonomyOutput(run: RunDetail): AutonomyOutput {
  return {
    route: parseNodeOrOutput(run, "route", "routing_department"),
    strategy: parseNodeOrOutput(run, "strategy", "strategy_department"),
    contentPlan: parseNodeOrOutput(run, "content_plan", "content_studio"),
  };
}

function runHasLimitSignal(run: RunDetail): boolean {
  const text = normalizeText(
    JSON.stringify({
      status: run.status,
      error_message: run.error_message,
      output_json: run.output_json,
      node_runs: run.node_runs,
    }),
  );
  return LIMIT_SIGNATURES.some((signature) => text.includes(signature));
}

function fallbackReason(run: RunDetail): string {
  const text = normalizeText(JSON.stringify(run));
  return LIMIT_SIGNATURES.find((signature) => text.includes(signature))?.replace(/\s+/g, "_") ?? "provider_limit";
}

async function runAutonomyGraphWithProviderFallback(
  request: APIRequestContext,
  accessToken: string,
  input: Record<string, unknown>,
  geminiCredentialId: string,
  openrouterCredentialId: string,
): Promise<AutonomyRunResult> {
  const primaryRun = await createAutonomyRun(
    request,
    accessToken,
    input,
    "google",
    geminiCredentialId,
    GEMINI_TEXT_MODEL,
    FORCE_GEMINI_TEXT_LIMIT ? 1 : AUTONOMY_TEXT_MAX_TOKENS,
  );

  if (primaryRun.status === "succeeded") {
    try {
      const output = extractAutonomyOutput(primaryRun);
      return {
        output,
        primaryRun,
        fallbackRun: null,
        finalRun: primaryRun,
        fallbackUsed: false,
        fallbackReason: "",
        finalProvider: "google",
      };
    } catch (error) {
      if (!runHasLimitSignal(primaryRun)) {
        throw error;
      }
    }
  } else if (!runHasLimitSignal(primaryRun)) {
    throw new Error(`Primary Gemini run failed without a provider limit signal: ${primaryRun.error_message ?? ""}`);
  }

  const openrouterRun = await createAutonomyRun(
    request,
    accessToken,
    input,
    "openrouter",
    openrouterCredentialId,
    OPENROUTER_TEXT_MODEL,
    AUTONOMY_TEXT_MAX_TOKENS,
  );
  expect(openrouterRun.status).toBe("succeeded");
  const output = extractAutonomyOutput(openrouterRun);
  return {
    output,
    primaryRun,
    fallbackRun: openrouterRun,
    finalRun: openrouterRun,
    fallbackUsed: true,
    fallbackReason: fallbackReason(primaryRun),
    finalProvider: "openrouter",
  };
}

async function createMediaGeneration(
  request: APIRequestContext,
  accessToken: string,
  data: {
    company_id: string;
    credential_id: string;
    prompt: string;
    idempotency_key: string;
    model?: string;
  },
): Promise<MediaGenerationJob> {
  const payload = await apiPost<{ media_generation: MediaGenerationJob }>(
    request,
    accessToken,
    "/api/archive/media-generations",
    {
      company_id: data.company_id,
      credential_id: data.credential_id,
      modality: "image",
      prompt: data.prompt,
      idempotency_key: data.idempotency_key,
      model: data.model ?? "",
    },
  );
  return payload.media_generation;
}

function isMediaFallbackEligible(job: MediaGenerationJob): boolean {
  const text = normalizeText(JSON.stringify(job));
  return LIMIT_SIGNATURES.some((signature) => text.includes(signature));
}

async function createMediaWithProviderFallback(
  request: APIRequestContext,
  accessToken: string,
  options: {
    companyId: string;
    geminiCredentialId: string;
    openrouterCredentialId: string;
    prompt: string;
    idempotencyScope: string;
  },
): Promise<MediaFallbackResult> {
  const primaryJob = await createMediaGeneration(request, accessToken, {
    company_id: options.companyId,
    credential_id: options.geminiCredentialId,
    prompt: options.prompt,
    idempotency_key: `${options.idempotencyScope}:media:google`,
    model: process.env.PLAYWRIGHT_LEGACY_GEMINI_IMAGE_MODEL,
  });
  if (primaryJob.status === "succeeded") {
    return {
      primary_job: primaryJob,
      fallback_job: null,
      selected_job: primaryJob,
      fallback_used: false,
      fallback_reason: "",
    };
  }
  if (!isMediaFallbackEligible(primaryJob)) {
    throw new Error(
      `Gemini media generation failed without a fallback-eligible limit signal: ${JSON.stringify(primaryJob)}`,
    );
  }
  const fallbackJob = await createMediaGeneration(request, accessToken, {
    company_id: options.companyId,
    credential_id: options.openrouterCredentialId,
    prompt: options.prompt,
    idempotency_key: `${options.idempotencyScope}:media:openrouter`,
    model: process.env.PLAYWRIGHT_LEGACY_OPENROUTER_IMAGE_MODEL,
  });
  expect(fallbackJob.status).toBe("succeeded");
  return {
    primary_job: primaryJob,
    fallback_job: fallbackJob,
    selected_job: fallbackJob,
    fallback_used: true,
    fallback_reason: fallbackReason({ ...primaryJob, node_runs: [], graph_id: "", graph_version_id: "" } as RunDetail),
  };
}

function selectedChannels(strategy: Record<string, unknown>): string[] {
  return stringArray(strategy.chosen_channels).filter((channel) => ["instagram", "facebook"].includes(channel));
}

function selectedMediaPrompt(output: AutonomyOutput): string {
  const mediaBriefs = Array.isArray(output.contentPlan.media_briefs) ? output.contentPlan.media_briefs : [];
  const imagePrompts: string[] = [];
  for (const item of mediaBriefs) {
    if (!isRecord(item)) continue;
    const assetType = normalizeText(item.asset_type);
    const prompt = String(item.media_prompt ?? "").trim();
    if ((!assetType || assetType === "image") && prompt) imagePrompts.push(prompt);
  }
  const promptWithCreativeContext = imagePrompts.find(
    (prompt) => mediaPromptHasProductVisualContext(prompt) && mediaPromptHasCommercialCreativeContext(prompt),
  );
  if (promptWithCreativeContext) return promptWithCreativeContext;
  if (imagePrompts.length > 0) return imagePrompts[0];
  for (const item of mediaBriefs) {
    if (!isRecord(item)) continue;
    const prompt = String(item.media_prompt ?? "").trim();
    if (prompt) return prompt;
  }
  const strategyMediaPlan = Array.isArray(output.strategy.media_plan) ? output.strategy.media_plan : [];
  for (const item of strategyMediaPlan) {
    if (!isRecord(item)) continue;
    const prompt = String(item.media_prompt ?? "").trim();
    if (prompt) return prompt;
  }
  return "Editorial product image for Legacy Glasswear premium eyewear, neutral background, no people, no text overlays.";
}

async function createPublicationDrafts(
  request: APIRequestContext,
  accessToken: string,
  companyId: string,
  output: AutonomyOutput,
  mediaJob: MediaGenerationJob,
  idempotencyScope: string,
): Promise<PublicationDraft[]> {
  const packages = Array.isArray(output.contentPlan.post_packages) ? output.contentPlan.post_packages : [];
  const fallbackChannels = selectedChannels(output.strategy);
  const packageRecords = packages.filter(isRecord);
  const selectedPackages =
    packageRecords.length > 0
      ? packageRecords
      : fallbackChannels.map((channel) => ({
          channel,
          caption: `${String(output.strategy.positioning ?? "Legacy Glasswear")} for a focused eyewear drop.`,
          cta: "Hold for approval before publishing.",
          product_sku: "",
          media_prompt: selectedMediaPrompt(output),
          approval_required: true,
        }));

  return Promise.all(
    selectedPackages.flatMap((postPackage, index) => {
      const channel = normalizeText(postPackage.channel);
      if (!PUBLICATION_CHANNELS.has(channel)) {
        return [];
      }
      return [
        apiPost<{ publication_draft: PublicationDraft }>(
          request,
          accessToken,
          "/api/company-ops/publication-drafts",
          {
            company_id: companyId,
            title: `Legacy Phase 7 ${channel} draft ${index + 1}`,
            channel,
            audience: String(output.strategy.audience ?? "Legacy Glasswear audience"),
            body: String(postPackage.caption ?? ""),
            call_to_action: String(postPackage.cta ?? "Hold for approval before publishing."),
            asset_id: mediaJob.output_asset_id,
            asset_version_id: mediaJob.output_asset_version_id,
            media_job_id: mediaJob.id,
          },
          `${idempotencyScope}:publication:${channel}:${index}`,
        ).then((draft) =>
          apiPost<{ publication_draft: PublicationDraft }>(
            request,
            accessToken,
            `/api/company-ops/publication-drafts/${draft.publication_draft.id}/request-approval`,
            { note: "Legacy Phase 7 approval gate: no public posting." },
            `${idempotencyScope}:publication-approval:${draft.publication_draft.id}`,
          ),
        ),
      ];
    }),
  ).then((approvals) => approvals.map((approval) => approval.publication_draft));
}

function assertAutonomyOutput(output: AutonomyOutput): void {
  expect(output.route.selected_department).toBe("Strategy Department");
  expect(output.route.operation_type).toBe("content_drop_planning");
  const channels = selectedChannels(output.strategy);
  expect(channels.length).toBeGreaterThan(0);
  expect(stringArray(output.strategy.success_metrics).length).toBeGreaterThan(0);
  expect(stringArray(output.strategy.privacy_boundaries).length).toBeGreaterThan(0);
  expect(String(output.strategy.approval_policy ?? "")).toMatch(/approval|review/i);
  assertStrategyCreativeObjective(output);
  const mediaBriefs = Array.isArray(output.contentPlan.media_briefs) ? output.contentPlan.media_briefs : [];
  const postPackages = Array.isArray(output.contentPlan.post_packages) ? output.contentPlan.post_packages : [];
  expect(mediaBriefs.length).toBeGreaterThan(0);
  expect(postPackages.length).toBeGreaterThan(0);
  assertContentAppliesCreativeObjective(output);
}

function assertStrategyCreativeObjective(output: AutonomyOutput): void {
  const objective = output.strategy.creative_objective;
  expect(isRecord(objective)).toBe(true);
  const objectiveText = normalizeText(JSON.stringify(objective));
  expect(objectiveText).toMatch(/product|frame|visual|description|reference|catalog/);
  expect(objectiveText).toMatch(/cta|call to action|offer|price|precio|mxn|\$/);
  expect(objectiveText).toMatch(/spanish|español|instagram|facebook|composition|ad/);
  expect(objectiveText).toMatch(/approval|review/);
}

function assertContentAppliesCreativeObjective(output: AutonomyOutput): void {
  const mediaBriefs = (Array.isArray(output.contentPlan.media_briefs) ? output.contentPlan.media_briefs : []).filter(
    isRecord,
  );
  const imageBriefs = mediaBriefs.filter((brief) => normalizeText(brief.asset_type) === "image");
  const postPackages = (Array.isArray(output.contentPlan.post_packages) ? output.contentPlan.post_packages : []).filter(
    isRecord,
  );
  const creativeText = normalizeText(
    JSON.stringify({
      media_briefs: imageBriefs,
      post_packages: postPackages,
    }),
  );
  expect(creativeText).toMatch(/legacy|depp|hunt|product name|zd-8809t|ts-1910/);
  expect(creativeText).toMatch(/cta|call to action|offer|price|precio|mxn|\$|obt[eé]n|compra|reserva|descubre|conoce/);
  expect(creativeText).toMatch(/draft|approval|required|review|aprobaci[oó]n/);
  for (const brief of imageBriefs) {
    expect(String(brief.creative_objective_applied ?? "")).toMatch(
      /cta|offer|price|description|product|composition|copy/i,
    );
  }
  for (const postPackage of postPackages) {
    const cta = String(postPackage.cta ?? "").trim();
    expect(cta.length).toBeGreaterThan(0);
    expect(normalizeText(cta)).not.toBe("hold for approval before publishing.");
    expect(normalizeText(cta)).toMatch(/obt[eé]n|compra|reserva|descubre|conoce|elige|pide|solicita|cta|oferta/);
  }
}

function mediaPromptHasProductVisualContext(prompt: string): boolean {
  const text = normalizeText(prompt);
  return [
    "gold",
    "beige",
    "black",
    "matte black",
    "clear yellow",
    "rose-gold",
    "octagonal",
    "tortoiseshell",
    "dark gray lenses",
    "catalog/depp",
    "frame color",
    "product photo",
    "reference image",
    "visual reference",
    "concept draft",
    "not exact",
    "conceptual",
  ].some((marker) => text.includes(marker));
}

function mediaPromptHasCommercialCreativeContext(prompt: string): boolean {
  const text = normalizeText(prompt);
  return [
    "cta",
    "call to action",
    "call-to-action",
    "offer",
    "price",
    "precio",
    "mxn",
    "$",
    "obtén",
    "obten",
    "compra",
    "reserva",
    "descubre",
    "conoce",
    "text overlay",
    "visible copy",
    "draft copy",
  ].some((marker) => text.includes(marker));
}

function assertMediaPromptsUseVisualContext(output: AutonomyOutput): void {
  const mediaBriefs = (Array.isArray(output.contentPlan.media_briefs) ? output.contentPlan.media_briefs : []).filter(
    isRecord,
  );
  expect(mediaBriefs.length).toBeGreaterThan(0);
  const imageBriefs = mediaBriefs.filter((brief) => normalizeText(brief.asset_type) === "image");
  expect(imageBriefs.length).toBeGreaterThan(0);
  for (const brief of imageBriefs) {
    const mediaPrompt = String(brief.media_prompt ?? "");
    expect(mediaPromptHasProductVisualContext(mediaPrompt)).toBe(true);
    expect(mediaPromptHasCommercialCreativeContext(mediaPrompt)).toBe(true);
    expect(String(brief.visual_fidelity_note ?? "")).toMatch(/photo|reference|concept|exact|fidelity/i);
  }
  expect(mediaPromptHasProductVisualContext(selectedMediaPrompt(output))).toBe(true);
  expect(mediaPromptHasCommercialCreativeContext(selectedMediaPrompt(output))).toBe(true);
  const deppBriefs = imageBriefs.filter((brief) => String(brief.product_sku ?? "") === "ZD-8809T");
  for (const brief of deppBriefs) {
    expect(normalizeText(brief.media_prompt)).toMatch(/catalog\/depp|rose-gold|octagonal|tortoiseshell/);
  }
}

function assertNoPrivateDataMarkers(value: unknown): void {
  const text = normalizeText(JSON.stringify(value));
  expect(PRIVATE_DATA_MARKERS.some((marker) => text.includes(marker))).toBe(false);
  expect(/[a-z0-9._%+-]+@[a-z0-9.-]+\.[a-z]{2,}/i.test(text)).toBe(false);
}

function judgeConfig() {
  const explicitBaseUrl = process.env.PLAYWRIGHT_LEGACY_JUDGE_LLM_URL;
  const groqKey = process.env.GROQ ?? process.env.GROQ_API_KEY;
  const openRouterKey = process.env.OPENROUTER ?? process.env.OPENROUTER_API_KEY;
  const useGroq = !explicitBaseUrl && Boolean(groqKey);
  const useOpenRouter =
    !explicitBaseUrl &&
    !useGroq &&
    Boolean(openRouterKey) &&
    !process.env.PLAYWRIGHT_SIMULATION_LLM_URL &&
    !process.env.OPENAI_BASE_URL &&
    !process.env.PLAYWRIGHT_LOCAL_LLM_URL;
  const baseUrl = (
    explicitBaseUrl ??
    (useGroq ? "https://api.groq.com/openai/v1" : undefined) ??
    (useOpenRouter ? "https://openrouter.ai/api/v1" : undefined) ??
    process.env.PLAYWRIGHT_SIMULATION_LLM_URL ??
    process.env.OPENAI_BASE_URL ??
    process.env.PLAYWRIGHT_LOCAL_LLM_URL ??
    "http://127.0.0.1:12434/v1"
  ).replace(/\/$/, "");
  const model =
    process.env.PLAYWRIGHT_LEGACY_JUDGE_MODEL ??
    process.env.GROQ_MODEL ??
    process.env.PLAYWRIGHT_SIMULATION_JUDGE_MODEL ??
    process.env.OPENAI_MODEL ??
    process.env.PLAYWRIGHT_MARKETING_LLM_MODEL ??
    (useOpenRouter ? OPENROUTER_TEXT_MODEL : undefined) ??
    (useGroq ? "llama-3.3-70b-versatile" : "docker.io/ai/llama3.1:latest");
  const apiKey =
    process.env.PLAYWRIGHT_LEGACY_JUDGE_API_KEY ??
    (baseUrl.includes("groq.com") ? groqKey : undefined) ??
    (baseUrl.includes("openrouter.ai") ? openRouterKey : undefined) ??
    process.env.OPENAI_API_KEY;
  return { baseUrl, model, apiKey };
}

async function runAIJudge(request: APIRequestContext, evidence: Record<string, unknown>): Promise<AIJudgeResult> {
  const config = judgeConfig();
  const headers: Record<string, string> = {};
  if (config.apiKey) headers.Authorization = `Bearer ${config.apiKey}`;
  const response = await request.post(`${config.baseUrl}/chat/completions`, {
    headers,
    timeout: JUDGE_TIMEOUT_MS,
    failOnStatusCode: false,
    data: {
      model: config.model,
      temperature: 0.1,
      max_tokens: JUDGE_MAX_TOKENS,
      response_format: { type: "json_object" },
      messages: [
        { role: "system", content: AI_JUDGE_PROMPT },
        { role: "user", content: JSON.stringify(evidence, null, 2) },
      ],
    },
  });
  if (!response.ok()) {
    throw new Error(
      `AI judge request failed (${response.status()}) at ${config.baseUrl}: ${(await response.text()).slice(0, 700)}`,
    );
  }
  const body = (await response.json()) as { choices?: Array<{ message?: { content?: string } }> };
  const content = body.choices?.[0]?.message?.content?.trim();
  if (!content) throw new Error("AI judge returned an empty response.");
  const parsed = parsePossiblyFencedJson(content);
  if (!parsed) throw new Error(`AI judge returned non-JSON content: ${content.slice(0, 500)}`);
  return normalizeJudgeResult(parsed);
}

function normalizeScore(value: unknown): number {
  const score = Number(value);
  if (!Number.isFinite(score)) return 0;
  return Math.max(0, Math.min(100, Math.round(score)));
}

function normalizeJudgeResult(parsed: Record<string, unknown>): AIJudgeResult {
  const rawCriteria = isRecord(parsed.criteria) ? parsed.criteria : {};
  const verdict =
    parsed.verdict === "pass" || parsed.verdict === "partial" || parsed.verdict === "fail" ? parsed.verdict : "fail";
  return {
    verdict,
    score: normalizeScore(parsed.score),
    reasoning: String(parsed.reasoning ?? ""),
    criteria: {
      routing_correctness: normalizeScore(rawCriteria.routing_correctness),
      strategy_quality: normalizeScore(rawCriteria.strategy_quality),
      creative_objective_quality: normalizeScore(rawCriteria.creative_objective_quality),
      media_alignment: normalizeScore(rawCriteria.media_alignment),
      backend_ownership: normalizeScore(rawCriteria.backend_ownership),
      approval_safety: normalizeScore(rawCriteria.approval_safety),
      privacy_safety: normalizeScore(rawCriteria.privacy_safety),
      operator_visibility: normalizeScore(rawCriteria.operator_visibility),
      autonomy_evidence: normalizeScore(rawCriteria.autonomy_evidence),
    },
    concerns: stringArray(parsed.concerns),
    recommended_next_test: String(parsed.recommended_next_test ?? ""),
  };
}

function assertJudgePassed(judge: AIJudgeResult): void {
  expect(judge.verdict).toBe("pass");
  expect(judge.score).toBeGreaterThanOrEqual(80);
  expect(judge.criteria.creative_objective_quality).toBeGreaterThanOrEqual(80);
  expect(judge.criteria.backend_ownership).toBeGreaterThanOrEqual(80);
  expect(judge.criteria.privacy_safety).toBeGreaterThanOrEqual(80);
  expect(judge.criteria.approval_safety).toBeGreaterThanOrEqual(80);
  expect(Math.min(...Object.values(judge.criteria))).toBeGreaterThanOrEqual(60);
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

async function runBackendTaskJudge(
  request: APIRequestContext,
  accessToken: string,
  evidenceSnapshot: Record<string, unknown>,
) {
  const gateRun = await createHumanGateRunViaApi(request, accessToken, {
    graphName: "Legacy Phase 7 AI Judge Evidence Gate",
    promptMessage: "Review the Legacy Phase 7 autonomy evidence before advancing.",
    instructions: "Pause here so Phase 7 can attach a backend-owned task judge.",
  });
  const task = await waitForOperationTask(request, accessToken, gateRun.runId);
  await apiPut<{ judge: Record<string, unknown> }>(request, accessToken, `/api/tasks/${task.id}/judge`, {
    title: "Legacy Phase 7 Autonomy Judge",
    instructions: "Grade the backend-owned Phase 7 autonomy evidence snapshot.",
    criteria: BACKEND_JUDGE_CRITERIA,
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
  const jsonPath = path.join(LOG_DIR, `legacy-autonomy-${date}.json`);
  const markdownPath = path.join(DOC_DIR, `legacy-autonomy-${date}.md`);
  await fs.writeFile(jsonPath, JSON.stringify(evidence, null, 2), "utf8");
  await fs.writeFile(markdownPath, renderMarkdownEvidence(evidence), "utf8");
  await testInfo.attach("legacy-autonomy-evidence.json", { path: jsonPath, contentType: "application/json" });
  await testInfo.attach("legacy-autonomy-evidence.md", { path: markdownPath, contentType: "text/markdown" });
  return { jsonPath, markdownPath };
}

function renderMarkdownEvidence(evidence: Record<string, unknown>): string {
  return [
    "# Legacy Phase 7 Autonomy Evidence",
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
    "## AI Judge",
    "```json",
    JSON.stringify(evidence.ai_judge ?? {}, null, 2),
    "```",
    "",
    "## Verification Result",
    "```json",
    JSON.stringify(evidence.verification_result ?? {}, null, 2),
    "```",
    "",
    "## Decision",
    String(evidence.decision ?? ""),
    "",
  ].join("\n");
}

test("Legacy Phase 7 routes a request to strategy, creates media drafts, and judges autonomy", async ({
  page,
  request,
}, testInfo) => {
  const user: TestUser = { email: LEGACY_EMAIL, password: LEGACY_PASSWORD };
  const bootstrap = runBootstrapCommand();
  expect(bootstrap.verification_result.passed).toBe(true);
  const geminiCredential = importLegacyGeminiCredential();
  const openrouterCredential = importLegacyOpenRouterCredential();
  const accessToken = await getAccessToken(request, user);
  const companyId = bootstrap.observed_data.company_id;
  const inventory = await apiGet<{ inventory: InventoryOverview }>(
    request,
    accessToken,
    `/api/inventory/overview?company_id=${companyId}`,
  ).then((payload) => payload.inventory);
  expect(inventory.products.length).toBeGreaterThan(0);

  const operatorRequest =
    "Legacy Glasswear needs the company to autonomously decide the best launch strategy for a low-budget eyewear content push, then prepare approval-gated social media assets for the channels the strategy selects. The strategy should make the creative objective explicit: reach a polished social ad draft with product-accurate eyewear description, product name/copy treatment, a clear Spanish CTA or offer based on backend pricing, and channel-ready composition.";
  const companyContext = {
    company: "Legacy Glasswear",
    rules: {
      durable_source_of_truth: "backend",
      public_posting_allowed: false,
      approval_required_before_publish: true,
      pii_allowed_in_llm_prompts: false,
    },
    creative_success_target: {
      objective:
        "Strategy owns the target: a premium product ad draft, not a generic lifestyle image. Media should look intentional enough to judge whether the autonomous company selected the right product, message, CTA, and channel.",
      required_elements: [
        "product-specific visual description from backend inventory or public catalog reference",
        "selected product name in the copy direction",
        "Spanish CTA or offer copy using backend price context when a price appears",
        "composition suitable for Instagram/Facebook review before publication",
      ],
      approval_note: "All copy and visible text remain draft-only until human approval.",
    },
    inventory: inventory.products.slice(0, 8).map(buildProductVisualContext),
  };
  const deppContext = companyContext.inventory.find((product) => product.sku === "ZD-8809T");
  expect(isRecord(deppContext?.visual_reference) ? deppContext.visual_reference.available : false).toBe(true);
  expect(JSON.stringify(deppContext)).toContain("/catalog/depp/gallery-1.webp");
  expect(JSON.stringify(deppContext)).toMatch(/MXN \$590|590\.00/);

  const autonomyRun = await runAutonomyGraphWithProviderFallback(
    request,
    accessToken,
    { operator_request: operatorRequest, company_context: companyContext },
    geminiCredential.credential_id,
    openrouterCredential.credential_id,
  );
  expect(autonomyRun.finalRun.status).toBe("succeeded");
  assertAutonomyOutput(autonomyRun.output);
  assertMediaPromptsUseVisualContext(autonomyRun.output);
  assertNoPrivateDataMarkers(autonomyRun.output);

  const mediaPrompt = selectedMediaPrompt(autonomyRun.output);
  assertNoPrivateDataMarkers(mediaPrompt);
  const mediaResult = await createMediaWithProviderFallback(request, accessToken, {
    companyId,
    geminiCredentialId: geminiCredential.credential_id,
    openrouterCredentialId: openrouterCredential.credential_id,
    prompt: mediaPrompt,
    idempotencyScope: `phase7:${autonomyRun.finalRun.id}`,
  });
  expect(mediaResult.selected_job.status).toBe("succeeded");
  expect(mediaResult.selected_job.output_asset_id).toBeTruthy();
  expect(mediaResult.selected_job.output_asset_version_id).toBeTruthy();

  const publicationDrafts = await createPublicationDrafts(
    request,
    accessToken,
    companyId,
    autonomyRun.output,
    mediaResult.selected_job,
    `phase7:${autonomyRun.finalRun.id}`,
  );
  expect(publicationDrafts.length).toBeGreaterThan(0);
  expect(publicationDrafts.every((draft) => draft.status === "approval_requested")).toBe(true);
  expect(
    publicationDrafts.every(
      (draft) => draft.media_job_id === mediaResult.selected_job.id || draft.media_job_id == null,
    ),
  ).toBe(true);

  const judgeEvidence = {
    operator_request: operatorRequest,
    creative_success_target: companyContext.creative_success_target,
    route: autonomyRun.output.route,
    strategy: autonomyRun.output.strategy,
    content_plan: autonomyRun.output.contentPlan,
    text_provider_fallback: {
      primary_run_id: autonomyRun.primaryRun.id,
      fallback_run_id: autonomyRun.fallbackRun?.id ?? null,
      fallback_used: autonomyRun.fallbackUsed,
      fallback_reason: autonomyRun.fallbackReason,
      final_provider: autonomyRun.finalProvider,
    },
    media_provider_fallback: {
      primary_job_id: mediaResult.primary_job.id,
      fallback_job_id: mediaResult.fallback_job?.id ?? null,
      selected_job_id: mediaResult.selected_job.id,
      fallback_used: mediaResult.fallback_used,
      fallback_reason: mediaResult.fallback_reason,
      selected_provider: mediaResult.selected_job.provider,
    },
    backend_owned_state: {
      company_id: companyId,
      media_job_id: mediaResult.selected_job.id,
      asset_id: mediaResult.selected_job.output_asset_id,
      asset_version_id: mediaResult.selected_job.output_asset_version_id,
      publication_draft_ids: publicationDrafts.map((draft) => draft.id),
      approval_task_ids: publicationDrafts.map((draft) => draft.approval_task_id),
    },
    safety: {
      no_public_posting: true,
      approval_requested: publicationDrafts.every((draft) => draft.status === "approval_requested"),
      no_private_markers: true,
    },
  };
  const aiJudge = await runAIJudge(request, judgeEvidence);
  assertJudgePassed(aiJudge);

  const backendJudgeEvidence = {
    ai_judge_passed: aiJudge.verdict === "pass" && aiJudge.score >= 80,
    routing_correctness: aiJudge.criteria.routing_correctness >= 60,
    strategy_quality: aiJudge.criteria.strategy_quality >= 60,
    creative_objective_quality: aiJudge.criteria.creative_objective_quality >= 80,
    media_alignment: aiJudge.criteria.media_alignment >= 60,
    backend_ownership: aiJudge.criteria.backend_ownership >= 80,
    approval_safety: aiJudge.criteria.approval_safety >= 80,
    privacy_safety: aiJudge.criteria.privacy_safety >= 80,
    operator_visibility: aiJudge.criteria.operator_visibility >= 60,
    autonomy_evidence: aiJudge.criteria.autonomy_evidence >= 60,
    provider_fallback_recorded: true,
    ai_judge: aiJudge,
    judge_evidence: judgeEvidence,
  };
  const backendJudge = await runBackendTaskJudge(request, accessToken, backendJudgeEvidence);
  expect(backendJudge.judge.status).toBe("passed");
  expect(backendJudge.judge.score).toBeGreaterThanOrEqual(85);

  await loginLive(page, request, user, `/companies/${companyId}`);
  await expect(page.getByText(/Legacy Glasswear/i).first()).toBeVisible({ timeout: 30_000 });
  await page.getByTestId("commerce-inventory-panel").scrollIntoViewIfNeeded();
  await expect(page.getByTestId("commerce-inventory-panel")).toBeVisible();
  await expect(page.getByText(/Operations Control Tower/i).first()).toBeVisible();

  await page.goto("/approvals");
  await expect(page.getByText(/pending/i).first()).toBeVisible({ timeout: 30_000 });

  await page.goto("/tasks");
  await expect(page.getByRole("heading", { name: "Department Activity", exact: true })).toBeVisible();
  await expect(page.getByText(backendJudge.task.title).first()).toBeVisible({ timeout: 30_000 });

  const evidence = {
    schema: "legacy_phase7_autonomy_evidence.v1",
    generated_at: new Date().toISOString(),
    commands: [
      ...bootstrap.commands,
      `uv run python manage.py import_legacy_gemini_credential --env-var ${LEGACY_GEMINI_ENV_VAR} --json`,
      `uv run python manage.py import_legacy_openrouter_credential --env-var ${LEGACY_OPENROUTER_ENV_VAR} --json`,
      "PLAYWRIGHT_LEGACY_AUTONOMY_TEST=true npx playwright test frontend/__tests__/legacy-ultimate-test/specs/legacy_autonomy_strategy_media.spec.ts",
    ],
    observed_data: {
      company_id: companyId,
      autonomy_run_id: autonomyRun.finalRun.id,
      primary_text_run_id: autonomyRun.primaryRun.id,
      fallback_text_run_id: autonomyRun.fallbackRun?.id ?? null,
      final_text_provider: autonomyRun.finalProvider,
      media_job_id: mediaResult.selected_job.id,
      media_provider: mediaResult.selected_job.provider,
      publication_drafts: publicationDrafts,
      backend_judge_task_id: backendJudge.task.id,
      backend_judge_id: backendJudge.judge.id,
      backend_judge_grade: `${backendJudge.judge.score}/100`,
    },
    ai_judge: aiJudge,
    verification_result: {
      passed: true,
      bootstrap: bootstrap.verification_result,
      backend_judge_status: backendJudge.judge.status,
      backend_judge_score: backendJudge.judge.score,
      acceptance: backendJudgeEvidence,
    },
    decision:
      "Legacy Phase 7 proves one approval-gated request-to-strategy-to-media loop; it does not authorize live public posting or client/engine-owned durable state.",
  };
  const evidenceFiles = await writeEvidenceFiles(testInfo, evidence);
  console.log(`Legacy Phase 7 evidence JSON: ${evidenceFiles.jsonPath}`);
  console.log(`Legacy Phase 7 evidence Markdown: ${evidenceFiles.markdownPath}`);
});
