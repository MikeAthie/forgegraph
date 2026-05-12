import { expect, test } from "@playwright/test";

import { createTestUser, ensureUserRegistered, seedFrontendControlPlaneFixture } from "./helpers";

const API_BASE_URL = (
  process.env.PLAYWRIGHT_API_URL ??
  process.env.NEXT_PUBLIC_API_URL ??
  "http://127.0.0.1:8000"
).replace(/\/$/, "");

test.describe("Command retry idempotency", () => {
  test("retries a backend command without duplicating the mutation", async ({ request }, testInfo) => {
    const user = createTestUser(testInfo, "command-retry");
    await ensureUserRegistered(request, user);
    const fixture = seedFrontendControlPlaneFixture(user);

    const loginResponse = await request.post(`${API_BASE_URL}/api/auth/login`, {
      data: { email: user.email, password: user.password },
    });
    expect(loginResponse.ok()).toBeTruthy();
    const loginBody = (await loginResponse.json()) as { access: string };
    const commandId = `e2e-command-retry:${fixture.runIds.running}:cancel`;
    const headers = {
      Authorization: `Bearer ${loginBody.access}`,
      "Idempotency-Key": commandId,
    };

    const { first, second } = await request.post(`${API_BASE_URL}/api/runs/${fixture.runIds.running}/cancel`, {
      headers,
      data: {},
    }).then(async (first) => ({
      first,
      second: await request.post(`${API_BASE_URL}/api/runs/${fixture.runIds.running}/cancel`, {
        headers,
        data: {},
      }),
    }));

    expect(first.ok()).toBeTruthy();
    expect(second.ok()).toBeTruthy();
    const [firstBody, secondBody] = await Promise.all([first.json(), second.json()]);
    expect(firstBody.data.idempotency.status).toBe("applied");
    expect(secondBody.data.idempotency.status).toBe("already_applied");
    expect(secondBody.data.duplicate).toBe(true);
  });
});
