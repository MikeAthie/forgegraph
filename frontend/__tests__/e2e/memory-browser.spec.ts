import { expect, test, type Route } from "@playwright/test";

import { createTestUser, ensureUserRegistered, openAuthenticatedPage } from "./helpers";

function apiSuccess<T>(data: T) {
  return {
    data,
    meta: {
      requestId: "playwright-memory-browser",
      timestamp: "2026-04-01T12:00:00.000Z",
    },
  };
}

test.describe("Memory Browser", () => {
  test("shows curated observations seeded through backend-facing memory APIs", async ({ page, request }, testInfo) => {
    const user = createTestUser(testInfo, "memory-browser");
    await ensureUserRegistered(request, user);

    const observation = {
      id: "aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaa1",
      tenant_id: "org-playwright-memory",
      graph_id: "workflow-memory-001",
      run_id: null,
      session_id: null,
      agent_id: "agent-memory-001",
      memory_chunk_id: null,
      type: "customer_memory",
      title: "Jackie Memory Dossier",
      content: "Jackie prefers concise planning updates and values concrete next steps.",
      scope: "graph",
      topic_key: "jackie-memory",
      tool_name: "memory_write",
      revision_count: 1,
      duplicate_count: 0,
      last_seen_at: "2026-04-01T11:55:00.000Z",
      created_at: "2026-04-01T11:55:00.000Z",
      updated_at: "2026-04-01T11:55:00.000Z",
      deleted_at: null,
      is_deleted: false,
    };

    await page.route(/\/api\/decisions\/count(?:\?.*)?$/, async (route: Route) => {
      await route.fulfill({
        status: 200,
        contentType: "application/json",
        body: JSON.stringify(apiSuccess({ count: 0 })),
      });
    });

    await page.route(/\/api\/orgs\/me(?:\?.*)?$/, async (route: Route) => {
      await route.fulfill({
        status: 200,
        contentType: "application/json",
        body: JSON.stringify(
          apiSuccess({
            organization: {
              id: "org-playwright-memory",
              name: "Playwright Memory Org",
              created_at: "2026-04-01T10:00:00.000Z",
              updated_at: "2026-04-01T10:00:00.000Z",
            },
            role: "owner",
            governance: {
              current_role_capabilities: {
                can_view_observations: true,
                can_delete_observations: true,
                can_manage_retention: true,
                can_export_memory_data: true,
                can_manage_members: true,
              },
              role_capabilities: {},
            },
          }),
        ),
      });
    });

    await page.route(/\/api\/memory\/observations\/timeline(?:\?.*)?$/, async (route: Route) => {
      await route.fulfill({
        status: 200,
        contentType: "application/json",
        body: JSON.stringify(apiSuccess([observation])),
      });
    });

    await page.route(/\/api\/memory\/observations\/search(?:\?.*)?$/, async (route: Route) => {
      const query = new URL(route.request().url()).searchParams.get("query") ?? "";
      const matches = query.toLowerCase().includes("dossier") ? [observation] : [];
      await route.fulfill({
        status: 200,
        contentType: "application/json",
        body: JSON.stringify(apiSuccess(matches)),
      });
    });

    await page.route(new RegExp(`/api/memory/observations/${observation.id}(?:\\?.*)?$`), async (route: Route) => {
      await route.fulfill({
        status: 200,
        contentType: "application/json",
        body: JSON.stringify(apiSuccess(observation)),
      });
    });

    await openAuthenticatedPage(page, user, "/memory", {
      organizationId: "org-playwright-memory",
    });

    await expect(page.getByRole("heading", { name: /browse the knowledge layer/i })).toBeVisible();
    await expect(page.getByRole("button", { name: /jackie memory dossier/i })).toBeVisible();

    await page.getByRole("searchbox", { name: /search observations/i }).fill("dossier");
    await expect(page.getByRole("button", { name: /jackie memory dossier/i })).toBeVisible();

    await page.getByRole("button", { name: /jackie memory dossier/i }).click();
    await expect(page.getByText(/observation detail/i).first()).toBeVisible();
    await expect(page.getByText(/concise planning updates and values concrete next steps/i).first()).toBeVisible();
    await expect(page.getByText(/topic jackie-memory/i).last()).toBeVisible();
  });
});
