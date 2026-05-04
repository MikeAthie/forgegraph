import fs from "fs";
import path from "path";

const repoRoot = path.resolve(__dirname, "../../../..");

function readFrontendSource(relativePath: string): string {
  return fs.readFileSync(path.join(repoRoot, relativePath), "utf8");
}

describe("financial metric provenance guardrail", () => {
  const overviewSource = readFrontendSource("frontend/pages/overview/index.tsx");
  const accountingSource = readFrontendSource("frontend/pages/accounting.tsx");
  const combinedSource = `${overviewSource}\n${accountingSource}`;

  it("does not compute revenue, profit, or accounting projections locally", () => {
    expect(combinedSource).not.toMatch(/\b(revenueMultiplier|weeklyMultiplier|monthlyMultiplier)\b/);
    expect(combinedSource).not.toMatch(/\b(revenueToday|revenueMonth|profitToday|profitMonth)\b/);
    expect(combinedSource).not.toMatch(/Mock value for company-OS scenarios/);
    expect(combinedSource).not.toMatch(/modeled revenue/i);
    expect(combinedSource).not.toMatch(/projected profit/i);
    expect(combinedSource).not.toMatch(/Projected revenue|Projected profit/);
    expect(combinedSource).not.toMatch(/formatCurrency\([^)]*\b(revenue|profit)\b/i);
  });

  it("shows unavailable revenue and profit with backend provenance metadata", () => {
    expect(combinedSource).toMatch(/Not yet instrumented/);
    expect(combinedSource).toMatch(/metricProvenance\.revenue/);
    expect(combinedSource).toMatch(/metricProvenance\.profit/);
    expect(combinedSource).toMatch(/metricProvenance\.totalCostUsd/);
  });
});
