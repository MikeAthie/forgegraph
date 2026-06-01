import { spawn } from "node:child_process";

const env = normalizeChildEnv({
  ...process.env,
  LIVE_LLM_E2E: process.env.LIVE_LLM_E2E ?? "true",
  LIVE_LLM_PROVIDER: process.env.LIVE_LLM_PROVIDER ?? "openai",
  OPENAI_API_KEY: process.env.OPENAI_API_KEY ?? "local-playwright-key",
  OPENAI_BASE_URL: process.env.OPENAI_BASE_URL ?? "http://127.0.0.1:12434/v1",
  PLAYWRIGHT_DOCKER_LOCAL_LLM_URL:
    process.env.PLAYWRIGHT_DOCKER_LOCAL_LLM_URL ?? "http://127.0.0.1:12434/v1",
  PLAYWRIGHT_RUNTIME_TARGET: process.env.PLAYWRIGHT_RUNTIME_TARGET ?? "docker",
  PLAYWRIGHT_REUSE_EXISTING_SERVER: process.env.PLAYWRIGHT_REUSE_EXISTING_SERVER ?? "true",
  PLAYWRIGHT_DOCKER_FRONTEND_URL:
    process.env.PLAYWRIGHT_DOCKER_FRONTEND_URL ?? "http://127.0.0.1:3000",
  PLAYWRIGHT_DOCKER_BACKEND_URL:
    process.env.PLAYWRIGHT_DOCKER_BACKEND_URL ?? "http://127.0.0.1:8000",
});

const playwrightArgs = [
  "playwright",
  "test",
  "__tests__/product-modes-live/atlas-agency-full-flow.e2e.spec.ts",
  "--project=chromium",
  "--workers=1",
];
const command = process.platform === "win32" ? "cmd.exe" : "npx";
const args =
  process.platform === "win32"
    ? ["/d", "/s", "/c", ["npx", ...playwrightArgs].join(" ")]
    : playwrightArgs;

const child = spawn(command, args, {
  cwd: process.cwd(),
  env,
  stdio: "inherit",
});

child.on("exit", (code, signal) => {
  if (signal) {
    process.kill(process.pid, signal);
    return;
  }
  process.exit(code ?? 1);
});

function normalizeChildEnv(source) {
  const result = {};
  const seen = new Set();
  for (const [key, value] of Object.entries(source)) {
    if (value == null) {
      continue;
    }
    const normalizedKey = process.platform === "win32" ? key.toUpperCase() : key;
    if (seen.has(normalizedKey)) {
      continue;
    }
    seen.add(normalizedKey);
    result[key] = String(value);
  }
  return result;
}
