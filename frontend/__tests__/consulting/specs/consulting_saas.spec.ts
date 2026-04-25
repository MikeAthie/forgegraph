import { expect, test, type APIRequestContext, type TestInfo } from "@playwright/test";
import { execFileSync } from "child_process";

import { buildConsultingGraph } from "../fixtures/consulting-graph";
import { createGraphName, createTestUser, ensureUserRegistered, getAccessToken } from "../../e2e/helpers";
import { evaluateStructure, type ConsultingExecutionState, type StructureEvaluation } from "../utils/evaluateStructure";
import { evaluateReasoning, type ReasoningEvaluation } from "../utils/evaluateReasoning";
import { evaluateWeaknesses, type EvaluationWeaknesses } from "../utils/evaluateWeaknesses";
import { runBaseline } from "../utils/runBaseline";

const API_BASE_URL = (
  process.env.PLAYWRIGHT_API_URL ??
  process.env.NEXT_PUBLIC_API_URL ??
  "http://127.0.0.1:8000"
).replace(/\/$/, "");

const consultingInput = {
  problem: "A B2B SaaS company has increased churn from 5% to 12% in 3 months",
  context: {
    product: "CRM",
    customers: "SMBs",
  },
} as const;

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

type ScoreDelta = {
  structure: number;
  coverage: number;
  coherence: number;
  usefulness: number;
  evidence: number;
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

async function createGraph(request: APIRequestContext, accessToken: string): Promise<string> {
  const response = await request.post(`${API_BASE_URL}/api/graphs/`, {
    headers: { Authorization: `Bearer ${accessToken}` },
    data: {
      name: createGraphName("Consulting SaaS Experiment"),
      description: "Minimal replayable consulting workflow experiment.",
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

async function createRun(request: APIRequestContext, accessToken: string, graphVersionId: string): Promise<string> {
  const response = await request.post(`${API_BASE_URL}/api/runs`, {
    headers: { Authorization: `Bearer ${accessToken}` },
    data: {
      graph_version_id: graphVersionId,
      input_json: consultingInput,
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
  });
}

function captureDockerRuntimeEvidence(sinceIso: string): DockerRuntimeEvidence {
  return {
    backend_logs: readDockerLogs("forgegraph-backend", sinceIso),
    engine_logs: readDockerLogs("forgegraph-engine", sinceIso),
  };
}

function attachRunArtifacts(testInfo: TestInfo, run: ConsultingRunDetail): Promise<void[]> {
  return Promise.all([
    testInfo.attach("consulting-run-detail.json", {
      body: Buffer.from(JSON.stringify(run, null, 2), "utf8"),
      contentType: "application/json",
    }),
    testInfo.attach("consulting-node-runs.json", {
      body: Buffer.from(JSON.stringify(run.node_runs, null, 2), "utf8"),
      contentType: "application/json",
    }),
  ]);
}

test.describe("Consulting SaaS Experiment", () => {
  test("creates, runs, and validates a consulting workflow artifact", async ({ request }, testInfo) => {
    test.setTimeout(420_000);
    const dockerLogWindowStart = new Date(Date.now() - 5_000).toISOString();
    const user = createTestUser(testInfo, "consulting-saas");

    await ensureUserRegistered(request, user);
    const accessToken = await getAccessToken(request, user);

    const graphId = await createGraph(request, accessToken);
    const graphVersion = await createGraphVersion(request, accessToken, graphId);
    const graphVersionId = graphVersion.id;
    const runId = await createRun(request, accessToken, graphVersionId);
    const run = await pollRunDetail(request, accessToken, runId);
    const persistedGraphVersion = await fetchGraphVersion(request, accessToken, graphId, graphVersionId);
    await attachRunArtifacts(testInfo, run);

    const state = (run.output_json ?? {}) as ConsultingExecutionState;
    let structure: StructureEvaluation | null = null;
    let systemScore: ReasoningEvaluation | null = null;
    let baselineState: ConsultingExecutionState | null = null;
    let baselineScore: ReasoningEvaluation | null = null;
    let weaknesses: EvaluationWeaknesses | null = null;
    let delta: ScoreDelta | null = null;
    let dockerRuntime: DockerRuntimeEvidence | null = null;

    console.log(
      JSON.stringify(
        {
          backend_url: API_BASE_URL,
          graph_id: graphId,
          graph_version_id: graphVersionId,
          run_id: runId,
        },
        null,
        2,
      ),
    );

    try {
      if (run.status !== "succeeded") {
        console.error(
          JSON.stringify(
            {
              run_id: run.id,
              status: run.status,
              error_message: run.error_message ?? null,
              execution_state: state,
              system_score: systemScore,
              baseline_score: baselineScore,
              node_runs: run.node_runs,
            },
            null,
            2,
          ),
        );
        throw new Error(`Consulting run ${run.id} ended with ${run.status}: ${run.error_message ?? "unknown error"}`);
      }

      structure = evaluateStructure(state);
      systemScore = await evaluateReasoning(state);
      weaknesses = await evaluateWeaknesses(state);
      baselineState = await runBaseline(consultingInput);
      baselineScore = await evaluateReasoning(baselineState);
      dockerRuntime = captureDockerRuntimeEvidence(dockerLogWindowStart);
      delta = {
        structure: systemScore.structure - baselineScore.structure,
        coverage: systemScore.coverage - baselineScore.coverage,
        coherence: systemScore.coherence - baselineScore.coherence,
        usefulness: systemScore.usefulness - baselineScore.usefulness,
        evidence: systemScore.evidence - baselineScore.evidence,
      };

      await Promise.all([
        testInfo.attach("consulting-structure-evaluation.json", {
          body: Buffer.from(JSON.stringify(structure, null, 2), "utf8"),
          contentType: "application/json",
        }),
        testInfo.attach("consulting-system-score.json", {
          body: Buffer.from(JSON.stringify(systemScore, null, 2), "utf8"),
          contentType: "application/json",
        }),
        testInfo.attach("consulting-baseline-score.json", {
          body: Buffer.from(JSON.stringify(baselineScore, null, 2), "utf8"),
          contentType: "application/json",
        }),
        testInfo.attach("consulting-weaknesses.json", {
          body: Buffer.from(JSON.stringify(weaknesses, null, 2), "utf8"),
          contentType: "application/json",
        }),
        testInfo.attach("consulting-score-delta.json", {
          body: Buffer.from(JSON.stringify(delta, null, 2), "utf8"),
          contentType: "application/json",
        }),
        testInfo.attach("consulting-baseline-state.json", {
          body: Buffer.from(JSON.stringify(baselineState, null, 2), "utf8"),
          contentType: "application/json",
        }),
        testInfo.attach("consulting-persisted-graph-version.json", {
          body: Buffer.from(JSON.stringify(persistedGraphVersion, null, 2), "utf8"),
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

      console.log(
        JSON.stringify(
          {
            backend_url: API_BASE_URL,
            graph_id: graphId,
            graph_version_id: graphVersionId,
            run_id: run.id,
            status: run.status,
            execution_state: state,
            system_score: systemScore,
            baseline_score: baselineScore,
            delta,
            weaknesses,
          },
          null,
          2,
        ),
      );

      expect(run.backend_attempt_id).toBeTruthy();
      expect(run.graph_id).toBe(graphId);
      expect(run.graph_version_id).toBe(graphVersionId);
      expect(run.status_history[0]).toBe("pending");
      expect(run.status_history).toContain("running");
      expect(run.status_history.at(-1)).toBe("succeeded");
      expect(persistedGraphVersion.graph_json).toEqual(graphVersion.graphJson);
      expect(state.reflection).toBeTruthy();
      expect(state.reflection?.weak_hypotheses?.length ?? 0).toBeGreaterThan(0);
      expect(state.reflection?.missing_evidence?.length ?? 0).toBeGreaterThan(0);
      expect(state.reflection?.inconsistencies?.length ?? 0).toBeGreaterThan(0);

      expect(structure.structure_valid).toBe(true);
      expect(structure.artifact_complete).toBe(true);
      expect(structure.state_consistent).toBe(true);

      expect(systemScore.structure).toBeGreaterThan(1);
      expect(systemScore.fatal_error).toBe(false);
      expect(typeof baselineScore.structure).toBe("number");
      expect(typeof baselineScore.fatal_error).toBe("boolean");

      if (!delta || !weaknesses) {
        throw new Error("Evaluation outputs were missing after scoring.");
      }

      const allZero = Object.values(delta).every((value) => value === 0);
      expect(allZero).toBe(false);

      const totalWeaknesses = Object.values(weaknesses).reduce((count, items) => count + items.length, 0);
      expect(totalWeaknesses).toBeGreaterThan(0);

      if (!dockerRuntime) {
        throw new Error("Docker runtime evidence was not captured.");
      }

      expect(dockerRuntime.backend_logs).toContain(runId);
      expect(dockerRuntime.engine_logs).toContain(runId);
      expect(dockerRuntime.backend_logs).toContain("/api/runs/engine-events");
      expect(dockerRuntime.backend_logs).not.toContain("DeadlockDetected");
      expect(dockerRuntime.backend_logs).not.toContain("deadlock detected");
      expect(dockerRuntime.backend_logs).not.toContain("Internal Server Error: /api/runs/engine-events");
      expect(dockerRuntime.engine_logs).not.toContain("status 500");
    } catch (error) {
      console.error(
        JSON.stringify(
          {
            run_id: run.id,
            status: run.status,
            error_message: run.error_message ?? null,
            execution_state: state,
            structure,
            system_score: systemScore,
            baseline_state: baselineState,
            baseline_score: baselineScore,
            delta,
            weaknesses,
            node_runs: run.node_runs,
          },
          null,
          2,
        ),
      );
      throw error;
    }
  });
});
