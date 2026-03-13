import { expect, test } from "@playwright/test";

import {
  addAgentNode,
  addMemoryNode,
  addOutputNode,
  createGraph,
  createGraphName,
  getAccessToken,
  getGraphNodeByLabel,
  getPlaywrightRuntimeFixtureUser,
  installRuntimePackage,
  login,
  saveGraph,
  startRunFromEditor,
  waitForRunTerminal,
} from "./helpers";

const runtimeFixtureUser = getPlaywrightRuntimeFixtureUser();
const packageName =
  process.env.PLAYWRIGHT_RUNTIME_PACKAGE_NAME ??
  "Playwright Runtime Health Check";
const toolName =
  process.env.PLAYWRIGHT_RUNTIME_TOOL_NAME ?? "playwright_runtime_health_check";

test.describe("Jackie workflow", () => {
  test.describe.configure({ mode: "serial" });

  test("manually authors and runs a Jackie-style agent workflow against the local LLM mock", async ({
    page,
    request,
  }) => {
    test.setTimeout(90_000);

    const accessToken = await getAccessToken(request, runtimeFixtureUser);
    await login(page, runtimeFixtureUser);
    await installRuntimePackage(page, packageName, toolName);

    const graphName = createGraphName("Jackie Workflow");
    await createGraph(page, graphName);

    await addMemoryNode(page, "Conversation Memory", {
      key: "conversation_history",
    });

    await addAgentNode(page, {
      graphName,
      agentLabel: "Jackie",
      instructions:
        "You are Jackie, a Telegram personal assistant. Check system status with the allowed tool when needed, then reply with a concise productivity update for the user.",
      toolNames: [toolName],
      provider: "openai",
      model: "gpt-4.1-mini",
    });

    await addOutputNode(page, "Telegram Reply");
    await saveGraph(page);

    await expect(
      getGraphNodeByLabel(page, "Conversation Memory"),
    ).toBeVisible();
    await expect(getGraphNodeByLabel(page, "Jackie")).toBeVisible();
    await expect(page.locator('[data-testid^="rf__edge-"]')).toHaveCount(2);

    const runId = await startRunFromEditor(page);
    const run = await waitForRunTerminal(request, accessToken, runId);
    expect(run.status).toBe("succeeded");

    await page.reload();
    await expect(page.getByText(graphName)).toBeVisible();
    await expect(page.getByText(/succeeded/i).first()).toBeVisible();

    const jackieNodeButton = page
      .getByRole("button", { name: /jackie attempt 1/i })
      .first();
    await expect(jackieNodeButton).toBeVisible();
    await jackieNodeButton.click();

    await expect(page.getByText(/Final answer/i).first()).toBeVisible();
    await expect(page.getByText(/Tool calls/i).first()).toBeVisible();
    await expect(
      page.getByText(new RegExp(toolName, "i")).first(),
    ).toBeVisible();
    await expect(
      page
        .getByText(
          /Jackie checked your workspace health and everything looks good\. No urgent issues found\./i,
        )
        .first(),
    ).toBeVisible();
  });
});
