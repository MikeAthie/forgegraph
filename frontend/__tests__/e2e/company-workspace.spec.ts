import { expect, test } from "@playwright/test";

import { installCompanyWorkspaceMocks, type CompanyWorkspaceMockState } from "./company-ux-fixtures";
import {
  createCompanyViaApi,
  createTestUser,
  ensureUserRegistered,
  fetchLatestGraphVersion,
  getAccessToken,
  openBackendAuthenticatedPage,
} from "./helpers";

test.describe("Company workspace UX", () => {
  test("lets a user continue work from an existing company and launch another operation", async ({
    page,
    request,
  }, testInfo) => {
    const user = createTestUser(testInfo, "company-continue");
    await ensureUserRegistered(request, user);
    const accessToken = await getAccessToken(request, user);
    const seed = await createCompanyViaApi(request, accessToken, {
      name: "Continuum Revenue Ops",
      companyType: "Revenue Operations",
      objective: "Keep follow-up moving and deliver a clear weekly operating update.",
      autonomyMode: "assisted",
      aiAccessMode: "managed",
    });
    const latestVersion = await fetchLatestGraphVersion(request, accessToken, seed.companyId);

    const state: CompanyWorkspaceMockState = {
      companyId: seed.companyId,
      companyName: "Continuum Revenue Ops",
      graphVersion: latestVersion,
      pendingApprovalCount: 0,
      operations: [
        {
          id: "21111111-1111-4111-8111-111111111111",
          status: "succeeded",
          startedAt: "2026-04-26T09:00:00.000Z",
          endedAt: "2026-04-26T09:04:00.000Z",
          operationBrief: "Assemble the first weekly operating report.",
          deliverable:
            "Deliverable: weekly follow-up summary, owner assignments, and next-step recommendations for the revenue team.",
          llmMode: "managed",
        },
      ],
      onStart: (input, currentState) => {
        const inputJson =
          input.input_json && typeof input.input_json === "object" ? (input.input_json as Record<string, unknown>) : {};
        const operatingBrief =
          inputJson.operating_brief && typeof inputJson.operating_brief === "object"
            ? (inputJson.operating_brief as Record<string, unknown>)
            : {};
        const stakeholders = Array.isArray(operatingBrief.stakeholders) ? operatingBrief.stakeholders : [];
        const hasEnterpriseTarget = stakeholders.includes("Enterprise clients");

        return {
          id: "22222222-2222-4222-8222-222222222222",
          status: "succeeded",
          startedAt: "2026-04-26T10:00:00.000Z",
          endedAt: "2026-04-26T10:03:00.000Z",
          operationBrief: String(inputJson.operation_brief ?? "Run the next company operation."),
          deliverable: hasEnterpriseTarget
            ? "Deliverable: refreshed follow-up queue with the enterprise-client operating brief attached."
            : "Deliverable: refreshed follow-up queue, customer-ready summary, and a concise operating memo for the next cycle.",
          currentNodeId: currentState.graphVersion.graph_json.nodes[0]?.id ?? null,
          llmMode: "managed",
        };
      },
    };

    await installCompanyWorkspaceMocks(page, state);
    await openBackendAuthenticatedPage(page, request, user, "/companies");

    await expect(page.getByRole("heading", { name: /operate ai-driven companies/i })).toBeVisible();
    await expect(page.getByRole("link", { name: /continuum revenue ops/i }).first()).toBeVisible();
    await expect(page.getByText(/revenue operations/i).first()).toBeVisible();
    await expect(page.getByText(/open workspace/i).first()).toBeVisible();

    await page.getByRole("link", { name: /continuum revenue ops/i }).click();
    await page.waitForURL(new RegExp(`/companies/${seed.companyId}$`));

    await expect(page.getByRole("heading", { name: /continuum revenue ops/i }).first()).toBeVisible();
    await expect(
      page
        .getByText(
          /deliverable: weekly follow-up summary, owner assignments, and next-step recommendations for the revenue team\./i,
        )
        .first(),
    ).toBeVisible();
    await expect(page.getByText(/^stable$/i).first()).toBeVisible();
    await expect(page.getByTestId("operating-brief-panel")).toBeVisible();

    await page.getByTestId("operating-brief-input").fill("Actually target enterprise clients");
    await page.getByTestId("operating-brief-submit-button").click();

    await expect(page.getByText(/^enterprise clients$/i)).toBeVisible();
    const pmResponse = page.getByTestId("command-ops-response-card");
    await expect(pmResponse).toBeVisible();
    await expect(pmResponse).toContainText(/i understand the objective as/i);
    await expect(pmResponse).toContainText(/keep follow-up moving/i);
    await expect(pmResponse).toContainText(/interpreted as/i);
    await expect(pmResponse).toContainText(/before i proceed/i);
    await expect(pmResponse).toContainText(/which channels are allowed or off-limits/i);
    await expect(pmResponse.getByTestId("command-ops-response-next-step")).toContainText(
      /recorded assumptions and can start a draft plan/i,
    );

    await page
      .getByTestId("company-launch-operation-input")
      .fill("Prepare the next revenue operating cycle and ship an updated operator summary.");
    await page.getByTestId("company-launch-operation-button").click();

    await expect(
      page
        .getByText(/deliverable: refreshed follow-up queue with the enterprise-client operating brief attached\./i)
        .first(),
    ).toBeVisible();
    await expect(page.getByText(/^operation 22222222/i)).toBeVisible();
    await expect(page.getByText(/latest outputs/i)).toBeVisible();
  });

  test("shows company status, command ops health, and actionable controls", async ({ page, request }, testInfo) => {
    const user = createTestUser(testInfo, "company-command-ops");
    await ensureUserRegistered(request, user);
    const accessToken = await getAccessToken(request, user);
    const seed = await createCompanyViaApi(request, accessToken, {
      name: "Signal Growth Studio",
      companyType: "Growth Studio",
      objective: "Operate launch planning, messaging, production, and performance review from one company shell.",
      autonomyMode: "assisted",
      aiAccessMode: "managed",
    });
    const latestVersion = await fetchLatestGraphVersion(request, accessToken, seed.companyId);

    const failedOperationId = "33333333-3333-4333-8333-333333333333";
    const state: CompanyWorkspaceMockState = {
      companyId: seed.companyId,
      companyName: "Signal Growth Studio",
      graphVersion: latestVersion,
      pendingApprovalCount: 2,
      operations: [
        {
          id: "31111111-1111-4111-8111-111111111111",
          status: "running",
          startedAt: "2026-04-26T11:00:00.000Z",
          currentNodeId: latestVersion.graph_json.nodes[2]?.id ?? latestVersion.graph_json.nodes[1]?.id ?? null,
          operationBrief: "Push the next launch package forward.",
          llmMode: "managed",
        },
        {
          id: failedOperationId,
          status: "failed",
          startedAt: "2026-04-26T10:00:00.000Z",
          endedAt: "2026-04-26T10:06:00.000Z",
          failedNodeId: latestVersion.graph_json.nodes[1]?.id ?? latestVersion.graph_json.nodes[0]?.id ?? null,
          errorMessage: "Managed provider unavailable while Creative Production was packaging the final asset set.",
          llmMode: "managed",
        },
        {
          id: "34444444-4444-4444-8444-444444444444",
          status: "succeeded",
          startedAt: "2026-04-26T09:00:00.000Z",
          endedAt: "2026-04-26T09:05:00.000Z",
          deliverable: "Deliverable: approved messaging strategy, creative brief, and reporting plan.",
          llmMode: "managed",
        },
      ],
      onReplay: () => ({
        id: failedOperationId,
        status: "succeeded",
        startedAt: "2026-04-26T10:07:00.000Z",
        endedAt: "2026-04-26T10:10:00.000Z",
        deliverable: "Deliverable: retried creative package completed successfully.",
        llmMode: "managed",
      }),
    };

    await installCompanyWorkspaceMocks(page, state);
    await openBackendAuthenticatedPage(page, request, user, `/companies/${seed.companyId}`);

    const commandOpsPanel = page.locator(".command-ops-panel");
    await expect(page.getByRole("heading", { name: /signal growth studio/i }).first()).toBeVisible();
    await expect(page.getByText(/company category/i)).toBeVisible();
    await expect(page.getByText(/^growth studio$/i)).toBeVisible();
    await expect(page.getByText(/awaiting approval/i).first()).toBeVisible();
    await expect(commandOpsPanel.getByText(/active operations/i)).toBeVisible();
    await expect(commandOpsPanel.getByText(/failed operations/i)).toBeVisible();
    await expect(commandOpsPanel.getByText(/pending approvals/i)).toBeVisible();
    await expect(commandOpsPanel.getByText(/ai mode and usage/i)).toBeVisible();
    await expect(commandOpsPanel.getByText(/^managed$/i).last()).toBeVisible();
    await expect(page.getByText(/latest outputs/i)).toBeVisible();
    await expect(page.getByTestId("company-launch-operation-button")).toBeVisible();
    await expect(page.getByTestId("company-retry-operation-button")).toBeVisible();
    await expect(page.getByTestId("company-update-objective-button")).toBeVisible();
    await expect(page.getByRole("button", { name: /^pause company$/i })).toBeVisible();

    await page.getByTestId("company-retry-operation-button").click();

    await expect(
      page.getByText(/deliverable: retried creative package completed successfully\./i).first(),
    ).toBeVisible();
    await expect(
      page.getByText(/deliverable: approved messaging strategy, creative brief, and reporting plan\./i).first(),
    ).toBeVisible();
  });

  test("turns runtime failure into actionable user-facing language", async ({ page, request }, testInfo) => {
    const user = createTestUser(testInfo, "company-failure");
    await ensureUserRegistered(request, user);
    const accessToken = await getAccessToken(request, user);
    const seed = await createCompanyViaApi(request, accessToken, {
      name: "Atlas Research Lab",
      companyType: "Research Lab",
      objective: "Investigate strategic questions and deliver a clear recommendation package.",
      autonomyMode: "manual",
      aiAccessMode: "managed",
    });
    const latestVersion = await fetchLatestGraphVersion(request, accessToken, seed.companyId);
    const failedDepartmentId = latestVersion.graph_json.nodes[1]?.id ?? latestVersion.graph_json.nodes[0]?.id ?? null;
    const failedDepartmentLabel =
      latestVersion.graph_json.nodes.find((node) => node.id === failedDepartmentId)?.name ?? "Department";

    const state: CompanyWorkspaceMockState = {
      companyId: seed.companyId,
      companyName: "Atlas Research Lab",
      graphVersion: latestVersion,
      pendingApprovalCount: 0,
      operations: [
        {
          id: "41111111-1111-4111-8111-111111111111",
          status: "failed",
          startedAt: "2026-04-26T12:00:00.000Z",
          endedAt: "2026-04-26T12:03:00.000Z",
          failedNodeId: failedDepartmentId,
          errorMessage: "LLM timeout while waiting for provider response from the research synthesis step.",
          llmMode: "managed",
        },
      ],
    };

    await installCompanyWorkspaceMocks(page, state);
    await openBackendAuthenticatedPage(page, request, user, `/companies/${seed.companyId}`);

    await expect(page.getByText(/intelligence provider timed out/i)).toBeVisible();
    await expect(page.getByText(/a department waited too long for an ai response/i)).toBeVisible();
    await expect(page.getByText(new RegExp(failedDepartmentLabel, "i")).first()).toBeVisible();
    await expect(page.getByRole("button", { name: /^retry$/i })).toBeVisible();
    await expect(page.getByTestId("company-update-objective-button")).toBeVisible();
    await expect(page.getByText(/support details/i)).toBeVisible();
    await expect(page.getByText(/llm timeout while waiting for provider response/i)).not.toBeVisible();

    await page.getByText(/support details/i).click();

    await expect(
      page.getByText(/llm timeout while waiting for provider response from the research synthesis step\./i),
    ).toBeVisible();
    await expect(page.getByRole("link", { name: /switch ai access mode/i })).toBeVisible();
  });
});
