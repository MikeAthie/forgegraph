import { expect, test } from "@playwright/test";

import { createTestUser, ensureUserRegistered, login, type TestUser } from "./helpers";

let seededUser: TestUser;

test.beforeAll(async ({ request }, testInfo) => {
  seededUser = createTestUser(testInfo, "auth");
  await ensureUserRegistered(request, seededUser);
});

test.describe("Authentication Flow", () => {
  test.beforeEach(async ({ page }) => {
    await page.goto("/");
  });

  test("shows the public landing actions", async ({ page }) => {
    await expect(page.getByRole("link", { name: /sign in/i })).toBeVisible();
    await expect(page.getByRole("link", { name: /start operating/i })).toBeVisible();
  });

  test("navigates to the register page from the landing screen", async ({ page }) => {
    await page.getByRole("link", { name: /start operating/i }).click();
    await expect(page).toHaveURL("/register");
    await expect(page.locator("#email")).toBeVisible();
    await expect(page.getByRole("button", { name: /^create account$/i })).toBeVisible();
  });

  test("navigates to the login page from the landing screen", async ({ page }) => {
    await page.getByRole("link", { name: /sign in/i }).click();
    await expect(page).toHaveURL("/login");
    await expect(page.getByText(/sign in to continue operating your companies/i)).toBeVisible();
  });
});

test.describe("User Registration", () => {
  test.beforeEach(async ({ page }) => {
    await page.goto("/register");
  });

  test("displays registration form fields", async ({ page }) => {
    await expect(page.locator("#email")).toBeVisible();
    await expect(page.locator("#password")).toBeVisible();
    await expect(page.locator("#confirmPassword")).toBeVisible();
    await expect(page.getByRole("button", { name: /create account/i })).toBeVisible();
  });

  test("shows validation errors for an empty form", async ({ page }) => {
    await page.getByRole("button", { name: /create account/i }).click();
    await expect(page.getByText(/^email is required$/i)).toBeVisible();
  });

  test("shows an error for an invalid email format", async ({ page }) => {
    await page.locator("#email").fill("invalid-email");
    await page.locator("#password").fill("ForgeGraphTest!12345");
    await page.locator("#confirmPassword").fill("ForgeGraphTest!12345");
    await page.getByRole("button", { name: /create account/i }).click();
    await expect(page.getByText(/^please enter a valid email address$/i)).toBeVisible();
  });

  test("shows the post-registration sign-in banner", async ({ page }) => {
    await page.goto("/login?registered=true");
    await expect(page.getByText(/account created\./i)).toBeVisible();
  });

  test("navigates to login from the register screen", async ({ page }) => {
    await page
      .getByRole("main")
      .getByRole("link", { name: /sign in/i })
      .click();
    await expect(page).toHaveURL("/login");
  });
});

test.describe("User Login", () => {
  test.beforeEach(async ({ page }) => {
    await page.goto("/login");
  });

  test("displays login fields", async ({ page }) => {
    await expect(page.locator("#email")).toBeVisible();
    await expect(page.locator("#password")).toBeVisible();
    await expect(page.getByRole("button", { name: /^sign in$/i })).toBeVisible();
  });

  test("shows validation errors for an empty login form", async ({ page }) => {
    await page.getByRole("button", { name: /^sign in$/i }).click();
    await expect(page.getByText(/^email is required$/i)).toBeVisible();
  });

  test("shows an error for invalid credentials", async ({ page }) => {
    await page.locator("#email").fill("wrong@example.com");
    await page.locator("#password").fill("wrongpassword");
    await page.getByRole("button", { name: /^sign in$/i }).click();

    await expect(page.getByText(/no active account|login failed|invalid credentials/i)).toBeVisible();
  });

  test("navigates to registration from login", async ({ page }) => {
    await page.getByRole("link", { name: /create one/i }).click();
    await expect(page).toHaveURL("/register");
  });

  test.describe("Authenticated User", () => {
    test.beforeEach(async ({ page }) => {
      await login(page, seededUser);
    });

    test("opens the operating shell for an authenticated session", async ({ page }) => {
      await expect(page).toHaveURL("/companies");
      await expect(page.getByRole("heading", { name: /operate ai-driven companies/i })).toBeVisible();
      await expect(page.getByRole("link", { name: /^companies$/i })).toBeVisible();
    });

    test("shows the company-first shell navigation instead of builder-first links", async ({ page }) => {
      await expect(page.getByRole("link", { name: /^companies$/i })).toBeVisible();
      await expect(page.getByRole("link", { name: /^command ops$/i })).toBeVisible();
      await expect(page.getByRole("link", { name: /^departments$/i })).toBeVisible();
      await expect(page.getByRole("link", { name: /^approvals$/i })).toBeVisible();
      await expect(page.getByRole("link", { name: /^knowledge$/i })).toBeVisible();
      await expect(page.getByRole("link", { name: /^advanced$/i })).toBeVisible();
    });

    test("shows the signed-in user control in the shell header", async ({ page }) => {
      await expect(page.getByRole("button", { name: seededUser.email })).toBeVisible();
    });
  });
});

test.describe("User Logout", () => {
  test.beforeEach(async ({ page }) => {
    await login(page, seededUser);
  });

  test("logs out from the shell header", async ({ page }) => {
    await page.getByRole("button", { name: seededUser.email }).click();
    await expect(page).toHaveURL("/login");
  });

  test("blocks protected routes after logout", async ({ page }) => {
    await page.getByRole("button", { name: seededUser.email }).click();
    await page.waitForURL("/login");

    await page.goto("/companies");
    await expect(page).toHaveURL("/login");
  });
});

test.describe("Protected Routes", () => {
  test("redirects unauthenticated users away from companies", async ({ page }) => {
    await page.goto("/companies");
    await expect(page).toHaveURL("/login");
  });

  test("redirects unauthenticated users away from agents", async ({ page }) => {
    await page.goto("/agents");
    await expect(page).toHaveURL("/login");
  });

  test("redirects unauthenticated users away from executions", async ({ page }) => {
    await page.goto("/executions");
    await expect(page).toHaveURL("/login");
  });

  test("keeps public auth routes accessible", async ({ page }) => {
    await page.goto("/");
    await expect(page).toHaveURL("/");

    await page.goto("/login");
    await expect(page).toHaveURL("/login");

    await page.goto("/register");
    await expect(page).toHaveURL("/register");
  });
});
