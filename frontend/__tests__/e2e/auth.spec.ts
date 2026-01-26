/**
 * End-to-end tests for authentication flows.
 *
 * Tests complete user journeys through registration, login, and logout.
 */

import { test, expect } from "@playwright/test";
import { createTestUser, ensureUserRegistered, login, type TestUser } from "./helpers";

let seededUser: TestUser;

test.beforeAll(async ({ request }, testInfo) => {
  seededUser = createTestUser(testInfo);
  await ensureUserRegistered(request, seededUser);
});

test.describe("Authentication Flow", () => {
  test.beforeEach(async ({ page }) => {
    await page.goto("/");
  });

  test("should display landing page with Get Started and Sign In buttons", async ({ page }) => {
    const nav = page.getByRole("navigation");
    await expect(nav.getByRole("link", { name: /get started/i })).toBeVisible();
    await expect(nav.getByRole("link", { name: /sign in/i })).toBeVisible();
  });

  test("should navigate to register page", async ({ page }) => {
    const nav = page.getByRole("navigation");
    await nav.getByRole("link", { name: /get started/i }).click();
    await expect(page).toHaveURL("/register");
    await expect(page.locator("#email")).toBeVisible();
    await expect(page.getByRole("button", { name: /^create account$/i })).toBeVisible();
  });

  test("should navigate to login page", async ({ page }) => {
    const nav = page.getByRole("navigation");
    await nav.getByRole("link", { name: /sign in/i }).click();
    await expect(page).toHaveURL("/login");
    await expect(page.getByText(/sign in to your account/i)).toBeVisible();
  });
});

test.describe("User Registration", () => {
  test.beforeEach(async ({ page }) => {
    await page.goto("/register");
  });

  test("should display registration form", async ({ page }) => {
    await expect(page.locator("#email")).toBeVisible();
    await expect(page.locator("#password")).toBeVisible();
    await expect(page.locator("#confirmPassword")).toBeVisible();
    await expect(page.getByRole("button", { name: /create account/i })).toBeVisible();
  });

  test("should show validation errors for empty form", async ({ page }) => {
    await page.getByRole("button", { name: /create account/i }).click();
    await expect(page.getByText(/^email is required$/i)).toBeVisible();
  });

  test("should show error for invalid email format", async ({ page }) => {
    await page.locator("#email").fill("invalid-email");
    await page.locator("#password").fill("ForgeGraphTest!12345");
    await page.locator("#confirmPassword").fill("ForgeGraphTest!12345");
    await page.getByRole("button", { name: /create account/i }).click();
    await expect(page.getByText(/^please enter a valid email address$/i)).toBeVisible();
  });

  test("should successfully register a new user", async ({ page }) => {
    // Use a unique email for each test run
    const timestamp = Date.now();
    const email = `test${timestamp}@example.com`;

    await page.locator("#email").fill(email);
    await page.locator("#password").fill("ForgeGraphTest!12345");
    await page.locator("#confirmPassword").fill("ForgeGraphTest!12345");
    await page.getByRole("button", { name: /create account/i }).click();

    // Should redirect to login page after successful registration
    await expect(page).toHaveURL(/\/login\?registered=(true|1)/);
  });

  test("should navigate to login page from sign in link", async ({ page }) => {
    await page.getByRole("main").getByRole("link", { name: /^sign in$/i }).click();
    await expect(page).toHaveURL("/login");
  });
});

test.describe("User Login", () => {
  test.beforeEach(async ({ page }) => {
    await page.goto("/login");
  });

  test("should display login form", async ({ page }) => {
    await expect(page.locator("#email")).toBeVisible();
    await expect(page.locator("#password")).toBeVisible();
    await expect(page.getByRole("button", { name: /^sign in$/i })).toBeVisible();
  });

  test("should show validation errors for empty form", async ({ page }) => {
    await page.getByRole("button", { name: /^sign in$/i }).click();
    await expect(page.getByText(/^email is required$/i)).toBeVisible();
  });

  test("should show error for invalid credentials", async ({ page }) => {
    await page.locator("#email").fill("wrong@example.com");
    await page.locator("#password").fill("wrongpassword");
    await page.getByRole("button", { name: /^sign in$/i }).click();

    // Should display error message
    await expect(page.getByText(/no active account|login failed|invalid credentials/i)).toBeVisible();
  });

  test("should navigate to register page from get started link", async ({ page }) => {
    await page.getByRole("link", { name: /create a new account|get started/i }).click();
    await expect(page).toHaveURL("/register");
  });

  test.describe("Authenticated User", () => {
    test.beforeEach(async ({ page }) => {
      await login(page, seededUser);
    });

    test("should successfully login and redirect to graphs page", async ({ page }) => {
      await expect(page).toHaveURL("/graphs");
    });

    test("should display authenticated navigation", async ({ page }) => {
      await expect(page.getByRole("link", { name: /^graphs$/i })).toBeVisible();
      await expect(page.getByRole("link", { name: /^prompts$/i })).toBeVisible();
      await expect(page.getByRole("link", { name: /^runs$/i })).toBeVisible();
    });

    test("should display user email in header", async ({ page }) => {
      await expect(page.getByText(seededUser.email)).toBeVisible();
    });

    test("should not display sign in/get started buttons when authenticated", async ({ page }) => {
      const nav = page.getByRole("navigation");
      await expect(nav.getByRole("link", { name: /sign in/i })).not.toBeVisible();
      await expect(nav.getByRole("link", { name: /get started/i })).not.toBeVisible();
    });
  });
});

test.describe("User Logout", () => {
  test.beforeEach(async ({ page }) => {
    await login(page, seededUser);
  });

  test("should successfully logout", async ({ page }) => {
    // Open user menu
    await page.getByRole("button", { name: new RegExp(seededUser.email, "i") }).click();

    // Click sign out
    await page.getByRole("menuitem", { name: /sign out/i }).dispatchEvent("click");

    // Should redirect to login page
    await expect(page).toHaveURL("/login");
  });

  test("should not be able to access protected pages after logout", async ({ page }) => {
    // Logout
    await page.getByRole("button", { name: new RegExp(seededUser.email, "i") }).click();
    await page.getByRole("menuitem", { name: /sign out/i }).dispatchEvent("click");
    await page.waitForURL("/login");

    // Try to access protected page
    await page.goto("/graphs");

    // Should be redirected back to login
    await expect(page).toHaveURL("/login");
  });
});

test.describe("Protected Routes", () => {
  test("should redirect to login when accessing protected page without authentication", async ({ page }) => {
    await page.goto("/graphs");
    await expect(page).toHaveURL("/login");
  });

  test("should redirect to login when accessing prompts page without authentication", async ({ page }) => {
    await page.goto("/prompts");
    await expect(page).toHaveURL("/login");
  });

  test("should redirect to login when accessing runs page without authentication", async ({ page }) => {
    await page.goto("/runs");
    await expect(page).toHaveURL("/login");
  });

  test("should allow access to public pages without authentication", async ({ page }) => {
    await page.goto("/");
    await expect(page).toHaveURL("/");

    await page.goto("/login");
    await expect(page).toHaveURL("/login");

    await page.goto("/register");
    await expect(page).toHaveURL("/register");
  });
});
