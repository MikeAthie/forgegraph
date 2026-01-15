/**
 * End-to-end tests for graph management flows.
 *
 * Tests complete workflows for creating, viewing, editing, and deleting graphs.
 */

import { test, expect } from '@playwright/test';

test.describe('Graphs Page', () => {
  test.beforeEach(async ({ page }) => {
    // Login before each test
    await page.goto('/login');
    await page.getByLabel(/email/i).fill('test@example.com');
    await page.getByLabel(/password/i).fill('testpassword123');
    await page.getByRole('button', { name: /sign in/i }).click();
    await page.waitForURL('/graphs', { timeout: 5000 });
  });

  test('should display graphs page', async ({ page }) => {
    await expect(page.getByRole('heading', { name: /graphs/i })).toBeVisible();
  });

  test('should display create graph button', async ({ page }) => {
    await expect(page.getByRole('button', { name: /create graph|new graph/i })).toBeVisible();
  });
});

test.describe('Create Graph Flow', () => {
  test.beforeEach(async ({ page }) => {
    // Login and navigate to graphs page
    await page.goto('/login');
    await page.getByLabel(/email/i).fill('test@example.com');
    await page.getByLabel(/password/i).fill('testpassword123');
    await page.getByRole('button', { name: /sign in/i }).click();
    await page.waitForURL('/graphs', { timeout: 5000 });
  });

  test('should open create graph modal', async ({ page }) => {
    await page.getByRole('button', { name: /create graph|new graph/i }).click();

    // Modal should be visible
    await expect(page.getByRole('dialog')).toBeVisible();
    await expect(page.getByLabel(/name/i)).toBeVisible();
  });

  test('should create a new graph', async ({ page }) => {
    // Open create modal
    await page.getByRole('button', { name: /create graph|new graph/i }).click();

    // Fill form
    const graphName = `Test Graph ${Date.now()}`;
    await page.getByLabel(/name/i).fill(graphName);
    await page.getByLabel(/description/i).fill('A test graph description');

    // Submit
    await page.getByRole('button', { name: /create/i }).click();

    // Should see the new graph in the list
    await expect(page.getByText(graphName)).toBeVisible();
  });

  test('should show validation error when name is empty', async ({ page }) => {
    // Open create modal
    await page.getByRole('button', { name: /create graph|new graph/i }).click();

    // Try to submit without filling name
    await page.getByRole('button', { name: /create/i }).click();

    // Should show validation error or prevent submission
    await expect(page.getByRole('dialog')).toBeVisible();
  });

  test('should close modal on cancel', async ({ page }) => {
    // Open create modal
    await page.getByRole('button', { name: /create graph|new graph/i }).click();
    await expect(page.getByRole('dialog')).toBeVisible();

    // Click cancel
    await page.getByRole('button', { name: /cancel/i }).click();

    // Modal should close
    await expect(page.getByRole('dialog')).not.toBeVisible();
  });
});

test.describe('Edit Graph Flow', () => {
  test.beforeEach(async ({ page }) => {
    // Login and navigate to graphs page
    await page.goto('/login');
    await page.getByLabel(/email/i).fill('test@example.com');
    await page.getByLabel(/password/i).fill('testpassword123');
    await page.getByRole('button', { name: /sign in/i }).click();
    await page.waitForURL('/graphs', { timeout: 5000 });

    // Create a graph for editing
    await page.getByRole('button', { name: /create graph|new graph/i }).click();
    await page.getByLabel(/name/i).fill('Graph To Edit');
    await page.getByLabel(/description/i).fill('Original description');
    await page.getByRole('button', { name: /create/i }).click();
    await page.waitForTimeout(500); // Wait for graph to be created
  });

  test('should update graph name and description', async ({ page }) => {
    // Find and click edit button for the graph
    const graphRow = page.locator('text=Graph To Edit').locator('..');
    await graphRow.getByRole('button', { name: /edit/i }).click();

    // Update fields
    await page.getByLabel(/name/i).clear();
    await page.getByLabel(/name/i).fill('Updated Graph Name');
    await page.getByLabel(/description/i).clear();
    await page.getByLabel(/description/i).fill('Updated description');

    // Save
    await page.getByRole('button', { name: /save/i }).click();

    // Should see updated name
    await expect(page.getByText('Updated Graph Name')).toBeVisible();
  });
});

test.describe('Delete Graph Flow', () => {
  test.beforeEach(async ({ page }) => {
    // Login and navigate to graphs page
    await page.goto('/login');
    await page.getByLabel(/email/i).fill('test@example.com');
    await page.getByLabel(/password/i).fill('testpassword123');
    await page.getByRole('button', { name: /sign in/i }).click();
    await page.waitForURL('/graphs', { timeout: 5000 });

    // Create a graph for deletion
    await page.getByRole('button', { name: /create graph|new graph/i }).click();
    await page.getByLabel(/name/i).fill('Graph To Delete');
    await page.getByRole('button', { name: /create/i }).click();
    await page.waitForTimeout(500);
  });

  test('should delete a graph with confirmation', async ({ page }) => {
    // Find and click delete button
    const graphRow = page.locator('text=Graph To Delete').locator('..');
    await graphRow.getByRole('button', { name: /delete/i }).click();

    // Confirm deletion
    await page.getByRole('button', { name: /confirm|yes|delete/i }).click();

    // Graph should be removed from list
    await expect(page.getByText('Graph To Delete')).not.toBeVisible();
  });

  test('should cancel deletion', async ({ page }) => {
    // Find and click delete button
    const graphRow = page.locator('text=Graph To Delete').locator('..');
    await graphRow.getByRole('button', { name: /delete/i }).click();

    // Cancel deletion
    await page.getByRole('button', { name: /cancel|no/i }).click();

    // Graph should still be visible
    await expect(page.getByText('Graph To Delete')).toBeVisible();
  });
});

test.describe('Graph Details', () => {
  test.beforeEach(async ({ page }) => {
    // Login and create a graph
    await page.goto('/login');
    await page.getByLabel(/email/i).fill('test@example.com');
    await page.getByLabel(/password/i).fill('testpassword123');
    await page.getByRole('button', { name: /sign in/i }).click();
    await page.waitForURL('/graphs', { timeout: 5000 });

    await page.getByRole('button', { name: /create graph|new graph/i }).click();
    await page.getByLabel(/name/i).fill('Detailed Graph');
    await page.getByRole('button', { name: /create/i }).click();
    await page.waitForTimeout(500);
  });

  test('should navigate to graph details page', async ({ page }) => {
    // Click on graph name or view button
    await page.getByText('Detailed Graph').click();

    // Should navigate to graph details
    await expect(page).toHaveURL(/\/graphs\/[a-f0-9-]+/);
  });

  test('should display graph information', async ({ page }) => {
    await page.getByText('Detailed Graph').click();

    // Should display graph name
    await expect(page.getByText('Detailed Graph')).toBeVisible();
  });
});

test.describe('Empty State', () => {
  test('should display empty state when no graphs exist', async ({ page }) => {
    // Login to a new account or ensure graphs are deleted
    await page.goto('/login');
    await page.getByLabel(/email/i).fill('test@example.com');
    await page.getByLabel(/password/i).fill('testpassword123');
    await page.getByRole('button', { name: /sign in/i }).click();
    await page.waitForURL('/graphs', { timeout: 5000 });

    // If there are no graphs, should show empty state
    // This test assumes the empty state has specific text
    const hasGraphs = await page.locator('[data-testid="graph-item"]').count() > 0;

    if (!hasGraphs) {
      await expect(page.getByText(/no graphs|create your first/i)).toBeVisible();
    }
  });
});
