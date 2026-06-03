import { spawn, spawnSync } from "node:child_process";
import { dirname, resolve } from "node:path";
import { fileURLToPath } from "node:url";

const scriptDir = dirname(fileURLToPath(import.meta.url));
const frontendDir = resolve(scriptDir, "..");
const repoRoot = resolve(frontendDir, "..");
const composeFiles = ["-f", "docker-compose.yml", "-f", "docker-compose.kafka.yml"];

const env = normalizeChildEnv({
  ...process.env,
  LIVE_LLM_E2E: process.env.LIVE_LLM_E2E ?? "true",
  LIVE_LLM_PROVIDER: process.env.LIVE_LLM_PROVIDER ?? "openai",
  OPENAI_API_KEY: process.env.OPENAI_API_KEY ?? "local-playwright-key",
  OPENAI_BASE_URL: process.env.OPENAI_BASE_URL ?? "http://127.0.0.1:12434/v1",
  PLAYWRIGHT_DOCKER_LOCAL_LLM_URL: process.env.PLAYWRIGHT_DOCKER_LOCAL_LLM_URL ?? "http://127.0.0.1:12434/v1",
  PLAYWRIGHT_RUNTIME_TARGET: process.env.PLAYWRIGHT_RUNTIME_TARGET ?? "docker",
  PLAYWRIGHT_REUSE_EXISTING_SERVER: process.env.PLAYWRIGHT_REUSE_EXISTING_SERVER ?? "true",
  PLAYWRIGHT_DOCKER_FRONTEND_URL: process.env.PLAYWRIGHT_DOCKER_FRONTEND_URL ?? "http://127.0.0.1:3000",
  PLAYWRIGHT_DOCKER_BACKEND_URL: process.env.PLAYWRIGHT_DOCKER_BACKEND_URL ?? "http://127.0.0.1:8000",
  PLAYWRIGHT_ATLAS_REQUIRE_BOARD_KAFKA: "true",
  WHITEBOARD_BOARD_KAFKA_ENABLED: "true",
});

await main();

async function main() {
  runDockerCompose([
    "up",
    "-d",
    "redpanda",
    "backend",
    "backend-run-queue",
    "backend-runtime-intents",
    "backend-os-projections",
    "memory-grpc",
    "frontend",
  ]);
  await waitForHttp(`${env.PLAYWRIGHT_DOCKER_BACKEND_URL}/health`, "backend");
  await waitForHttp(env.PLAYWRIGHT_DOCKER_FRONTEND_URL, "frontend");

  runDockerCompose([
    "exec",
    "-d",
    "backend",
    "python",
    "manage.py",
    "publish_whiteboard_board_outbox",
    "--limit",
    process.env.WHITEBOARD_BOARD_KAFKA_PUBLISH_LIMIT ?? "100",
    "--sleep",
    process.env.WHITEBOARD_BOARD_KAFKA_PUBLISH_SLEEP ?? "0.5",
  ]);
  runDockerCompose([
    "exec",
    "-d",
    "backend",
    "python",
    "manage.py",
    "consume_whiteboard_board_kafka",
    "--limit",
    process.env.WHITEBOARD_BOARD_KAFKA_CONSUME_LIMIT ?? "100",
    "--poll-timeout",
    process.env.WHITEBOARD_BOARD_KAFKA_POLL_TIMEOUT ?? "1",
    "--sleep",
    process.env.WHITEBOARD_BOARD_KAFKA_CONSUME_SLEEP ?? "0.5",
  ]);

  const playwrightArgs = [
    "playwright",
    "test",
    "__tests__/product-modes-live/atlas-agency-full-flow.e2e.spec.ts",
    "--project=chromium",
    "--workers=1",
  ];
  const command = process.platform === "win32" ? "cmd.exe" : "npx";
  const args = process.platform === "win32" ? ["/d", "/s", "/c", ["npx", ...playwrightArgs].join(" ")] : playwrightArgs;

  const child = spawn(command, args, {
    cwd: frontendDir,
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
}

async function waitForHttp(url, label) {
  const timeoutMs = Number(process.env.PLAYWRIGHT_DOCKER_READY_TIMEOUT_MS ?? "180000");
  const deadline = Date.now() + timeoutMs;
  let lastError = "";
  while (Date.now() < deadline) {
    try {
      const response = await fetch(url);
      if (response.ok) {
        return;
      }
      lastError = `${response.status} ${response.statusText}`;
    } catch (error) {
      lastError = error instanceof Error ? error.message : String(error);
    }
    await sleep(1000);
  }
  throw new Error(`Timed out waiting for ${label} at ${url}: ${lastError}`);
}

function sleep(ms) {
  return new Promise((resolve) => setTimeout(resolve, ms));
}

function runDockerCompose(args) {
  const result = spawnSync("docker", ["compose", ...composeFiles, ...args], {
    cwd: repoRoot,
    env,
    stdio: "inherit",
  });
  if (result.status !== 0) {
    process.exit(result.status ?? 1);
  }
}

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
