import { expect, test } from "@playwright/test";

import {
  apiBaseUrl,
  createCompanyViaApi,
  createGraphName,
  createTestUser,
  loginLive,
  startRunViaApi,
  waitForRunTerminal,
} from "./live-helpers";

const API_BASE_URL = apiBaseUrl();
const LLM_MOCK_URL = process.env.PLAYWRIGHT_LLM_MOCK_URL ?? "http://127.0.0.1:8011";

async function configureLlmMock(errorMode: "off" | "rate_limit") {
  const response = await fetch(`${LLM_MOCK_URL}/control`, {
    method: "POST",
    headers: { "content-type": "application/json" },
    body: JSON.stringify({
      errorMode,
      responseDelayMs: 0,
      maxInFlight: 0,
    }),
  });
  if (!response.ok) {
    throw new Error(`Unable to configure deterministic LLM mock (${response.status}): ${await response.text()}`);
  }
}

test.describe("Failure retry dead-letter live flow", () => {
  test("records retry exhaustion and exposes the dead-lettered task through backend-owned state", async ({
    page,
    request,
  }, testInfo) => {
    test.setTimeout(180_000);

    const user = createTestUser(testInfo, "failure-dead-letter-live");
    const accessToken = await loginLive(page, request, user, "/tasks");
    const graphName = createGraphName("Failure Dead Letter Live");
    const { versionId } = await createCompanyViaApi(request, accessToken, {
      name: graphName,
      companyType: "Operations Reliability",
      objective: "Exercise retry exhaustion through the live backend, engine, Redis, Postgres, and WebSocket stack.",
      operationBrief: "Trigger a deterministic LLM backpressure failure.",
    });

    await configureLlmMock("rate_limit");
    try {
      const { runId } = await startRunViaApi(request, accessToken, {
        versionId,
        inputJson: {
          objective: "Exercise retry exhaustion through the live stack.",
          operation_brief: "The deterministic LLM mock should rate limit this run.",
        },
      });

      const terminalRun = await waitForRunTerminal(request, accessToken, runId);
      expect(terminalRun.status).toBe("failed");

      await expect
        .poll(
          async () => {
            const response = await request.get(`${API_BASE_URL}/api/operator/runs/${runId}/state`, {
              headers: { Authorization: `Bearer ${accessToken}` },
            });
            expect(response.ok()).toBeTruthy();
            const body = (await response.json()) as {
              data?: {
                dead_letter_count?: number;
                tasks?: Array<{
                  status: string;
                  dead_letter?: { reason?: string; last_error?: string; recovery_options?: string[] } | null;
                }>;
              };
            };
            return {
              deadLetters: body.data?.dead_letter_count ?? 0,
              hasDeadLetteredTask: (body.data?.tasks ?? []).some(
                (task) =>
                  task.status === "dead_lettered" && task.dead_letter?.recovery_options?.includes("replay_intent"),
              ),
            };
          },
          {
            timeout: 45_000,
            message: "Timed out waiting for backend-owned retry exhaustion and dead-letter projection.",
          },
        )
        .toEqual({ deadLetters: 1, hasDeadLetteredTask: true });

      const deadLetters = await request.get(`${API_BASE_URL}/api/operator/dead-letters`, {
        headers: { Authorization: `Bearer ${accessToken}` },
      });
      expect(deadLetters.ok()).toBeTruthy();
      const deadLetterBody = (await deadLetters.json()) as {
        data?: {
          task_dead_letters?: Array<{
            run_id: string;
            reason?: string;
            attempt_count?: number;
            last_error?: string;
            recovery_options?: string[];
          }>;
        };
      };
      const runDeadLetter = deadLetterBody.data?.task_dead_letters?.find((item) => item.run_id === runId);
      expect(runDeadLetter?.reason).toContain("retry exhausted");
      expect(runDeadLetter?.attempt_count).toBeGreaterThan(0);
      expect(runDeadLetter?.last_error).toBeTruthy();
      expect(runDeadLetter?.recovery_options).toContain("force_fail_run");

      await page.goto("/tasks");
      await expect(page.getByText(/Needs recovery/i).first()).toBeVisible({ timeout: 30_000 });
      await expect(page.getByText(/Recovery:.*replay_intent/i).first()).toBeVisible();

      await page.goto(`/runs/${runId}`);
      await expect(page.getByText(/dead letter/i).first()).toBeVisible({ timeout: 30_000 });
      await expect(page.getByText(/retry/i).first()).toBeVisible();
    } finally {
      await configureLlmMock("off");
    }
  });
});
