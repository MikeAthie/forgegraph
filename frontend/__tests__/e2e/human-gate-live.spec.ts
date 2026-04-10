import { expect, test } from "@playwright/test";

import {
  addHumanGateNode,
  addOutputNode,
  createGraph,
  createGraphName,
  createTestUser,
  ensureUserRegistered,
  getAccessToken,
  login,
  openBackendAuthenticatedPage,
  saveGraph,
  startRunFromEditor,
  waitForRunStatus,
} from "./helpers";

test.describe("Human gate live flow", () => {
  test.describe.configure({ mode: "serial" });

  test("pauses at a human gate and resumes from the inbox without refreshing the run page", async ({
    page,
    request,
  }, testInfo) => {
    test.setTimeout(120_000);

    const user = createTestUser(testInfo, "human-gate-live");
    await ensureUserRegistered(request, user);
    const accessToken = await getAccessToken(request, user);
    await login(page, user);

    const graphName = createGraphName("Human Gate Live");
    await createGraph(page, graphName);
    await addHumanGateNode(page, {
      label: "Finance approval",
      promptMessage: "Approve the outbound refund before execution resumes.",
      instructions: "Approve only when the refund amount is within policy.",
    });
    await addOutputNode(page, "Final Output");
    await saveGraph(page);

    const runId = await startRunFromEditor(page);
    await expect(page).toHaveURL(new RegExp(`/runs/${runId}$`));
    await expect(page.getByText(/live updates/i).first()).toBeVisible({ timeout: 30_000 });

    await waitForRunStatus(request, accessToken, runId, "paused");
    await expect(page.getByText(/approve the outbound refund before execution resumes/i).first()).toBeVisible({
      timeout: 30_000,
    });
    await expect(page.getByRole("link", { name: /open inbox/i })).toBeVisible();

    const reviewPage = await page.context().newPage();
    await openBackendAuthenticatedPage(reviewPage, request, user, "/inbox");
    const approvalRow = reviewPage.getByRole("button", { name: new RegExp(graphName, "i") }).first();
    await expect(approvalRow).toBeVisible({ timeout: 30_000 });
    await approvalRow.click();
    await reviewPage
      .getByPlaceholder(/add guidance, constraints, or corrections that should travel with this decision/i)
      .fill("Approved by the live Playwright reliability test.");
    await reviewPage.getByRole("button", { name: /approve with notes/i }).click();
    await reviewPage.close();

    await waitForRunStatus(request, accessToken, runId, "succeeded");
    await page.bringToFront();
    await expect(page).toHaveURL(new RegExp(`/runs/${runId}$`));
    await expect(page.getByText(/^succeeded$/i).first()).toBeVisible({ timeout: 30_000 });
  });
});
