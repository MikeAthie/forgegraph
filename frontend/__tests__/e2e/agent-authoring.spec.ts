import { expect, test } from "@playwright/test";

import {
  addMarketplaceToolNode,
  authorAgentWorkflow,
  clearGraphSelection,
  connectGraphNodes,
  createGraph,
  createGraphName,
  fetchLatestGraphVersion,
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
const packageSlug =
  process.env.PLAYWRIGHT_RUNTIME_PACKAGE_SLUG ??
  "playwright-runtime-health-check";
const toolName =
  process.env.PLAYWRIGHT_RUNTIME_TOOL_NAME ?? "playwright_runtime_health_check";

test.describe("Manual workflow authoring", () => {
  test.describe.configure({ mode: "serial" });

  test("manually authors and saves an agent workflow from the canvas UI", async ({
    page,
    request,
  }) => {
    test.setTimeout(90_000);

    const accessToken = await getAccessToken(request, runtimeFixtureUser);
    await login(page, runtimeFixtureUser);
    await installRuntimePackage(page, packageName, toolName);

    const graphName = createGraphName("Agent Authoring");
    const agentLabel = "Jackie";
    const outputLabel = "Telegram Response";

    const { graphId } = await authorAgentWorkflow(page, {
      graphName,
      agentLabel,
      outputLabel,
      provider: "openai",
      model: "gpt-4.1-mini",
      instructions:
        "Act as Jackie, a personal productivity assistant. Use the allowed tool when you need live system status, then return a concise Telegram-ready response.",
      toolNames: [toolName],
    });

    await expect(getGraphNodeByLabel(page, agentLabel)).toBeVisible();
    await expect(getGraphNodeByLabel(page, outputLabel)).toBeVisible();

    const latestVersion = await fetchLatestGraphVersion(
      request,
      accessToken,
      graphId,
    );
    expect(latestVersion.graph_json.nodes).toHaveLength(2);
    expect(latestVersion.graph_json.edges).toHaveLength(3);

    const agentNode = latestVersion.graph_json.nodes.find(
      (node) => node.type === "agent",
    );
    expect(agentNode).toBeTruthy();
    expect(agentNode?.name).toBe(agentLabel);
    expect(agentNode?.config?.provider).toBe("openai");
    expect(agentNode?.config?.model).toBe("gpt-4.1-mini");
    expect(agentNode?.config?.instructions).toContain("Jackie");
    expect(agentNode?.config?.tools).toEqual([toolName]);

    const outputNode = latestVersion.graph_json.nodes.find(
      (node) => node.type === "output",
    );
    expect(outputNode).toBeTruthy();
    expect(outputNode?.name).toBe(outputLabel);

    const agentToOutputEdge = latestVersion.graph_json.edges.find(
      (edge) => edge.from === agentNode?.id && edge.to === outputNode?.id,
    );
    expect(agentToOutputEdge).toBeTruthy();
  });

  test("manually builds a runtime tool workflow and executes it", async ({
    page,
    request,
  }) => {
    test.setTimeout(90_000);

    const accessToken = await getAccessToken(request, runtimeFixtureUser);
    await login(page, runtimeFixtureUser);
    await installRuntimePackage(page, packageName, toolName);

    const graphName = createGraphName("Manual Runtime Tool");
    await createGraph(page, graphName);

    await addMarketplaceToolNode(page, packageSlug, "Health Check Tool");
    await clearGraphSelection(page);
    await page.getByTestId("palette-item-output").click();
    const outputDialog = page.getByRole("dialog", {
      name: /configure output node/i,
    });
    await expect(outputDialog).toBeVisible();
    await outputDialog.locator("#node-label").fill("Tool Result");
    await outputDialog.getByRole("button", { name: /^add node$/i }).click();
    await expect(outputDialog).toBeHidden();

    await connectGraphNodes(page, "Health Check Tool", "Tool Result");
    await saveGraph(page);

    const runId = await startRunFromEditor(page);
    const run = await waitForRunTerminal(request, accessToken, runId);
    expect(run.status).toBe("succeeded");

    await page.reload();
    await expect(page.getByText(graphName)).toBeVisible();
    await expect(page.getByText(/succeeded/i).first()).toBeVisible();

    const toolRunButton = page
      .getByRole("button", { name: /health check tool/i })
      .first();
    await expect(toolRunButton).toBeVisible();
    await toolRunButton.click();

    await expect(
      page.getByText(new RegExp(`"tool":\\s*"${toolName}"`, "i")).first(),
    ).toBeVisible();
    await expect(page.getByText(/"status":\s*200/i).first()).toBeVisible();
    await expect(page.getByText(/"status":\s*"ok"/i).first()).toBeVisible();
  });
});
