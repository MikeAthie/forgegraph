import { defineConfig, devices } from "@playwright/test";
import path from "path";

import baseConfig from "./playwright.config";

const captureDir = path.resolve(__dirname, "..", process.env.PLAYWRIGHT_DEMO_CAPTURE_DIR ?? "logs/demo-captures");

export default defineConfig({
  ...baseConfig,
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
      size: { width: 1280, height: 720 },
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
