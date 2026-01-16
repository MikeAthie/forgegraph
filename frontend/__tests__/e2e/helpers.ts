import type { APIRequestContext, Page, TestInfo } from "@playwright/test";

export type TestUser = {
  email: string;
  password: string;
};

const TEST_PASSWORD = "ForgeGraphTest!12345";
const API_BASE_URL = (process.env.PLAYWRIGHT_API_URL ??
  process.env.NEXT_PUBLIC_API_URL ??
  "http://127.0.0.1:8000"
).replace(/\/$/, "");

export function createTestUser(testInfo: TestInfo, prefix = "e2e"): TestUser {
  const runId = `${Date.now()}-${Math.random().toString(16).slice(2)}`;
  const project = testInfo.project.name.replace(/[^a-z0-9]+/gi, "-").toLowerCase();
  return {
    email: `${prefix}-${project}-${runId}@example.com`,
    password: TEST_PASSWORD,
  };
}

export async function ensureUserRegistered(request: APIRequestContext, user: TestUser): Promise<void> {
  const response = await request.post(`${API_BASE_URL}/api/auth/register`, {
    data: { email: user.email, password: user.password },
  });

  if (response.ok()) return;

  // If the user already exists, registration returns 400. That's fine for idempotency.
  if (response.status() === 400) return;

  const body = await response.text();
  throw new Error(`Failed to register test user (status ${response.status()}): ${body}`);
}

export async function login(page: Page, user: TestUser): Promise<void> {
  await page.goto("/login");
  await page.locator("#email").fill(user.email);
  await page.locator("#password").fill(user.password);
  await page.getByRole("button", { name: /^sign in$/i }).click();
  await page.waitForURL("/graphs", { timeout: 10_000 });
}
