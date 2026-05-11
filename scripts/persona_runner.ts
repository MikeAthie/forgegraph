const fs = require("fs");
const path = require("path");

type StepLog = {
  step: string;
  ui_seen: string;
  action: string;
  result: string;
  thought: string;
  confidence: "high" | "medium" | "low";
  expected_next_action?: string;
  ui_enabled_next_action?: string;
  expectation_gap?: string;
  error?: string;
};

type InteractionLog = {
  steps: StepLog[];
};

type PersonaExpectation = {
  expectation: string;
  success_criteria: string[];
  likely_concerns: string[];
  likely_first_action: string;
};

type PersonaFeedback = {
  persona: "Carlos";
  goal: string;
  success: boolean;
  expectation: string;
  expectation_match: string;
  confusion_score: number;
  clarity_score: number;
  yays: string[];
  nays: string[];
  friction_points: string[];
  trust: string;
  would_use_again: boolean;
};

type MockOperation = {
  id: string;
  status: "pending" | "running" | "succeeded" | "failed" | "paused";
  startedAt: string;
  endedAt?: string | null;
  operationBrief: string;
  deliverable?: string;
  currentNodeId?: string | null;
  failedNodeId?: string | null;
  errorMessage?: string;
  llmMode: "managed" | "byok";
};

type CompanyState = {
  id: string;
  versionId: string;
  version: number;
  name: string;
  description: string;
  graphJson: Record<string, any> | null;
  operationSeed: number;
  operations: MockOperation[];
};

const ROOT_DIR = process.cwd();
const { chromium } = require(
  path.join(ROOT_DIR, "frontend", "node_modules", "playwright"),
);
const OUTPUT_DIR = path.join(ROOT_DIR, "logs", "persona");
const OUTPUT_PATH = path.join(OUTPUT_DIR, "carlos.json");
const GOAL = "Create a company and launch useful work as quickly as possible";
const PERSONA = "Carlos" as const;
const DEFAULT_FRONTEND_URLS = [
  "http://127.0.0.1:3001",
  "http://127.0.0.1:3000",
];
const DEFAULT_LLM_BASE_URL = "http://127.0.0.1:12434/v1";
const OPERATION_COMPLETED_DELIVERABLE =
  "Deliverable: weekly business summary, priorities for the next cycle, and owner assignments Carlos can act on immediately.";

function loadRootEnv(): void {
  const envPath = path.join(ROOT_DIR, ".env");
  if (!fs.existsSync(envPath)) {
    return;
  }

  const raw = fs.readFileSync(envPath, "utf8");
  for (const rawLine of raw.split(/\r?\n/)) {
    const line = rawLine.trim();
    if (!line || line.startsWith("#")) {
      continue;
    }
    const separatorIndex = line.indexOf("=");
    if (separatorIndex < 1) {
      continue;
    }

    const key = line.slice(0, separatorIndex).trim();
    const value = line
      .slice(separatorIndex + 1)
      .trim()
      .replace(/^['"]|['"]$/g, "");

    if (!(key in process.env)) {
      process.env[key] = value;
    }
  }
}

async function isReachable(url: string): Promise<boolean> {
  try {
    const response = await fetch(url, { method: "GET" });
    return response.ok;
  } catch {
    return false;
  }
}

async function resolveFrontendUrl(): Promise<string> {
  const configured = [
    process.env.PLAYWRIGHT_DOCKER_FRONTEND_URL,
    process.env.PLAYWRIGHT_FRONTEND_URL,
    ...DEFAULT_FRONTEND_URLS,
    process.env.FRONTEND_URL,
  ].filter(Boolean) as string[];

  for (const baseUrl of configured) {
    if (await isReachable(`${baseUrl.replace(/\/$/, "")}/companies/new`)) {
      return baseUrl.replace(/\/$/, "");
    }
  }

  throw new Error(
    `Could not find a reachable ForgeGraph frontend. Checked: ${configured.map((value) => `${value}/companies/new`).join(", ")}`,
  );
}

function createCompanyState(): CompanyState {
  return {
    id: "c1111111-1111-4111-8111-111111111111",
    versionId: "v1111111-1111-4111-8111-111111111111",
    version: 1,
    name: "",
    description: "",
    graphJson: null,
    operationSeed: 1,
    operations: [],
  };
}

function getDepartmentNodes(
  graphJson: Record<string, any> | null,
): Array<Record<string, any>> {
  if (!graphJson || !Array.isArray(graphJson.nodes)) {
    return [];
  }

  return graphJson.nodes.filter(
    (node: Record<string, any>) => node.type !== "output",
  );
}

function findNodeLabel(
  graphJson: Record<string, any> | null,
  nodeId: string | null | undefined,
): string {
  if (!nodeId) {
    return "Department";
  }

  const node = graphJson?.nodes?.find?.(
    (candidate: Record<string, any>) => candidate.id === nodeId,
  );
  return typeof node?.name === "string" && node.name.trim()
    ? node.name.trim()
    : "Department";
}

function buildNodeRuns(
  operation: MockOperation,
  graphJson: Record<string, any> | null,
): Array<Record<string, any>> {
  const nodes = getDepartmentNodes(graphJson);
  const currentNodeId = operation.currentNodeId ?? nodes[0]?.id ?? null;
  const failedNodeId = operation.failedNodeId ?? currentNodeId;
  const currentIndex = nodes.findIndex((node) => node.id === currentNodeId);
  const failedIndex = nodes.findIndex((node) => node.id === failedNodeId);

  return nodes.flatMap((node, index) => {
    const base = {
      id: `${operation.id}-node-${index + 1}`,
      node_id: node.id,
      node_type: node.type,
      attempt: 1,
      started_at: operation.startedAt,
      ended_at: null,
      duration_ms: 12000,
      input_json: {
        operation_brief: operation.operationBrief,
      },
      output_json: null,
      error_json: null,
      agent_trace: null,
      memory_activity: null,
    };

    if (operation.status === "running") {
      if (index < (currentIndex >= 0 ? currentIndex : 0)) {
        return [
          {
            ...base,
            status: "succeeded",
            ended_at: "2026-04-26T12:03:00.000Z",
            output_json: {
              deliverable: `${node.name ?? "Department"} handed work forward.`,
            },
          },
        ];
      }
      if (index === (currentIndex >= 0 ? currentIndex : 0)) {
        return [{ ...base, status: "running" }];
      }
      return [];
    }

    if (operation.status === "failed") {
      if (index < (failedIndex >= 0 ? failedIndex : 0)) {
        return [
          {
            ...base,
            status: "succeeded",
            ended_at: "2026-04-26T12:03:00.000Z",
            output_json: {
              deliverable: `${node.name ?? "Department"} completed its work.`,
            },
          },
        ];
      }
      if (index === (failedIndex >= 0 ? failedIndex : 0)) {
        return [
          {
            ...base,
            status: "failed",
            ended_at: operation.endedAt ?? "2026-04-26T12:05:00.000Z",
            error_json: {
              message: operation.errorMessage ?? "Department needs attention.",
            },
          },
        ];
      }
      return [];
    }

    return [
      {
        ...base,
        status: "succeeded",
        ended_at: operation.endedAt ?? "2026-04-26T12:05:00.000Z",
        output_json: {
          deliverable:
            index === nodes.length - 1
              ? (operation.deliverable ?? "Deliverable ready for review.")
              : `${node.name ?? "Department"} completed its work.`,
        },
      },
    ];
  });
}

function buildRunDetail(
  company: CompanyState,
  operation: MockOperation,
): Record<string, any> {
  return {
    id: operation.id,
    owner_id: "persona-runner",
    thread_id: null,
    graph_id: company.id,
    graph_name: company.name,
    graph_version_id: company.versionId,
    graph_version: company.version,
    status: operation.status,
    queue_status:
      operation.status === "pending"
        ? "queued"
        : operation.status === "paused"
          ? "paused"
          : operation.status === "succeeded"
            ? "completed"
            : operation.status,
    queue_attempts: 1,
    queue_available_at: null,
    started_at: operation.startedAt,
    ended_at: operation.endedAt ?? null,
    input_json: {
      company_name: company.name,
      objective: company.description,
      operation_brief: operation.operationBrief,
    },
    output_json:
      operation.status === "succeeded"
        ? {
            deliverable:
              operation.deliverable ?? "Deliverable ready for review.",
          }
        : null,
    error_message: operation.errorMessage ?? "",
    duration_ms: operation.endedAt ? 120000 : 45000,
    node_runs: buildNodeRuns(operation, company.graphJson),
    agent_events: [],
    memory_activity: null,
    llm_access: {
      llm_mode: operation.llmMode,
      provider: "openai",
      credential_id: operation.llmMode === "byok" ? "persona-credential" : null,
      api_key_present: operation.llmMode === "byok",
    },
    paused_node_id: null,
    pause_payload: null,
  };
}

function buildRunListItem(
  company: CompanyState,
  operation: MockOperation,
): Record<string, any> {
  return {
    id: operation.id,
    graph_id: company.id,
    graph_name: company.name,
    graph_version_id: company.versionId,
    graph_version: company.version,
    status: operation.status,
    queue_status:
      operation.status === "pending"
        ? "queued"
        : operation.status === "paused"
          ? "paused"
          : operation.status === "succeeded"
            ? "completed"
            : operation.status,
    queue_attempts: 1,
    queue_available_at: null,
    started_at: operation.startedAt,
    ended_at: operation.endedAt ?? null,
    duration_ms: operation.endedAt ? 120000 : 45000,
    llm_access: {
      llm_mode: operation.llmMode,
      provider: "openai",
      credential_id: operation.llmMode === "byok" ? "persona-credential" : null,
      api_key_present: operation.llmMode === "byok",
    },
    memory_activity: {
      has_activity: false,
      save_node_count: 0,
      saved_observation_count: 0,
      retrieval_node_count: 0,
      retrieved_observation_count: 0,
      influenced_node_count: 0,
      influenced_observation_count: 0,
      degraded: false,
    },
  };
}

function apiSuccess(data: any): Record<string, any> {
  return {
    data,
    meta: {
      requestId: "persona-runner",
      timestamp: new Date().toISOString(),
    },
  };
}

function nextOperationId(company: CompanyState): string {
  company.operationSeed += 1;
  return `r1111111-1111-4111-8111-${String(company.operationSeed).padStart(12, "0")}`;
}

async function maybeText(locator: any): Promise<string | null> {
  try {
    if ((await locator.count()) < 1) {
      return null;
    }
    const first = locator.first();
    if (!(await first.isVisible().catch(() => false))) {
      return null;
    }
    const text = (await first.innerText().catch(() => null))?.trim();
    return text ? text.replace(/\s+/g, " ") : null;
  } catch {
    return null;
  }
}

async function joinSeen(
  parts: Array<Promise<string | null> | string | null>,
): Promise<string> {
  const resolved = [];
  for (const part of parts) {
    const value = typeof part === "string" || part === null ? part : await part;
    if (value) {
      resolved.push(value);
    }
  }
  return resolved.join(" | ");
}

function normalizeJsonResponse(raw: string): string {
  const fenced = raw.match(/```(?:json)?\s*([\s\S]*?)```/i);
  if (fenced?.[1]) {
    return fenced[1].trim();
  }

  const firstBrace = raw.indexOf("{");
  const lastBrace = raw.lastIndexOf("}");
  if (firstBrace >= 0 && lastBrace > firstBrace) {
    return raw.slice(firstBrace, lastBrace + 1);
  }
  return raw.trim();
}

async function callLocalLlmJson<T>(prompt: string): Promise<T> {
  const baseUrl = (
    process.env.OPENAI_BASE_URL ??
    process.env.LOCAL_LLM_BASE_URL ??
    DEFAULT_LLM_BASE_URL
  ).replace(/\/$/, "");
  const model =
    process.env.PERSONA_LLM_MODEL ?? (await resolveLocalModelId(baseUrl));
  const response = await fetch(`${baseUrl}/chat/completions`, {
    method: "POST",
    headers: {
      "Content-Type": "application/json",
      Authorization: `Bearer ${process.env.OPENAI_API_KEY ?? "local-persona-runner"}`,
    },
    body: JSON.stringify({
      model,
      temperature: 0.2,
      messages: [{ role: "user", content: prompt }],
    }),
  });

  if (!response.ok) {
    throw new Error(`Local LLM call failed with status ${response.status}.`);
  }

  const body = (await response.json()) as {
    choices?: Array<{
      message?: {
        content?: string;
      };
    }>;
  };
  const content = body.choices?.[0]?.message?.content;
  if (!content) {
    throw new Error("Local LLM did not return a message.");
  }

  return JSON.parse(normalizeJsonResponse(content)) as T;
}

function extractLineAfterLabel(text: string, label: string): string | null {
  const pattern = new RegExp(`${label}\\s*:?\\s*([^\\n]+)`, "i");
  const match = text.match(pattern);
  return match?.[1]?.trim() ?? null;
}

async function resolveLocalModelId(baseUrl: string): Promise<string> {
  const response = await fetch(`${baseUrl.replace(/\/$/, "")}/models`);
  if (!response.ok) {
    throw new Error(
      `Local LLM model discovery failed with status ${response.status}.`,
    );
  }
  const body = (await response.json()) as { data?: Array<{ id?: string }> };
  const modelId = body.data?.[0]?.id;
  if (!modelId) {
    throw new Error("Local LLM did not return any model ids.");
  }
  return modelId;
}

async function buildPersonaExpectation(): Promise<PersonaExpectation> {
  return callLocalLlmJson<PersonaExpectation>(`You are Carlos.

Persona:
- Mid 30s entrepreneur in Mexico
- Fluent English
- Moderately technical, no programming experience
- Outcome-driven
- Impatient with complexity
- Wants results fast
- Open to AI, skeptical if confusing
- Comfortable with business tools, not developer tools

Goal:
${GOAL}

Assume Carlos opens the product directly. He does not read documentation first, does not watch tutorials first, and wants a useful result in under 2 minutes.
Carlos does not think in developer or system terms. He is trying to create a company and get useful work done.
Do not assume Carlos expects graphs, nodes, workflows, or projects unless the visible product experience would force that conclusion.

Before using ForgeGraph, what do you expect will happen inside the product itself?

Return only valid JSON:
{
  "expectation": "...",
  "success_criteria": ["..."],
  "likely_concerns": ["..."],
  "likely_first_action": "..."
}`);
}

async function enrichInteractionLog(
  expectation: PersonaExpectation,
  interactionLog: InteractionLog,
): Promise<InteractionLog> {
  const prompt = `You are Carlos, an entrepreneur using ForgeGraph.

Goal:
${GOAL}

Before starting, you expected:
${JSON.stringify(expectation, null, 2)}

Here is the interaction log:
${JSON.stringify(interactionLog, null, 2)}

For each step, add:
- "thought": what Carlos is thinking in the moment
- "confidence": "high", "medium", or "low"
- "expected_next_action": what Carlos wants to do next
- "ui_enabled_next_action": what the UI seems to allow next
- "expectation_gap": short note on mismatch between expectation and reality at that step

Be blunt, realistic, and impatient. Do not be polite.

Return only valid JSON:
{
  "steps": [
    {
      "step": "same step name",
      "thought": "...",
      "confidence": "high",
      "expected_next_action": "...",
      "ui_enabled_next_action": "...",
      "expectation_gap": "..."
    }
  ]
}`;

  const enriched = await callLocalLlmJson<{
    steps?: Array<{
      step?: string;
      thought?: string;
      confidence?: "high" | "medium" | "low";
      expected_next_action?: string;
      ui_enabled_next_action?: string;
      expectation_gap?: string;
    }>;
  }>(prompt);

  const annotationsByStep = new Map(
    (enriched.steps ?? []).map((step) => [step.step ?? "", step]),
  );

  return {
    steps: interactionLog.steps.map((step) => {
      const annotation = annotationsByStep.get(step.step);
      return {
        ...step,
        thought: annotation?.thought?.trim() || step.thought,
        confidence:
          annotation?.confidence === "high" ||
          annotation?.confidence === "medium" ||
          annotation?.confidence === "low"
            ? annotation.confidence
            : step.confidence,
        expected_next_action:
          annotation?.expected_next_action?.trim() || step.expected_next_action,
        ui_enabled_next_action:
          annotation?.ui_enabled_next_action?.trim() ||
          step.ui_enabled_next_action,
        expectation_gap:
          annotation?.expectation_gap?.trim() || step.expectation_gap,
      };
    }),
  };
}

async function evaluatePersona(
  expectation: PersonaExpectation,
  interactionLog: InteractionLog,
): Promise<PersonaFeedback> {
  const prompt = `You are Carlos, an entrepreneur using ForgeGraph.

Before using ForgeGraph, you expected:
${JSON.stringify(expectation, null, 2)}

You just tried to:

Create a company and launch useful work.

Here is what happened:

${JSON.stringify(interactionLog, null, 2)}

---

Evaluate your experience.

---

# OUTPUT

## Did you succeed?

yes / no

---

## Yays

What felt good or valuable?

---

## Nays

What was confusing, frustrating, or unclear?

---

## Friction Points

Where did you hesitate or feel lost?

---

## Trust

Do you trust the system? Why or why not?

---

## Would you use it again?

yes / no

---

Be honest. Be critical. Do not be polite.
Prioritize concrete friction over compliments. If something is only acceptable, do not list it as a yay.
Scoring:
- confusion_score: 0 means no confusion, 10 means very confused
- clarity_score: 0 means unclear, 10 means extremely clear

Return only valid JSON with this exact shape:
{
  "persona": "Carlos",
  "goal": "${GOAL}",
  "success": true,
  "expectation": "...",
  "expectation_match": "...",
  "confusion_score": 0,
  "clarity_score": 0,
  "yays": ["..."],
  "nays": ["..."],
  "friction_points": ["..."],
  "trust": "...",
  "would_use_again": true
}`;

  const parsed = await callLocalLlmJson<PersonaFeedback>(prompt);

  return {
    persona: PERSONA,
    goal: GOAL,
    success: Boolean(parsed.success),
    expectation:
      typeof parsed.expectation === "string"
        ? parsed.expectation
        : expectation.expectation,
    expectation_match:
      typeof parsed.expectation_match === "string"
        ? parsed.expectation_match
        : "",
    confusion_score: Number.isFinite(parsed.confusion_score)
      ? Math.max(0, Math.min(10, Number(parsed.confusion_score)))
      : 0,
    clarity_score: Number.isFinite(parsed.clarity_score)
      ? Math.max(0, Math.min(10, Number(parsed.clarity_score)))
      : 0,
    yays: Array.isArray(parsed.yays) ? parsed.yays.map(String) : [],
    nays: Array.isArray(parsed.nays) ? parsed.nays.map(String) : [],
    friction_points: Array.isArray(parsed.friction_points)
      ? parsed.friction_points.map(String)
      : [],
    trust: typeof parsed.trust === "string" ? parsed.trust : "",
    would_use_again: Boolean(parsed.would_use_again),
  };
}

async function runPersonaFlow(frontendUrl: string): Promise<InteractionLog> {
  const browser = await chromium.launch({ headless: true });
  const context = await browser.newContext({ baseURL: frontendUrl });
  const page = await context.newPage();
  const interactionLog: InteractionLog = { steps: [] };
  const company = createCompanyState();
  const accessToken = "persona-carlos-token";
  const organizationId = "a1111111-1111-4111-8111-111111111111";
  const organizationName = "Operadora Horizonte";
  const objective = "i want to understand my business better and improve it";
  const operationBrief = "help me figure out what to do next this week";

  function logStep(step: StepLog): void {
    interactionLog.steps.push(step);
  }

  await context.route("**/api/auth/me", async (route: any) => {
    await route.fulfill({
      status: 200,
      contentType: "application/json",
      body: JSON.stringify({
        id: "persona-carlos-user",
        email: "carlos.persona@example.com",
        created_at: new Date().toISOString(),
        is_active: true,
        default_organization_id: organizationId,
        organization_role: "owner",
      }),
    });
  });

  await context.route("**/api/auth/refresh", async (route: any) => {
    await route.fulfill({
      status: 200,
      contentType: "application/json",
      body: JSON.stringify({ access: accessToken }),
    });
  });

  await context.route(/\/api\/orgs\/?(?:\?.*)?$/, async (route: any) => {
    if (route.request().method() === "GET") {
      await route.fulfill({
        status: 200,
        contentType: "application/json",
        body: JSON.stringify(
          apiSuccess([
            {
              id: organizationId,
              name: organizationName,
              created_at: "2026-04-26T12:00:00.000Z",
              updated_at: "2026-04-26T12:00:00.000Z",
              role: "owner",
              is_default: true,
              joined_at: "2026-04-26T12:00:00.000Z",
            },
          ]),
        ),
      });
      return;
    }

    await route.fallback();
  });

  await context.route(/\/api\/orgs\/current(?:\?.*)?$/, async (route: any) => {
    await route.fulfill({
      status: 200,
      contentType: "application/json",
      body: JSON.stringify(
        apiSuccess({
          id: organizationId,
          name: organizationName,
          created_at: "2026-04-26T12:00:00.000Z",
          updated_at: "2026-04-26T12:00:00.000Z",
          role: "owner",
          is_default: true,
          joined_at: "2026-04-26T12:00:00.000Z",
        }),
      ),
    });
  });

  await context.route(/\/api\/graphs\/?(?:\?.*)?$/, async (route: any) => {
    const method = route.request().method();
    if (method === "GET") {
      const graphList =
        company.graphJson && company.name
          ? [
              {
                id: company.id,
                name: company.name,
                description: company.description,
                created_at: "2026-04-26T12:00:00.000Z",
                updated_at: "2026-04-26T12:00:00.000Z",
                version_count: company.version,
                latest_version: company.version,
              },
            ]
          : [];
      await route.fulfill({
        status: 200,
        contentType: "application/json",
        body: JSON.stringify(apiSuccess(graphList)),
      });
      return;
    }

    if (method === "POST") {
      const payload = route.request().postDataJSON() as Record<string, any>;
      company.name = String(payload?.name ?? "Carlos Company");
      company.description = String(payload?.description ?? "");
      await route.fulfill({
        status: 200,
        contentType: "application/json",
        body: JSON.stringify(
          apiSuccess({
            id: company.id,
            name: company.name,
            description: company.description,
          }),
        ),
      });
      return;
    }

    await route.fallback();
  });

  await context.route(
    new RegExp(`/api/graphs/${company.id}/versions(?:\\?.*)?$`),
    async (route: any) => {
      if (route.request().method() !== "POST") {
        await route.fallback();
        return;
      }

      const payload = route.request().postDataJSON() as Record<string, any>;
      company.graphJson = payload?.graph_json ?? null;
      await route.fulfill({
        status: 200,
        contentType: "application/json",
        body: JSON.stringify(
          apiSuccess({
            id: company.versionId,
            version: company.version,
            graph_json: company.graphJson,
          }),
        ),
      });
    },
  );

  await context.route(
    new RegExp(`/api/graphs/${company.id}/versions/latest(?:\\?.*)?$`),
    async (route: any) => {
      await route.fulfill({
        status: 200,
        contentType: "application/json",
        body: JSON.stringify(
          apiSuccess({
            id: company.versionId,
            version: company.version,
            graph_json: company.graphJson,
          }),
        ),
      });
    },
  );

  await context.route(
    new RegExp(`/api/graphs/${company.id}(?:\\?.*)?$`),
    async (route: any) => {
      await route.fulfill({
        status: 200,
        contentType: "application/json",
        body: JSON.stringify(
          apiSuccess({
            id: company.id,
            owner_id: "persona-carlos-user",
            name: company.name,
            description: company.description,
            created_at: "2026-04-26T12:00:00.000Z",
            updated_at: "2026-04-26T12:00:00.000Z",
            versions: [
              {
                id: company.versionId,
                version: company.version,
                checksum: `checksum-${company.versionId}`,
                created_at: "2026-04-26T12:00:00.000Z",
              },
            ],
          }),
        ),
      });
    },
  );

  await context.route(
    /\/api\/approvals\/count(?:\?.*)?$/,
    async (route: any) => {
      await route.fulfill({
        status: 200,
        contentType: "application/json",
        body: JSON.stringify(apiSuccess({ count: 0 })),
      });
    },
  );

  await context.route(
    /\/api\/decisions\/count(?:\?.*)?$/,
    async (route: any) => {
      await route.fulfill({
        status: 200,
        contentType: "application/json",
        body: JSON.stringify(apiSuccess({ count: 0 })),
      });
    },
  );

  await context.route(/\/api\/approvals\/?(?:\?.*)?$/, async (route: any) => {
    await route.fulfill({
      status: 200,
      contentType: "application/json",
      body: JSON.stringify(apiSuccess([])),
    });
  });

  await context.route(/\/api\/runs\/start(?:\?.*)?$/, async (route: any) => {
    const payload =
      (route.request().postDataJSON() as Record<string, any>) ?? {};
    const departments = getDepartmentNodes(company.graphJson);
    const currentNodeId = departments[1]?.id ?? departments[0]?.id ?? null;
    const operation: MockOperation = {
      id: nextOperationId(company),
      status: "running",
      startedAt: "2026-04-26T12:01:00.000Z",
      operationBrief:
        String(
          (payload?.input_json as Record<string, any> | undefined)
            ?.operation_brief ?? "",
        ) || "Run the next company operation.",
      currentNodeId,
      llmMode: payload?.llm_mode === "byok" ? "byok" : "managed",
    };
    company.operations = [operation];
    await route.fulfill({
      status: 200,
      contentType: "application/json",
      body: JSON.stringify(apiSuccess(buildRunDetail(company, operation))),
    });
  });

  await context.route(/\/api\/runs\/?(?:\?.*)?$/, async (route: any) => {
    if (route.request().method() !== "GET") {
      await route.fallback();
      return;
    }

    await route.fulfill({
      status: 200,
      contentType: "application/json",
      body: JSON.stringify(
        apiSuccess(
          company.operations.map((operation) =>
            buildRunListItem(company, operation),
          ),
        ),
      ),
    });
  });

  await context.route(
    /\/api\/runs\/(?!start(?:\?|$))[^/]+(?:\?.*)?$/,
    async (route: any) => {
      const runId =
        route.request().url().split("/api/runs/")[1]?.split("?")[0] ?? "";
      const operation = company.operations.find(
        (candidate) => candidate.id === runId,
      );
      if (!operation) {
        await route.fulfill({
          status: 404,
          contentType: "application/json",
          body: JSON.stringify({
            error: {
              code: "NOT_FOUND",
              message: "Operation not found.",
            },
            meta: {
              requestId: "persona-runner-not-found",
              timestamp: new Date().toISOString(),
            },
          }),
        });
        return;
      }

      await route.fulfill({
        status: 200,
        contentType: "application/json",
        body: JSON.stringify(apiSuccess(buildRunDetail(company, operation))),
      });
    },
  );

  await context.addInitScript((seedToken: string) => {
    window.sessionStorage.setItem("__FORGEGRAPH_E2E_ACCESS_TOKEN__", seedToken);
    (
      window as Window & { __FORGEGRAPH_E2E_ACCESS_TOKEN__?: string }
    ).__FORGEGRAPH_E2E_ACCESS_TOKEN__ = seedToken;
  }, accessToken);

  try {
    await page.goto("/companies/new");
    await page.waitForLoadState("networkidle");
    logStep({
      step: "Open the company builder",
      ui_seen: await joinSeen([
        maybeText(
          page.getByRole("heading", { name: /define the objective first/i }),
        ),
        maybeText(page.getByText(/what should this company accomplish\?/i)),
        maybeText(page.getByText(/launch a marketing campaign/i)),
      ]),
      action: "Open the builder to create a company.",
      result:
        "The objective-first wizard loads and explains the first decision clearly.",
      thought: "I just want to get something useful running fast.",
      confidence: "medium",
      expected_next_action: "Name the company and describe the result I want.",
      ui_enabled_next_action:
        "Enter a company name and business objective, then continue.",
      expectation_gap:
        "No major gap yet. The entry point looks business-oriented, not technical.",
    });

    await page.getByTestId("company-name-input").fill("Operadora Horizonte");
    await page.getByTestId("company-objective-input").fill(objective);
    logStep({
      step: "Define the company objective",
      ui_seen: await joinSeen([
        maybeText(
          page.getByRole("heading", { name: /define the objective first/i }),
        ),
        maybeText(page.getByTestId("company-objective-input")),
      ]),
      action: "Name the company and describe the work it should accomplish.",
      result: `Carlos defines an outcome-driven objective: "${objective}"`,
      thought:
        "This is vague, but that's how I'd probably describe it in real life.",
      confidence: "medium",
      expected_next_action:
        "See if the product can turn that vague goal into a sensible setup.",
      ui_enabled_next_action: "Continue to the suggested setup.",
      expectation_gap:
        "The UI accepts ambiguous input, which is good, but I still don't know how much guidance I'll get.",
    });
    await page.getByRole("button", { name: /continue/i }).click();

    await page.waitForLoadState("networkidle");
    logStep({
      step: "Review the suggested setup",
      ui_seen: await joinSeen([
        maybeText(page.getByText(/review the suggested structure/i)),
        maybeText(page.getByText(/suggested category/i)),
        maybeText(
          page.getByText(
            /general company|operations & delivery|research & advisory|professional services/i,
          ),
        ),
        maybeText(page.getByText(/because your goal is/i)),
        maybeText(page.getByText(/this company will/i)),
      ]),
      action:
        "Review the company category and starting team suggested from the objective.",
      result:
        "ForgeGraph suggests a broad company setup instead of forcing Carlos to categorize the company first.",
      thought:
        "I think this makes sense, but I want to know why it picked this structure.",
      confidence: "medium",
      expected_next_action:
        "Decide whether to keep the suggestion or adjust it.",
      ui_enabled_next_action:
        "Review the suggested category, change it if needed, then continue.",
      expectation_gap:
        "The UI shows the suggestion, but not much reasoning behind it.",
    });
    await page.getByRole("button", { name: /continue/i }).click();

    await page.waitForLoadState("networkidle");
    const visibleDepartment = await maybeText(
      page.locator('[data-testid^="department-chip-"]').first(),
    );
    logStep({
      step: "Adjust the team",
      ui_seen: await joinSeen([
        maybeText(page.getByText(/adjust the team/i)),
        maybeText(page.getByText(/this team will work together to:/i)),
        visibleDepartment,
        maybeText(
          page.getByText(
            /helps you decide what to do|produce usable output|tell you what to do next/i,
          ),
        ),
      ]),
      action:
        "Scan the suggested departments and keep the default team to move quickly.",
      result: `Carlos sees a department-first team model${visibleDepartment ? `, starting with ${visibleDepartment}` : ""}.`,
      thought:
        "I could tweak this, but I mostly want to move on unless something looks obviously wrong.",
      confidence: "medium",
      expected_next_action:
        "Either accept the default team or make one obvious adjustment.",
      ui_enabled_next_action:
        "Modify departments and skills or continue with the default team.",
      expectation_gap:
        "The step is usable, but the value of each department is not explained enough for a quick decision.",
    });
    await page.getByRole("button", { name: /continue/i }).click();

    await page.waitForLoadState("networkidle");
    logStep({
      step: "Choose operating rules",
      ui_seen: await joinSeen([
        maybeText(page.getByText(/choose operating rules/i)),
        maybeText(
          page.getByText(
            /assisted starts work automatically and pauses only when a decision is worth your time/i,
          ),
        ),
        maybeText(
          page.getByText(
            /managed uses forgegraph's ai access so you can launch immediately/i,
          ),
        ),
      ]),
      action: "Keep the default Assisted autonomy mode and Managed AI mode.",
      result:
        "The default policy makes it obvious what happens after launch and avoids configuration overhead.",
      thought:
        "I’ll keep the defaults, but I’m trusting the wording more than I fully understand the implications.",
      confidence: "medium",
      expected_next_action:
        "Confirm the safest default path and move to launch.",
      ui_enabled_next_action: "Choose autonomy and AI mode, then continue.",
      expectation_gap:
        "The defaults are clear enough to accept, but not yet clear enough to feel fully informed.",
    });
    await page.getByRole("button", { name: /continue/i }).click();

    await page.waitForLoadState("networkidle");
    await page
      .getByTestId("company-operation-brief-input")
      .fill(operationBrief);
    logStep({
      step: "Launch the first operation",
      ui_seen: await joinSeen([
        maybeText(page.getByText(/launch first operation/i)),
        maybeText(page.getByTestId("company-operation-brief-input")),
        maybeText(page.getByText(/preview outcome/i)),
        maybeText(page.getByText(/a clear plan/i)),
        maybeText(page.getByText(/concrete actions/i)),
      ]),
      action: "Add a concrete first operation brief and launch the company.",
      result: `Carlos launches useful work immediately with: "${operationBrief}"`,
      thought:
        "This is the moment of truth. If I click launch, I expect visible work, not more setup.",
      confidence: "high",
      expected_next_action:
        "Launch and see the company actually do something useful.",
      ui_enabled_next_action:
        "Create the company and launch the first operation immediately.",
      expectation_gap: "The UI supports the right next move cleanly here.",
    });
    await page.getByTestId("company-create-submit").click();

    await page.waitForURL(new RegExp(`/companies/${company.id}$`), {
      timeout: 20000,
    });
    await page.waitForLoadState("networkidle");
    const runningOperation = company.operations[0];
    const workspaceText = await page.locator("main").innerText();
    const currentDepartment =
      extractLineAfterLabel(workspaceText, "Current department") ??
      findNodeLabel(company.graphJson, runningOperation?.currentNodeId);
    logStep({
      step: "Observe the company workspace",
      ui_seen: await joinSeen([
        maybeText(page.getByRole("heading", { name: /operadora horizonte/i })),
        maybeText(page.getByRole("heading", { name: /^operations$/i })),
        currentDepartment,
      ]),
      action:
        "Review the running operation and see which department is acting now.",
      result: `The workspace shows live progress through departments, with ${currentDepartment} currently working.`,
      thought:
        "Good, something is happening. I want to know if this will end in a usable output fast.",
      confidence: "high",
      expected_next_action:
        "Watch progress briefly and check whether a deliverable appears.",
      ui_enabled_next_action:
        "Inspect the running operation, departments, and command controls.",
      expectation_gap:
        "The workspace feels alive, but I still need clearer proof of what I'll get at the end.",
    });

    company.operations[0] = {
      ...runningOperation,
      status: "succeeded",
      endedAt: "2026-04-26T12:05:00.000Z",
      deliverable: OPERATION_COMPLETED_DELIVERABLE,
    };

    await page.reload();
    await page.waitForLoadState("networkidle");
    const completedWorkspaceText = await page.locator("main").innerText();
    const deliverablePreview =
      extractLineAfterLabel(completedWorkspaceText, "Latest outputs") ??
      extractLineAfterLabel(completedWorkspaceText, "Operation deliverable") ??
      "Deliverable preview visible";
    logStep({
      step: "Review the deliverable",
      ui_seen: await joinSeen([
        maybeText(page.getByText(/^completed$/i)),
        maybeText(page.getByText(/latest outputs/i)),
        deliverablePreview,
      ]),
      action: "Review the completed operation and its output.",
      result:
        "Carlos receives a readable deliverable in plain language instead of raw system output.",
      thought: "This is what I wanted: something I can read and act on.",
      confidence: "high",
      expected_next_action:
        "Decide whether to run another operation or change the objective.",
      ui_enabled_next_action:
        "Review the deliverable and choose a next action from the workspace.",
      expectation_gap:
        "The result matches the promise better here than in the middle steps.",
    });
  } catch (error) {
    const message = error instanceof Error ? error.message : String(error);
    logStep({
      step: "Persona run failed",
      ui_seen: page.url(),
      action: "Attempt to complete the onboarding and workspace flow.",
      result: "The persona flow did not complete.",
      thought: "Something broke and I don't know if it's me or the product.",
      confidence: "low",
      expected_next_action: "Recover quickly or leave.",
      ui_enabled_next_action: "Unknown because the flow failed.",
      expectation_gap:
        "The product did not support a smooth path to first success.",
      error: message,
    });
    throw error;
  } finally {
    await browser.close();
  }

  return interactionLog;
}

async function main(): Promise<void> {
  loadRootEnv();
  fs.mkdirSync(OUTPUT_DIR, { recursive: true });

  const frontendUrl = await resolveFrontendUrl();
  const expectation = await buildPersonaExpectation();
  const interactionLog = await runPersonaFlow(frontendUrl);
  const enrichedInteractionLog = await enrichInteractionLog(
    expectation,
    interactionLog,
  );
  const feedback = await evaluatePersona(expectation, enrichedInteractionLog);

  const output = {
    persona: PERSONA,
    goal: GOAL,
    expectation,
    success: feedback.success,
    expectation_match: feedback.expectation_match,
    confusion_score: feedback.confusion_score,
    clarity_score: feedback.clarity_score,
    yays: feedback.yays,
    nays: feedback.nays,
    friction_points: feedback.friction_points,
    trust: feedback.trust,
    would_use_again: feedback.would_use_again,
    interaction_log: enrichedInteractionLog,
    metadata: {
      frontend_url: frontendUrl,
      llm_base_url: (
        process.env.OPENAI_BASE_URL ??
        process.env.LOCAL_LLM_BASE_URL ??
        DEFAULT_LLM_BASE_URL
      ).replace(/\/$/, ""),
      generated_at: new Date().toISOString(),
    },
  };

  fs.writeFileSync(OUTPUT_PATH, `${JSON.stringify(output, null, 2)}\n`, "utf8");
  process.stdout.write(`${JSON.stringify(output, null, 2)}\n`);
}

main().catch((error: unknown) => {
  const message =
    error instanceof Error ? (error.stack ?? error.message) : String(error);
  process.stderr.write(`${message}\n`);
  process.exitCode = 1;
});
