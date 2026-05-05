import fs from "fs";
import path from "path";

const repoRoot = path.resolve(__dirname, "../../../..");

describe("state feed reconnect contract", () => {
  it("uses backend state versions for resume and exposes full resync explicitly", () => {
    const source = fs.readFileSync(path.join(repoRoot, "frontend/hooks/useStateFeed.ts"), "utf8");

    expect(source).toMatch(/last_seen_state_version/);
    expect(source).toMatch(/type:\s*"resume"/);
    expect(source).toMatch(/full_resync_required/);
    expect(source).toMatch(/onFullResync/);
    expect(source).not.toMatch(/localStorage/);
  });
});
