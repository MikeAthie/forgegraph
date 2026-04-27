import { expect, test } from "@playwright/test";

import { installCompanyWorkspaceMocks, type CompanyWorkspaceMockState } from "./company-ux-fixtures";
import { buildCompanyGraphJson, buildCompanyProfile, companyPresets } from "../../lib/company-workspace";
import { createTestUser, ensureUserRegistered, login, type TestUser } from "./helpers";

let seededUser: TestUser;

test.beforeAll(async ({ request }, testInfo) => {
  seededUser = createTestUser(testInfo, "company-onboarding");
  await ensureUserRegistered(request, seededUser);
});

test.describe("Create and launch company", () => {
  test.describe.configure({ mode: "serial" });

  test.beforeEach(async ({ page }) => {
    await login(page, seededUser);
  });

  test("creates a company, launches its first operation, and shows a deliverable in company language", async ({
    page,
  }) => {
    test.setTimeout(60_000);

    const companyId = "55555555-5555-4555-8555-555555555555";
    const versionId = "66666666-6666-4666-8666-666666666666";
    const objective =
      "Coordinate the company's first weekly operating cycle and deliver a clear action summary for stakeholders.";
    const operationBrief = "Run the first operating cycle and produce a deliverable the business can use immediately.";
    const expectedProfile = buildCompanyProfile({
      companyName: "Northstar Operating Co.",
      companyType: "General Company",
      objective,
      departments: companyPresets[0]!.departments,
      skills: companyPresets[0]!.skills,
      autonomyMode: "assisted",
      aiAccessMode: "managed",
    });
    const expectedGraphJson = buildCompanyGraphJson(expectedProfile);
    let createdGraphPayload: Record<string, unknown> | null = null;
    let createdVersionPayload: Record<string, unknown> | null = null;
    let startedOperationPayload: Record<string, unknown> | null = null;

    const state: CompanyWorkspaceMockState = {
      companyId,
      companyName: "Northstar Operating Co.",
      graphVersion: {
        id: versionId,
        version: 1,
        graph_json: expectedGraphJson,
      },
      pendingApprovalCount: 0,
      operations: [],
      onStart: (input) => {
        startedOperationPayload = input;
        return {
          id: "11111111-1111-4111-8111-111111111111",
          status: "running",
          startedAt: "2026-04-26T11:00:00.000Z",
          operationBrief,
          currentNodeId: expectedGraphJson.nodes[1]?.id ?? expectedGraphJson.nodes[0]?.id ?? null,
          llmMode: "managed",
        };
      },
    };

    await installCompanyWorkspaceMocks(page, state);

    await page.route(/\/api\/graphs\/?(?:\?.*)?$/, async (route) => {
      if (route.request().method() === "POST") {
        createdGraphPayload = (route.request().postDataJSON() as Record<string, unknown>) ?? null;
        await route.fulfill({
          status: 200,
          contentType: "application/json",
          body: JSON.stringify({
            data: {
              id: companyId,
              name: "Northstar Operating Co.",
              description: objective,
            },
          }),
        });
        return;
      }

      await route.fallback();
    });

    await page.route(new RegExp(`/api/graphs/${companyId}/versions(?:\\?.*)?$`), async (route) => {
      createdVersionPayload = (route.request().postDataJSON() as Record<string, unknown>) ?? null;
      await route.fulfill({
        status: 200,
        contentType: "application/json",
        body: JSON.stringify({
          data: {
            id: versionId,
            version: 1,
            graph_json: expectedGraphJson,
          },
        }),
      });
    });

    await page.goto("/companies/new");

    await expect(page.getByRole("heading", { name: /define the objective first/i })).toBeVisible();
    await expect(page.getByText(/step 1 of 5/i)).toBeVisible();
    await expect(page.getByText(/what should this company accomplish\?/i).first()).toBeVisible();
    await expect(page.getByText(/launch a marketing campaign/i)).toBeVisible();

    await page.getByTestId("company-name-input").fill("Northstar Operating Co.");
    await page.getByText(/manage operations/i).click();
    await expect(page.getByTestId("company-objective-input")).toHaveValue(/manage operations/i);
    await page.getByTestId("company-objective-input").fill(objective);
    await page.getByRole("button", { name: /continue/i }).click();

    await expect(page.getByText(/review the suggested structure/i).first()).toBeVisible();
    await expect(page.getByText(/suggested category/i).first()).toBeVisible();
    await expect(page.getByText(/operations & delivery|general company/i).first()).toBeVisible();
    await expect(page.getByText(companyPresets[0]!.departments[0]!.label).first()).toBeVisible();
    await page.getByRole("button", { name: /continue/i }).click();

    await expect(page.getByText(/adjust the team/i).first()).toBeVisible();
    await expect(page.getByTestId(`department-chip-${companyPresets[0]!.departments[0]!.id}`)).toBeVisible();
    await page.getByRole("button", { name: /continue/i }).click();

    await expect(page.getByText(/choose operating rules/i).first()).toBeVisible();
    await expect(
      page.getByText(/assisted starts work automatically and pauses only when a decision is worth your time/i),
    ).toBeVisible();
    await expect(page.getByText(/managed uses forgegraph's ai access so you can launch immediately/i)).toBeVisible();
    await page.getByRole("button", { name: /continue/i }).click();

    await expect(page.getByText(/^5\. launch$/i).first()).toBeVisible();
    await expect(page.getByText(/launch first operation/i).first()).toBeVisible();
    await page.getByTestId("company-operation-brief-input").fill(operationBrief);

    await page.getByTestId("company-create-submit").click();
    await page.waitForURL(/\/companies\/[a-f0-9-]+$/, { timeout: 20_000 });

    expect(createdGraphPayload).toMatchObject({
      name: "Northstar Operating Co.",
      description: objective,
    });
    expect(createdVersionPayload?.graph_json).toMatchObject(expectedGraphJson);
    expect(createdVersionPayload?.graph_json?.metadata?.company_profile).toMatchObject({
      companyName: "Northstar Operating Co.",
      objective,
      autonomyMode: "assisted",
      aiAccessMode: "managed",
    });
    expect(startedOperationPayload).toMatchObject({
      graph_version_id: versionId,
      llm_mode: "managed",
    });
    expect(
      startedOperationPayload?.input_json &&
        typeof startedOperationPayload.input_json === "object" &&
        "operation_brief" in startedOperationPayload.input_json
        ? startedOperationPayload.input_json.operation_brief
        : null,
    ).toBe(operationBrief);

    await expect(page.getByRole("heading", { name: /northstar operating co\./i }).first()).toBeVisible();
    await expect(page.getByRole("heading", { name: /^operations$/i })).toBeVisible();
    await expect(page.getByText(/^operation 11111111/i)).toBeVisible();
    await expect(page.getByText(/current department:/i)).toBeVisible();
    await expect(page.getByText(new RegExp(companyPresets[0]!.departments[0]!.label, "i")).first()).toBeVisible();
    await expect(page.getByText(/latest deliverable preview/i)).toBeVisible();
    await expect(
      page.getByText(/handed work forward|deliverable will appear once this operation finishes/i).first(),
    ).toBeVisible();
    await expect(page.getByText(/show internal identifiers/i)).toBeVisible();
    await expect(page.getByText(/graph id:/i)).not.toBeVisible();
    await expect(page.getByText(/version id:/i)).not.toBeVisible();
    await expect(page.getByText(/run id/i)).not.toBeVisible();

    state.operations[0] = {
      ...state.operations[0],
      status: "succeeded",
      endedAt: "2026-04-26T11:04:00.000Z",
      deliverable:
        "Deliverable: weekly operating summary, owner assignments, and the next round of recommended actions.",
    };

    await page.reload();
    await page.waitForLoadState("networkidle");

    await expect(page.getByText(/^completed$/i).first()).toBeVisible();
    await expect(
      page
        .getByText(
          /deliverable: weekly operating summary, owner assignments, and the next round of recommended actions\./i,
        )
        .first(),
    ).toBeVisible();
    await expect(page.getByText(/deliverable from operation 11111111/i)).toBeVisible();
  });
});
