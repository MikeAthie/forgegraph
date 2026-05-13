import { test } from "@playwright/test";

test.describe("Product modes", () => {
  test.fixme("ATLAS managed-service customer acceptance waits for customer-facing service UI", async () => {
    // Blocker: the repo currently has generic service repository/API contracts, but no customer-facing
    // service catalog, engagement status, approval, or deliverables pages to exercise with Playwright.
    //
    // Future passing coverage should seed an ATLAS service catalog item, a customer Company, an engagement,
    // approvals, and deliverables, then drive the real UI through the generic service facade:
    // - /api/service-catalog
    // - /api/service-engagements
    // - /api/service-engagements/:engagementId/deliverables
    // - /api/approvals
    // - /api/work-artifacts or /api/report-runs for published deliverables
    //
    // The customer-facing route must show intake, status, approvals, deliverables, and service history while
    // hiding pack internals, manifests, namespaces, private config, and any vertical route such as /api/marketing/*.
  });
});
