import { expect, test } from "@playwright/test";

import {
  apiBaseUrl,
  createGraphName,
  createTestUser,
  ensureUserRegistered,
  getAccessToken,
  startRunViaApi,
} from "./live-helpers";

const API_BASE_URL = apiBaseUrl();
const RUN_COUNT = Number(process.env.PLAYWRIGHT_LOAD_SMOKE_RUNS ?? "100");
const START_CONCURRENCY = Number(process.env.PLAYWRIGHT_LOAD_SMOKE_START_CONCURRENCY ?? "10");
const STATUS_POLL_CONCURRENCY = Number(process.env.PLAYWRIGHT_LOAD_SMOKE_STATUS_POLL_CONCURRENCY ?? "10");
const TEST_TIMEOUT_MS = Number(process.env.PLAYWRIGHT_LOAD_SMOKE_TIMEOUT_MS ?? "840000");
const TERMINAL_TIMEOUT_MS = Number(process.env.PLAYWRIGHT_LOAD_SMOKE_TERMINAL_TIMEOUT_MS ?? "720000");

async function mapWithConcurrency<T, R>(
  items: T[],
  concurrency: number,
  worker: (item: T, index: number) => Promise<R>,
): Promise<R[]> {
  const limit = Math.max(1, Math.min(concurrency, items.length || 1));
  const results = new Array<R>(items.length);
  let nextIndex = 0;

  async function runWorker(): Promise<void> {
    const currentIndex = nextIndex;
    if (currentIndex >= items.length) {
      return;
    }
    nextIndex += 1;
    results[currentIndex] = await worker(items[currentIndex], currentIndex);
    await runWorker();
  }

  await Promise.all(Array.from({ length: limit }, () => runWorker()));
  return results;
}

test.describe("No-LLM load smoke live flow", () => {
  test("completes queued output-only runs without silent task loss", async ({ request }, testInfo) => {
    test.setTimeout(TEST_TIMEOUT_MS);

    const user = createTestUser(testInfo, "load-smoke-live");
    await ensureUserRegistered(request, user);
    const accessToken = await getAccessToken(request, user);
    const graphName = createGraphName("Load Smoke Live");

    const graphResponse = await request.post(`${API_BASE_URL}/api/graphs/`, {
      headers: { Authorization: `Bearer ${accessToken}` },
      data: {
        name: graphName,
        description: "Deterministic no-LLM queued load smoke graph.",
      },
    });
    expect(graphResponse.ok()).toBeTruthy();
    const graphBody = (await graphResponse.json()) as { data: { id: string } };

    const versionResponse = await request.post(`${API_BASE_URL}/api/graphs/${graphBody.data.id}/versions`, {
      headers: { Authorization: `Bearer ${accessToken}` },
      data: {
        graph_json: {
          nodes: [
            {
              id: "final_output",
              type: "output",
              name: "Final Output",
              config: {
                output_mapping: {
                  request: "input.request",
                  worker: "input.worker",
                },
              },
            },
          ],
          edges: [
            { id: "start-final", from: "START", to: "final_output" },
            { id: "final-end", from: "final_output", to: "END" },
          ],
          metadata: {
            name: graphName,
            description: "Output-only queued load smoke; no LLM calls are expected.",
            engine_contract_version: "2",
          },
        },
      },
    });
    expect(versionResponse.ok()).toBeTruthy();
    const versionBody = (await versionResponse.json()) as { data: { id: string } };

    const started = await mapWithConcurrency(
      Array.from({ length: RUN_COUNT }, (_, index) => index),
      START_CONCURRENCY,
      (index) =>
        startRunViaApi(request, accessToken, {
          versionId: versionBody.data.id,
          inputJson: {
            request: "complete deterministic output",
            worker: index,
          },
        }),
    );
    const runIds = started.map((item) => item.runId);

    await expect
      .poll(
        async () => {
          const statuses = await mapWithConcurrency(runIds, STATUS_POLL_CONCURRENCY, async (runId) => {
            try {
              const response = await request.get(`${API_BASE_URL}/api/runs/${runId}`, {
                headers: { Authorization: `Bearer ${accessToken}` },
              });
              if (!response.ok()) {
                return "missing";
              }
              const body = (await response.json()) as { data?: { status?: string } };
              return body.data?.status ?? "missing";
            } catch {
              return "missing";
            }
          });
          return statuses.filter((status) => !["succeeded", "failed", "canceled"].includes(status)).length;
        },
        {
          timeout: TERMINAL_TIMEOUT_MS,
          message: "Timed out waiting for all no-LLM smoke runs to reach backend-owned terminal state.",
        },
      )
      .toBe(0);

    const details = await mapWithConcurrency(runIds, STATUS_POLL_CONCURRENCY, async (runId) => {
      const response = await request.get(`${API_BASE_URL}/api/runs/${runId}`, {
        headers: { Authorization: `Bearer ${accessToken}` },
      });
      expect(response.ok()).toBeTruthy();
      return (await response.json()) as {
        data: {
          id: string;
          status: string;
          node_runs?: Array<{ node_id: string; status: string }>;
        };
      };
    });

    const nonSucceeded = details.filter((item) => item.data.status !== "succeeded");
    expect(nonSucceeded, JSON.stringify(nonSucceeded.slice(0, 5))).toHaveLength(0);

    const duplicateNodeRuns = details.filter((item) => {
      const counts = new Map<string, number>();
      for (const nodeRun of item.data.node_runs ?? []) {
        counts.set(nodeRun.node_id, (counts.get(nodeRun.node_id) ?? 0) + 1);
      }
      return [...counts.values()].some((count) => count > 1);
    });
    expect(duplicateNodeRuns, JSON.stringify(duplicateNodeRuns.slice(0, 5))).toHaveLength(0);

    const runsWithoutCompletedNode = details.filter(
      (item) => !(item.data.node_runs ?? []).some((nodeRun) => nodeRun.status === "succeeded"),
    );
    expect(runsWithoutCompletedNode, JSON.stringify(runsWithoutCompletedNode.slice(0, 5))).toHaveLength(0);

    const deadLetterStates = await mapWithConcurrency(runIds, STATUS_POLL_CONCURRENCY, async (runId) => {
      const response = await request.get(`${API_BASE_URL}/api/operator/runs/${runId}/state`, {
        headers: { Authorization: `Bearer ${accessToken}` },
      });
      expect(response.ok()).toBeTruthy();
      const body = (await response.json()) as { data?: { dead_letter_count?: number } };
      return body.data?.dead_letter_count ?? 0;
    });
    expect(deadLetterStates.reduce((sum, count) => sum + count, 0)).toBe(0);

    testInfo.attach("load-smoke-summary", {
      body: JSON.stringify(
        {
          requested_runs: RUN_COUNT,
          start_concurrency: START_CONCURRENCY,
          completed_runs: details.length,
          dead_letters: 0,
          duplicate_node_execution: 0,
          note: "CI load smoke only; this is not a production concurrency claim.",
        },
        null,
        2,
      ),
      contentType: "application/json",
    });
  });
});
