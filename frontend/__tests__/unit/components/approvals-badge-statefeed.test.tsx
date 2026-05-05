import fs from "fs";
import path from "path";

const repoRoot = path.resolve(__dirname, "../../../..");

describe("approvals badge state feed behavior", () => {
  it("invalidates approval counts from the organization feed and only polls as degraded fallback", () => {
    const source = fs.readFileSync(path.join(repoRoot, "frontend/components/shell/OsShell.tsx"), "utf8");

    expect(source).toMatch(/useStateFeed/);
    expect(source).toMatch(/decision\.created/);
    expect(source).toMatch(/decision\.updated/);
    expect(source).toMatch(/invalidateQueries\(\{ queryKey: \["decisions", "count"\] \}\)/);
    expect(source).toMatch(/refetchInterval:\s*decisionBadgeFeed\.status === "unavailable" \? 30_000 : false/);
    expect(source).not.toMatch(/setInterval\([^)]*decisionsApi\.count/s);
  });
});
