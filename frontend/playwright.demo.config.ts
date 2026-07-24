import { defineConfig, devices } from "@playwright/test";
import path from "path";

import baseConfig from "./playwright.config";

const captureDir = path.resolve(
  __dirname,
  "..",
  process.env.PLAYWRIGHT_DEMO_CAPTURE_DIR ?? "artifacts/fiverr/forgegraph/.playwright",
);
const demoWebServer = Array.isArray(baseConfig.webServer)
  ? baseConfig.webServer
      .filter((server) => !String(server.command ?? "").includes("go run ."))
      .map((server) => {
        if (!String(server.command ?? "").startsWith("python scripts/run_playwright_backend.py")) {
          return server;
        }
        return {
          ...server,
          command: `${process.env.PLAYWRIGHT_BACKEND_PYTHON ?? "python"} scripts/run_playwright_backend.py`,
        };
      })
  : baseConfig.webServer;

export default defineConfig({
  ...baseConfig,
  webServer: demoWebServer,
  testDir: "./__tests__/demo-captures",
  testMatch: ["**/*.spec.ts"],
  testIgnore: [],
  retries: 0,
  reporter: [
    ["line"],
    [
      "html",
      {
        outputFolder: "playwright-demo-report",
        open: "never",
      },
    ],
  ],
  outputDir: path.join(captureDir, "playwright-output"),
  use: {
    ...baseConfig.use,
    screenshot: "only-on-failure",
    trace: "retain-on-failure",
    video: {
      mode: "on",
      size: { width: 1440, height: 900 },
    },
    viewport: { width: 1440, height: 900 },
  },
  projects: [
    {
      name: "demo-chromium",
      use: {
        ...devices["Desktop Chrome"],
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
  ],
});
