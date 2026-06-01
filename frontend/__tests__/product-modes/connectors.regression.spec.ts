import { expect, test } from "@playwright/test";

import {
  buildLegacyMultiPackProductModeState,
  collectProductModeApiRequests,
  installProductModeMocks,
  legacyMultiPackIds,
  verticalProductModeApiRequests,
} from "./fixtures";
import {
  createCompanyViaApi,
  createTestUser,
  ensureUserRegistered,
  fetchLatestGraphVersion,
  getAccessToken,
  openBackendAuthenticatedPage,
} from "../e2e/helpers";

const forbiddenVerticalRoutePattern = /\/api\/(?:marketing|atlas|legacy)(?:\/|$)/i;
const forbiddenPayloadPattern =
  /(?:secret-api-key|bearer\s+|authorization|access_token|app_secret|owner@example\.com|\+15550101234|<p>|private caption|https:\/\/cdn\.example\/private|https:\/\/social\.example\/posts\/private)/i;

test.describe("Product-mode connector contracts", () => {
  test("mocked connector channels expose sanitized evidence and honest missing-connector blocks", async ({
    page,
    request,
  }, testInfo) => {
    const apiRequests = collectProductModeApiRequests(page);
    const user = createTestUser(testInfo, "product-mode-connectors");
    await ensureUserRegistered(request, user);
    const accessToken = await getAccessToken(request, user);
    const seed = await createCompanyViaApi(request, accessToken, {
      name: "Legacy Eyewear",
      companyType: "Eyewear Company",
      objective: "Exercise generic connector contracts in product-mode fixtures.",
      autonomyMode: "assisted",
      aiAccessMode: "managed",
    });
    const latestVersion = await fetchLatestGraphVersion(request, accessToken, seed.companyId);
    const state = buildLegacyMultiPackProductModeState({
      companyId: seed.companyId,
      companyName: "Legacy Eyewear",
      graphVersion: latestVersion,
      pendingApprovalCount: 0,
      operations: [],
    });

    await installProductModeMocks(page, state);
    await openBackendAuthenticatedPage(page, request, user, "/companies");
    await page
      .getByRole("link", { name: /Legacy Eyewear/i })
      .first()
      .click();
    await page.waitForURL(new RegExp(`/companies/${seed.companyId}$`));

    await page.getByTestId("whiteboard-deployment-section").scrollIntoViewIfNeeded();
    await expect(page.getByTestId("whiteboard-deployment-channel-email")).toContainText(/Receipt|Captured/i);
    await expect(page.getByTestId("whiteboard-deployment-channel-whatsapp")).toContainText(/Blocked/i);
    await expect(page.getByTestId("whiteboard-deployment-channel-instagram")).toContainText(/Blocked/i);
    await expect(page.getByTestId("whiteboard-deployment-channel-facebook")).toContainText(/Blocked/i);
    await expect(page.getByTestId("whiteboard-deployment-channel-landing_page")).toContainText(/Blocked/i);
    await expect(page.getByTestId("whiteboard-performance-source-email")).toContainText(/Metrics|Collected|Receipt/i);
    await expect(page.getByTestId("whiteboard-performance-source-social")).toContainText(/Blocked/i);
    await expect(page.getByText(/fake success/i)).toHaveCount(0);

    const connectorContracts = await page.evaluate(async (whiteboardId) => {
      const deployment = await fetch(`/api/whiteboards/${whiteboardId}/deployment`).then((response) => response.json());
      const performance = await fetch(`/api/whiteboards/${whiteboardId}/performance`).then((response) =>
        response.json(),
      );
      return { deployment: deployment.data.deployment_contract, performance: performance.data.performance_contract };
    }, legacyMultiPackIds.whiteboard);

    const emailChannel = connectorContracts.deployment.channels.find(
      (channel: { id: string }) => channel.id === "email",
    );
    expect(emailChannel.receipt.result.mode).toBe("dry_run");
    expect(emailChannel.receipt.result.evidence_mode).toBe("sandbox");
    expect(emailChannel.receipt.result.recipient_count).toBe(0);
    expect(emailChannel.receipt.result.recipient_domains).toEqual([]);
    expect(emailChannel.receipt.result.recipient_hashes).toEqual([]);
    for (const channelId of ["whatsapp", "instagram", "facebook", "landing_page"]) {
      const channel = connectorContracts.deployment.channels.find(
        (candidate: { id: string }) => candidate.id === channelId,
      );
      expect(channel.status).toBe("blocked");
      expect(channel.blocked_reason_code).toBe("connector_missing");
      expect(channel.tool_execution_id).toBe("");
      expect(channel.company_signal_id).toBeTruthy();
      expect(channel.routing_record_id).toBeTruthy();
      expect(channel.receipt ?? null).toBeNull();
    }

    const renderedPayload = JSON.stringify(connectorContracts);
    expect(renderedPayload).not.toMatch(forbiddenPayloadPattern);
    expect(verticalProductModeApiRequests(apiRequests, forbiddenVerticalRoutePattern)).toEqual([]);
  });
});
