import { expect, test } from "@playwright/test";

import { createGraphName, createHumanGateRunViaApi, createTestUser, loginLive, waitForRunStatus } from "./live-helpers";

test.describe("Human gate live flow", () => {
  test.describe.configure({ mode: "serial" });

  test("pauses at a human gate and resumes from the inbox without refreshing the run page", async ({
    page,
    request,
  }, testInfo) => {
    test.setTimeout(120_000);

    const user = createTestUser(testInfo, "human-gate-live");
    const accessToken = await loginLive(page, request, user);

    const graphName = createGraphName("Human Gate Live");
    const promptMessage = "Approve the outbound refund before execution resumes.";
    const { runId } = await createHumanGateRunViaApi(request, accessToken, {
      graphName,
      promptMessage,
      instructions: "Approve only when the refund amount is within policy.",
    });

    await page.goto(`/runs/${runId}`);
    await expect(page).toHaveURL(new RegExp(`/runs/${runId}$`));
    await expect(page.getByRole("heading", { name: /operation detail/i }).first()).toBeVisible({
      timeout: 30_000,
    });

    await waitForRunStatus(request, accessToken, runId, "paused");
    await expect(page.getByRole("heading", { name: /approval is waiting/i })).toBeVisible({ timeout: 30_000 });
    await expect(page.getByRole("link", { name: /open approvals/i })).toBeVisible();

    const reviewPage = await page.context().newPage();
    await loginLive(reviewPage, request, user, "/inbox");
    await reviewPage.getByRole("button", { name: /^all$/i }).click();
    const approvalRow = reviewPage.getByRole("button", { name: new RegExp(graphName, "i") }).first();
    await expect(approvalRow).toBeVisible({ timeout: 30_000 });
    await approvalRow.click();
    await expect(reviewPage.getByText(promptMessage).first()).toBeVisible({ timeout: 30_000 });
    await reviewPage
      .getByPlaceholder(/add guidance, constraints, or corrections that should travel with this decision/i)
      .fill("Approved by the live Playwright reliability test.");
    const approveButton = reviewPage.getByRole("button", { name: /approve with notes/i });
    await expect(approveButton).toBeEnabled();
    const resumeResponsePromise = reviewPage.waitForResponse(
      (response) => response.url().includes(`/api/runs/${runId}/resume`) && response.request().method() === "POST",
    );
    await approveButton.click();
    const resumeResponse = await resumeResponsePromise;
    expect(resumeResponse.ok()).toBeTruthy();
    await reviewPage.close();

    const completedRun = await waitForRunStatus(request, accessToken, runId, "succeeded");
    const eventTypes = new Set((completedRun.timeline ?? []).map((event) => event.event_type));
    expect(eventTypes.has("decision_required")).toBeTruthy();
    expect(eventTypes.has("decision_resolved")).toBeTruthy();
    expect(eventTypes.has("run.resume_requested")).toBeTruthy();
    expect(eventTypes.has("run_resumed")).toBeTruthy();
    await page.bringToFront();
    await expect(page).toHaveURL(new RegExp(`/runs/${runId}$`));
    await expect(page.getByText(/^completed$/i).first()).toBeVisible({ timeout: 30_000 });
  });
});
