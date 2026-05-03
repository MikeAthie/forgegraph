import { expect, test } from "@playwright/test";

import {
  apiBaseUrl,
  createGraphName,
  createHumanGateRunViaApi,
  createObservationViaApi,
  createTestUser,
  ensureUserRegistered,
  getAccessToken,
  loginLive,
  waitForRunStatus,
} from "./live-helpers";

const API_BASE_URL = apiBaseUrl();

function websocketBaseUrl() {
  return API_BASE_URL.replace(/^http:/, "ws:").replace(/^https:/, "wss:");
}

test.describe("Tenant isolation live gate", () => {
  test("keeps tenant A run, approval, task, memory, and run WebSocket data out of tenant B", async ({
    page,
    request,
  }, testInfo) => {
    test.setTimeout(120_000);

    const tenantA = createTestUser(testInfo, "tenant-a-live");
    const tenantB = createTestUser(testInfo, "tenant-b-live");
    await ensureUserRegistered(request, tenantA);
    await ensureUserRegistered(request, tenantB);
    const tenantAToken = await getAccessToken(request, tenantA);
    const tenantBToken = await loginLive(page, request, tenantB, "/runs");

    const graphName = createGraphName("Tenant A Live Isolation");
    const promptMessage = "Tenant A approval should never appear in tenant B.";
    const memoryMarker = `tenant-a-memory-${Date.now()}-${Math.random().toString(16).slice(2)}`;
    const { companyId, runId } = await createHumanGateRunViaApi(request, tenantAToken, {
      graphName,
      promptMessage,
      instructions: "This approval belongs only to tenant A.",
    });
    await createObservationViaApi(request, tenantAToken, {
      type: "operator_note",
      title: "Tenant A private note",
      content: memoryMarker,
      scope: "graph",
      graph_id: companyId,
      dedupe: false,
      update_topic: false,
    });
    await waitForRunStatus(request, tenantAToken, runId, "paused");

    const crossTenantRunDetail = await request.get(`${API_BASE_URL}/api/runs/${runId}`, {
      headers: { Authorization: `Bearer ${tenantBToken}` },
    });
    expect([403, 404]).toContain(crossTenantRunDetail.status());

    const tenantBRuns = await request.get(`${API_BASE_URL}/api/runs/`, {
      headers: { Authorization: `Bearer ${tenantBToken}` },
    });
    expect(tenantBRuns.ok()).toBeTruthy();
    const tenantBRunsBody = (await tenantBRuns.json()) as { data?: unknown[] };
    expect(JSON.stringify(tenantBRunsBody.data ?? [])).not.toContain(runId);
    expect(JSON.stringify(tenantBRunsBody.data ?? [])).not.toContain(graphName);

    const tenantBApprovals = await request.get(`${API_BASE_URL}/api/approvals/?status=all`, {
      headers: { Authorization: `Bearer ${tenantBToken}` },
    });
    expect(tenantBApprovals.ok()).toBeTruthy();
    const tenantBApprovalsBody = (await tenantBApprovals.json()) as { data?: unknown[] };
    const tenantBApprovalsText = JSON.stringify(tenantBApprovalsBody.data ?? []);
    expect(tenantBApprovalsText).not.toContain(runId);
    expect(tenantBApprovalsText).not.toContain(promptMessage);

    const tenantBTasks = await request.get(`${API_BASE_URL}/api/tasks/`, {
      headers: { Authorization: `Bearer ${tenantBToken}` },
    });
    expect(tenantBTasks.ok()).toBeTruthy();
    const tenantBTasksBody = (await tenantBTasks.json()) as { data?: unknown[] };
    expect(JSON.stringify(tenantBTasksBody.data ?? [])).not.toContain(runId);

    const tenantBMemory = await request.get(
      `${API_BASE_URL}/api/memory/observations/search?query=${encodeURIComponent(memoryMarker)}`,
      {
        headers: { Authorization: `Bearer ${tenantBToken}` },
      },
    );
    expect(tenantBMemory.ok()).toBeTruthy();
    const tenantBMemoryBody = (await tenantBMemory.json()) as { data?: unknown[] };
    expect(JSON.stringify(tenantBMemoryBody.data ?? [])).not.toContain(memoryMarker);

    await page.goto("/runs");
    await expect(page.getByText(graphName)).toHaveCount(0);

    const ticketResponse = await request.post(`${API_BASE_URL}/api/ws-ticket`, {
      headers: { Authorization: `Bearer ${tenantBToken}` },
      data: {},
    });
    expect(ticketResponse.ok()).toBeTruthy();
    const ticketBody = (await ticketResponse.json()) as { ticket: string };
    const wsOutcome = await page.evaluate(
      ({ runId: targetRunId, ticket, wsBaseUrl }) =>
        new Promise<string>((resolve) => {
          const socket = new WebSocket(
            `${wsBaseUrl}/ws/runs/${encodeURIComponent(targetRunId)}/?ticket=${encodeURIComponent(ticket)}`,
          );
          let settled = false;
          const finish = (result: string) => {
            if (settled) return;
            settled = true;
            try {
              socket.close();
            } catch {
              // The socket may already be closed by the backend.
            }
            resolve(result);
          };
          socket.onopen = () => {
            window.setTimeout(() => finish("opened"), 250);
          };
          socket.onclose = (event) => finish(`closed:${event.code}`);
          socket.onerror = () => finish("error");
          window.setTimeout(() => finish("timeout"), 2000);
        }),
      { runId, ticket: ticketBody.ticket, wsBaseUrl: websocketBaseUrl() },
    );
    expect(wsOutcome).not.toBe("opened");
  });
});
