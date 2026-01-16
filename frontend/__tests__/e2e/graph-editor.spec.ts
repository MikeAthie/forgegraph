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

import { test, expect } from "@playwright/test";
import { createTestUser, ensureUserRegistered, login, type TestUser } from "./helpers";

let seededUser: TestUser;

const createGraphName = (prefix: string) =>
  `${prefix} ${Date.now()}-${Math.random().toString(16).slice(2)}`;

test.beforeAll(async ({ request }, testInfo) => {
  seededUser = createTestUser(testInfo, "e2e-graph-editor");
  await ensureUserRegistered(request, seededUser);
});

test.describe("Graph Editor", () => {
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
    await expect(page).toHaveURL(/\/graphs\/[a-f0-9-]+/);

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

    await expect(page).toHaveURL(/\/graphs\/[a-f0-9-]+/);

    // Check enabled node types
    await expect(page.getByRole("button", { name: /^prompt/i })).toBeEnabled();
    await expect(page.getByRole("button", { name: /^http/i })).toBeEnabled();
    await expect(page.getByRole("button", { name: /^transform/i })).toBeEnabled();
    await expect(page.getByRole("button", { name: /^output/i })).toBeEnabled();

    // Check disabled node types (Phase 5 and 6)
    await expect(page.getByRole("button", { name: /^branch/i })).toBeDisabled();
    await expect(page.getByRole("button", { name: /^merge/i })).toBeDisabled();
    await expect(page.getByRole("button", { name: /^human gate/i })).toBeDisabled();
  });

  test("adds a node from palette", async ({ page }) => {
    const graphName = createGraphName("Add Node Test");

    // Create and open graph
    await page.getByRole("button", { name: /^new graph$/i }).click();
    await page.locator("#create-graph-name").fill(graphName);
    await page.getByRole("dialog").getByRole("button", { name: /^create$/i }).click();

    await expect(page).toHaveURL(/\/graphs\/[a-f0-9-]+/);

    // Add a Prompt node
    await page.getByRole("button", { name: /^prompt/i }).click();

    // Node should appear in the canvas
    await expect(page.getByText("Prompt Node")).toBeVisible();
  });

  test("adds multiple nodes of different types", async ({ page }) => {
    const graphName = createGraphName("Multiple Nodes Test");

    await page.getByRole("button", { name: /^new graph$/i }).click();
    await page.locator("#create-graph-name").fill(graphName);
    await page.getByRole("dialog").getByRole("button", { name: /^create$/i }).click();

    await expect(page).toHaveURL(/\/graphs\/[a-f0-9-]+/);

    // Add different node types
    await page.getByRole("button", { name: /^prompt/i }).click();
    await expect(page.getByText("Prompt Node")).toBeVisible();

    await page.getByRole("button", { name: /^http/i }).click();
    await expect(page.getByText("HTTP Node")).toBeVisible();

    await page.getByRole("button", { name: /^transform/i }).click();
    await expect(page.getByText("Transform Node")).toBeVisible();

    await page.getByRole("button", { name: /^output/i }).click();
    await expect(page.getByText("Output Node")).toBeVisible();
  });

  test("shows graph info in inspector when no node is selected", async ({ page }) => {
    const graphName = createGraphName("Inspector Info");
    const description = "Test graph description";

    await page.getByRole("button", { name: /^new graph$/i }).click();
    await page.locator("#create-graph-name").fill(graphName);
    await page.locator("#create-graph-description").fill(description);
    await page.getByRole("dialog").getByRole("button", { name: /^create$/i }).click();

    await expect(page).toHaveURL(/\/graphs\/[a-f0-9-]+/);

    // Inspector should show graph info
    await expect(page.getByRole("heading", { name: /^graph info$/i })).toBeVisible();
    await expect(page.getByText(graphName)).toBeVisible();
    await expect(page.getByText(description)).toBeVisible();
  });

  test("selects node and shows configuration in inspector", async ({ page }) => {
    const graphName = createGraphName("Node Config Test");

    await page.getByRole("button", { name: /^new graph$/i }).click();
    await page.locator("#create-graph-name").fill(graphName);
    await page.getByRole("dialog").getByRole("button", { name: /^create$/i }).click();

    await expect(page).toHaveURL(/\/graphs\/[a-f0-9-]+/);

    // Add a node
    await page.getByRole("button", { name: /^prompt/i }).click();

    // Click on the node to select it
    await page.getByText("Prompt Node").click();

    // Inspector should show node config
    await expect(page.getByText("Node Config")).toBeVisible();
    await expect(page.getByText("prompt", { exact: true })).toBeVisible(); // Type badge
    await expect(page.getByRole("button", { name: /delete/i })).toBeVisible();
  });

  test("updates node name via inspector", async ({ page }) => {
    const graphName = createGraphName("Update Node Name");

    await page.getByRole("button", { name: /^new graph$/i }).click();
    await page.locator("#create-graph-name").fill(graphName);
    await page.getByRole("dialog").getByRole("button", { name: /^create$/i }).click();

    await expect(page).toHaveURL(/\/graphs\/[a-f0-9-]+/);

    // Add a node and select it
    await page.getByRole("button", { name: /^prompt/i }).click();
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

    await expect(page).toHaveURL(/\/graphs\/[a-f0-9-]+/);

    // Add and select prompt node
    await page.getByRole("button", { name: /^prompt/i }).click();
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

    await expect(page).toHaveURL(/\/graphs\/[a-f0-9-]+/);

    // Add and select HTTP node
    await page.getByRole("button", { name: /^http/i }).click();
    await page.getByText("HTTP Node").click();

    // Configure HTTP settings
    await expect(page.getByText("HTTP Configuration")).toBeVisible();

    const methodSelect = page.locator("select").first();
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

    await expect(page).toHaveURL(/\/graphs\/[a-f0-9-]+/);

    // Add and select Transform node
    await page.getByRole("button", { name: /^transform/i }).click();
    await page.getByText("Transform Node").click();

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

    await expect(page).toHaveURL(/\/graphs\/[a-f0-9-]+/);

    // Add a node to make the graph dirty
    await page.getByRole("button", { name: /^prompt/i }).click();

    // Save button should be enabled
    const saveButton = page.getByRole("button", { name: /^save$/i });
    await expect(saveButton).toBeEnabled();

    // Click save
    await saveButton.click();

    // Should show saving state and then success
    await expect(page.getByRole("button", { name: /saving\.\.\./i })).toBeVisible();

    // Should show version number
    await expect(page.getByText(/v1/)).toBeVisible();

    // Should show success toast
    await expect(page.getByText(/saved as version/i)).toBeVisible();
  });

  test("shows dirty indicator when graph has unsaved changes", async ({ page }) => {
    const graphName = createGraphName("Dirty State Test");

    await page.getByRole("button", { name: /^new graph$/i }).click();
    await page.locator("#create-graph-name").fill(graphName);
    await page.getByRole("dialog").getByRole("button", { name: /^create$/i }).click();

    await expect(page).toHaveURL(/\/graphs\/[a-f0-9-]+/);

    // Initially no dirty indicator
    await expect(page.getByText("*")).not.toBeVisible();

    // Add a node
    await page.getByRole("button", { name: /^prompt/i }).click();

    // Should show dirty indicator (asterisk)
    await expect(page.getByText("*")).toBeVisible();

    // Save
    await page.getByRole("button", { name: /^save$/i }).click();

    // Wait for save to complete
    await expect(page.getByText(/saved as version/i)).toBeVisible();

    // Dirty indicator should be gone
    await expect(page.getByText("*")).not.toBeVisible();
  });

  test("deletes node via inspector", async ({ page }) => {
    const graphName = createGraphName("Delete Node Test");

    await page.getByRole("button", { name: /^new graph$/i }).click();
    await page.locator("#create-graph-name").fill(graphName);
    await page.getByRole("dialog").getByRole("button", { name: /^create$/i }).click();

    await expect(page).toHaveURL(/\/graphs\/[a-f0-9-]+/);

    // Add a node
    await page.getByRole("button", { name: /^prompt/i }).click();
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

    await expect(page).toHaveURL(/\/graphs\/[a-f0-9-]+/);

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
    await expect(page.getByText("Updated Graph Name")).toBeVisible();
    await expect(page.getByText("Updated description")).toBeVisible();

    // Should show success toast
    await expect(page.getByText(/graph info updated/i)).toBeVisible();
  });

  test("cancels graph metadata edit", async ({ page }) => {
    const graphName = createGraphName("Cancel Edit Test");

    await page.getByRole("button", { name: /^new graph$/i }).click();
    await page.locator("#create-graph-name").fill(graphName);
    await page.getByRole("dialog").getByRole("button", { name: /^create$/i }).click();

    await expect(page).toHaveURL(/\/graphs\/[a-f0-9-]+/);

    // Click Edit Info
    await page.getByRole("button", { name: /edit info/i }).click();

    // Make changes
    const nameInput = page.locator("#edit-graph-name");
    await nameInput.fill("Should Not Save");

    // Cancel
    await page.getByRole("button", { name: /^cancel$/i }).click();

    // Should show original name
    await expect(page.getByText(graphName)).toBeVisible();
    await expect(page.getByText("Should Not Save")).not.toBeVisible();
  });

  test("reloads graph and preserves node configuration", async ({ page }) => {
    const graphName = createGraphName("Reload Test");

    await page.getByRole("button", { name: /^new graph$/i }).click();
    await page.locator("#create-graph-name").fill(graphName);
    await page.getByRole("dialog").getByRole("button", { name: /^create$/i }).click();

    await expect(page).toHaveURL(/\/graphs\/[a-f0-9-]+/);

    // Add and configure a node
    await page.getByRole("button", { name: /^prompt/i }).click();
    await page.getByText("Prompt Node").click();

    const promptIdInput = page.getByPlaceholder(/select or enter prompt id/i);
    await promptIdInput.fill("saved-prompt-id");

    // Save the graph
    await page.getByRole("button", { name: /^save$/i }).click();
    await expect(page.getByText(/saved as version/i)).toBeVisible();

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

    await expect(page).toHaveURL(/\/graphs\/[a-f0-9-]+/);

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

    await expect(page).toHaveURL(/\/graphs\/[a-f0-9-]+/);

    // Check for keyboard shortcuts section
    await expect(page.getByText("Keyboard Shortcuts")).toBeVisible();
    await expect(page.getByText("Save")).toBeVisible();
    await expect(page.getByText("Ctrl+S")).toBeVisible();
    await expect(page.getByText("Delete node")).toBeVisible();
    await expect(page.getByText("Delete", { exact: true })).toBeVisible();
  });

  test("handles empty graph (no nodes)", async ({ page }) => {
    const graphName = createGraphName("Empty Graph Test");

    await page.getByRole("button", { name: /^new graph$/i }).click();
    await page.locator("#create-graph-name").fill(graphName);
    await page.getByRole("dialog").getByRole("button", { name: /^create$/i }).click();

    await expect(page).toHaveURL(/\/graphs\/[a-f0-9-]+/);

    // Should show no version initially
    await expect(page.getByText("No version")).toBeVisible();

    // Save button should be disabled (no changes)
    const saveButton = page.getByRole("button", { name: /^save$/i });
    await expect(saveButton).toBeDisabled();
  });

  test("creates a simple workflow with connected nodes", async ({ page }) => {
    const graphName = createGraphName("Workflow Test");

    await page.getByRole("button", { name: /^new graph$/i }).click();
    await page.locator("#create-graph-name").fill(graphName);
    await page.getByRole("dialog").getByRole("button", { name: /^create$/i }).click();

    await expect(page).toHaveURL(/\/graphs\/[a-f0-9-]+/);

    // Add nodes in sequence
    await page.getByRole("button", { name: /^prompt/i }).click();
    await page.getByRole("button", { name: /^http/i }).click();
    await page.getByRole("button", { name: /^transform/i }).click();
    await page.getByRole("button", { name: /^output/i }).click();

    // All nodes should be visible
    await expect(page.getByText("Prompt Node")).toBeVisible();
    await expect(page.getByText("HTTP Node")).toBeVisible();
    await expect(page.getByText("Transform Node")).toBeVisible();
    await expect(page.getByText("Output Node")).toBeVisible();

    // Save the workflow
    await page.getByRole("button", { name: /^save$/i }).click();
    await expect(page.getByText(/saved as version 1/i)).toBeVisible();
  });
});
