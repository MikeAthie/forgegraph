import { defineConfig, devices } from '@playwright/test';
import path from "path";
import os from "os";

/**
 * See https://playwright.dev/docs/test-configuration.
 */
const devPort = process.env.PLAYWRIGHT_DEV_PORT ? Number(process.env.PLAYWRIGHT_DEV_PORT) : 3001;
// Use 127.0.0.1 to keep frontend/backend on the same "site" for SameSite=Lax cookies.
const devUrl = `http://127.0.0.1:${devPort}`;
const backendPort = process.env.PLAYWRIGHT_BACKEND_PORT ? Number(process.env.PLAYWRIGHT_BACKEND_PORT) : 8002;
const backendUrl = `http://127.0.0.1:${backendPort}`;
const enginePort = process.env.PLAYWRIGHT_ENGINE_PORT ? Number(process.env.PLAYWRIGHT_ENGINE_PORT) : 50071;
const engineMetricsPort = process.env.PLAYWRIGHT_ENGINE_METRICS_PORT
  ? Number(process.env.PLAYWRIGHT_ENGINE_METRICS_PORT)
  : 9091;
const engineMetricsUrl = `http://127.0.0.1:${engineMetricsPort}`;
const runtimeFixtureTenantId =
  process.env.PLAYWRIGHT_RUNTIME_TENANT_ID ?? "00000000-0000-0000-0000-00000000e2e1";
const runtimeFixtureEmail =
  process.env.PLAYWRIGHT_RUNTIME_FIXTURE_EMAIL ?? "playwright-runtime@example.com";
const runtimeFixturePassword =
  process.env.PLAYWRIGHT_RUNTIME_FIXTURE_PASSWORD ?? "ForgeGraphTest!12345";
const runtimeFixturePackageSlug =
  process.env.PLAYWRIGHT_RUNTIME_PACKAGE_SLUG ?? "playwright-runtime-health-check";
const runtimeFixturePackageName =
  process.env.PLAYWRIGHT_RUNTIME_PACKAGE_NAME ?? "Playwright Runtime Health Check";
const runtimeFixtureToolName =
  process.env.PLAYWRIGHT_RUNTIME_TOOL_NAME ?? "playwright_runtime_health_check";
const runtimeFixtureToolUrl =
  process.env.PLAYWRIGHT_RUNTIME_TOOL_URL ?? `${backendUrl}/health`;
const callbackSecret = process.env.ENGINE_CALLBACK_SECRET ?? "playwright-callback-secret";
const dbHost = process.env.DB_HOST ?? "localhost";
const dbPort = process.env.DB_PORT ?? "5433";
const dbName = process.env.DB_NAME ?? "forgegraph";
const dbUser = process.env.DB_USER ?? "forgegraph";
const dbPassword = process.env.DB_PASSWORD ?? "forgegraph_secret";
const engineDatabaseUrl =
  process.env.DATABASE_URL ??
  `postgres://${dbUser}:${dbPassword}@${dbHost}:${dbPort}/${dbName}?sslmode=disable`;

// Give E2E helpers a stable default API URL (avoids IPv6 localhost issues on some hosts).
process.env.PLAYWRIGHT_API_URL = process.env.PLAYWRIGHT_API_URL ?? backendUrl;
process.env.PLAYWRIGHT_RUNTIME_TENANT_ID = runtimeFixtureTenantId;
process.env.PLAYWRIGHT_RUNTIME_FIXTURE_EMAIL = runtimeFixtureEmail;
process.env.PLAYWRIGHT_RUNTIME_FIXTURE_PASSWORD = runtimeFixturePassword;
process.env.PLAYWRIGHT_RUNTIME_PACKAGE_SLUG = runtimeFixturePackageSlug;
process.env.PLAYWRIGHT_RUNTIME_PACKAGE_NAME = runtimeFixturePackageName;
process.env.PLAYWRIGHT_RUNTIME_TOOL_NAME = runtimeFixtureToolName;
process.env.PLAYWRIGHT_RUNTIME_TOOL_URL = runtimeFixtureToolUrl;

const workerOverride = process.env.PLAYWRIGHT_WORKERS ? Number(process.env.PLAYWRIGHT_WORKERS) : undefined;
const useSqlite = (process.env.USE_SQLITE ?? "false").toLowerCase() === "true";
const sqliteDbPath = process.env.SQLITE_DB_PATH ?? path.join(os.tmpdir(), "forgegraph-playwright-db.sqlite3");

// Ensure the Playwright test process and any helper subprocesses (e.g. seed_run_trace)
// point at the same SQLite DB as the Django webServer.
process.env.SQLITE_DB_PATH = sqliteDbPath;
process.env.USE_SQLITE = process.env.USE_SQLITE ?? "false";
process.env.USE_IN_MEMORY_CHANNEL_LAYER = process.env.USE_IN_MEMORY_CHANNEL_LAYER ?? "true";
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
      use: {
        ...devices['Desktop Chrome'],
        // Enable GPU acceleration for faster rendering (requires GPU)
        launchOptions: {
          args: [
            '--enable-gpu',
            '--enable-webgl',
            '--use-gl=desktop',
            '--enable-accelerated-2d-canvas',
            '--ignore-gpu-blocklist',
          ],
        },
      },
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
      command: `python manage.py migrate --noinput --verbosity 0 && python manage.py seed_playwright_runtime_fixture --email "${runtimeFixtureEmail}" --password "${runtimeFixturePassword}" --tenant-id "${runtimeFixtureTenantId}" --package-slug "${runtimeFixturePackageSlug}" --package-name "${runtimeFixturePackageName}" --tool-name "${runtimeFixtureToolName}" --runtime-url "${runtimeFixtureToolUrl}" && python manage.py runserver 127.0.0.1:${backendPort} --noreload --verbosity 0`,
      url: `${backendUrl}/health`,
      reuseExistingServer: !process.env.CI,
      cwd: path.join(__dirname, "..", "backend"),
      env: {
        ...process.env,
        DEBUG: process.env.DEBUG ?? "true",
        USE_SQLITE: process.env.USE_SQLITE ?? "false",
        SQLITE_DB_PATH: sqliteDbPath,
        USE_IN_MEMORY_CHANNEL_LAYER: process.env.USE_IN_MEMORY_CHANNEL_LAYER ?? "true",
        DB_HOST: dbHost,
        DB_PORT: dbPort,
        DB_NAME: dbName,
        DB_USER: dbUser,
        DB_PASSWORD: dbPassword,
        ENGINE_HOST: process.env.ENGINE_HOST ?? "127.0.0.1",
        ENGINE_PORT: String(process.env.ENGINE_PORT ?? enginePort),
        ENGINE_CALLBACK_URL: process.env.ENGINE_CALLBACK_URL ?? `${backendUrl}/api/runs/engine-events`,
        ENGINE_CALLBACK_SECRET: callbackSecret,
        FORGEGRAPH_RUNTIME_MODE: process.env.FORGEGRAPH_RUNTIME_MODE ?? "cloud",
      },
    },
    {
      command: "go run .",
      url: `${engineMetricsUrl}/metrics`,
      reuseExistingServer: !process.env.CI,
      cwd: path.join(__dirname, "..", "engine"),
      env: {
        ...process.env,
        GRPC_PORT: String(enginePort),
        METRICS_PORT: String(engineMetricsPort),
        CONTROL_PLANE_URL: backendUrl,
        ENGINE_CALLBACK_SECRET: callbackSecret,
        TENANT_ID: runtimeFixtureTenantId,
        MARKETPLACE_MANIFEST_REFRESH_SECONDS:
          process.env.MARKETPLACE_MANIFEST_REFRESH_SECONDS ?? "1",
        FORGEGRAPH_RUNTIME_MODE: process.env.FORGEGRAPH_RUNTIME_MODE ?? "cloud",
        TOOL_MANIFEST_DIR: process.env.TOOL_MANIFEST_DIR ?? "",
        DATABASE_URL: engineDatabaseUrl,
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
