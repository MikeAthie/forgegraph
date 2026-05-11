import { expect, test, type Page, type TestInfo } from "@playwright/test";
import { execFileSync } from "child_process";
import { existsSync } from "fs";
import fs from "fs/promises";
import path from "path";

import { getAccessToken, openBackendAuthenticatedPage, type TestUser } from "../e2e/helpers";

const API_BASE_URL = (
  process.env.PLAYWRIGHT_API_URL ??
  process.env.NEXT_PUBLIC_API_URL ??
  "http://127.0.0.1:8000"
).replace(/\/$/, "");

const REPO_ROOT = path.resolve(__dirname, "..", "..", "..");
const BACKEND_DIR = path.join(REPO_ROOT, "backend");
const PHASE1_VIDEO_DIR = path.resolve(
  __dirname,
  "..",
  "..",
  "..",
  process.env.PLAYWRIGHT_LEGACY_PHASE1_TUTORIAL_DIR ?? "docs/legacy-ultimate-test/tutorial-videos/phase1",
);

const LEGACY_EMAIL = process.env.PLAYWRIGHT_LEGACY_EMAIL ?? "legacy.glasswear.test@example.com";
const LEGACY_PASSWORD =
  process.env.PLAYWRIGHT_LEGACY_PASSWORD ?? process.env.LEGACY_TEST_PASSWORD ?? "ForgeGraphLegacy!12345";
const LEGACY_OPENROUTER_ENV_VAR = process.env.PLAYWRIGHT_LEGACY_OPENROUTER_ENV_VAR ?? "OPENROUTER";
const LEGACY_OPENROUTER_FALLBACK_ENV_VAR =
  process.env.PLAYWRIGHT_LEGACY_OPENROUTER_FALLBACK_ENV_VAR ?? "OPENROUTER_API_KEY";
const LEGACY_IMAGE_MODEL =
  process.env.PLAYWRIGHT_LEGACY_IMAGE_MODEL ??
  process.env.OPENROUTER_IMAGE_MODEL ??
  "black-forest-labs/flux.2-klein-4b";
const UV_BINARY = resolveUvBinary();

const IMAGE_PROMPT =
  "Create a premium product-campaign image draft for Legacy Glasswear: limited designer optical frames on a clean editorial surface, high-end retail lighting, no text, no logos, no people, no private customer data.";

type BootstrapEvidence = {
  observed_data: {
    company_id: string;
    products_imported: number;
    active_units_imported: number;
  };
  verification_result: {
    passed: boolean;
  };
};

type CredentialImport = {
  credential_id: string;
  provider: string;
  key_present: boolean;
};

function resolveUvBinary(): string {
  if (process.env.PLAYWRIGHT_UV_PATH) {
    return process.env.PLAYWRIGHT_UV_PATH;
  }

  if (process.platform === "win32") {
    try {
      const firstMatch = execFileSync("where.exe", ["uv"], { encoding: "utf8" }).split(/\r?\n/)[0]?.trim();
      if (firstMatch) {
        return firstMatch;
      }
    } catch {
      return "uv.exe";
    }
  }

  return "uv";
}

test.skip(
  process.env.PLAYWRIGHT_LEGACY_PHASE1_CAPTURE !== "true",
  "Set PLAYWRIGHT_LEGACY_PHASE1_CAPTURE=true to record the Legacy Phase 1 media proof.",
);

test.skip(
  !process.env[LEGACY_OPENROUTER_ENV_VAR] && !process.env[LEGACY_OPENROUTER_FALLBACK_ENV_VAR],
  `Set ${LEGACY_OPENROUTER_ENV_VAR} or ${LEGACY_OPENROUTER_FALLBACK_ENV_VAR} for the Legacy Phase 1 OpenRouter media proof.`,
);

test.describe.configure({ mode: "serial" });
test.setTimeout(360_000);

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
  expect(overflow, "page should not have horizontal overflow in media proof capture").toBeLessThanOrEqual(1);
}

async function waitForGeneratedImageOrProviderError(
  page: Page,
  imageCountBefore: number,
): Promise<{ status: "image" } | { status: "blocked"; message: string }> {
  const imageReady = page
    .waitForFunction(
      (countBefore) =>
        document.querySelectorAll('[data-testid="media-draft-preview-image"]').length > Number(countBefore),
      imageCountBefore,
      { timeout: 180_000, polling: 2000 },
    )
    .then(() => ({ status: "image" }) as const);
  const errorReady = page
    .getByTestId("media-error")
    .waitFor({ state: "visible", timeout: 180_000 })
    .then(async () => {
      const message = (await page.getByTestId("media-error").textContent())?.trim();
      return {
        status: "blocked",
        message: message || "OpenRouter media generation failed before an image draft became visible.",
      } as const;
    });

  return Promise.race([imageReady, errorReady]);
}

function runBootstrapCommand(): BootstrapEvidence {
  if (!existsSync(BACKEND_DIR)) {
    throw new Error(`Backend directory does not exist: ${BACKEND_DIR}`);
  }

  const raw = execFileSync(
    UV_BINARY,
    ["run", "python", "manage.py", "legacy_glasswear_first_run", "--database", "postgres", "--json", "--strict"],
    {
      cwd: BACKEND_DIR,
      env: { ...process.env, LEGACY_TEST_PASSWORD: LEGACY_PASSWORD },
      encoding: "utf8",
      maxBuffer: 32 * 1024 * 1024,
    },
  );
  return JSON.parse(raw) as BootstrapEvidence;
}

function importLegacyOpenRouterCredential(): CredentialImport {
  const raw = execFileSync(
    UV_BINARY,
    [
      "run",
      "python",
      "manage.py",
      "import_legacy_openrouter_credential",
      "--env-var",
      LEGACY_OPENROUTER_ENV_VAR,
      "--fallback-env-var",
      LEGACY_OPENROUTER_FALLBACK_ENV_VAR,
      "--image-model",
      LEGACY_IMAGE_MODEL,
      "--json",
    ],
    {
      cwd: BACKEND_DIR,
      env: { ...process.env, LEGACY_TEST_PASSWORD: LEGACY_PASSWORD },
      encoding: "utf8",
      maxBuffer: 32 * 1024 * 1024,
    },
  );
  return JSON.parse(raw) as CredentialImport;
}

async function savePhase1Video(
  page: Page,
  testInfo: TestInfo,
  metadata: Record<string, unknown>,
  slug = "01-openrouter-image-draft",
): Promise<void> {
  await expectNoHorizontalOverflow(page);
  await pauseForVideo(page, 1000);
  const video = page.video();
  await page.close();
  if (!video) {
    throw new Error("Playwright video recording is not enabled for this Phase 1 capture.");
  }

  await fs.mkdir(PHASE1_VIDEO_DIR, { recursive: true });
  const sourcePath = await video.path();
  const videoPath = path.join(PHASE1_VIDEO_DIR, `${slug}.webm`);
  const metadataPath = path.join(PHASE1_VIDEO_DIR, `${slug}.json`);
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
          "Sanitized product and styling context only. No customer data, payment data, addresses, API keys, raw logs, or private messages.",
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

async function writeProcessEvaluation(metadata: Record<string, unknown>) {
  const finalResultVisible = metadata.final_result_visible === true;
  await fs.mkdir(PHASE1_VIDEO_DIR, { recursive: true });
  const evaluationPath = path.join(PHASE1_VIDEO_DIR, "process-evaluation-2026-05-08.md");
  const body = [
    "# Legacy Phase 1 Media Proof Video Evaluation: 2026-05-08",
    "",
    "## Capture",
    "",
    "- Command: `PLAYWRIGHT_RUNTIME_TARGET=docker PLAYWRIGHT_REUSE_EXISTING_SERVER=true PLAYWRIGHT_DEMO_CAPTURE=true PLAYWRIGHT_LEGACY_PHASE1_CAPTURE=true PLAYWRIGHT_DEMO_CAPTURE_DIR=logs/legacy-phase1-media-playwright-output npx playwright test --config=playwright.demo.config.ts __tests__/demo-captures/legacy-phase1-media-videos.spec.ts --project=demo-chromium`",
    `- Stable output: \`${finalResultVisible ? "01-openrouter-image-draft.webm" : "01-openrouter-image-draft-blocked.webm"}\``,
    "",
    "## Observed Data",
    "",
    "```json",
    JSON.stringify(metadata, null, 2),
    "```",
    "",
    "## Evaluation",
    "",
    finalResultVisible
      ? "- The recording shows the Legacy workspace, media draft controls, sanitized prompt, image generation action, backend-owned draft status, and the generated image rendered from the archive content API."
      : "- The recording shows the Legacy workspace, media draft controls, sanitized prompt, image generation action, and the provider quota blocker rendered through the product surface.",
    finalResultVisible
      ? "- The image is visible in the final frame and loaded with non-zero natural dimensions."
      : "- No generated image is visible because the OpenRouter key or selected model could not produce an image in this run.",
    finalResultVisible
      ? "- The generated image is converted into an Instagram/Facebook publication package with caption, CTA, and human approval status visible in the product surface."
      : "- No social publication package was created because the image generation step was blocked.",
    "- The capture avoids raw logs, customer data, payment data, addresses, API keys, and publishing actions.",
    "",
    "## Decision",
    "",
    finalResultVisible
      ? "Use this as the Phase 1 commercial media operation proof. Video-generation evidence should be kept in the Phase 1 evidence packet because Veo polling can outlive a short tutorial recording."
      : "Do not use this as the final tutorial proof. Enable OpenRouter image-generation access or provide a key/model with image output, then rerun until `final_result_visible=true`.",
    "",
  ].join("\n");
  await fs.writeFile(evaluationPath, body, "utf8");
}

test("01 - OpenRouter image draft is generated and visible in the Legacy workspace", async ({
  page,
  request,
}, testInfo) => {
  const bootstrap = runBootstrapCommand();
  expect(bootstrap.verification_result.passed).toBe(true);
  expect(bootstrap.observed_data.products_imported).toBe(21);
  expect(bootstrap.observed_data.active_units_imported).toBe(62);

  const credential = importLegacyOpenRouterCredential();
  expect(credential.provider).toBe("openrouter");
  expect(credential.key_present).toBe(true);

  const user: TestUser = { email: LEGACY_EMAIL, password: LEGACY_PASSWORD };
  const accessToken = await getAccessToken(request, user);
  const companyId = bootstrap.observed_data.company_id;

  await openBackendAuthenticatedPage(page, request, user, `/companies/${companyId}`);
  await expect(page.getByText(/Legacy Glasswear/i).first()).toBeVisible({ timeout: 30_000 });
  await page.getByTestId("commerce-inventory-panel").scrollIntoViewIfNeeded();
  await expect(page.getByTestId("media-drafts-panel")).toBeVisible({ timeout: 30_000 });
  await pauseForVideo(page);

  const imageCountBefore = await page.getByTestId("media-draft-preview-image").count();
  await page.getByTestId("media-prompt").fill(IMAGE_PROMPT);
  await pauseForVideo(page);
  if (imageCountBefore === 0) {
    await page.getByTestId("generate-media-image-draft").click();

    const outcome = await waitForGeneratedImageOrProviderError(page, imageCountBefore);
    if (outcome.status === "blocked") {
      const metadata = {
        company_id: companyId,
        credential_id: credential.credential_id,
        image_model: LEGACY_IMAGE_MODEL,
        existing_image_reused: false,
        final_result_visible: false,
        blocked_reason: outcome.message,
      };
      await savePhase1Video(page, testInfo, metadata, "01-openrouter-image-draft-blocked");
      await writeProcessEvaluation(metadata);
      throw new Error(outcome.message);
    }
  }

  const image = page.getByTestId("media-draft-preview-image").first();
  await expect(image).toBeVisible();
  const imageMetrics = await image.evaluate((element) => {
    const img = element as HTMLImageElement;
    return {
      naturalWidth: img.naturalWidth,
      naturalHeight: img.naturalHeight,
      renderedWidth: img.getBoundingClientRect().width,
      renderedHeight: img.getBoundingClientRect().height,
    };
  });
  expect(imageMetrics.naturalWidth).toBeGreaterThan(0);
  expect(imageMetrics.naturalHeight).toBeGreaterThan(0);
  await expect(page.getByText(/draft/i).first()).toBeVisible();
  await pauseForVideo(page, 1600);

  await expect(page.getByTestId("social-post-package-card")).toBeVisible();
  await expect(page.getByTestId("social-post-caption-preview").first()).toBeVisible();
  await page.getByTestId("create-social-post-draft").first().click();
  await expect(page.getByTestId("social-post-draft-status").first()).toContainText(/approval requested/i, {
    timeout: 30_000,
  });
  await pauseForVideo(page, 1200);

  const assetQuery = new URLSearchParams({ company_id: companyId, asset_type: "image", status: "active" });
  const response = await request.get(`${API_BASE_URL}/api/archive/assets?${assetQuery.toString()}`, {
    headers: { Authorization: `Bearer ${accessToken}` },
  });
  expect(response.ok()).toBeTruthy();
  const archivePayload = (await response.json()) as {
    data: { assets: Array<{ id: string; latest_version_id: string }> };
  };
  expect(archivePayload.data.assets.length).toBeGreaterThan(0);
  const latestAsset = archivePayload.data.assets[0];

  const companyOpsQuery = new URLSearchParams({ company_id: companyId });
  const companyOpsResponse = await request.get(`${API_BASE_URL}/api/company-ops/overview?${companyOpsQuery}`, {
    headers: { Authorization: `Bearer ${accessToken}` },
  });
  expect(companyOpsResponse.ok()).toBeTruthy();
  const companyOpsPayload = (await companyOpsResponse.json()) as {
    data: {
      company_ops: {
        publication_drafts: Array<{
          id: string;
          asset_id: string | null;
          channel: string;
          status: string;
          approval_task_id: string | null;
          body: string;
        }>;
      };
    };
  };
  const socialDraft = companyOpsPayload.data.company_ops.publication_drafts.find(
    (draft) => draft.asset_id === latestAsset?.id,
  );
  expect(socialDraft?.status).toBe("approval_requested");
  expect(socialDraft?.approval_task_id).toBeTruthy();

  const metadata = {
    company_id: companyId,
    credential_id: credential.credential_id,
    image_model: LEGACY_IMAGE_MODEL,
    existing_image_reused: imageCountBefore > 0,
    image_assets_visible: archivePayload.data.assets.length,
    latest_image_asset_id: latestAsset?.id ?? null,
    latest_image_version_id: latestAsset?.latest_version_id ?? null,
    image_metrics: imageMetrics,
    social_publication_draft_id: socialDraft?.id ?? null,
    social_publication_channel: socialDraft?.channel ?? null,
    social_publication_status: socialDraft?.status ?? null,
    social_publication_approval_task_id: socialDraft?.approval_task_id ?? null,
    commercial_package_visible: true,
    approval_gated: socialDraft?.status === "approval_requested" && Boolean(socialDraft?.approval_task_id),
    final_result_visible: true,
  };
  await savePhase1Video(page, testInfo, metadata);
  await writeProcessEvaluation(metadata);
});
