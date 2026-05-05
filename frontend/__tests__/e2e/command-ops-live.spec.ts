import { execFileSync } from "child_process";
import path from "path";

import { expect, test, type APIRequestContext } from "@playwright/test";

import {
  createTestUser,
  ensureUserRegistered,
  getAccessToken,
  login,
  seedFrontendControlPlaneFixture,
} from "./helpers";

const backendDir = path.join(__dirname, "..", "..", "..", "backend");
const managementEnv = {
  ...process.env,
  DJANGO_SETTINGS_MODULE: process.env.DJANGO_SETTINGS_MODULE ?? "config.test_settings",
};

async function waitForOrganizationWebSocketSubscription(
  request: APIRequestContext,
  accessToken: string,
  organizationId: string,
) {
  const apiBase = (process.env.PLAYWRIGHT_API_URL ?? "http://127.0.0.1:8002").replace(/\/$/, "");
  await expect
    .poll(
      async () => {
        const response = await request.get(`${apiBase}/api/operator/ws/subscribers`, {
          headers: { Authorization: `Bearer ${accessToken}` },
        });
        if (!response.ok()) {
          return 0;
        }
        const body = (await response.json()) as {
          data?: { by_org?: Array<{ organization_id?: string; connections?: number }> };
          by_org?: Array<{ organization_id?: string; connections?: number }>;
        };
        const snapshot = body.data ?? body;
        const organizationSubscription = snapshot.by_org?.find((item) => item.organization_id === organizationId);
        return organizationSubscription?.connections ?? 0;
      },
      { timeout: 30_000 },
    )
    .toBeGreaterThan(0);
}

function createProjectedDecisionAndNotify(organizationId: string, label: string) {
  const script = `
from django.utils import timezone
from infrastructure.orm.models import DecisionRecord, Organization
from application.services.organization_state_feed import publish_organization_state_feed_event

organization = Organization.objects.get(id="${organizationId}")
decision = DecisionRecord.objects.create(
    organization=organization,
    decision_type="human_approval",
    status="pending",
    external_key="e2e-command-ops-live-${Date.now()}",
    context_json={"summary": "${label}"},
    requested_at=timezone.now(),
)
publish_organization_state_feed_event(
    organization=organization,
    event_type="decision.created",
    resource_type="decision",
    resource_id=str(decision.id),
    event_id=f"e2e-command-ops-live:{decision.id}",
    payload={},
)
`;
  execFileSync("python", ["manage.py", "shell", "-c", script], {
    cwd: backendDir,
    env: managementEnv,
    encoding: "utf8",
  });
}

test.describe("Command Ops live organization state feed", () => {
  test("updates overview from a backend organization state event without manual refresh", async ({
    page,
    request,
  }, testInfo) => {
    test.setTimeout(60_000);
    const user = createTestUser(testInfo, "command-ops-live");
    await ensureUserRegistered(request, user);
    const fixture = seedFrontendControlPlaneFixture(user);
    const accessToken = await getAccessToken(request, user);

    await login(page, user);
    const overviewResponse = page.waitForResponse(
      (response) =>
        response.request().method() === "GET" &&
        response.url().includes("/api/system-state/overview") &&
        response.status() === 200,
    );
    const orgSocket = page.waitForEvent("websocket", { timeout: 15_000 });
    await page.goto("/overview");
    await overviewResponse;
    await orgSocket;
    await waitForOrganizationWebSocketSubscription(request, accessToken, fixture.organizationId);

    await expect(page.getByRole("heading", { name: /command ops/i }).first()).toBeVisible();

    const label = `Live Command Ops approval ${Date.now()}`;
    createProjectedDecisionAndNotify(fixture.organizationId, label);

    await expect(page.getByText(label).first()).toBeVisible({ timeout: 20_000 });
  });
});
