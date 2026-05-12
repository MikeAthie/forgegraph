import { expect, test, type APIRequestContext, type Page, type TestInfo } from "@playwright/test";
import fs from "fs/promises";
import path from "path";

import {
  createCompanyViaApi,
  createTestUser,
  ensureUserRegistered,
  getAccessToken,
  loginLive,
  openBackendAuthenticatedPage,
} from "../e2e/helpers";

const API_BASE_URL = (
  process.env.PLAYWRIGHT_API_URL ??
  process.env.NEXT_PUBLIC_API_URL ??
  "http://127.0.0.1:8000"
).replace(/\/$/, "");

const CAPTURE_DIR = path.resolve(
  __dirname,
  "..",
  "..",
  "..",
  process.env.PLAYWRIGHT_DEMO_CAPTURE_DIR ?? "../logs/demo-captures",
);

test.skip(
  process.env.PLAYWRIGHT_DEMO_CAPTURE !== "true",
  "Set PLAYWRIGHT_DEMO_CAPTURE=true to record promo-safe walkthrough videos.",
);

async function pauseForVideo(page: Page, ms = 900) {
  if (process.env.PLAYWRIGHT_DEMO_FAST === "true") {
    return;
  }
  await page.waitForTimeout(ms);
}

async function writeDemoEvidence(testInfo: TestInfo, name: string, payload: Record<string, unknown>) {
  await fs.mkdir(CAPTURE_DIR, { recursive: true });
  const safeName = name.replace(/[^a-z0-9]+/gi, "-").toLowerCase();
  const filePath = path.join(CAPTURE_DIR, `${safeName}-${Date.now()}.json`);
  await fs.writeFile(
    filePath,
    JSON.stringify(
      {
        name,
        test_id: testInfo.testId,
        project: testInfo.project.name,
        captured_at: new Date().toISOString(),
        sensitive_data_policy:
          "Sanitized demo account only. No API keys, payment details, addresses, private customer messages, raw logs, or DB views.",
        ...payload,
      },
      null,
      2,
    ),
    "utf8",
  );
}

async function createDemoSignal(
  request: APIRequestContext,
  accessToken: string,
  companyId: string,
  externalKey: string,
) {
  const response = await request.post(`${API_BASE_URL}/api/company-ops/signals`, {
    headers: {
      Authorization: `Bearer ${accessToken}`,
      "Idempotency-Key": `demo-signal:${externalKey}`,
    },
    data: {
      company_id: companyId,
      signal_type: "manual",
      title: "Demo demand signal",
      summary: "Sanitized buyer interest from a demo channel. No private customer data included.",
      source: "demo_capture",
      external_key: externalKey,
      channel: "demo",
      contact_alias: "demo-buyer",
      metadata: {
        capture: true,
        pii: "sanitized",
      },
    },
  });
  expect(response.ok()).toBeTruthy();
  return ((await response.json()) as { data: { signal: { id: string } } }).data.signal;
}

async function launchDemoOperation(
  request: APIRequestContext,
  accessToken: string,
  companyId: string,
  operationType: string,
  idempotencyKey: string,
  sourceSignalId?: string,
) {
  const response = await request.post(`${API_BASE_URL}/api/company-ops/operations`, {
    headers: {
      Authorization: `Bearer ${accessToken}`,
      "Idempotency-Key": idempotencyKey,
    },
    data: {
      company_id: companyId,
      operation_type: operationType,
      source_signal_id: sourceSignalId ?? null,
      context_note: "Demo capture operation using sanitized business context only.",
    },
  });
  expect(response.ok()).toBeTruthy();
  return ((await response.json()) as { data: { operation: { id: string; status: string } } }).data.operation;
}

test("video 1 - create a company operating workspace", async ({ page, request }, testInfo) => {
  const user = createTestUser(testInfo, "demo-create-company");
  await ensureUserRegistered(request, user);

  await loginLive(page, request, user, "/companies/new");
  await pauseForVideo(page);

  const companyName = process.env.PLAYWRIGHT_DEMO_COMPANY_NAME ?? "Legacy Glasswear Demo";
  const objective =
    process.env.PLAYWRIGHT_DEMO_COMPANY_OBJECTIVE ??
    "Operate a limited inventory commerce test with stock, cash, learning, and reorder discipline.";

  await page.getByTestId("company-name-input").fill(companyName);
  await page.getByTestId("company-objective-input").fill(objective);
  await pauseForVideo(page);

  await page.getByRole("button", { name: /^continue$/i }).click();
  await expect(page.getByText(/suggested setup/i).first()).toBeVisible();
  await pauseForVideo(page);

  await page.getByRole("button", { name: /^continue$/i }).click();
  await expect(page.getByText(/adjust the team/i).first()).toBeVisible();
  await pauseForVideo(page);

  await page.getByRole("button", { name: /^continue$/i }).click();
  await expect(page.getByText(/choose operating rules/i).first()).toBeVisible();
  await pauseForVideo(page);

  await page.getByRole("button", { name: /^continue$/i }).click();
  await expect(page.getByText(/review and launch/i).first()).toBeVisible();
  await page
    .getByTestId("company-operation-brief-input")
    .fill("Prepare the first operating brief and identify what should happen next.");
  await pauseForVideo(page);

  await page.getByTestId("company-create-submit").click();
  await page.waitForURL(/\/companies\/[0-9a-f-]+$/i, { timeout: 60_000 });
  await expect(page.getByRole("heading", { name: new RegExp(companyName, "i") }).first()).toBeVisible({
    timeout: 30_000,
  });
  await pauseForVideo(page, 1400);

  await writeDemoEvidence(testInfo, "video-1-create-company", {
    company_name: companyName,
    final_url: page.url(),
    walkthrough: "Created a company through product UI and launched the first operation.",
  });
});

test("video 2 - supervise signals and operating loop", async ({ page, request }, testInfo) => {
  const user = createTestUser(testInfo, "demo-supervise");
  await ensureUserRegistered(request, user);
  const accessToken = await getAccessToken(request, user);
  const company = await createCompanyViaApi(request, accessToken, {
    name: "Demo Operating Company",
    companyType: "Commerce Operator",
    objective: "Supervise demand, stock, cash, drafts, and next operations from one workspace.",
  });
  const signal = await createDemoSignal(request, accessToken, company.companyId, `supervise-${testInfo.workerIndex}`);
  const operation = await launchDemoOperation(
    request,
    accessToken,
    company.companyId,
    "daily_operating_brief",
    `demo-daily-brief:${company.companyId}`,
    signal.id,
  );

  await openBackendAuthenticatedPage(page, request, user, `/companies/${company.companyId}`);
  await expect(page.getByRole("heading", { name: /demo operating company/i }).first()).toBeVisible();
  await pauseForVideo(page);

  await page.getByTestId("commerce-inventory-panel").scrollIntoViewIfNeeded();
  await expect(page.getByText(/operating loop/i).first()).toBeVisible({ timeout: 30_000 });
  await expect(page.getByText(/demo demand signal/i).first()).toBeVisible();
  await pauseForVideo(page, 1600);

  await writeDemoEvidence(testInfo, "video-2-supervise-operating-loop", {
    company_id: company.companyId,
    signal_id: signal.id,
    operation_id: operation.id,
    operation_status: operation.status,
    walkthrough: "Opened the company workspace and inspected the generic Operating Loop surface.",
  });
});

test("video 3 - duplicate trigger regression stays idempotent", async ({ page, request }, testInfo) => {
  const user = createTestUser(testInfo, "demo-regression");
  await ensureUserRegistered(request, user);
  const accessToken = await getAccessToken(request, user);
  const company = await createCompanyViaApi(request, accessToken, {
    name: "Demo Regression Company",
    companyType: "Commerce Operator",
    objective: "Show that duplicate business triggers converge to one durable operation.",
  });
  const signal = await createDemoSignal(request, accessToken, company.companyId, `regression-${testInfo.workerIndex}`);
  const idempotencyKey = `demo-duplicate-trigger:${company.companyId}`;
  const { firstOperation, replayedOperation } = await launchDemoOperation(
    request,
    accessToken,
    company.companyId,
    "sold_out_demand_capture",
    idempotencyKey,
    signal.id,
  ).then(async (firstOperation) => ({
    firstOperation,
    replayedOperation: await launchDemoOperation(
      request,
      accessToken,
      company.companyId,
      "sold_out_demand_capture",
      idempotencyKey,
      signal.id,
    ),
  }));

  expect(replayedOperation.id).toBe(firstOperation.id);

  await openBackendAuthenticatedPage(page, request, user, `/companies/${company.companyId}`);
  await expect(page.getByRole("heading", { name: /demo regression company/i }).first()).toBeVisible();
  await page.getByTestId("commerce-inventory-panel").scrollIntoViewIfNeeded();
  await expect(page.getByText(/operating loop/i).first()).toBeVisible({ timeout: 30_000 });
  await pauseForVideo(page, 1600);

  await writeDemoEvidence(testInfo, "video-3-idempotent-regression", {
    company_id: company.companyId,
    signal_id: signal.id,
    first_operation_id: firstOperation.id,
    replayed_operation_id: replayedOperation.id,
    duplicate_trigger_proof: firstOperation.id === replayedOperation.id,
    walkthrough: "Repeated the same operation trigger with the same idempotency key and showed one durable result.",
  });
});
