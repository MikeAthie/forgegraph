import {
  buildEdgeRouteLanes,
  getConnectionFeedback,
  GRAPH_EDITOR_SNAP_GRID,
  snapPositionToGrid,
  validateGraphConnection,
} from "@/lib/graph-editor-interactions";

describe("graph-editor-interactions", () => {
  describe("validateGraphConnection", () => {
    it("rejects missing endpoints", () => {
      const result = validateGraphConnection({ source: "a", target: null }, []);

      expect(result).toEqual({ valid: false, reason: "missing_endpoint" });
    });

    it("rejects self connections", () => {
      const result = validateGraphConnection({ source: "a", target: "a" }, []);

      expect(result).toEqual({ valid: false, reason: "self_connection" });
    });

    it("rejects duplicate edges", () => {
      const result = validateGraphConnection({ source: "a", target: "b" }, [{ source: "a", target: "b" }]);

      expect(result).toEqual({ valid: false, reason: "duplicate_connection" });
    });

    it("accepts valid unique connections", () => {
      const result = validateGraphConnection({ source: "a", target: "b" }, [{ source: "a", target: "c" }]);

      expect(result).toEqual({ valid: true });
    });
  });

  describe("getConnectionFeedback", () => {
    it("returns actionable duplicate feedback", () => {
      expect(getConnectionFeedback("duplicate_connection")).toEqual({
        title: "Connection already exists",
        description: "Use a different target or remove the existing edge first.",
      });
    });
  });

  describe("snapPositionToGrid", () => {
    it("snaps to configured grid", () => {
      const snapped = snapPositionToGrid({ x: 22, y: 37 }, GRAPH_EDITOR_SNAP_GRID);
      expect(snapped).toEqual({ x: 15, y: 30 });
    });

    it("handles negative coordinates", () => {
      const snapped = snapPositionToGrid({ x: -8, y: -22 }, GRAPH_EDITOR_SNAP_GRID);
      expect(snapped).toEqual({ x: -15, y: -15 });
    });
  });

  describe("buildEdgeRouteLanes", () => {
    it("returns zero lane for unpaired edges", () => {
      const lanes = buildEdgeRouteLanes([{ id: "e1", source: "a", target: "b" }]);
      expect(lanes.get("e1")).toBe(0);
    });

    it("splits bidirectional pairs into distinct lanes", () => {
      const lanes = buildEdgeRouteLanes([
        { id: "e1", source: "a", target: "b" },
        { id: "e2", source: "b", target: "a" },
      ]);

      expect(lanes.get("e1")).toBe(-0.5);
      expect(lanes.get("e2")).toBe(0.5);
    });

    it("centers larger edge groups around zero", () => {
      const lanes = buildEdgeRouteLanes([
        { id: "e1", source: "a", target: "b" },
        { id: "e2", source: "a", target: "b" },
        { id: "e3", source: "b", target: "a" },
      ]);

      expect(lanes.get("e1")).toBe(-1);
      expect(lanes.get("e2")).toBe(0);
      expect(lanes.get("e3")).toBe(1);
    });
  });
});
