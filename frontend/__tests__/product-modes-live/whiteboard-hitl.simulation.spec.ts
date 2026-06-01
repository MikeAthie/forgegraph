import { execFileSync } from "child_process";
import path from "path";

import { expect, test, type APIRequestContext, type Page, type TestInfo } from "@playwright/test";

import { getAccessToken, openBackendAuthenticatedPage, type TestUser } from "../e2e/helpers";

type HitlFixture = {
  company_id: string;
  whiteboard_id: string;
  human_card_id: string;
  evaluation_card_id: string;
  approval_task_id: string;
  evaluation_run_id: string;
  users: {
    routing: TestUser;
    department: TestUser;
    approver: TestUser;
    customer: TestUser;
  };
};

type BoardCard = {
  id: string;
  status: string;
  review_kind?: string | null;
  links: Record<string, string | undefined>;
  allowed_actions: string[];
};

type BoardSnapshot = {
  cards: BoardCard[];
};

const API_BASE_URL = (
  process.env.PLAYWRIGHT_API_URL ??
  process.env.NEXT_PUBLIC_API_URL ??
  "http://127.0.0.1:8000"
).replace(/\/$/, "");
const backendDir = path.join(__dirname, "..", "..", "..", "backend");
const forbiddenVerticalRoutePattern =
  /\/api\/(?:marketing|growth-marketing|digital-marketing|marketing-campaigns|atlas|legacy)(?:\/|$)/i;

function seedHitlFixture(testInfo: TestInfo): HitlFixture {
  const project = testInfo.project.name.replace(/[^a-z0-9]+/gi, "-").toLowerCase();
  const prefix = `hitl-${project}-${Date.now()}-${Math.random().toString(16).slice(2, 8)}`;
  const raw = execFileSync("python", ["manage.py", "seed_whiteboard_hitl_fixture", "--prefix", prefix, "--json"], {
    cwd: backendDir,
    env: {
      ...process.env,
      USE_SQLITE: process.env.USE_SQLITE ?? "false",
      SQLITE_DB_PATH: process.env.SQLITE_DB_PATH,
    },
    encoding: "utf8",
  }).trim();
  return JSON.parse(raw) as HitlFixture;
}

function collectApiRequests(page: Page): string[] {
  const requests: string[] = [];
  page.on("request", (request) => {
    const url = new URL(request.url());
    if (url.pathname.startsWith("/api/")) {
      requests.push(url.pathname);
    }
  });
  return requests;
}

async function getBoard(request: APIRequestContext, token: string, whiteboardId: string): Promise<BoardSnapshot> {
  const response = await request.get(`${API_BASE_URL}/api/whiteboards/${whiteboardId}/board`, {
    headers: { Authorization: `Bearer ${token}` },
  });
  expect(response.ok(), await response.text()).toBeTruthy();
  const body = (await response.json()) as { data: { board: BoardSnapshot } };
  return body.data.board;
}

async function expectBoardCard(
  request: APIRequestContext,
  token: string,
  fixture: HitlFixture,
  cardId: string,
  predicate: (card: BoardCard) => boolean,
  message: string,
): Promise<BoardCard> {
  let latest: BoardCard | undefined;
  try {
    await expect
      .poll(
        async () => {
          const board = await getBoard(request, token, fixture.whiteboard_id);
          latest = board.cards.find((card) => card.id === cardId);
          return latest ? predicate(latest) : false;
        },
        { timeout: 30_000, message },
      )
      .toBe(true);
  } catch (error) {
    throw new Error(`${message} Latest card: ${JSON.stringify(latest ?? null)}`, { cause: error });
  }
  if (!latest) {
    throw new Error(`Card ${cardId} was not present on board ${fixture.whiteboard_id}.`);
  }
  return latest;
}

async function getApprovalStatus(request: APIRequestContext, token: string, approvalTaskId: string): Promise<string> {
  const response = await request.get(`${API_BASE_URL}/api/approvals/${approvalTaskId}`, {
    headers: { Authorization: `Bearer ${token}` },
  });
  expect(response.ok(), await response.text()).toBeTruthy();
  const body = (await response.json()) as { data: { status: string } };
  return body.data.status;
}

function expectNoVerticalRoutes(paths: string[]): void {
  expect(paths.filter((path) => forbiddenVerticalRoutePattern.test(path))).toEqual([]);
}

async function clickBoardPatchAction(page: Page, fixture: HitlFixture, testId: string, cardId: string): Promise<void> {
  const button = page.getByTestId(`${testId}-${cardId}`);
  await expect(button).toBeVisible({ timeout: 30_000 });
  await expect(button).toBeEnabled();
  const patchResponse = page.waitForResponse(
    (response) => {
      const url = new URL(response.url());
      return (
        url.pathname === `/api/whiteboards/${fixture.whiteboard_id}/board/cards/${cardId}` &&
        response.request().method() === "PATCH"
      );
    },
    { timeout: 30_000 },
  );
  await button.click();
  const response = await patchResponse;
  expect(response.ok(), await response.text()).toBeTruthy();
}

async function refreshBoardThroughUi(page: Page, fixture: HitlFixture): Promise<void> {
  const refreshResponse = page.waitForResponse(
    (response) => {
      const url = new URL(response.url());
      return (
        url.pathname === `/api/whiteboards/${fixture.whiteboard_id}/board` && response.request().method() === "GET"
      );
    },
    { timeout: 30_000 },
  );
  await page.getByTestId("whiteboard-board-refresh").click();
  const response = await refreshResponse;
  expect(response.ok(), await response.text()).toBeTruthy();
}

test.describe("Whiteboard HITL board simulation", () => {
  test("drives department review, human approval, completion, and customer-safe visibility", async ({
    browser,
    request,
  }, testInfo) => {
    const fixture = seedHitlFixture(testInfo);
    const departmentToken = await getAccessToken(request, fixture.users.department);
    const approverToken = await getAccessToken(request, fixture.users.approver);
    const customerToken = await getAccessToken(request, fixture.users.customer);

    const departmentPage = await browser.newPage();
    const departmentRoutes = collectApiRequests(departmentPage);
    await openBackendAuthenticatedPage(
      departmentPage,
      request,
      fixture.users.department,
      `/companies/${fixture.company_id}`,
    );
    await departmentPage.getByTestId("whiteboard-board").scrollIntoViewIfNeeded();
    await expect(departmentPage.getByTestId(`whiteboard-board-card-${fixture.human_card_id}`)).toBeVisible();

    await clickBoardPatchAction(departmentPage, fixture, "whiteboard-card-start", fixture.human_card_id);
    await expectBoardCard(
      request,
      departmentToken,
      fixture,
      fixture.human_card_id,
      (card) => card.status === "in_progress",
      "Department user should start the assigned card.",
    );
    await expect(departmentPage.getByTestId(`whiteboard-card-status-${fixture.human_card_id}`)).toContainText(
      /in_progress/i,
    );

    await clickBoardPatchAction(departmentPage, fixture, "whiteboard-card-ready", fixture.human_card_id);
    await expectBoardCard(
      request,
      departmentToken,
      fixture,
      fixture.human_card_id,
      (card) => card.status === "ready_for_review" && card.review_kind === "human_approval",
      "Ready card with ApprovalTask should require human approval.",
    );
    await expect(departmentPage.getByTestId(`whiteboard-card-review-${fixture.human_card_id}`)).toContainText(
      /Human approval required/i,
    );
    await expect(departmentPage.getByTestId(`whiteboard-card-complete-${fixture.human_card_id}`)).toHaveCount(0);

    const evaluationCard = await expectBoardCard(
      request,
      departmentToken,
      fixture,
      fixture.evaluation_card_id,
      (card) => card.review_kind === "automated_gate" && card.links.evaluation_run_id === fixture.evaluation_run_id,
      "Evaluation-linked card should serialize as an automated gate.",
    );
    expect(evaluationCard.status).toBe("ready_for_review");
    await expect(departmentPage.getByTestId(`whiteboard-card-review-${fixture.evaluation_card_id}`)).toContainText(
      /Automated evaluation required/i,
    );

    const customerBoard = await getBoard(request, customerToken, fixture.whiteboard_id);
    const customerHumanCard = customerBoard.cards.find((card) => card.id === fixture.human_card_id);
    const customerEvaluationCard = customerBoard.cards.find((card) => card.id === fixture.evaluation_card_id);
    expect(customerHumanCard?.review_kind).toBe("department");
    expect(customerHumanCard?.links.approval_task_id).toBeUndefined();
    expect(customerEvaluationCard?.review_kind).toBe("department");
    expect(customerEvaluationCard?.links.evaluation_run_id).toBeUndefined();
    expect(JSON.stringify(customerBoard)).not.toContain(fixture.approval_task_id);
    expect(JSON.stringify(customerBoard)).not.toContain(fixture.evaluation_run_id);

    const customerPage = await browser.newPage();
    const customerRoutes = collectApiRequests(customerPage);
    await openBackendAuthenticatedPage(
      customerPage,
      request,
      fixture.users.customer,
      `/companies/${fixture.company_id}`,
    );
    await customerPage.getByTestId("whiteboard-board").scrollIntoViewIfNeeded();
    await expect(customerPage.getByTestId(`whiteboard-card-review-${fixture.human_card_id}`)).toContainText(
      /Department review required/i,
    );
    await expect(customerPage.getByTestId(`whiteboard-card-complete-${fixture.human_card_id}`)).toHaveCount(0);

    const approverPage = await browser.newPage();
    const approverRoutes = collectApiRequests(approverPage);
    await openBackendAuthenticatedPage(
      approverPage,
      request,
      fixture.users.approver,
      `/approvals?item=${fixture.approval_task_id}`,
    );
    const decisionBrief = approverPage
      .getByRole("heading", { name: "Decision brief" })
      .locator("xpath=ancestor::section[1]");
    await expect(decisionBrief.getByText(/Approve the board card after department review/i).first()).toBeVisible();
    await approverPage.getByPlaceholder(/Add guidance/i).fill("Approved in the browser HITL simulation.");
    const resolveResponse = approverPage.waitForResponse(
      (response) =>
        response.url().includes(`/api/approvals/${fixture.approval_task_id}/resolve`) &&
        response.request().method() === "POST",
    );
    await approverPage.getByRole("button", { name: "Approve with notes" }).click();
    await expect((await resolveResponse).ok()).toBeTruthy();
    await expect
      .poll(() => getApprovalStatus(request, approverToken, fixture.approval_task_id), {
        timeout: 30_000,
        message: "ApprovalTask should be approved through the UI.",
      })
      .toBe("approved");

    await refreshBoardThroughUi(departmentPage, fixture);
    await expect(departmentPage.getByTestId(`whiteboard-card-complete-${fixture.human_card_id}`)).toBeVisible();
    await clickBoardPatchAction(departmentPage, fixture, "whiteboard-card-complete", fixture.human_card_id);
    await expectBoardCard(
      request,
      departmentToken,
      fixture,
      fixture.human_card_id,
      (card) => card.status === "completed",
      "Department user should complete card only after backend approval is satisfied.",
    );
    await expect(departmentPage.getByTestId(`whiteboard-card-status-${fixture.human_card_id}`)).toContainText(
      /completed/i,
    );

    expectNoVerticalRoutes([...departmentRoutes, ...approverRoutes, ...customerRoutes]);

    await Promise.all([departmentPage.close(), approverPage.close(), customerPage.close()]);
  });
});
