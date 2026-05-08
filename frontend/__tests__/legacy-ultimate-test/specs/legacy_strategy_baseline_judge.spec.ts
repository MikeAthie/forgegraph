import { expect, test, type APIRequestContext, type TestInfo } from "@playwright/test";
import { execFileSync } from "child_process";

import { getAccessToken } from "../../e2e/helpers";

const API_BASE_URL = (
  process.env.PLAYWRIGHT_API_URL ??
  process.env.NEXT_PUBLIC_API_URL ??
  "http://127.0.0.1:8000"
).replace(/\/$/, "");

const LEGACY_EMAIL = process.env.PLAYWRIGHT_LEGACY_EMAIL ?? "legacy.glasswear.test@example.com";
const LEGACY_PASSWORD = process.env.PLAYWRIGHT_LEGACY_PASSWORD ?? process.env.LEGACY_TEST_PASSWORD ?? "";
const LEGACY_COMPANY_ID = process.env.PLAYWRIGHT_LEGACY_COMPANY_ID ?? "";
const LEGACY_RUN_ID = process.env.PLAYWRIGHT_LEGACY_RUN_ID ?? process.env.LEGACY_STRATEGY_RUN_ID ?? "";

test.skip(
  process.env.PLAYWRIGHT_LEGACY_ULTIMATE_TEST !== "true",
  "Set PLAYWRIGHT_LEGACY_ULTIMATE_TEST=true to judge the Legacy ultimate-test run.",
);

test.skip(!LEGACY_PASSWORD, "Set PLAYWRIGHT_LEGACY_PASSWORD or LEGACY_TEST_PASSWORD for the seeded Legacy user.");

type TestUser = {
  email: string;
  password: string;
};

type LegacyRunDetail = {
  id: string;
  graph_id: string;
  graph_name?: string | null;
  graph_version_id: string;
  status: string;
  duration_ms?: number | null;
  error_message?: string | null;
  output_json?: Record<string, unknown> | null;
  node_runs: Array<{
    node_id: string;
    node_type?: string;
    status: string;
    attempt: number;
    output_json?: Record<string, unknown> | null;
    error_json?: Record<string, unknown> | null;
  }>;
};

type LegacyObjectiveContract = {
  id: string;
  operation_id: string;
  status: string;
  run_goal: string;
  target_signal?: string | null;
  success_score?: number | null;
  miss_analysis?: string | null;
  next_decision?: string | null;
  integrity_gates?: Record<string, unknown> | null;
};

type CompanyOpsOverview = {
  company_id: string;
  objective_contracts?: LegacyObjectiveContract[];
};

type GraphListItem = {
  id: string;
  name: string;
  description?: string | null;
};

type StrategyBaseline = {
  strategy?: {
    positioning?: string | null;
    first_run_focus?: string | null;
    operating_principles?: string[] | null;
    department_roles?: Array<{
      department?: string | null;
      responsibility?: string | null;
    }> | null;
  } | null;
  visual_content_needed?: Array<{
    asset?: string | null;
    purpose?: string | null;
    priority?: string | null;
  }> | null;
  kpis?: Array<{
    name?: string | null;
    target?: string | null;
    measurement?: string | null;
    owner?: string | null;
  }> | null;
  goals?: string[] | null;
  success_criteria?: string[] | null;
  out_of_scope?: string[] | null;
  next_run_plan?: string[] | null;
};

type JudgeCheck = {
  name: string;
  passed: boolean;
  points: number;
  reason: string;
};

type LegacyStrategyJudgement = {
  verdict: "pass" | "partial" | "fail";
  score: number;
  earned_points: number;
  possible_points: number;
  threshold: number;
  required_missing: string[];
  checks: JudgeCheck[];
};

const REQUIRED_SECTIONS: Array<keyof StrategyBaseline> = [
  "strategy",
  "visual_content_needed",
  "kpis",
  "goals",
  "success_criteria",
  "out_of_scope",
  "next_run_plan",
];

const EXPECTED_DEPARTMENTS = [
  "Operating System",
  "Content Studio",
  "Social Desk",
  "Sales Desk",
  "Ops & Inventory",
  "Finance & Procurement",
];

function unwrap<T>(payload: unknown): T {
  if (payload && typeof payload === "object" && "data" in payload) {
    return (payload as { data: T }).data;
  }
  return payload as T;
}

function isRecord(value: unknown): value is Record<string, unknown> {
  return Boolean(value && typeof value === "object" && !Array.isArray(value));
}

function isNonEmptyString(value: unknown): value is string {
  return typeof value === "string" && value.trim().length > 0;
}

function isNonEmptyArray(value: unknown): value is unknown[] {
  return Array.isArray(value) && value.length > 0;
}

function normalize(value: unknown): string {
  return String(value ?? "")
    .toLowerCase()
    .replace(/\s+/g, " ")
    .trim();
}

function parsePossiblyFencedJson(value: unknown): Record<string, unknown> | null {
  if (isRecord(value)) {
    return value;
  }
  if (typeof value !== "string") {
    return null;
  }

  let text = value.trim();
  const fenced = text.match(/^```(?:json)?\s*([\s\S]*?)\s*```$/i);
  if (fenced) {
    text = fenced[1].trim();
  }

  try {
    const parsed = JSON.parse(text);
    return isRecord(parsed) ? parsed : null;
  } catch {
    const firstBrace = text.indexOf("{");
    const lastBrace = text.lastIndexOf("}");
    if (firstBrace < 0 || lastBrace <= firstBrace) {
      return null;
    }
    try {
      const parsed = JSON.parse(text.slice(firstBrace, lastBrace + 1));
      return isRecord(parsed) ? parsed : null;
    } catch {
      return null;
    }
  }
}

function extractStrategyBaseline(run: LegacyRunDetail): StrategyBaseline | null {
  const output = run.output_json;
  const candidates: unknown[] = [];

  if (isRecord(output)) {
    candidates.push(output.strategy_baseline);
    const trace = output.planner_trace;
    if (isRecord(trace)) {
      candidates.push(trace.response, trace.raw_response);
    }
  }

  for (const nodeRun of run.node_runs ?? []) {
    const nodeOutput = nodeRun.output_json;
    if (!isRecord(nodeOutput)) {
      continue;
    }
    candidates.push(nodeOutput.strategy_baseline);
    const trace = nodeOutput.planner_trace;
    if (isRecord(trace)) {
      candidates.push(trace.response, trace.raw_response);
    }
  }

  for (const candidate of candidates) {
    const parsed = parsePossiblyFencedJson(candidate);
    if (parsed) {
      return parsed as StrategyBaseline;
    }
  }

  return null;
}

function arraySectionComplete(value: unknown): boolean {
  return (
    isNonEmptyArray(value) &&
    value.every((item) => {
      if (typeof item === "string") {
        return item.trim().length > 0;
      }
      return isRecord(item) && Object.values(item).some(isNonEmptyString);
    })
  );
}

function sectionComplete(baseline: StrategyBaseline, section: keyof StrategyBaseline): boolean {
  const value = baseline[section];
  if (Array.isArray(value)) {
    return arraySectionComplete(value);
  }
  if (section === "strategy") {
    return Boolean(
      value &&
      isRecord(value) &&
      isNonEmptyString(value.positioning) &&
      isNonEmptyString(value.first_run_focus) &&
      arraySectionComplete(value.operating_principles) &&
      arraySectionComplete(value.department_roles),
    );
  }
  return false;
}

function allBaselineText(baseline: StrategyBaseline): string {
  return normalize(JSON.stringify(baseline));
}

function hasAllDepartmentRoles(baseline: StrategyBaseline): boolean {
  const roles = baseline.strategy?.department_roles ?? [];
  const departmentText = roles.map((role) => normalize(role.department)).join(" | ");
  return EXPECTED_DEPARTMENTS.every((department) => departmentText.includes(normalize(department)));
}

function hasInventoryGrounding(baseline: StrategyBaseline): boolean {
  const text = allBaselineText(baseline);
  const hasStockTruth = text.includes("stock") || text.includes("inventory");
  const hasMetricGap = text.includes("low stock") || text.includes("reconcile");
  const hasScarcityOrProducts =
    text.includes("scarcity") ||
    ["gaga", "hendrix", "winehouse", "watson", "maverick"].some((model) => text.includes(model));
  return hasStockTruth && hasMetricGap && hasScarcityOrProducts;
}

function hasGuardrails(baseline: StrategyBaseline): boolean {
  const outOfScopeText = normalize((baseline.out_of_scope ?? []).join(" | "));
  const requiredGuardrails = [
    ["outreach", "customer"],
    ["live sales", "sales"],
    ["media generation", "media"],
    ["checkout", "payment"],
    ["procurement", "order"],
  ];
  return requiredGuardrails.every((terms) => terms.some((term) => outOfScopeText.includes(term)));
}

function hasScorableKpis(baseline: StrategyBaseline): boolean {
  const kpis = baseline.kpis ?? [];
  return (
    kpis.length >= 3 &&
    kpis.every(
      (kpi) =>
        isNonEmptyString(kpi.name) &&
        isNonEmptyString(kpi.target) &&
        isNonEmptyString(kpi.measurement) &&
        isNonEmptyString(kpi.owner),
    )
  );
}

function hasActionableNextRun(baseline: StrategyBaseline): boolean {
  const nextSteps = baseline.next_run_plan ?? [];
  const text = normalize(nextSteps.join(" | "));
  return nextSteps.length >= 3 && (text.includes("visual") || text.includes("asset")) && text.includes("reconcile");
}

function avoidsPrivateDataMarkers(baseline: StrategyBaseline): boolean {
  const text = allBaselineText(baseline);
  const blockedMarkers = [
    "customer_email",
    "buyer_email",
    "shipping_address",
    "billing_address",
    "payment_intent",
    "checkout_session",
    "stripe_session",
    "client_secret",
    "session_secret",
  ];
  const containsBlockedMarker = blockedMarkers.some((marker) => text.includes(marker));
  const containsEmail = /[a-z0-9._%+-]+@[a-z0-9.-]+\.[a-z]{2,}/i.test(text);
  return !containsBlockedMarker && !containsEmail;
}

function objectiveGatesPassed(objective: LegacyObjectiveContract | null): boolean {
  if (!objective) {
    return false;
  }
  const gates = objective.integrity_gates;
  if (!isRecord(gates)) {
    return false;
  }
  return Object.values(gates).every((gate) => {
    if (!isRecord(gate)) {
      return false;
    }
    return gate.status === "pass";
  });
}

function judgeLegacyStrategyBaseline(
  run: LegacyRunDetail,
  baseline: StrategyBaseline | null,
  objective: LegacyObjectiveContract | null,
): LegacyStrategyJudgement {
  const requiredMissing = baseline
    ? REQUIRED_SECTIONS.filter((section) => !sectionComplete(baseline, section))
    : [...REQUIRED_SECTIONS];
  const nodeRuns = run.node_runs ?? [];
  const nodeRunsSucceeded = nodeRuns.length > 0 && nodeRuns.every((nodeRun) => nodeRun.status === "succeeded");
  const finishReason =
    isRecord(run.output_json) && isRecord(run.output_json.planner_trace)
      ? run.output_json.planner_trace.finish_reason
      : null;

  const checks: JudgeCheck[] = [
    {
      name: "backend_run_succeeded",
      passed: run.status === "succeeded",
      points: 10,
      reason: `Run status was ${run.status}.`,
    },
    {
      name: "node_runs_succeeded",
      passed: nodeRunsSucceeded,
      points: 10,
      reason: `${run.node_runs.filter((nodeRun) => nodeRun.status === "succeeded").length}/${run.node_runs.length} node runs succeeded.`,
    },
    {
      name: "not_truncated",
      passed: finishReason !== "MAX_TOKENS",
      points: 8,
      reason: `Planner finish reason was ${String(finishReason ?? "unknown")}.`,
    },
    {
      name: "required_sections_complete",
      passed: requiredMissing.length === 0,
      points: 17,
      reason:
        requiredMissing.length === 0
          ? "All required Strategy Baseline sections were present."
          : `Missing or incomplete sections: ${requiredMissing.join(", ")}.`,
    },
    {
      name: "department_roles_complete",
      passed: Boolean(baseline && hasAllDepartmentRoles(baseline)),
      points: 10,
      reason: "All six Legacy departments need an explicit planning role.",
    },
    {
      name: "inventory_grounded",
      passed: Boolean(baseline && hasInventoryGrounding(baseline)),
      points: 12,
      reason: "The baseline should use stock truth, scarcity/product context, and the low-stock metric gap.",
    },
    {
      name: "guardrails_respected",
      passed: Boolean(baseline && hasGuardrails(baseline)),
      points: 10,
      reason: "Out-of-scope boundaries should block outreach, live sales, media generation, checkout, and procurement.",
    },
    {
      name: "kpis_scorable",
      passed: Boolean(baseline && hasScorableKpis(baseline)),
      points: 6,
      reason: "KPIs need name, target, measurement, and owner.",
    },
    {
      name: "next_run_actionable",
      passed: Boolean(baseline && hasActionableNextRun(baseline)),
      points: 5,
      reason: "The next run should include visual asset work and low-stock reconciliation.",
    },
    {
      name: "no_private_data_markers",
      passed: Boolean(baseline && avoidsPrivateDataMarkers(baseline)),
      points: 5,
      reason: "The baseline must not expose buyer emails, addresses, payment IDs, or checkout session secrets.",
    },
    {
      name: "backend_objective_evaluated",
      passed: Boolean(objective && objective.status === "evaluated" && (objective.success_score ?? 0) >= 85),
      points: 4,
      reason: `Objective score was ${String(objective?.success_score ?? "missing")}.`,
    },
    {
      name: "backend_integrity_gates_passed",
      passed: objectiveGatesPassed(objective),
      points: 3,
      reason: "Backend-owned objective integrity gates should all pass.",
    },
  ];

  const earnedPoints = checks.reduce((total, check) => total + (check.passed ? check.points : 0), 0);
  const possiblePoints = checks.reduce((total, check) => total + check.points, 0);
  const score = possiblePoints > 0 ? Math.round((earnedPoints / possiblePoints) * 100) : 0;
  const threshold = 85;
  const verdict: LegacyStrategyJudgement["verdict"] =
    score >= threshold && requiredMissing.length === 0 ? "pass" : score >= 65 ? "partial" : "fail";

  return {
    verdict,
    score,
    earned_points: earnedPoints,
    possible_points: possiblePoints,
    threshold,
    required_missing: requiredMissing,
    checks,
  };
}

async function apiGet<T>(request: APIRequestContext, accessToken: string, path: string): Promise<T> {
  const response = await request.get(`${API_BASE_URL}${path}`, {
    headers: { Authorization: `Bearer ${accessToken}` },
  });
  if (!response.ok()) {
    throw new Error(`GET ${path} failed with ${response.status()}: ${await response.text()}`);
  }
  return unwrap<T>(await response.json());
}

async function findLegacyCompanyId(request: APIRequestContext, accessToken: string): Promise<string> {
  if (LEGACY_COMPANY_ID) {
    return LEGACY_COMPANY_ID;
  }

  const graphs = await apiGet<GraphListItem[]>(request, accessToken, "/api/graphs/");
  const legacyCompany = graphs.find((graph) => normalize(graph.name).includes("legacy glasswear"));
  if (!legacyCompany?.id) {
    throw new Error("Could not find the Legacy Glasswear company for the seeded user.");
  }
  return legacyCompany.id;
}

function findStrategyObjective(overview: CompanyOpsOverview): LegacyObjectiveContract | null {
  const objectives = overview.objective_contracts ?? [];
  return (
    objectives.find((objective) => {
      const text = normalize(
        `${objective.run_goal} ${objective.target_signal ?? ""} ${objective.miss_analysis ?? ""} ${objective.next_decision ?? ""}`,
      );
      return text.includes("strategy baseline") && text.includes("visual");
    }) ?? null
  );
}

async function resolveRunAndObjective(
  request: APIRequestContext,
  accessToken: string,
): Promise<{ run: LegacyRunDetail; objective: LegacyObjectiveContract | null; overview: CompanyOpsOverview | null }> {
  if (LEGACY_RUN_ID) {
    const run = await apiGet<LegacyRunDetail>(request, accessToken, `/api/runs/${LEGACY_RUN_ID}`);
    const companyId = LEGACY_COMPANY_ID || run.graph_id;
    const overview = await apiGet<{ company_ops: CompanyOpsOverview }>(
      request,
      accessToken,
      `/api/company-ops/overview?company_id=${companyId}`,
    ).then((payload) => payload.company_ops);
    const objective =
      (overview.objective_contracts ?? []).find((candidate) => candidate.operation_id === run.id) ?? null;
    return { run, objective, overview };
  }

  const companyId = await findLegacyCompanyId(request, accessToken);
  const overview = await apiGet<{ company_ops: CompanyOpsOverview }>(
    request,
    accessToken,
    `/api/company-ops/overview?company_id=${companyId}`,
  ).then((payload) => payload.company_ops);

  const objective = findStrategyObjective(overview);
  if (!objective) {
    throw new Error(
      "No evaluated Strategy Baseline objective found. Set PLAYWRIGHT_LEGACY_RUN_ID to judge a run explicitly.",
    );
  }

  const run = await apiGet<LegacyRunDetail>(request, accessToken, `/api/runs/${objective.operation_id}`);
  return { run, objective, overview };
}

function readDockerLogs(containerName: string, runId: string): string | null {
  try {
    const logs = execFileSync("docker", ["logs", "--tail", "2000", containerName], {
      encoding: "utf8",
      maxBuffer: 32 * 1024 * 1024,
    });
    return logs
      .split(/\r?\n/)
      .filter((line) => line.includes(runId))
      .join("\n");
  } catch {
    return null;
  }
}

async function attachJson(testInfo: TestInfo, name: string, payload: unknown): Promise<void> {
  await testInfo.attach(name, {
    body: Buffer.from(JSON.stringify(payload, null, 2), "utf8"),
    contentType: "application/json",
  });
}

test.describe("Legacy Ultimate Test Judge", () => {
  test("judges the Strategy Baseline objective from backend-owned run state", async ({ request }, testInfo) => {
    const user: TestUser = {
      email: LEGACY_EMAIL,
      password: LEGACY_PASSWORD,
    };
    const accessToken = await getAccessToken(request, user);
    const { run, objective, overview } = await resolveRunAndObjective(request, accessToken);
    const baseline = extractStrategyBaseline(run);
    const judgement = judgeLegacyStrategyBaseline(run, baseline, objective);

    await Promise.all([
      attachJson(testInfo, "legacy-strategy-run-detail.json", run),
      attachJson(testInfo, "legacy-strategy-baseline.json", baseline),
      attachJson(testInfo, "legacy-strategy-objective.json", objective),
      attachJson(testInfo, "legacy-strategy-judge.json", judgement),
      attachJson(testInfo, "legacy-company-ops-overview.json", overview),
    ]);

    const backendLogs = readDockerLogs("forgegraph-backend", run.id);
    const engineLogs = readDockerLogs("forgegraph-engine", run.id);
    if (backendLogs) {
      await testInfo.attach("legacy-backend-run.log", {
        body: Buffer.from(backendLogs, "utf8"),
        contentType: "text/plain",
      });
    }
    if (engineLogs) {
      await testInfo.attach("legacy-engine-run.log", {
        body: Buffer.from(engineLogs, "utf8"),
        contentType: "text/plain",
      });
    }

    console.log(JSON.stringify(judgement, null, 2));

    expect(run.status).toBe("succeeded");
    expect(run.node_runs.every((nodeRun) => nodeRun.status === "succeeded")).toBe(true);
    expect(baseline).not.toBeNull();
    expect(judgement.required_missing).toEqual([]);
    expect(judgement.score).toBeGreaterThanOrEqual(judgement.threshold);
    expect(judgement.verdict).toBe("pass");
  });
});
