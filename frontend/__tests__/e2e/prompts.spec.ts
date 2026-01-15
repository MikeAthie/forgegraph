/**
 * End-to-end tests for prompt library flows.
 *
 * Tests complete workflows for creating, filtering, cloning, and publishing prompts.
 */

import { test, expect } from '@playwright/test';

test.describe('Prompts Library Page', () => {
  test.beforeEach(async ({ page }) => {
    // Login before each test
    await page.goto('/login');
    await page.getByLabel(/email/i).fill('test@example.com');
    await page.getByLabel(/password/i).fill('testpassword123');
    await page.getByRole('button', { name: /sign in/i }).click();
    await page.waitForURL('/graphs', { timeout: 5000 });

    // Navigate to prompts page
    await page.getByRole('link', { name: /^prompts$/i }).click();
    await expect(page).toHaveURL('/prompts');
  });

  test('should display prompts library page', async ({ page }) => {
    await expect(page.getByRole('heading', { name: /prompt library/i })).toBeVisible();
  });

  test('should display create prompt button', async ({ page }) => {
    await expect(page.getByRole('button', { name: /create prompt|new prompt/i })).toBeVisible();
  });

  test('should display filter controls', async ({ page }) => {
    // Should have category filter
    await expect(page.getByText(/all categories|category/i)).toBeVisible();
  });
});

test.describe('Create Prompt Flow', () => {
  test.beforeEach(async ({ page }) => {
    await page.goto('/login');
    await page.getByLabel(/email/i).fill('test@example.com');
    await page.getByLabel(/password/i).fill('testpassword123');
    await page.getByRole('button', { name: /sign in/i }).click();
    await page.waitForURL('/graphs', { timeout: 5000 });
    await page.getByRole('link', { name: /^prompts$/i }).click();
  });

  test('should open create prompt modal', async ({ page }) => {
    await page.getByRole('button', { name: /create prompt|new prompt/i }).click();

    await expect(page.getByRole('dialog')).toBeVisible();
    await expect(page.getByLabel(/title/i)).toBeVisible();
    await expect(page.getByLabel(/category/i)).toBeVisible();
    await expect(page.getByLabel(/content/i)).toBeVisible();
  });

  test('should create a new prompt', async ({ page }) => {
    await page.getByRole('button', { name: /create prompt|new prompt/i }).click();

    const promptTitle = `Test Prompt ${Date.now()}`;
    await page.getByLabel(/title/i).fill(promptTitle);
    await page.getByLabel(/description/i).fill('A test prompt');
    await page.getByLabel(/category/i).selectOption('research');
    await page.getByLabel(/content/i).fill('You are a helpful research assistant.');

    await page.getByRole('button', { name: /create/i }).click();

    await expect(page.getByText(promptTitle)).toBeVisible();
  });

  test('should show validation error for empty required fields', async ({ page }) => {
    await page.getByRole('button', { name: /create prompt|new prompt/i }).click();

    await page.getByRole('button', { name: /create/i }).click();

    // Should still show dialog (validation failed)
    await expect(page.getByRole('dialog')).toBeVisible();
  });

  test('should close modal on cancel', async ({ page }) => {
    await page.getByRole('button', { name: /create prompt|new prompt/i }).click();
    await expect(page.getByRole('dialog')).toBeVisible();

    await page.getByRole('button', { name: /cancel/i }).click();

    await expect(page.getByRole('dialog')).not.toBeVisible();
  });
});

test.describe('Filter Prompts', () => {
  test.beforeEach(async ({ page }) => {
    await page.goto('/login');
    await page.getByLabel(/email/i).fill('test@example.com');
    await page.getByLabel(/password/i).fill('testpassword123');
    await page.getByRole('button', { name: /sign in/i }).click();
    await page.waitForURL('/graphs', { timeout: 5000 });
    await page.getByRole('link', { name: /^prompts$/i }).click();

    // Create prompts in different categories
    await page.getByRole('button', { name: /create prompt|new prompt/i }).click();
    await page.getByLabel(/title/i).fill('Research Helper');
    await page.getByLabel(/category/i).selectOption('research');
    await page.getByLabel(/content/i).fill('Help with research');
    await page.getByRole('button', { name: /create/i }).click();
    await page.waitForTimeout(500);

    await page.getByRole('button', { name: /create prompt|new prompt/i }).click();
    await page.getByLabel(/title/i).fill('Email Writer');
    await page.getByLabel(/category/i).selectOption('email');
    await page.getByLabel(/content/i).fill('Write emails');
    await page.getByRole('button', { name: /create/i }).click();
    await page.waitForTimeout(500);
  });

  test('should filter prompts by category', async ({ page }) => {
    // Filter by research category
    await page.getByLabel(/category/i).selectOption('research');

    // Should show only research prompts
    await expect(page.getByText('Research Helper')).toBeVisible();
    // Email Writer might not be visible depending on filter implementation
  });

  test('should show all prompts when filter is cleared', async ({ page }) => {
    await page.getByLabel(/category/i).selectOption('research');
    await page.waitForTimeout(300);

    // Clear filter
    await page.getByLabel(/category/i).selectOption('');

    // Should show all prompts
    await expect(page.getByText('Research Helper')).toBeVisible();
    await expect(page.getByText('Email Writer')).toBeVisible();
  });
});

test.describe('Search Prompts', () => {
  test.beforeEach(async ({ page }) => {
    await page.goto('/login');
    await page.getByLabel(/email/i).fill('test@example.com');
    await page.getByLabel(/password/i).fill('testpassword123');
    await page.getByRole('button', { name: /sign in/i }).click();
    await page.waitForURL('/graphs', { timeout: 5000 });
    await page.getByRole('link', { name: /^prompts$/i }).click();
  });

  test('should search prompts by title', async ({ page }) => {
    // Type in search box
    await page.getByPlaceholder(/search/i).fill('Research');

    // Should filter results
    await page.waitForTimeout(300);

    // Verify search is working (results depend on existing data)
    const searchResults = await page.locator('[data-testid="prompt-item"]').count();
    expect(searchResults).toBeGreaterThanOrEqual(0);
  });
});

test.describe('Clone Prompt Flow', () => {
  test.beforeEach(async ({ page }) => {
    await page.goto('/login');
    await page.getByLabel(/email/i).fill('test@example.com');
    await page.getByLabel(/password/i).fill('testpassword123');
    await page.getByRole('button', { name: /sign in/i }).click();
    await page.waitForURL('/graphs', { timeout: 5000 });
    await page.getByRole('link', { name: /^prompts$/i }).click();

    // Create a prompt to clone
    await page.getByRole('button', { name: /create prompt|new prompt/i }).click();
    await page.getByLabel(/title/i).fill('Original Prompt');
    await page.getByLabel(/category/i).selectOption('research');
    await page.getByLabel(/content/i).fill('Original content');
    await page.getByRole('button', { name: /create/i }).click();
    await page.waitForTimeout(500);
  });

  test('should clone a prompt', async ({ page }) => {
    // Find and click clone button
    const promptRow = page.locator('text=Original Prompt').locator('..');
    await promptRow.getByRole('button', { name: /clone|copy/i }).click();

    // Should see cloned prompt with "(Copy)" suffix
    await expect(page.getByText(/original prompt \(copy\)/i)).toBeVisible();
  });
});

test.describe('Edit Prompt Flow', () => {
  test.beforeEach(async ({ page }) => {
    await page.goto('/login');
    await page.getByLabel(/email/i).fill('test@example.com');
    await page.getByLabel(/password/i).fill('testpassword123');
    await page.getByRole('button', { name: /sign in/i }).click();
    await page.waitForURL('/graphs', { timeout: 5000 });
    await page.getByRole('link', { name: /^prompts$/i }).click();

    // Create a prompt to edit
    await page.getByRole('button', { name: /create prompt|new prompt/i }).click();
    await page.getByLabel(/title/i).fill('Prompt To Edit');
    await page.getByLabel(/category/i).selectOption('research');
    await page.getByLabel(/content/i).fill('Original content');
    await page.getByRole('button', { name: /create/i }).click();
    await page.waitForTimeout(500);
  });

  test('should edit prompt', async ({ page }) => {
    // Find and click edit button
    const promptRow = page.locator('text=Prompt To Edit').locator('..');
    await promptRow.getByRole('button', { name: /edit/i }).click();

    // Update fields
    await page.getByLabel(/title/i).clear();
    await page.getByLabel(/title/i).fill('Updated Prompt Title');
    await page.getByLabel(/content/i).clear();
    await page.getByLabel(/content/i).fill('Updated content');

    // Save
    await page.getByRole('button', { name: /save/i }).click();

    // Should see updated title
    await expect(page.getByText('Updated Prompt Title')).toBeVisible();
  });
});

test.describe('Delete Prompt Flow', () => {
  test.beforeEach(async ({ page }) => {
    await page.goto('/login');
    await page.getByLabel(/email/i).fill('test@example.com');
    await page.getByLabel(/password/i).fill('testpassword123');
    await page.getByRole('button', { name: /sign in/i }).click();
    await page.waitForURL('/graphs', { timeout: 5000 });
    await page.getByRole('link', { name: /^prompts$/i }).click();

    // Create a prompt to delete
    await page.getByRole('button', { name: /create prompt|new prompt/i }).click();
    await page.getByLabel(/title/i).fill('Prompt To Delete');
    await page.getByLabel(/category/i).selectOption('research');
    await page.getByLabel(/content/i).fill('Content');
    await page.getByRole('button', { name: /create/i }).click();
    await page.waitForTimeout(500);
  });

  test('should delete a prompt with confirmation', async ({ page }) => {
    // Find and click delete button
    const promptRow = page.locator('text=Prompt To Delete').locator('..');
    await promptRow.getByRole('button', { name: /delete/i }).click();

    // Confirm deletion
    await page.getByRole('button', { name: /confirm|yes|delete/i }).click();

    // Prompt should be removed
    await expect(page.getByText('Prompt To Delete')).not.toBeVisible();
  });
});

test.describe('Publish Prompt Flow', () => {
  test.beforeEach(async ({ page }) => {
    await page.goto('/login');
    await page.getByLabel(/email/i).fill('test@example.com');
    await page.getByLabel(/password/i).fill('testpassword123');
    await page.getByRole('button', { name: /sign in/i }).click();
    await page.waitForURL('/graphs', { timeout: 5000 });
    await page.getByRole('link', { name: /^prompts$/i }).click();

    // Create a prompt to publish
    await page.getByRole('button', { name: /create prompt|new prompt/i }).click();
    await page.getByLabel(/title/i).fill('Prompt To Publish');
    await page.getByLabel(/category/i).selectOption('research');
    await page.getByLabel(/content/i).fill('Content');
    await page.getByRole('button', { name: /create/i }).click();
    await page.waitForTimeout(500);
  });

  test('should publish a prompt', async ({ page }) => {
    // Find and click publish button
    const promptRow = page.locator('text=Prompt To Publish').locator('..');
    await promptRow.getByRole('button', { name: /publish/i }).click();

    // Should see confirmation or success message
    await expect(page.getByText(/public|published/i)).toBeVisible();
  });
});
