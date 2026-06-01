import { expect, test } from "@playwright/test";

import {
  buildLegacyMultiPackProductModeState,
  collectProductModeApiRequests,
  installProductModeMocks,
  legacyMultiPackIds,
  sawProductModeApiPath,
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

const forbiddenVerticalRoutePattern =
  /\/api\/(?:marketing|growth-marketing|digital-marketing|marketing-campaigns|atlas|legacy)(?:\/|$)/i;

test.describe("Whiteboard board command center", () => {
  test("renders generic lanes and role-aware board controls", async ({ page, request }, testInfo) => {
    const apiRequests = collectProductModeApiRequests(page);
    const user = createTestUser(testInfo, "whiteboard-board");
    await ensureUserRegistered(request, user);
    const accessToken = await getAccessToken(request, user);
    const seed = await createCompanyViaApi(request, accessToken, {
      name: "Legacy Eyewear",
      companyType: "Eyewear Company",
      objective: "Exercise generic whiteboard board routes.",
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
    await page.getByTestId("whiteboard-board").scrollIntoViewIfNeeded();

    await expect(page.getByTestId("whiteboard-board-lane-strategy")).toContainText(/Strategy intake/i);
    await expect(page.getByTestId("whiteboard-board-lane-content-creative")).toContainText(/Content production/i);
    await expect(page.getByTestId("whiteboard-card-review-legacy-whiteboard-performance-task")).toContainText(
      /Automated evaluation required/i,
    );
    await expect(page.getByTestId("whiteboard-routing-create-card")).toBeVisible();
    await expect(page.getByTestId("whiteboard-card-reassign-legacy-whiteboard-strategy-card")).toBeVisible();
    await page.getByTestId("whiteboard-card-start-legacy-whiteboard-strategy-card").click();
    await expect(page.getByTestId("whiteboard-card-status-legacy-whiteboard-strategy-card")).toContainText(
      /in_progress/i,
    );

    expect(sawProductModeApiPath(apiRequests, `/api/whiteboards/${legacyMultiPackIds.whiteboard}/board`)).toBe(true);
    expect(
      sawProductModeApiPath(
        apiRequests,
        `/api/whiteboards/${legacyMultiPackIds.whiteboard}/board/cards/legacy-whiteboard-strategy-card`,
      ),
    ).toBe(true);
    expect(verticalProductModeApiRequests(apiRequests, forbiddenVerticalRoutePattern)).toEqual([]);
  });

  test("customer-safe board hides internal cards and structural controls", async ({ page, request }, testInfo) => {
    const user = createTestUser(testInfo, "whiteboard-board-customer");
    await ensureUserRegistered(request, user);
    const accessToken = await getAccessToken(request, user);
    const seed = await createCompanyViaApi(request, accessToken, {
      name: "Legacy Eyewear",
      companyType: "Eyewear Company",
      objective: "Exercise customer-safe whiteboard board rendering.",
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
    const board = state.whiteboardBoards?.[0];
    if (board) {
      board.allowed_actions = {
        can_modify_structure: false,
        can_update_assigned_cards: false,
        can_view_internal: false,
      };
      board.cards = board.cards.filter((card) => card.customer_visible);
      board.cards.forEach((card) => {
        card.reason = "";
        card.allowed_actions = [];
        card.blocker_reason = "";
        card.links = {};
      });
      board.lanes = board.lanes
        .map((lane) => ({
          ...lane,
          cards: lane.cards.filter((card) => card.customer_visible),
        }))
        .filter((lane) => lane.cards.length);
    }

    await installProductModeMocks(page, state);
    await openBackendAuthenticatedPage(page, request, user, "/companies");
    await page
      .getByRole("link", { name: /Legacy Eyewear/i })
      .first()
      .click();
    await page.waitForURL(new RegExp(`/companies/${seed.companyId}$`));
    await page.getByTestId("whiteboard-board").scrollIntoViewIfNeeded();

    await expect(page.getByTestId("whiteboard-board")).toContainText(/Content production/i);
    await expect(page.getByText(/Deployment readiness/i)).toHaveCount(0);
    await expect(page.getByTestId("whiteboard-routing-create-card")).toHaveCount(0);
    await expect(page.locator('[data-testid^="whiteboard-card-reassign-"]')).toHaveCount(0);
  });
});
