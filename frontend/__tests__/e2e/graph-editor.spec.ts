/**
 * E2E tests for Graph Editor.
 *
 * Tests the complete graph editing flow including:
 * - Creating and opening graphs
 * - Adding nodes from palette
 * - Connecting nodes with edges
 * - Configuring nodes via inspector
 * - Saving and reloading graphs
 * - Deleting nodes and edges
 * - Editing graph metadata
 */

import { test, expect, type APIRequestContext, type Locator, type Page } from "@playwright/test";
import { createTestUser, ensureUserRegistered, login, type TestUser } from "./helpers";

let seededUser: TestUser;

const API_BASE_URL = (process.env.PLAYWRIGHT_API_URL ??
  process.env.NEXT_PUBLIC_API_URL ??
  "http://127.0.0.1:8000"
).replace(/\/$/, "");

const createGraphName = (prefix: string) =>
  `${prefix} ${Date.now()}-${Math.random().toString(16).slice(2)}`;
const GRAPH_URL_PATTERN = /\/graphs\/[a-f0-9-]+/;

async function expectGraphEditorOpen(page: Page) {
  await expect(page).toHaveURL(GRAPH_URL_PATTERN, { timeout: 15_000 });
}

async function getAccessToken(request: APIRequestContext, user: TestUser): Promise<string> {
  const response = await request.post(`${API_BASE_URL}/api/auth/login`, {
    data: { email: user.email, password: user.password },
  });
  expect(response.ok()).toBeTruthy();
  const json = (await response.json()) as { access?: string };
  if (!json.access) {
    throw new Error(`Login did not return access token: ${JSON.stringify(json)}`);
  }
  return json.access;
}

async function getCenter(locator: Locator) {
  const box = await locator.boundingBox();
  if (!box) {
    throw new Error("Could not determine element bounding box");
  }
  return { x: box.x + box.width / 2, y: box.y + box.height / 2 };
}

async function connectNodes(
  page: Page,
  sourceLabel: string,
  targetLabel: string
) {
  const edges = page.locator('[data-testid^="rf__edge-"]');
  const beforeCount = await edges.count();

  const sourceNode = page.locator(".react-flow__node").filter({ hasText: sourceLabel }).first();
  const targetNode = page.locator(".react-flow__node").filter({ hasText: targetLabel }).first();

  await expect(sourceNode).toBeVisible();
  await expect(targetNode).toBeVisible();

  const sourceHandle = sourceNode
    .locator(".react-flow__handle.source.react-flow__handle-bottom")
    .first();

  await expect(sourceHandle).toBeVisible();
  await expect(sourceHandle).toHaveClass(/connectionindicator/);

  const targetHandle = targetNode
    .locator(".react-flow__handle.target.react-flow__handle-top")
    .first();

  await expect(targetHandle).toBeVisible();
  await expect(targetHandle).toHaveClass(/connectionindicator/);

  const from = await getCenter(sourceHandle);
  const to = await getCenter(targetHandle);

  try {
    await sourceHandle.click();
    await targetHandle.click();
    await expect(edges).toHaveCount(beforeCount + 1, { timeout: 1500 });
    return;
  } catch {
    // Fall back to drag-to-connect for browsers where click-connect is flaky.
  }

  await page.keyboard.press("Escape").catch(() => undefined);

  await page.mouse.move(from.x, from.y);
  await page.mouse.down();
  await page.mouse.move(to.x, to.y, { steps: 18 });
  await page.mouse.up();

  await expect(edges).toHaveCount(beforeCount + 1);
}

async function addPromptNodeViaWizard(
  page: Page,
  options?: { task?: string; saveToLibrary?: boolean },
) {
  const task = options?.task ?? "Write a short response.";
  const saveToLibrary = options?.saveToLibrary ?? false;

  await page.getByRole("button", { name: /^prompt/i }).click();

  const wizard = page.getByRole("dialog", { name: /prompt node wizard/i });
  await expect(wizard).toBeVisible();

  await wizard.getByRole("button", { name: /^next$/i }).click(); // Role -> Task
  await wizard.getByPlaceholder(/write a clear task description/i).fill(task);
  await wizard.getByRole("button", { name: /^next$/i }).click(); // Task -> Examples
  await wizard.getByRole("button", { name: /^next$/i }).click(); // Examples -> Output
  await wizard.getByRole("button", { name: /^next$/i }).click(); // Output -> Review

  if (!saveToLibrary) {
    await wizard.getByRole("checkbox", { name: /save to prompt library/i }).uncheck();
  }

  await wizard.getByRole("button", { name: /^finish$/i }).click();
  await expect(wizard).toBeHidden();
}

async function addNodeViaConfigDialog(
  page: Page,
  options: { buttonLabel: RegExp; dialogLabel: RegExp; nodeLabel: string },
) {
  await page.getByRole("button", { name: options.buttonLabel }).click();

  const dialog = page.getByRole("dialog", { name: options.dialogLabel });
  await expect(dialog).toBeVisible();
  await dialog.getByRole("button", { name: /^add node$/i }).click();
  await expect(dialog).toBeHidden();

  // Scope assertion to canvas nodes only to avoid matching palette/inspector elements
  const canvasNode = page.locator(".react-flow__node").filter({ hasText: options.nodeLabel });
  await expect(canvasNode.first()).toBeVisible();
}

test.beforeAll(async ({ request }, testInfo) => {
  seededUser = createTestUser(testInfo, "e2e-graph-editor");
  await ensureUserRegistered(request, seededUser);
});

test.describe("Graph Editor", () => {
  test.describe.configure({ mode: "serial" });
  test.beforeEach(async ({ page }) => {
    await login(page, seededUser);
  });

  test("creates graph and opens editor", async ({ page }) => {
    const graphName = createGraphName("Editor Test Graph");

    await page.getByRole("button", { name: /^new graph$/i }).click();
    await page.locator("#create-graph-name").fill(graphName);
    await page.locator("#create-graph-description").fill("Testing graph editor");
    await page.getByRole("dialog").getByRole("button", { name: /^create$/i }).click();

    // Should navigate to graph detail page with editor
    await expectGraphEditorOpen(page);

    // Editor components should be visible
    await expect(page.getByText("Add Nodes")).toBeVisible();
    await expect(page.getByText("Click to add a node to the canvas")).toBeVisible();
  });

  test("displays node palette with all node types", async ({ page }) => {
    const graphName = createGraphName("Palette Test");

    // Create and open graph
    await page.getByRole("button", { name: /^new graph$/i }).click();
    await page.locator("#create-graph-name").fill(graphName);
    await page.getByRole("dialog").getByRole("button", { name: /^create$/i }).click();

    await expectGraphEditorOpen(page);

    // Check enabled node types
    await expect(page.getByRole("button", { name: /^prompt/i })).toBeEnabled();
    await expect(page.getByRole("button", { name: /^http/i })).toBeEnabled();
    await expect(page.getByRole("button", { name: /^transform/i })).toBeEnabled();
    await expect(page.getByRole("button", { name: /^output/i })).toBeEnabled();

    // Branch + Merge + Human Gate are available in the editor.
    await expect(page.getByRole("button", { name: /^branch/i })).toBeEnabled();
    await expect(page.getByRole("button", { name: /^merge/i })).toBeEnabled();
    await expect(page.getByRole("button", { name: /^human gate/i })).toBeEnabled();
  });

  test("adds a node from palette", async ({ page }) => {
    const graphName = createGraphName("Add Node Test");

    // Create and open graph
    await page.getByRole("button", { name: /^new graph$/i }).click();
    await page.locator("#create-graph-name").fill(graphName);
    await page.getByRole("dialog").getByRole("button", { name: /^create$/i }).click();

    await expectGraphEditorOpen(page);

    // Add a Prompt node
    await addPromptNodeViaWizard(page);

    // Node should appear in the canvas
    await expect(page.getByText("Prompt Node")).toBeVisible();
  });

  test("adds multiple nodes of different types", async ({ page }) => {
    const graphName = createGraphName("Multiple Nodes Test");

    await page.getByRole("button", { name: /^new graph$/i }).click();
    await page.locator("#create-graph-name").fill(graphName);
    await page.getByRole("dialog").getByRole("button", { name: /^create$/i }).click();

    await expectGraphEditorOpen(page);

    // Add different node types
    await addPromptNodeViaWizard(page);
    await expect(page.getByText("Prompt Node")).toBeVisible();

    await addNodeViaConfigDialog(page, {
      buttonLabel: /^http/i,
      dialogLabel: /configure http node/i,
      nodeLabel: "HTTP",
    });

    await addNodeViaConfigDialog(page, {
      buttonLabel: /^transform/i,
      dialogLabel: /configure transform node/i,
      nodeLabel: "Transform",
    });

    await addNodeViaConfigDialog(page, {
      buttonLabel: /^output/i,
      dialogLabel: /configure output node/i,
      nodeLabel: "Output",
    });
  });

  test("shows graph info in inspector when no node is selected", async ({ page }) => {
    const graphName = createGraphName("Inspector Info");
    const description = "Test graph description";

    await page.getByRole("button", { name: /^new graph$/i }).click();
    await page.locator("#create-graph-name").fill(graphName);
    await page.locator("#create-graph-description").fill(description);
    await page.getByRole("dialog").getByRole("button", { name: /^create$/i }).click();

    await expectGraphEditorOpen(page);

    // Inspector should show graph info
    await expect(page.getByRole("heading", { name: /^graph info$/i })).toBeVisible();
    await expect(page.getByRole("heading", { name: graphName })).toBeVisible();
    await expect(page.getByText(description)).toBeVisible();
  });

  test("selects node and shows configuration in inspector", async ({ page }) => {
    const graphName = createGraphName("Node Config Test");

    await page.getByRole("button", { name: /^new graph$/i }).click();
    await page.locator("#create-graph-name").fill(graphName);
    await page.getByRole("dialog").getByRole("button", { name: /^create$/i }).click();

    await expectGraphEditorOpen(page);

    // Add a node
    await addPromptNodeViaWizard(page);

    // Click on the node to select it
    await page.getByText("Prompt Node").click();

    // Inspector should show node config
    await expect(
      page.getByRole("heading", { name: "Node Config", exact: true }),
    ).toBeVisible();
    await expect(page.getByText("prompt", { exact: true })).toBeVisible(); // Type badge
    await expect(page.getByRole("button", { name: /^delete$/i })).toBeVisible();
  });

  test("updates node name via inspector", async ({ page }) => {
    const graphName = createGraphName("Update Node Name");

    await page.getByRole("button", { name: /^new graph$/i }).click();
    await page.locator("#create-graph-name").fill(graphName);
    await page.getByRole("dialog").getByRole("button", { name: /^create$/i }).click();

    await expectGraphEditorOpen(page);

    // Add a node and select it
    await addPromptNodeViaWizard(page);
    await page.getByText("Prompt Node").click();

    // Update node name in inspector
    const nameInput = page.locator('input[value="Prompt Node"]');
    await nameInput.fill("My Custom Prompt");

    // Node should reflect the new name in canvas
    await expect(page.getByText("My Custom Prompt")).toBeVisible();
  });

  test("configures Prompt node with prompt ID", async ({ page }) => {
    const graphName = createGraphName("Configure Prompt");

    await page.getByRole("button", { name: /^new graph$/i }).click();
    await page.locator("#create-graph-name").fill(graphName);
    await page.getByRole("dialog").getByRole("button", { name: /^create$/i }).click();

    await expectGraphEditorOpen(page);

    // Add and select prompt node
    await addPromptNodeViaWizard(page);
    await page.getByText("Prompt Node").click();

    // Configure prompt ID
    await expect(page.getByText("Prompt Configuration")).toBeVisible();
    const promptIdInput = page.getByPlaceholder(/select or enter prompt id/i);
    await promptIdInput.fill("test-prompt-123");

    // Should show config in node
    await expect(page.getByText(/prompt: test-prompt-123/i)).toBeVisible();
  });

  test("configures HTTP node with method and URL", async ({ page }) => {
    const graphName = createGraphName("Configure HTTP");

    await page.getByRole("button", { name: /^new graph$/i }).click();
    await page.locator("#create-graph-name").fill(graphName);
    await page.getByRole("dialog").getByRole("button", { name: /^create$/i }).click();

    await expectGraphEditorOpen(page);

    // Add and select HTTP node
    await addNodeViaConfigDialog(page, {
      buttonLabel: /^http/i,
      dialogLabel: /configure http node/i,
      nodeLabel: "HTTP",
    });
    await page.locator(".react-flow__node").filter({ hasText: "HTTP" }).first().click();

    // Configure HTTP settings
    await expect(page.getByText("HTTP Configuration")).toBeVisible();

    const httpConfigSection = page
      .getByRole("heading", { name: /^http configuration$/i })
      .locator("..");
    const methodSelect = httpConfigSection.locator("select");
    await methodSelect.selectOption("POST");

    const urlInput = page.getByPlaceholder(/https:\/\/api\.example\.com/i);
    await urlInput.fill("https://api.test.com/endpoint");

    // Should show config preview
    await expect(page.getByText(/POST https:\/\/api\.test\.com/i)).toBeVisible();
  });

  test("configures Transform node with expression", async ({ page }) => {
    const graphName = createGraphName("Configure Transform");

    await page.getByRole("button", { name: /^new graph$/i }).click();
    await page.locator("#create-graph-name").fill(graphName);
    await page.getByRole("dialog").getByRole("button", { name: /^create$/i }).click();

    await expectGraphEditorOpen(page);

    // Add and select Transform node
    await addNodeViaConfigDialog(page, {
      buttonLabel: /^transform/i,
      dialogLabel: /configure transform node/i,
      nodeLabel: "Transform",
    });
    await page.locator(".react-flow__node").filter({ hasText: "Transform" }).first().click();

    // Configure expression
    await expect(page.getByText("Transform Configuration")).toBeVisible();
    const expressionInput = page.getByPlaceholder(/state\.input \| uppercase/i);
    await expressionInput.fill("state.data | lowercase");

    await expect(expressionInput).toHaveValue("state.data | lowercase");
    await expect(page.getByText(/state\.data \| lowercase\.\.\./i)).toBeVisible();
  });

  test("saves graph and shows version number", async ({ page }) => {
    const graphName = createGraphName("Save Test");

    await page.getByRole("button", { name: /^new graph$/i }).click();
    await page.locator("#create-graph-name").fill(graphName);
    await page.getByRole("dialog").getByRole("button", { name: /^create$/i }).click();

    await expectGraphEditorOpen(page);

    // Add nodes to make the graph dirty - need an output node for valid save
    await addPromptNodeViaWizard(page);
    await addNodeViaConfigDialog(page, {
      buttonLabel: /^output$/i,
      dialogLabel: /configure output node/i,
      nodeLabel: "Output",
    });

    // Save button should be enabled
    const saveButton = page.getByRole("button", { name: /^save$/i });
    await expect(saveButton).toBeEnabled();

    // Click save
    await saveButton.click();

    // Wait for save to complete - version dropdown becomes enabled when save finishes
    const versionSelect = page.getByRole("combobox", { name: /^version$/i });
    await expect(versionSelect).toBeEnabled({ timeout: 30000 });
    await expect
      .poll(async () => {
        return versionSelect.evaluate((el: HTMLSelectElement) => {
          return el.options[el.selectedIndex]?.textContent ?? "";
        });
      })
      .toMatch(/v1/i);
  });

  test("shows dirty indicator when graph has unsaved changes", async ({ page }) => {
    const graphName = createGraphName("Dirty State Test");

    await page.getByRole("button", { name: /^new graph$/i }).click();
    await page.locator("#create-graph-name").fill(graphName);
    await page.getByRole("dialog").getByRole("button", { name: /^create$/i }).click();

    await expectGraphEditorOpen(page);

    // Initially no dirty indicator
    await expect(page.getByText("*")).not.toBeVisible();

    // Add nodes - need an output node for valid save
    await addPromptNodeViaWizard(page);
    await addNodeViaConfigDialog(page, {
      buttonLabel: /^output$/i,
      dialogLabel: /configure output node/i,
      nodeLabel: "Output",
    });

    // Should show dirty indicator (asterisk)
    await expect(page.getByText("*")).toBeVisible();

    // Save
    await page.getByRole("button", { name: /^save$/i }).click();

    // Wait for save to complete - dirty indicator disappears when save finishes
    await expect(page.getByText("*")).not.toBeVisible({ timeout: 30000 });
  });

  test("deletes node via inspector", async ({ page }) => {
    const graphName = createGraphName("Delete Node Test");

    await page.getByRole("button", { name: /^new graph$/i }).click();
    await page.locator("#create-graph-name").fill(graphName);
    await page.getByRole("dialog").getByRole("button", { name: /^create$/i }).click();

    await expectGraphEditorOpen(page);

    // Add a node
    await addPromptNodeViaWizard(page);
    await expect(page.getByText("Prompt Node")).toBeVisible();

    // Select and delete
    await page.getByText("Prompt Node").click();
    await page.getByRole("button", { name: /^delete$/i }).click();

    // Node should be removed
    await expect(page.getByText("Prompt Node")).not.toBeVisible();

    // Inspector should show graph info again
    await expect(page.getByText("Graph Info")).toBeVisible();
  });

  test("edits graph name and description", async ({ page }) => {
    const graphName = createGraphName("Edit Metadata Test");
    const originalDescription = "Original description";

    await page.getByRole("button", { name: /^new graph$/i }).click();
    await page.locator("#create-graph-name").fill(graphName);
    await page.locator("#create-graph-description").fill(originalDescription);
    await page.getByRole("dialog").getByRole("button", { name: /^create$/i }).click();

    await expectGraphEditorOpen(page);

    // Click Edit Info
    await page.getByRole("button", { name: /edit info/i }).click();

    // Update name and description
    const nameInput = page.locator("#edit-graph-name");
    await nameInput.fill("Updated Graph Name");

    const descInput = page.locator("#edit-graph-description");
    await descInput.fill("Updated description");

    // Save changes
    await page.getByRole("button", { name: /^save$/i }).click();

    // Should show updated values
    await expect(
      page.getByRole("heading", { name: "Updated Graph Name", exact: true }),
    ).toBeVisible();
    await expect(page.getByText("Updated description")).toBeVisible();

    // Should show success toast
    await expect(page.getByText(/graph info updated/i)).toBeVisible();
  });

  test("cancels graph metadata edit", async ({ page }) => {
    const graphName = createGraphName("Cancel Edit Test");

    await page.getByRole("button", { name: /^new graph$/i }).click();
    await page.locator("#create-graph-name").fill(graphName);
    await page.getByRole("dialog").getByRole("button", { name: /^create$/i }).click();

    await expectGraphEditorOpen(page);

    // Click Edit Info
    await page.getByRole("button", { name: /edit info/i }).click();

    // Make changes
    const nameInput = page.locator("#edit-graph-name");
    await nameInput.fill("Should Not Save");

    // Cancel
    await page.getByRole("button", { name: /^cancel$/i }).click();

    // Should show original name
    await expect(
      page.getByRole("heading", { name: graphName, exact: true }),
    ).toBeVisible();
    await expect(page.getByText("Should Not Save")).not.toBeVisible();
  });

  test("reloads graph and preserves node configuration", async ({ page }) => {
    const graphName = createGraphName("Reload Test");

    await page.getByRole("button", { name: /^new graph$/i }).click();
    await page.locator("#create-graph-name").fill(graphName);
    await page.getByRole("dialog").getByRole("button", { name: /^create$/i }).click();

    await expectGraphEditorOpen(page);

    // Add and configure nodes - need output node for valid save
    await addPromptNodeViaWizard(page);
    await page.getByText("Prompt Node").click();

    const promptIdInput = page.getByPlaceholder(/select or enter prompt id/i);
    await promptIdInput.fill("saved-prompt-id");

    await addNodeViaConfigDialog(page, {
      buttonLabel: /^output$/i,
      dialogLabel: /configure output node/i,
      nodeLabel: "Output",
    });

    // Save the graph
    await page.getByRole("button", { name: /^save$/i }).click();
    // Wait for version dropdown to be enabled (indicates save completed)
    const versionSelect = page.getByRole("combobox", { name: /^version$/i });
    await expect(versionSelect).toBeEnabled({ timeout: 30000 });

    // Get current URL
    const url = page.url();

    // Navigate away and back
    await page.goto("/graphs");
    await expect(page.getByRole("heading", { name: /^graphs$/i })).toBeVisible();
    await page.goto(url);

    await expect(page.getByText("Add Nodes")).toBeVisible();

    // Node and config should be preserved
    await expect(page.getByText("Prompt Node")).toBeVisible();
    await expect(page.getByText(/prompt: saved-prompt-id/i)).toBeVisible();
  });

  test("navigates back to graphs list", async ({ page }) => {
    const graphName = createGraphName("Back Navigation Test");

    await page.getByRole("button", { name: /^new graph$/i }).click();
    await page.locator("#create-graph-name").fill(graphName);
    await page.getByRole("dialog").getByRole("button", { name: /^create$/i }).click();

    await expectGraphEditorOpen(page);

    // Click back button
    await page.getByRole("link", { name: /← back/i }).click();

    // Should navigate to graphs list
    await expect(page).toHaveURL(/\/graphs$/);
    await expect(page.getByRole("heading", { name: /^graphs$/i })).toBeVisible();
  });

  test("shows keyboard shortcuts in palette", async ({ page }) => {
    const graphName = createGraphName("Shortcuts Test");

    await page.getByRole("button", { name: /^new graph$/i }).click();
    await page.locator("#create-graph-name").fill(graphName);
    await page.getByRole("dialog").getByRole("button", { name: /^create$/i }).click();

    await expectGraphEditorOpen(page);

    // Check for keyboard shortcuts section
    await expect(page.getByText("Keyboard Shortcuts")).toBeVisible();
    await expect(page.getByText("Save")).toBeVisible();
    await expect(page.getByText("Ctrl+S", { exact: true })).toBeVisible();
    await expect(page.getByText("Delete node")).toBeVisible();
    await expect(page.getByText("Delete", { exact: true })).toBeVisible();
  });

  test("handles empty graph (no nodes)", async ({ page }) => {
    const graphName = createGraphName("Empty Graph Test");

    await page.getByRole("button", { name: /^new graph$/i }).click();
    const createDialog = page.getByRole("dialog");
    await createDialog.waitFor({ state: "visible" });
    await createDialog.locator("#create-graph-name").fill(graphName);
    await createDialog.getByRole("button", { name: /^create$/i }).click();

    await expectGraphEditorOpen(page);

    const versionSelect = page.getByRole("combobox", { name: /^version$/i });
    await expect(versionSelect).toBeDisabled();
    await expect
      .poll(async () => {
        return versionSelect.evaluate((el: HTMLSelectElement) => {
          return el.options[el.selectedIndex]?.textContent ?? "";
        });
      })
      .toMatch(/no version/i);

    // Save button should be disabled (no changes)
    const saveButton = page.getByRole("button", { name: /^save$/i });
    await expect(saveButton).toBeDisabled();
  });

  test("creates a simple workflow with connected nodes", async ({ page, request }) => {
    const graphName = createGraphName("Workflow Test");

    await page.getByRole("button", { name: /^new graph$/i }).click();
    await page.locator("#create-graph-name").fill(graphName);
    await page.getByRole("dialog").getByRole("button", { name: /^create$/i }).click();

    await expectGraphEditorOpen(page);

    // Add nodes in sequence (quick-add will connect to the selected node)
    await addPromptNodeViaWizard(page);
    await page.getByPlaceholder(/select or enter prompt id/i).fill("workflow-prompt");
    await expect(page.getByText(/prompt: workflow-prompt/i)).toBeVisible();

    await addNodeViaConfigDialog(page, {
      buttonLabel: /^http/i,
      dialogLabel: /configure http node/i,
      nodeLabel: "HTTP",
    });
    const httpConfigSection = page
      .getByRole("heading", { name: /^http configuration$/i })
      .locator("..");
    await httpConfigSection.locator("select").selectOption("POST");
    await page.getByPlaceholder(/https:\/\/api\.example\.com/i).fill("https://api.test.com/endpoint");
    await expect(page.getByText(/POST https:\/\/api\.test\.com/i)).toBeVisible();

    await addNodeViaConfigDialog(page, {
      buttonLabel: /^transform/i,
      dialogLabel: /configure transform node/i,
      nodeLabel: "Transform",
    });
    await page.getByPlaceholder(/state\.input \| uppercase/i).fill("state.data | lowercase");
    await expect(page.getByText(/state\.data \| lowercase\.\.\./i)).toBeVisible();

    await addNodeViaConfigDialog(page, {
      buttonLabel: /^output/i,
      dialogLabel: /configure output node/i,
      nodeLabel: "Output",
    });
    // Output node uses KeyValueEditor - add an output mapping
    await page.getByRole("button", { name: /add output key/i }).click();
    await page.getByPlaceholder(/output key/i).fill("result");
    await page.getByPlaceholder(/state path/i).fill("state.final_output");

    // All nodes should be visible on the canvas
    const canvasNodes = page.locator(".react-flow__node");
    await expect(canvasNodes.filter({ hasText: "Prompt Node" }).first()).toBeVisible();
    await expect(canvasNodes.filter({ hasText: "HTTP" }).first()).toBeVisible();
    await expect(canvasNodes.filter({ hasText: "Transform" }).first()).toBeVisible();
    await expect(canvasNodes.filter({ hasText: "Output" }).first()).toBeVisible();

    // Save the workflow
    await page.getByRole("button", { name: /^save$/i }).click();
    await expect(page.getByText(/saved as version 1/i)).toBeVisible();

    // Verify the persisted graph contains edges (ReactFlow rendering is flaky in WebKit)
    const graphId = page.url().match(/\/graphs\/([a-f0-9-]+)/)?.[1];
    expect(graphId).toBeTruthy();

    const accessToken = await getAccessToken(request, seededUser);
    const latestVersionResponse = await request.get(
      `${API_BASE_URL}/api/graphs/${graphId}/versions/latest`,
      {
        headers: { Authorization: `Bearer ${accessToken}` },
      },
    );
    expect(latestVersionResponse.ok()).toBeTruthy();
    const latestVersion = (await latestVersionResponse.json()) as {
      data?: { graph_json?: { edges?: unknown[] } };
    };
    const savedEdges = latestVersion.data?.graph_json?.edges ?? [];
    const workflowEdges = savedEdges.filter((edge) => {
      if (!edge || typeof edge !== "object") return false;
      const typed = edge as { from?: string; to?: string };
      return typed.from !== "START" && typed.to !== "END";
    });
    const startEdges = savedEdges.filter((edge) => {
      if (!edge || typeof edge !== "object") return false;
      return (edge as { from?: string }).from === "START";
    });
    const endEdges = savedEdges.filter((edge) => {
      if (!edge || typeof edge !== "object") return false;
      return (edge as { to?: string }).to === "END";
    });

    expect(workflowEdges.length).toBe(3);
    expect(startEdges.length).toBeGreaterThanOrEqual(1);
    expect(endEdges.length).toBeGreaterThanOrEqual(1);

    // Reload and verify nodes/edges still render
    const url = page.url();
    await page.goto("/graphs");
    await expect(page.getByRole("heading", { name: /^graphs$/i })).toBeVisible();
    await page.goto(url);

    await expect(page.getByText("Add Nodes")).toBeVisible();
    // Check nodes are visible on the canvas (reuse canvasNodes locator)
    await expect(canvasNodes.filter({ hasText: "Prompt Node" }).first()).toBeVisible();
    await expect(canvasNodes.filter({ hasText: "HTTP" }).first()).toBeVisible();
    await expect(canvasNodes.filter({ hasText: "Transform" }).first()).toBeVisible();
    await expect(canvasNodes.filter({ hasText: "Output" }).first()).toBeVisible();

    await expect(page.getByText(/prompt: workflow-prompt/i)).toBeVisible();
    await expect(page.getByText(/POST https:\/\/api\.test\.com/i)).toBeVisible();
    await expect(page.getByText(/state\.data \| lowercase\.\.\./i)).toBeVisible();
  });

  test("loads older versions from the dropdown", async ({ page }) => {
    const graphName = createGraphName("Version Switch Test");

    await page.getByRole("button", { name: /^new graph$/i }).click();
    await page.locator("#create-graph-name").fill(graphName);
    await page.getByRole("dialog").getByRole("button", { name: /^create$/i }).click();

    await expectGraphEditorOpen(page);

    const versionSelect = page.getByRole("combobox", { name: /^version$/i });

    // Create v1 - need output node for valid save
    await addPromptNodeViaWizard(page);
    await page.getByText("Prompt Node").click();
    await page.getByPlaceholder(/select or enter prompt id/i).fill("v1-prompt");
    await addNodeViaConfigDialog(page, {
      buttonLabel: /^output$/i,
      dialogLabel: /configure output node/i,
      nodeLabel: "Output",
    });
    await page.getByRole("button", { name: /^save$/i }).click();
    await expect(versionSelect).toBeEnabled({ timeout: 30000 });

    const versionIds = await versionSelect.evaluate((el: HTMLSelectElement) => {
      const byText = (text: string) => Array.from(el.options).find((o) => o.textContent === text)?.value ?? "";
      return { v1: byText("v1"), v2: byText("v2") };
    });

    // Create v2
    await page.locator(".react-flow__node").filter({ hasText: "Prompt Node" }).first().click();
    await page.getByPlaceholder(/select or enter prompt id/i).fill("v2-prompt");
    await page.getByRole("button", { name: /^save$/i }).click();
    // Wait for v2 to appear in dropdown
    await expect.poll(async () => {
      return versionSelect.evaluate((el: HTMLSelectElement) => {
        return Array.from(el.options).some((o) => o.textContent === "v2");
      });
    }, { timeout: 30000 }).toBe(true);

    const versionIdsAfterV2 = await versionSelect.evaluate((el: HTMLSelectElement) => {
      const byText = (text: string) => Array.from(el.options).find((o) => o.textContent === text)?.value ?? "";
      return { v1: byText("v1"), v2: byText("v2") };
    });

    expect(versionIdsAfterV2.v1).not.toBe("");
    expect(versionIdsAfterV2.v2).not.toBe("");

    // Make an unsaved change so switching prompts
    await page.locator(".react-flow__node").filter({ hasText: "Prompt Node" }).first().click();
    await page.getByPlaceholder(/select or enter prompt id/i).fill("unsaved-change");
    await expect(page.getByText("*")).toBeVisible();

    page.once("dialog", async (dialog) => {
      expect(dialog.type()).toBe("confirm");
      await dialog.accept();
    });

    await versionSelect.selectOption(versionIdsAfterV2.v1);

    await expect(page.getByText(/prompt: v1-prompt/i)).toBeVisible();
    await expect(page.getByText("*")).not.toBeVisible();

    // Saving after loading older version creates a new version (no overwrite)
    await page.locator(".react-flow__node").filter({ hasText: "Prompt Node" }).first().click();
    await page.getByPlaceholder(/select or enter prompt id/i).fill("v3-prompt");
    await page.getByRole("button", { name: /^save$/i }).click();
    // Wait for v3 to appear in dropdown
    await expect.poll(async () => {
      return versionSelect.evaluate((el: HTMLSelectElement) => {
        return Array.from(el.options).some((o) => o.textContent === "v3");
      });
    }, { timeout: 30000 }).toBe(true);
  });
});
