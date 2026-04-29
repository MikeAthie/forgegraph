import { defineConfig, devices } from "@playwright/test";
import fs from "fs";
import path from "path";
import os from "os";

/**
 * See https://playwright.dev/docs/test-configuration.
 */
function loadRootEnvFile() {
  const envPath = path.resolve(__dirname, "..", ".env");
  if (!fs.existsSync(envPath)) {
    return;
  }

  const envFile = fs.readFileSync(envPath, "utf8");
  for (const rawLine of envFile.split(/\r?\n/)) {
    const line = rawLine.trim();
    if (!line || line.startsWith("#")) {
      continue;
    }

    const separatorIndex = line.indexOf("=");
    if (separatorIndex < 1) {
      continue;
    }

    const key = line.slice(0, separatorIndex).trim();
    const value = line
      .slice(separatorIndex + 1)
      .trim()
      .replace(/^['"]|['"]$/g, "");

    process.env[key] ??= value;
  }
}

loadRootEnvFile();

const runtimeTarget = (process.env.PLAYWRIGHT_RUNTIME_TARGET ?? "docker").toLowerCase();
const useDockerRuntime = runtimeTarget !== "local";
const devPort = process.env.PLAYWRIGHT_DEV_PORT ? Number(process.env.PLAYWRIGHT_DEV_PORT) : 3001;
const dockerFrontendUrl = process.env.PLAYWRIGHT_DOCKER_FRONTEND_URL ?? "http://127.0.0.1:3000";
// Use 127.0.0.1 to keep frontend/backend on the same "site" for SameSite=Lax cookies.
const devUrl = useDockerRuntime ? dockerFrontendUrl : `http://127.0.0.1:${devPort}`;
const backendPort = process.env.PLAYWRIGHT_BACKEND_PORT ? Number(process.env.PLAYWRIGHT_BACKEND_PORT) : 8002;
const dockerBackendUrl = process.env.PLAYWRIGHT_DOCKER_BACKEND_URL ?? "http://127.0.0.1:8000";
const backendUrl = useDockerRuntime ? dockerBackendUrl : `http://127.0.0.1:${backendPort}`;
const trustedFrontendOrigins = [
  devUrl,
  "http://localhost:3000",
  "http://127.0.0.1:3000",
  "http://localhost:3001",
  "http://127.0.0.1:3001",
].join(",");
const enginePort = process.env.PLAYWRIGHT_ENGINE_PORT ? Number(process.env.PLAYWRIGHT_ENGINE_PORT) : 50071;
const engineMetricsPort = process.env.PLAYWRIGHT_ENGINE_METRICS_PORT
  ? Number(process.env.PLAYWRIGHT_ENGINE_METRICS_PORT)
  : 9091;
const engineMetricsUrl = `http://127.0.0.1:${engineMetricsPort}`;
const memoryGrpcHost = process.env.MEMORY_GRPC_HOST ?? process.env.PLAYWRIGHT_MEMORY_GRPC_HOST ?? "127.0.0.1";
const memoryGrpcPort = process.env.MEMORY_GRPC_PORT
  ? Number(process.env.MEMORY_GRPC_PORT)
  : process.env.PLAYWRIGHT_MEMORY_GRPC_PORT
    ? Number(process.env.PLAYWRIGHT_MEMORY_GRPC_PORT)
    : 50052;
const llmMockPort = process.env.PLAYWRIGHT_LLM_MOCK_PORT ? Number(process.env.PLAYWRIGHT_LLM_MOCK_PORT) : 8011;
const llmMockUrl = `http://127.0.0.1:${llmMockPort}`;
const dockerLocalLlmUrl = process.env.PLAYWRIGHT_DOCKER_LOCAL_LLM_URL ?? "http://127.0.0.1:12434/v1";
const preferredLlmBaseUrl =
  process.env.OPENAI_BASE_URL ??
  process.env.LOCAL_LLM_BASE_URL ??
  process.env.PLAYWRIGHT_LOCAL_LLM_URL ??
  (runtimeTarget === "docker" ? dockerLocalLlmUrl : `${llmMockUrl}/v1`);
const useLlmMockServer = preferredLlmBaseUrl === `${llmMockUrl}/v1`;
const playwrightRunId = process.env.PLAYWRIGHT_RUN_ID ?? `${Date.now()}`;
const engineEventSpoolPath =
  process.env.ENGINE_EVENT_SPOOL_PATH ??
  path.join(os.tmpdir(), `forgegraph-playwright-engine-events-${playwrightRunId}-${enginePort}.jsonl`);
const runtimeFixtureTenantId = process.env.PLAYWRIGHT_RUNTIME_TENANT_ID ?? "00000000-0000-0000-0000-00000000e2e1";
const runtimeFixtureEmail = process.env.PLAYWRIGHT_RUNTIME_FIXTURE_EMAIL ?? "playwright-runtime@example.com";
const runtimeFixturePassword = process.env.PLAYWRIGHT_RUNTIME_FIXTURE_PASSWORD ?? "ForgeGraphTest!12345";
const runtimeFixturePackageSlug = process.env.PLAYWRIGHT_RUNTIME_PACKAGE_SLUG ?? "playwright-runtime-health-check";
const runtimeFixturePackageName = process.env.PLAYWRIGHT_RUNTIME_PACKAGE_NAME ?? "Playwright Runtime Health Check";
const runtimeFixtureToolName = process.env.PLAYWRIGHT_RUNTIME_TOOL_NAME ?? "playwright_runtime_health_check";
const runtimeFixtureToolUrl = process.env.PLAYWRIGHT_RUNTIME_TOOL_URL ?? `${backendUrl}/health`;
const callbackSecret = process.env.ENGINE_CALLBACK_SECRET ?? "playwright-callback-secret";
const redisHost = process.env.PLAYWRIGHT_REDIS_HOST ?? "127.0.0.1";
const redisPort = process.env.PLAYWRIGHT_REDIS_PORT ?? "6379";
const redisAddr = `${redisHost}:${redisPort}`;
const dbHost = process.env.DB_HOST ?? "localhost";
const dbPort = process.env.DB_PORT ?? "5433";
const dbName = process.env.DB_NAME ?? "forgegraph";
const dbUser = process.env.DB_USER ?? "forgegraph";
const dbPassword = process.env.DB_PASSWORD ?? "forgegraph_secret";
const engineDatabaseUrl =
  process.env.DATABASE_URL ?? `postgres://${dbUser}:${dbPassword}@${dbHost}:${dbPort}/${dbName}?sslmode=disable`;

// Give E2E helpers a stable default API URL (avoids IPv6 localhost issues on some hosts).
process.env.PLAYWRIGHT_API_URL = process.env.PLAYWRIGHT_API_URL ?? backendUrl;
process.env.PLAYWRIGHT_RUNTIME_TARGET = runtimeTarget;
process.env.PLAYWRIGHT_RUNTIME_TENANT_ID = runtimeFixtureTenantId;
process.env.PLAYWRIGHT_RUNTIME_FIXTURE_EMAIL = runtimeFixtureEmail;
process.env.PLAYWRIGHT_RUNTIME_FIXTURE_PASSWORD = runtimeFixturePassword;
process.env.PLAYWRIGHT_RUNTIME_PACKAGE_SLUG = runtimeFixturePackageSlug;
process.env.PLAYWRIGHT_RUNTIME_PACKAGE_NAME = runtimeFixturePackageName;
process.env.PLAYWRIGHT_RUNTIME_TOOL_NAME = runtimeFixtureToolName;
process.env.PLAYWRIGHT_RUNTIME_TOOL_URL = runtimeFixtureToolUrl;
process.env.PLAYWRIGHT_LLM_MOCK_URL = llmMockUrl;
process.env.OPENAI_BASE_URL = process.env.OPENAI_BASE_URL ?? preferredLlmBaseUrl;
process.env.TESTING = process.env.TESTING ?? "true";
process.env.SECRET_KEY = process.env.SECRET_KEY ?? "django-insecure-test-key-change-in-production";
process.env.ALLOWED_HOSTS = process.env.ALLOWED_HOSTS ?? "127.0.0.1,localhost,testserver";
process.env.ENCRYPTION_KEY = process.env.ENCRYPTION_KEY ?? "31w_1yyrCRlD_5Uyp9iofvy68W9T1ty9W81BbBlkbWI=";
process.env.SECURE_SSL_REDIRECT = process.env.SECURE_SSL_REDIRECT ?? "false";
process.env.SESSION_COOKIE_SECURE = process.env.SESSION_COOKIE_SECURE ?? "false";
process.env.CSRF_COOKIE_SECURE = process.env.CSRF_COOKIE_SECURE ?? "false";
process.env.AUTH_REFRESH_COOKIE_SECURE = process.env.AUTH_REFRESH_COOKIE_SECURE ?? "false";
process.env.MEMORY_GRPC_HOST = process.env.MEMORY_GRPC_HOST ?? memoryGrpcHost;
process.env.MEMORY_GRPC_PORT = process.env.MEMORY_GRPC_PORT ?? String(memoryGrpcPort);

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
  testDir: "./__tests__",
  testMatch: ["**/e2e/**/*.spec.ts", "**/consulting/specs/*.spec.ts"],
  testIgnore: [
    "**/agent-authoring.spec.ts",
    "**/graph-editor.spec.ts",
    "**/graphs.spec.ts",
    "**/jackie-workflow.spec.ts",
    "**/marketplace-runtime.spec.ts",
    "**/prompts.spec.ts",
  ],
  fullyParallel: true,
  forbidOnly: !!process.env.CI,
  retries: process.env.CI ? 2 : 0,
  workers: workerCount,
  reporter: "html",
  use: {
    baseURL: devUrl,
    trace: "on-first-retry",
  },

  projects: [
    {
      name: "chromium",
      use: {
        ...devices["Desktop Chrome"],
        // Enable GPU acceleration for faster rendering (requires GPU)
        launchOptions: {
          args: [
            "--enable-gpu",
            "--enable-webgl",
            "--use-gl=desktop",
            "--enable-accelerated-2d-canvas",
            "--ignore-gpu-blocklist",
          ],
        },
      },
    },

    {
      name: "firefox",
      use: { ...devices["Desktop Firefox"] },
    },

    {
      name: "webkit",
      use: { ...devices["Desktop Safari"] },
    },
  ],

  webServer: [
    ...(useLlmMockServer
      ? [
          {
            command: `node scripts/playwright-openai-mock.mjs`,
            url: `${llmMockUrl}/health`,
            reuseExistingServer: !process.env.CI,
            cwd: __dirname,
            env: {
              ...process.env,
              PLAYWRIGHT_LLM_MOCK_PORT: String(llmMockPort),
            },
          },
        ]
      : []),
    ...(!useDockerRuntime
      ? [
          {
            command: "python scripts/run_playwright_backend.py",
            url: `${backendUrl}/health`,
            reuseExistingServer: !process.env.CI,
            cwd: path.join(__dirname, "..", "backend"),
            env: {
              ...process.env,
              TESTING: process.env.TESTING ?? "true",
              DEBUG: process.env.DEBUG ?? "true",
              SECRET_KEY: process.env.SECRET_KEY ?? "django-insecure-test-key-change-in-production",
              ALLOWED_HOSTS: process.env.ALLOWED_HOSTS ?? "127.0.0.1,localhost,testserver",
              ENCRYPTION_KEY: process.env.ENCRYPTION_KEY ?? "31w_1yyrCRlD_5Uyp9iofvy68W9T1ty9W81BbBlkbWI=",
              USE_SQLITE: process.env.USE_SQLITE ?? "false",
              SQLITE_DB_PATH: sqliteDbPath,
              USE_IN_MEMORY_CHANNEL_LAYER: process.env.USE_IN_MEMORY_CHANNEL_LAYER ?? "true",
              CORS_ALLOWED_ORIGINS: process.env.CORS_ALLOWED_ORIGINS ?? trustedFrontendOrigins,
              CSRF_TRUSTED_ORIGINS: process.env.CSRF_TRUSTED_ORIGINS ?? trustedFrontendOrigins,
              SECURE_SSL_REDIRECT: process.env.SECURE_SSL_REDIRECT ?? "false",
              SESSION_COOKIE_SECURE: process.env.SESSION_COOKIE_SECURE ?? "false",
              CSRF_COOKIE_SECURE: process.env.CSRF_COOKIE_SECURE ?? "false",
              AUTH_REFRESH_COOKIE_SECURE: process.env.AUTH_REFRESH_COOKIE_SECURE ?? "false",
              FRONTEND_URL: process.env.FRONTEND_URL ?? devUrl,
              DB_HOST: dbHost,
              DB_PORT: dbPort,
              DB_NAME: dbName,
              DB_USER: dbUser,
              DB_PASSWORD: dbPassword,
              PLAYWRIGHT_BACKEND_PORT: String(backendPort),
              REDIS_HOST: redisHost,
              REDIS_PORT: redisPort,
              REDIS_ADDR: redisAddr,
              REDIS_SENTINEL_ADDRS: "",
              REDIS_SENTINEL_MASTER_NAME: "",
              REDIS_SENTINELS: "",
              REDIS_SENTINEL_USERNAME: "",
              REDIS_SENTINEL_PASSWORD: "",
              ENGINE_HOST: process.env.ENGINE_HOST ?? "127.0.0.1",
              ENGINE_PORT: String(process.env.ENGINE_PORT ?? enginePort),
              ENGINE_INSTANCE_ID: process.env.ENGINE_INSTANCE_ID ?? "playwright-engine-1",
              ENGINE_TARGETS:
                process.env.ENGINE_TARGETS ??
                `playwright-engine-1=${process.env.ENGINE_HOST ?? "127.0.0.1"}:${String(process.env.ENGINE_PORT ?? enginePort)}`,
              ENGINE_CALLBACK_URL: process.env.ENGINE_CALLBACK_URL ?? `${backendUrl}/api/runs/engine-events`,
              ENGINE_CALLBACK_SECRET: callbackSecret,
              MEMORY_GRPC_HOST: process.env.MEMORY_GRPC_HOST ?? memoryGrpcHost,
              MEMORY_GRPC_PORT: String(process.env.MEMORY_GRPC_PORT ?? memoryGrpcPort),
              FORGEGRAPH_RUNTIME_MODE: process.env.FORGEGRAPH_RUNTIME_MODE ?? "cloud",
              OPENAI_API_KEY: process.env.OPENAI_API_KEY ?? "playwright-openai-key",
              OPENAI_BASE_URL: preferredLlmBaseUrl,
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
              ENGINE_RUN_STATE_MODE: process.env.ENGINE_RUN_STATE_MODE ?? "control-plane-http",
              ENGINE_CALLBACK_SECRET: callbackSecret,
              ENGINE_EVENT_VERBOSITY: process.env.ENGINE_EVENT_VERBOSITY ?? "default",
              ENGINE_INSTANCE_ID: process.env.ENGINE_INSTANCE_ID ?? "playwright-engine-1",
              ENGINE_EVENT_SPOOL_PATH: engineEventSpoolPath,
              REDIS_ADDR: redisAddr,
              REDIS_HOST: redisHost,
              REDIS_PORT: redisPort,
              REDIS_SENTINEL_ADDRS: "",
              REDIS_SENTINEL_MASTER_NAME: "",
              REDIS_SENTINELS: "",
              REDIS_SENTINEL_USERNAME: "",
              REDIS_SENTINEL_PASSWORD: "",
              TENANT_ID: runtimeFixtureTenantId,
              MARKETPLACE_MANIFEST_REFRESH_SECONDS: process.env.MARKETPLACE_MANIFEST_REFRESH_SECONDS ?? "1",
              FORGEGRAPH_RUNTIME_MODE: process.env.FORGEGRAPH_RUNTIME_MODE ?? "cloud",
              TOOL_MANIFEST_DIR: process.env.TOOL_MANIFEST_DIR ?? "",
              DATABASE_URL: engineDatabaseUrl,
              MEMORY_GRPC_HOST: process.env.MEMORY_GRPC_HOST ?? memoryGrpcHost,
              MEMORY_GRPC_PORT: String(process.env.MEMORY_GRPC_PORT ?? memoryGrpcPort),
              OPENAI_API_KEY: process.env.OPENAI_API_KEY ?? "playwright-openai-key",
              OPENAI_BASE_URL: preferredLlmBaseUrl,
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
        ]
      : []),
  ],
});
