import { expect, test, type APIRequestContext, type TestInfo } from "@playwright/test";
import { execFileSync } from "child_process";

import {
  buildConsultingExecutionInput,
  CONSULTING_CASE_PACK_V2,
  type ConsultingCaseDefinition,
  type ConsultingExecutionInput,
} from "../fixtures/case-pack-v2";
import { buildConsultingGraph } from "../fixtures/consulting-graph";
import { createGraphName, createTestUser, ensureUserRegistered, getAccessToken } from "../../e2e/helpers";
import { evaluateReadiness, hasCorrectDirection, type ReadinessEvaluation } from "../utils/evaluateReadiness";
import { evaluateStructure, type ConsultingExecutionState, type StructureEvaluation } from "../utils/evaluateStructure";
import { judgePairwise, type PairwiseJudgement } from "../utils/judgePairwise";
import { runBaseline } from "../utils/runBaseline";

const API_BASE_URL = (
  process.env.PLAYWRIGHT_API_URL ??
  process.env.NEXT_PUBLIC_API_URL ??
  "http://127.0.0.1:8000"
).replace(/\/$/, "");

type ConsultingRunDetail = {
  id: string;
  graph_id: string;
  graph_version_id: string;
  status: string;
  status_history: string[];
  backend_attempt_id: string;
  error_message?: string | null;
  output_json?: ConsultingExecutionState | null;
  node_runs: Array<{
    node_id: string;
    status: string;
    attempt: number;
    input_json?: Record<string, unknown> | null;
    output_json?: Record<string, unknown> | null;
    error_json?: Record<string, unknown> | null;
  }>;
};

type DockerRuntimeEvidence = {
  backend_logs: string;
  engine_logs: string;
};

type GraphVersionDetail = {
  id: string;
  graph_id: string;
  version: number;
  graph_json: Record<string, unknown>;
  checksum: string;
  created_at: string;
};

type GraphVersionCreateResult = {
  id: string;
  graphJson: Record<string, unknown>;
};

type SystemEvaluationRecord = {
  output: ConsultingExecutionState;
  structure: StructureEvaluation;
  evaluation: ReadinessEvaluation;
};

type ForgeGraphCaseResult = SystemEvaluationRecord & {
  run_id: string;
  graph_id: string;
  graph_version_id: string;
  status: string;
};

type CaseEvaluationRecord = {
  case_id: string;
  forgegraph: ForgeGraphCaseResult;
  baseline: SystemEvaluationRecord;
  evaluation: {
    forgegraph: ReadinessEvaluation;
    baseline: ReadinessEvaluation;
    pairwise: PairwiseJudgement;
  };
  winner: PairwiseJudgement["winner"];
};

type EvaluationSummary = {
  cases: CaseEvaluationRecord[];
  summary: {
    correct_direction_rate: string;
    baseline_correct_direction_rate: string;
    forgegraph_win_rate: string;
    baseline_win_rate: string;
    tie_rate: string;
  };
};

async function createGraph(
  request: APIRequestContext,
  accessToken: string,
  consultingCase: ConsultingCaseDefinition,
): Promise<string> {
  const response = await request.post(`${API_BASE_URL}/api/graphs/`, {
    headers: { Authorization: `Bearer ${accessToken}` },
    data: {
      name: createGraphName(`Consulting Eval ${consultingCase.case_id}`),
      description: `Benchmark consulting workflow for ${consultingCase.case_id}.`,
    },
  });
  expect(response.ok()).toBeTruthy();
  const body = (await response.json()) as { data: { id: string } };
  expect(body.data.id).toBeTruthy();
  return body.data.id;
}

async function createGraphVersion(
  request: APIRequestContext,
  accessToken: string,
  graphId: string,
): Promise<GraphVersionCreateResult> {
  const graphJson = buildConsultingGraph();
  const response = await request.post(`${API_BASE_URL}/api/graph-versions`, {
    headers: { Authorization: `Bearer ${accessToken}` },
    data: {
      graph_id: graphId,
      graph_json: graphJson,
    },
  });
  expect(response.ok()).toBeTruthy();
  const body = (await response.json()) as { data: { id: string } };
  expect(body.data.id).toBeTruthy();
  return {
    id: body.data.id,
    graphJson,
  };
}

async function createRun(
  request: APIRequestContext,
  accessToken: string,
  graphVersionId: string,
  input: ConsultingExecutionInput,
): Promise<string> {
  const response = await request.post(`${API_BASE_URL}/api/runs`, {
    headers: { Authorization: `Bearer ${accessToken}` },
    data: {
      graph_version_id: graphVersionId,
      input_json: input,
    },
  });
  expect(response.ok()).toBeTruthy();
  const body = (await response.json()) as { data: { id: string } };
  expect(body.data.id).toBeTruthy();
  return body.data.id;
}

async function pollRunDetail(
  request: APIRequestContext,
  accessToken: string,
  runId: string,
): Promise<ConsultingRunDetail> {
  let latestRun: ConsultingRunDetail | null = null;

  await expect
    .poll(
      async () => {
        const response = await request.get(`${API_BASE_URL}/api/runs/${runId}`, {
          headers: { Authorization: `Bearer ${accessToken}` },
        });
        expect(response.ok()).toBeTruthy();
        const body = (await response.json()) as { data: ConsultingRunDetail };
        latestRun = body.data;
        return body.data.status;
      },
      {
        timeout: 240_000,
        message: `Timed out waiting for consulting run ${runId} to complete.`,
      },
    )
    .toMatch(/^(succeeded|failed|canceled)$/);

  if (!latestRun) {
    throw new Error(`Run ${runId} did not return any detail payload.`);
  }

  return latestRun;
}

async function fetchGraphVersion(
  request: APIRequestContext,
  accessToken: string,
  graphId: string,
  graphVersionId: string,
): Promise<GraphVersionDetail> {
  const response = await request.get(`${API_BASE_URL}/api/graphs/${graphId}/versions/${graphVersionId}`, {
    headers: { Authorization: `Bearer ${accessToken}` },
  });
  expect(response.ok()).toBeTruthy();
  const body = (await response.json()) as { data: GraphVersionDetail };
  expect(body.data.id).toBe(graphVersionId);
  expect(body.data.graph_id).toBe(graphId);
  return body.data;
}

function readDockerLogs(containerName: string, sinceIso: string): string {
  return execFileSync("docker", ["logs", "--since", sinceIso, containerName], {
    encoding: "utf8",
    cwd: process.cwd(),
    maxBuffer: 64 * 1024 * 1024,
  });
}

function captureDockerRuntimeEvidence(sinceIso: string): DockerRuntimeEvidence {
  return {
    backend_logs: readDockerLogs("forgegraph-backend", sinceIso),
    engine_logs: readDockerLogs("forgegraph-engine", sinceIso),
  };
}

async function attachCaseArtifacts(
  testInfo: TestInfo,
  consultingCase: ConsultingCaseDefinition,
  run: ConsultingRunDetail,
  persistedGraphVersion: GraphVersionDetail,
  baselineState: ConsultingExecutionState,
): Promise<void> {
  await Promise.all([
    testInfo.attach(`${consultingCase.case_id}-run-detail.json`, {
      body: Buffer.from(JSON.stringify(run, null, 2), "utf8"),
      contentType: "application/json",
    }),
    testInfo.attach(`${consultingCase.case_id}-node-runs.json`, {
      body: Buffer.from(JSON.stringify(run.node_runs, null, 2), "utf8"),
      contentType: "application/json",
    }),
    testInfo.attach(`${consultingCase.case_id}-baseline-output.json`, {
      body: Buffer.from(JSON.stringify(baselineState, null, 2), "utf8"),
      contentType: "application/json",
    }),
    testInfo.attach(`${consultingCase.case_id}-persisted-graph-version.json`, {
      body: Buffer.from(JSON.stringify(persistedGraphVersion, null, 2), "utf8"),
      contentType: "application/json",
    }),
  ]);
}

function formatRate(count: number, total: number): string {
  return `${count}/${total}`;
}

test.describe("Consulting SaaS Experiment", () => {
  test("runs a benchmark case pack with deterministic evaluation and pairwise comparison", async ({ request }, testInfo) => {
    test.setTimeout(720_000);
    const dockerLogWindowStart = new Date(Date.now() - 5_000).toISOString();
    const user = createTestUser(testInfo, "consulting-eval-readiness");

    expect(CONSULTING_CASE_PACK_V2).toHaveLength(5);

    await ensureUserRegistered(request, user);
    const accessToken = await getAccessToken(request, user);

    const results: CaseEvaluationRecord[] = [];
    const allRunIds: string[] = [];

    for (const consultingCase of CONSULTING_CASE_PACK_V2) {
      const executionInput = buildConsultingExecutionInput(consultingCase);
      const graphId = await createGraph(request, accessToken, consultingCase);
      const graphVersion = await createGraphVersion(request, accessToken, graphId);
      const graphVersionId = graphVersion.id;
      const runId = await createRun(request, accessToken, graphVersionId, executionInput);
      const run = await pollRunDetail(request, accessToken, runId);
      const persistedGraphVersion = await fetchGraphVersion(request, accessToken, graphId, graphVersionId);

      if (run.status !== "succeeded") {
        console.error(
          JSON.stringify(
            {
              case_id: consultingCase.case_id,
              run_id: run.id,
              status: run.status,
              error_message: run.error_message ?? null,
              execution_state: run.output_json ?? {},
              node_runs: run.node_runs,
            },
            null,
            2,
          ),
        );
        throw new Error(`Consulting run ${run.id} for ${consultingCase.case_id} ended with ${run.status}.`);
      }

      const forgegraphState = (run.output_json ?? {}) as ConsultingExecutionState;
      const forgegraphStructure = evaluateStructure(forgegraphState);
      const forgegraphEvaluation = evaluateReadiness(forgegraphState, consultingCase.hidden_benchmark);

      const baselineState = await runBaseline(executionInput);
      const baselineStructure = evaluateStructure(baselineState);
      const baselineEvaluation = evaluateReadiness(baselineState, consultingCase.hidden_benchmark);

      const pairwise = judgePairwise(forgegraphEvaluation, baselineEvaluation);

      await attachCaseArtifacts(testInfo, consultingCase, run, persistedGraphVersion, baselineState);

      expect(run.backend_attempt_id).toBeTruthy();
      expect(run.graph_id).toBe(graphId);
      expect(run.graph_version_id).toBe(graphVersionId);
      expect(run.status_history[0]).toBe("pending");
      expect(run.status_history).toContain("running");
      expect(run.status_history.at(-1)).toBe("succeeded");
      expect(persistedGraphVersion.graph_json).toEqual(graphVersion.graphJson);

      results.push({
        case_id: consultingCase.case_id,
        forgegraph: {
          run_id: run.id,
          graph_id: graphId,
          graph_version_id: graphVersionId,
          status: run.status,
          output: forgegraphState,
          structure: forgegraphStructure,
          evaluation: forgegraphEvaluation,
        },
        baseline: {
          output: baselineState,
          structure: baselineStructure,
          evaluation: baselineEvaluation,
        },
        evaluation: {
          forgegraph: forgegraphEvaluation,
          baseline: baselineEvaluation,
          pairwise,
        },
        winner: pairwise.winner,
      });

      allRunIds.push(run.id);
    }

    const forgegraphCorrectDirectionCount = results.filter((result) =>
      hasCorrectDirection(result.evaluation.forgegraph),
    ).length;
    const baselineCorrectDirectionCount = results.filter((result) =>
      hasCorrectDirection(result.evaluation.baseline),
    ).length;
    const forgegraphWinCount = results.filter((result) => result.winner === "forgegraph").length;
    const baselineWinCount = results.filter((result) => result.winner === "baseline").length;
    const tieCount = results.filter((result) => result.winner === "tie").length;

    const dockerRuntime = captureDockerRuntimeEvidence(dockerLogWindowStart);

    const summary: EvaluationSummary = {
      cases: results,
      summary: {
        correct_direction_rate: formatRate(forgegraphCorrectDirectionCount, results.length),
        baseline_correct_direction_rate: formatRate(baselineCorrectDirectionCount, results.length),
        forgegraph_win_rate: formatRate(forgegraphWinCount, results.length),
        baseline_win_rate: formatRate(baselineWinCount, results.length),
        tie_rate: formatRate(tieCount, results.length),
      },
    };

    await Promise.all([
      testInfo.attach("consulting-case-pack-v2.json", {
        body: Buffer.from(JSON.stringify(CONSULTING_CASE_PACK_V2, null, 2), "utf8"),
        contentType: "application/json",
      }),
      testInfo.attach("consulting-evaluation-summary.json", {
        body: Buffer.from(JSON.stringify(summary, null, 2), "utf8"),
        contentType: "application/json",
      }),
      testInfo.attach("consulting-docker-backend.log", {
        body: Buffer.from(dockerRuntime.backend_logs, "utf8"),
        contentType: "text/plain",
      }),
      testInfo.attach("consulting-docker-engine.log", {
        body: Buffer.from(dockerRuntime.engine_logs, "utf8"),
        contentType: "text/plain",
      }),
    ]);

    console.log(JSON.stringify(summary, null, 2));

    expect(results).toHaveLength(CONSULTING_CASE_PACK_V2.length);
    expect(summary.summary.correct_direction_rate).toMatch(/^\d+\/\d+$/);
    expect(summary.summary.baseline_correct_direction_rate).toMatch(/^\d+\/\d+$/);
    expect(summary.summary.forgegraph_win_rate).toMatch(/^\d+\/\d+$/);
    expect(summary.summary.baseline_win_rate).toMatch(/^\d+\/\d+$/);
    expect(summary.summary.tie_rate).toMatch(/^\d+\/\d+$/);

    for (const result of results) {
      expect(["correct_primary", "correct_secondary", "acceptable", "wrong", "unclear"]).toContain(
        result.evaluation.forgegraph.driver_match,
      );
      expect(["high", "medium", "low"]).toContain(result.evaluation.forgegraph.actionability);
      expect(["consistent", "partial", "inconsistent"]).toContain(result.evaluation.forgegraph.consistency);
      expect(["correct_primary", "correct_secondary", "acceptable", "wrong", "unclear"]).toContain(
        result.evaluation.baseline.driver_match,
      );
      expect(["high", "medium", "low"]).toContain(result.evaluation.baseline.actionability);
      expect(["consistent", "partial", "inconsistent"]).toContain(result.evaluation.baseline.consistency);
      expect(["forgegraph", "baseline", "tie"]).toContain(result.winner);
    }

    for (const runId of allRunIds) {
      expect(dockerRuntime.backend_logs).toContain(runId);
      expect(dockerRuntime.engine_logs).toContain(runId);
    }

    expect(dockerRuntime.backend_logs).toContain("/api/runs/engine-events");
    expect(dockerRuntime.backend_logs).not.toContain("DeadlockDetected");
    expect(dockerRuntime.backend_logs).not.toContain("deadlock detected");
    expect(dockerRuntime.backend_logs).not.toContain("Internal Server Error: /api/runs/engine-events");
    expect(dockerRuntime.engine_logs).not.toContain("status 500");
  });
});
