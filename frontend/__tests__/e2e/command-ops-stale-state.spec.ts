import fs from "fs";
import path from "path";

import { expect, test } from "@playwright/test";

const repoRoot = path.resolve(__dirname, "../../..");

test.describe("Command Ops stale state guard", () => {
  test("renders stale, rebuilding, and degraded projection states from backend metadata", () => {
    const source = fs.readFileSync(path.join(repoRoot, "frontend/pages/overview/index.tsx"), "utf8");

    expect(source).toContain("projectionStatusLabel");
    expect(source).toContain("overviewCardTone");
    expect(source).toContain("rebuilding");
    expect(source).toContain("degraded");
    expect(source).toContain('stateFeed.status === "unavailable"');
    expect(source).not.toContain("setInterval(");
  });
});
