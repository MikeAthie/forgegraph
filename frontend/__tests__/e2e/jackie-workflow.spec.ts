import { expect, test } from "@playwright/test";

import {
  addAgentNode,
  addObservationContextNode,
  addObservationSaveNode,
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
    const graphId = await createGraph(page, graphName);

    await addObservationContextNode(page, "Recall Jackie Context", {
      query: "What should I remember about Jackie before answering?",
      limit: 3,
    });
    const contextNodeId = await getGraphNodeByLabel(
      page,
      "Recall Jackie Context",
    ).getAttribute("data-node-id");
    expect(contextNodeId).toBeTruthy();

    await addAgentNode(page, {
      graphName,
      agentLabel: "Jackie",
      instructions:
        "You are Jackie, a Telegram personal assistant. Review curated memory context before answering, check system status with the allowed tool when needed, then reply with a concise productivity update for the user.",
      toolNames: [toolName],
      observationContextPaths: [`node.${contextNodeId}.output`],
      provider: "openai",
      model: "gpt-4.1-mini",
    });

    await addObservationSaveNode(page, "Save Jackie Observation", {
      type: "customer_memory",
      scope: "graph",
      title: "Jackie preference",
      topicKey: "jackie-memory",
      content: "Jackie prefers concise planning updates.",
    });

    await addOutputNode(page, "Telegram Reply");
    await saveGraph(page);

    await expect(
      getGraphNodeByLabel(page, "Recall Jackie Context"),
    ).toBeVisible();
    await expect(getGraphNodeByLabel(page, "Jackie")).toBeVisible();
    await expect(
      getGraphNodeByLabel(page, "Save Jackie Observation"),
    ).toBeVisible();
    await expect(page.locator('[data-testid^="rf__edge-"]')).toHaveCount(3);

    const firstRunId = await startRunFromEditor(page);
    const firstRun = await waitForRunTerminal(request, accessToken, firstRunId);
    expect(firstRun.status).toBe("succeeded");

    await page.goto(`/graphs/${graphId}`);
    const secondRunId = await startRunFromEditor(page);
    const secondRun = await waitForRunTerminal(request, accessToken, secondRunId);
    expect(secondRun.status).toBe("succeeded");

    await page.reload();
    await expect(page).toHaveURL(new RegExp(`/runs/${secondRunId}$`));
    await expect(page.getByText(/succeeded/i).first()).toBeVisible();
    await expect(page.getByText(/^curated memory$/i)).toBeVisible();
    await expect(page.getByText(/built curated context/i).first()).toBeVisible();
    await expect(page.getByText(/used curated memory/i).first()).toBeVisible();
    await expect(page.getByText(/jackie preference/i).first()).toBeVisible();

    const jackieNodeButton = page
      .getByRole("button", { name: /jackie attempt 1/i })
      .first();
    await expect(jackieNodeButton).toBeVisible();
    await jackieNodeButton.click();

    await expect(page.getByText(/Final answer/i).first()).toBeVisible();
    await expect(page.getByText(/Tool calls/i).first()).toBeVisible();
    await expect(page.getByText(/curated memory activity/i).first()).toBeVisible();
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
