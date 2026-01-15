/**
 * End-to-end tests for authentication flows.
 *
 * Tests complete user journeys through registration, login, and logout.
 */

import { test, expect } from '@playwright/test';

test.describe('Authentication Flow', () => {
  test.beforeEach(async ({ page }) => {
    await page.goto('/');
  });

  test('should display landing page with Get Started and Sign In buttons', async ({ page }) => {
    await expect(page.getByRole('link', { name: /get started/i })).toBeVisible();
    await expect(page.getByRole('link', { name: /sign in/i })).toBeVisible();
  });

  test('should navigate to register page', async ({ page }) => {
    await page.getByRole('link', { name: /get started/i }).click();
    await expect(page).toHaveURL('/register');
    await expect(page.getByRole('heading', { name: /create your account/i })).toBeVisible();
  });

  test('should navigate to login page', async ({ page }) => {
    await page.getByRole('link', { name: /sign in/i }).click();
    await expect(page).toHaveURL('/login');
    await expect(page.getByRole('heading', { name: /sign in/i })).toBeVisible();
  });
});

test.describe('User Registration', () => {
  test.beforeEach(async ({ page }) => {
    await page.goto('/register');
  });

  test('should display registration form', async ({ page }) => {
    await expect(page.getByLabel(/email/i)).toBeVisible();
    await expect(page.getByLabel(/password/i)).toBeVisible();
    await expect(page.getByRole('button', { name: /create account/i })).toBeVisible();
  });

  test('should show validation errors for empty form', async ({ page }) => {
    await page.getByRole('button', { name: /create account/i }).click();

    // Form should show validation errors (HTML5 validation)
    const emailInput = page.getByLabel(/email/i);
    await expect(emailInput).toBeFocused();
  });

  test('should show error for invalid email format', async ({ page }) => {
    await page.getByLabel(/email/i).fill('invalid-email');
    await page.getByLabel(/password/i).fill('password123');
    await page.getByRole('button', { name: /create account/i }).click();

    // HTML5 validation should catch invalid email
    const emailInput = page.getByLabel(/email/i);
    const validationMessage = await emailInput.evaluate((el: HTMLInputElement) => el.validationMessage);
    expect(validationMessage).toBeTruthy();
  });

  test('should successfully register a new user', async ({ page }) => {
    // Use a unique email for each test run
    const timestamp = Date.now();
    const email = `test${timestamp}@example.com`;

    await page.getByLabel(/email/i).fill(email);
    await page.getByLabel(/password/i).fill('password123');
    await page.getByRole('button', { name: /create account/i }).click();

    // Should redirect to login page after successful registration
    await expect(page).toHaveURL(/\/login/);
  });

  test('should navigate to login page from sign in link', async ({ page }) => {
    await page.getByRole('link', { name: /sign in/i }).click();
    await expect(page).toHaveURL('/login');
  });
});

test.describe('User Login', () => {
  // Assuming a test user exists: test@example.com / testpassword123
  test.beforeEach(async ({ page }) => {
    await page.goto('/login');
  });

  test('should display login form', async ({ page }) => {
    await expect(page.getByLabel(/email/i)).toBeVisible();
    await expect(page.getByLabel(/password/i)).toBeVisible();
    await expect(page.getByRole('button', { name: /sign in/i })).toBeVisible();
  });

  test('should show validation errors for empty form', async ({ page }) => {
    await page.getByRole('button', { name: /sign in/i }).click();

    // Form should show validation errors (HTML5 validation)
    const emailInput = page.getByLabel(/email/i);
    await expect(emailInput).toBeFocused();
  });

  test('should show error for invalid credentials', async ({ page }) => {
    await page.getByLabel(/email/i).fill('wrong@example.com');
    await page.getByLabel(/password/i).fill('wrongpassword');
    await page.getByRole('button', { name: /sign in/i }).click();

    // Should display error message
    await expect(page.getByText(/login failed|invalid credentials/i)).toBeVisible();
  });

  test('should navigate to register page from get started link', async ({ page }) => {
    await page.getByRole('link', { name: /get started/i }).click();
    await expect(page).toHaveURL('/register');
  });

  test.describe('Authenticated User', () => {
    test.beforeEach(async ({ page }) => {
      // Login before each test
      await page.goto('/login');
      await page.getByLabel(/email/i).fill('test@example.com');
      await page.getByLabel(/password/i).fill('testpassword123');
      await page.getByRole('button', { name: /sign in/i }).click();
      await page.waitForURL('/graphs', { timeout: 5000 });
    });

    test('should successfully login and redirect to graphs page', async ({ page }) => {
      await expect(page).toHaveURL('/graphs');
    });

    test('should display authenticated navigation', async ({ page }) => {
      await expect(page.getByRole('link', { name: /^graphs$/i })).toBeVisible();
      await expect(page.getByRole('link', { name: /^prompts$/i })).toBeVisible();
      await expect(page.getByRole('link', { name: /^runs$/i })).toBeVisible();
    });

    test('should display user email in header', async ({ page }) => {
      await expect(page.getByText('test@example.com')).toBeVisible();
    });

    test('should not display sign in/get started buttons when authenticated', async ({ page }) => {
      await expect(page.getByRole('link', { name: /sign in/i })).not.toBeVisible();
      await expect(page.getByRole('link', { name: /get started/i })).not.toBeVisible();
    });
  });
});

test.describe('User Logout', () => {
  test.beforeEach(async ({ page }) => {
    // Login before each test
    await page.goto('/login');
    await page.getByLabel(/email/i).fill('test@example.com');
    await page.getByLabel(/password/i).fill('testpassword123');
    await page.getByRole('button', { name: /sign in/i }).click();
    await page.waitForURL('/graphs', { timeout: 5000 });
  });

  test('should successfully logout', async ({ page }) => {
    // Open user menu
    await page.getByRole('button', { name: /test@example.com/i }).click();

    // Click sign out
    await page.getByText(/sign out/i).click();

    // Should redirect to login page
    await expect(page).toHaveURL('/login');
  });

  test('should not be able to access protected pages after logout', async ({ page }) => {
    // Logout
    await page.getByRole('button', { name: /test@example.com/i }).click();
    await page.getByText(/sign out/i).click();
    await page.waitForURL('/login');

    // Try to access protected page
    await page.goto('/graphs');

    // Should be redirected back to login
    await expect(page).toHaveURL('/login');
  });
});

test.describe('Protected Routes', () => {
  test('should redirect to login when accessing protected page without authentication', async ({ page }) => {
    await page.goto('/graphs');
    await expect(page).toHaveURL('/login');
  });

  test('should redirect to login when accessing prompts page without authentication', async ({ page }) => {
    await page.goto('/prompts');
    await expect(page).toHaveURL('/login');
  });

  test('should redirect to login when accessing runs page without authentication', async ({ page }) => {
    await page.goto('/runs');
    await expect(page).toHaveURL('/login');
  });

  test('should allow access to public pages without authentication', async ({ page }) => {
    await page.goto('/');
    await expect(page).toHaveURL('/');

    await page.goto('/login');
    await expect(page).toHaveURL('/login');

    await page.goto('/register');
    await expect(page).toHaveURL('/register');
  });
});
