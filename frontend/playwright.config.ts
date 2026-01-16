import { defineConfig, devices } from '@playwright/test';
import path from "path";

/**
 * See https://playwright.dev/docs/test-configuration.
 */
const devPort = process.env.PLAYWRIGHT_DEV_PORT ? Number(process.env.PLAYWRIGHT_DEV_PORT) : 3001;
// Use 127.0.0.1 to keep frontend/backend on the same "site" for SameSite=Lax cookies.
const devUrl = `http://127.0.0.1:${devPort}`;
const backendPort = process.env.PLAYWRIGHT_BACKEND_PORT ? Number(process.env.PLAYWRIGHT_BACKEND_PORT) : 8000;
const backendUrl = `http://127.0.0.1:${backendPort}`;

// Give E2E helpers a stable default API URL (avoids IPv6 localhost issues on some hosts).
process.env.PLAYWRIGHT_API_URL = process.env.PLAYWRIGHT_API_URL ?? backendUrl;

const workerOverride = process.env.PLAYWRIGHT_WORKERS ? Number(process.env.PLAYWRIGHT_WORKERS) : undefined;
const useSqlite = (process.env.USE_SQLITE ?? "true").toLowerCase() === "true";
// SQLite-backed Django dev server can get flaky under high concurrency; default to serial execution unless overridden.
const workerCount =
  Number.isFinite(workerOverride) && workerOverride && workerOverride > 0
    ? workerOverride
    : process.env.CI || useSqlite
      ? 1
      : undefined;

export default defineConfig({
  testDir: './__tests__/e2e',
  fullyParallel: true,
  forbidOnly: !!process.env.CI,
  retries: process.env.CI ? 2 : 0,
  workers: workerCount,
  reporter: 'html',
  use: {
    baseURL: devUrl,
    trace: 'on-first-retry',
  },

  projects: [
    {
      name: 'chromium',
      use: { ...devices['Desktop Chrome'] },
    },

    {
      name: 'firefox',
      use: { ...devices['Desktop Firefox'] },
    },

    {
      name: 'webkit',
      use: { ...devices['Desktop Safari'] },
    },
  ],

  webServer: [
    {
      command: `python manage.py migrate && python manage.py runserver 127.0.0.1:${backendPort} --noreload`,
      url: `${backendUrl}/health`,
      reuseExistingServer: !process.env.CI,
      cwd: path.join(__dirname, "..", "backend"),
      env: {
        ...process.env,
        DEBUG: process.env.DEBUG ?? "true",
        USE_SQLITE: process.env.USE_SQLITE ?? "true",
      },
    },
    {
      command: `npm run dev -- -p ${devPort}`,
      url: devUrl,
      reuseExistingServer: !process.env.CI,
      env: {
        ...process.env,
        NEXT_PUBLIC_API_URL: process.env.NEXT_PUBLIC_API_URL ?? backendUrl,
      },
    },
  ],
});
