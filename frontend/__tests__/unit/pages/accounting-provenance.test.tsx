import fs from "fs";
import path from "path";

const repoRoot = path.resolve(__dirname, "../../../..");

describe("accounting provenance", () => {
  it("keeps cost backend-owned and revenue/profit explicitly unavailable", () => {
    const source = [
      "frontend/pages/overview/index.tsx",
      "frontend/domain/repositories/overviewRepository.ts",
      "frontend/lib/api.ts",
    ]
      .map((relativePath) => fs.readFileSync(path.join(repoRoot, relativePath), "utf8"))
      .join("\n");

    expect(source).toMatch(/accountingMetrics\.cost/);
    expect(source).toMatch(/backend_ledger/);
    expect(source).toMatch(/Not yet instrumented/);
    expect(source).not.toMatch(/\b(revenueMultiplier|profitToday|revenueToday)\b/);
    expect(source).not.toMatch(/formatCurrency\([^)]*\b(revenue|profit)\b/i);
  });
});
