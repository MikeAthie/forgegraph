import {
  buildNodePaletteCatalog,
  getRecentPaletteItems,
  getRecommendedPaletteItems,
  groupPaletteItems,
  searchNodePaletteCatalog,
  updateRecentPaletteIds,
} from "@/lib/node-palette-catalog";

describe("node-palette-catalog", () => {
  it("builds catalog entries with tags and badges", () => {
    const catalog = buildNodePaletteCatalog();
    const prompt = catalog.find((item) => item.id === "prompt");

    expect(prompt).toBeDefined();
    expect(prompt?.tags.length).toBeGreaterThan(0);
    expect(prompt?.badges.length).toBeGreaterThan(0);
  });

  it("ranks exact matches above fuzzy matches", () => {
    const catalog = buildNodePaletteCatalog();
    const results = searchNodePaletteCatalog(catalog, "http");

    expect(results.length).toBeGreaterThan(0);
    expect(results[0].id).toBe("http");
  });

  it("groups by category with deterministic ordering", () => {
    const catalog = buildNodePaletteCatalog();
    const grouped = groupPaletteItems(catalog);

    expect(grouped[0][0]).toBe("AI");
    expect(grouped.some(([category]) => category === "Annotations")).toBe(true);
  });

  it("returns recommended defaults", () => {
    const catalog = buildNodePaletteCatalog();
    const recommended = getRecommendedPaletteItems(catalog);

    expect(recommended.map((item) => item.id)).toEqual(
      expect.arrayContaining(["prompt", "http", "output"]),
    );
  });

  it("updates recent ids with recency ordering and dedupe", () => {
    const updated = updateRecentPaletteIds(["prompt", "http"], "prompt");
    expect(updated).toEqual(["prompt", "http"]);

    const next = updateRecentPaletteIds(updated, "transform");
    expect(next[0]).toBe("transform");
    expect(next).toEqual(expect.arrayContaining(["prompt", "http"]));
  });

  it("returns recent items in id order while skipping invalid ids", () => {
    const catalog = buildNodePaletteCatalog();
    const recent = getRecentPaletteItems(catalog, ["unknown", "output", "prompt"]);

    expect(recent.map((item) => item.id)).toEqual(["output", "prompt"]);
  });
});
