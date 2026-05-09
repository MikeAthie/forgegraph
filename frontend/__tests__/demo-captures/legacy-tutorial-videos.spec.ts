import { expect, test, type APIRequestContext, type Page, type TestInfo } from "@playwright/test";
import fs from "fs/promises";
import path from "path";

import { createHumanGateRunViaApi, ensureUserRegistered, getAccessToken, type TestUser } from "../e2e/helpers";

const API_BASE_URL = (
  process.env.PLAYWRIGHT_API_URL ??
  process.env.NEXT_PUBLIC_API_URL ??
  "http://127.0.0.1:8000"
).replace(/\/$/, "");

const TUTORIAL_DIR = path.resolve(
  __dirname,
  "..",
  "..",
  "..",
  process.env.PLAYWRIGHT_LEGACY_TUTORIAL_DIR ?? "docs/legacy-ultimate-test/tutorial-videos",
);

const TUTORIAL_PASSWORD = "ForgeGraphTutorial!12345";
const LEGACY_OBJECTIVE =
  "Operate a limited inventory eyewear company with stock, cash, learning, and reorder discipline.";

let tutorialUser: TestUser | null = null;
let judgeTaskId: string | null = null;

test.skip(
  process.env.PLAYWRIGHT_DEMO_CAPTURE !== "true",
  "Set PLAYWRIGHT_DEMO_CAPTURE=true to record Legacy tutorial videos.",
);

test.describe.configure({ mode: "serial" });
test.setTimeout(120_000);

async function pauseForVideo(page: Page, ms = 900) {
  if (process.env.PLAYWRIGHT_DEMO_FAST === "true") {
    return;
  }
  await page.waitForTimeout(ms);
}

async function expectNoHorizontalOverflow(page: Page) {
  const overflow = await page.evaluate(() => {
    const bodyWidth = document.body?.scrollWidth ?? 0;
    const documentWidth = document.documentElement.scrollWidth;
    return Math.max(bodyWidth, documentWidth) - window.innerWidth;
  });
  expect(overflow, "page should not have horizontal overflow in tutorial captures").toBeLessThanOrEqual(1);
}

function makeTutorialUser(testInfo: TestInfo): TestUser {
  const runId = `${Date.now()}-${testInfo.workerIndex}-${Math.random().toString(16).slice(2)}`;
  return {
    email: `legacy-tutorial-${runId}@example.com`,
    password: TUTORIAL_PASSWORD,
  };
}

async function saveTutorialVideo(
  page: Page,
  testInfo: TestInfo,
  slug: string,
  metadata: Record<string, unknown>,
): Promise<void> {
  await expectNoHorizontalOverflow(page);
  await pauseForVideo(page, 700);
  const video = page.video();
  await page.close();
  if (!video) {
    throw new Error("Playwright video recording is not enabled for this tutorial run.");
  }

  await fs.mkdir(TUTORIAL_DIR, { recursive: true });
  const sourcePath = await video.path();
  const videoPath = path.join(TUTORIAL_DIR, `${slug}.webm`);
  const metadataPath = path.join(TUTORIAL_DIR, `${slug}.json`);
  await fs.copyFile(sourcePath, videoPath);
  await fs.writeFile(
    metadataPath,
    JSON.stringify(
      {
        slug,
        captured_at: new Date().toISOString(),
        test_id: testInfo.testId,
        video: path.basename(videoPath),
        sensitive_data_policy:
          "Tutorial-only generated users and sanitized demo state. No payment data, private customer data, API keys, or raw logs.",
        ...metadata,
      },
      null,
      2,
    ),
    "utf8",
  );
  await testInfo.attach(`${slug}.webm`, { path: videoPath, contentType: "video/webm" });
  await testInfo.attach(`${slug}.json`, { path: metadataPath, contentType: "application/json" });
}

async function openTutorialPage(page: Page, targetPath: string) {
  if (!tutorialUser) {
    throw new Error("Tutorial user was not created by the registration step.");
  }
  await page.context().clearCookies();
  await page.goto("/login");
  await page.getByRole("textbox", { name: /email address/i }).fill(tutorialUser.email);
  await page.getByRole("textbox", { name: /password/i }).fill(tutorialUser.password);
  const loginResponsePromise = page.waitForResponse(
    (response) => response.url().includes("/api/auth/login") && response.request().method() === "POST",
    { timeout: 30_000 },
  );
  await page.getByRole("button", { name: /^sign in$/i }).click();
  const loginResponse = await loginResponsePromise;
  expect(loginResponse.ok()).toBeTruthy();
  await page.waitForURL(/\/companies(?:\?.*)?$/, { timeout: 30_000 });
  await page.waitForLoadState("networkidle");
  if (targetPath !== "/companies") {
    await page.goto(targetPath);
    await page.waitForLoadState("networkidle");
  }
}

async function completeObjectiveStep(page: Page, companyName: string) {
  await page.getByTestId("company-name-input").fill(companyName);
  await page.getByTestId("company-objective-input").fill(LEGACY_OBJECTIVE);
  await pauseForVideo(page);
  await page.getByRole("button", { name: /^review suggested setup$/i }).click();
  await expect(page.getByText(/suggested setup/i).first()).toBeVisible();
}

async function fetchTaskRecords(request: APIRequestContext, accessToken: string) {
  const response = await request.get(`${API_BASE_URL}/api/tasks/`, {
    headers: { Authorization: `Bearer ${accessToken}` },
  });
  expect(response.ok()).toBeTruthy();
  return ((await response.json()) as { data: Array<{ id: string; execution_id: string; title: string }> }).data;
}

async function waitForOperationTask(request: APIRequestContext, accessToken: string, runId: string) {
  let matchingTask: { id: string; execution_id: string; title: string } | null = null;
  await expect
    .poll(
      async () => {
        const tasks = await fetchTaskRecords(request, accessToken);
        matchingTask =
          tasks.find((task) => task.execution_id === runId && /finance approval/i.test(task.title)) ?? null;
        return matchingTask?.id ?? "";
      },
      {
        timeout: 90_000,
        intervals: [1000, 2000, 3000],
        message: `Timed out waiting for task projection for run ${runId}.`,
      },
    )
    .not.toBe("");
  if (!matchingTask) {
    throw new Error(`No projected task found for run ${runId}.`);
  }
  return matchingTask;
}

test("01 - registration", async ({ page }, testInfo) => {
  tutorialUser = makeTutorialUser(testInfo);

  await page.goto("/register");
  await expect(page.getByRole("button", { name: /^create account$/i })).toBeVisible();
  await pauseForVideo(page);

  await page.getByLabel(/email address/i).fill(tutorialUser.email);
  await page.getByLabel(/^password/i).fill(tutorialUser.password);
  await page.getByLabel(/confirm password/i).fill(tutorialUser.password);
  await pauseForVideo(page);

  await page.getByRole("button", { name: /^create account$/i }).click();
  await page.waitForURL(/\/login\?registered=true$/, { timeout: 30_000 });
  await expect(page.getByRole("heading", { name: /sign in/i })).toBeVisible();
  await pauseForVideo(page);

  await saveTutorialVideo(page, testInfo, "01-registration", {
    step: "Register a new tutorial user through the public UI.",
    email: tutorialUser.email,
  });
});

test("02 - company objective and suggested setup", async ({ page }, testInfo) => {
  await openTutorialPage(page, "/companies/new");
  await expect(page.getByTestId("quest-guide-overlay")).toHaveCount(0);
  await pauseForVideo(page);

  await completeObjectiveStep(page, "Legacy Tutorial Company");
  await pauseForVideo(page, 1300);

  await saveTutorialVideo(page, testInfo, "02-company-objective", {
    step: "Enter the company objective and review the suggested setup.",
  });
});

test("03 - create first department agent", async ({ page }, testInfo) => {
  await openTutorialPage(page, "/companies/new");
  await expect(page.getByTestId("quest-guide-overlay")).toHaveCount(0);
  await completeObjectiveStep(page, "Legacy Tutorial Team");

  await page.getByRole("button", { name: /^adjust team$/i }).click();
  await expect(page.getByText(/adjust the team/i).first()).toBeVisible();
  await pauseForVideo(page);

  await expect(page.getByTestId("department-chip-strategy-department")).toBeVisible();
  await page.getByTestId("skill-chip-prompt-refinement").click();
  await pauseForVideo(page, 1300);

  await page.getByRole("button", { name: /^choose policy$/i }).click();
  await expect(page.getByText(/choose operating rules/i).first()).toBeVisible();
  await page.getByRole("button", { name: /^review launch$/i }).click();
  await expect(page.getByText(/review and launch/i).first()).toBeVisible();
  await pauseForVideo(page);

  await page.getByRole("button", { name: /^create company without launch$/i }).click();
  await page.waitForURL(/\/companies\/[0-9a-f-]+(?:#.*)?$/i, { timeout: 60_000 });
  await pauseForVideo(page, 1200);

  await saveTutorialVideo(page, testInfo, "03-create-first-agent", {
    step: "Select the first department-style agent and create the company.",
  });
});

test("04 - create first judge", async ({ page, request }, testInfo) => {
  if (!tutorialUser) {
    tutorialUser = makeTutorialUser(testInfo);
    await ensureUserRegistered(request, tutorialUser);
  }

  const accessToken = await getAccessToken(request, tutorialUser);
  const run = await createHumanGateRunViaApi(request, accessToken, {
    graphName: "Legacy Tutorial Judge Operation",
    promptMessage: "Review the first tutorial task before it continues.",
    instructions: "Pause here so the tutorial can attach a task judge.",
  });
  const task = await waitForOperationTask(request, accessToken, run.runId);
  judgeTaskId = task.id;

  await openTutorialPage(page, `/tasks?task=${task.id}`);
  await expect(page.getByRole("heading", { name: "Department Activity", exact: true })).toBeVisible();
  await pauseForVideo(page);

  await page.getByLabel(/^name$/i).fill("First Task Judge");
  await page.getByLabel(/^pass$/i).fill("70");
  await page.getByLabel(/^criteria$/i).fill(["finance approval", "human decision", "tutorial task"].join("\n"));
  await page.getByLabel(/^rubric note$/i).fill("Use backend task evidence only.");
  await pauseForVideo(page, 1200);

  await page.getByRole("button", { name: /^save judge$/i }).click();
  await expect(page.getByText(/pending/i).last()).toBeVisible({ timeout: 30_000 });
  await pauseForVideo(page, 1200);

  await saveTutorialVideo(page, testInfo, "04-create-first-judge", {
    step: "Attach the first backend-owned judge to a projected task.",
    run_id: run.runId,
    task_id: task.id,
  });
});

test("05 - run first judge", async ({ page, request }, testInfo) => {
  if (!tutorialUser || !judgeTaskId) {
    throw new Error("Judge creation step did not produce a task id.");
  }

  await openTutorialPage(page, `/tasks?task=${judgeTaskId}`);
  await expect(page.getByRole("heading", { name: "Department Activity", exact: true })).toBeVisible();
  await pauseForVideo(page);

  const runJudgeButton = page.getByRole("button", { name: /^run judge$/i });
  await runJudgeButton.scrollIntoViewIfNeeded();
  await pauseForVideo(page, 500);
  await runJudgeButton.click();
  await expect(page.getByText(/passed|failed|inconclusive/i).last()).toBeVisible({ timeout: 30_000 });
  await pauseForVideo(page, 1500);

  await saveTutorialVideo(page, testInfo, "05-run-first-judge", {
    step: "Run the task judge and show the resulting grade.",
    task_id: judgeTaskId,
  });
});
