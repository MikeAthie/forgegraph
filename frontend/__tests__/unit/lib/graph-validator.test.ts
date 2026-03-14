import type { Node, Edge } from "@xyflow/react";
import {
  validateGraph,
  getQuickFixesForError,
  ValidationErrorCode,
  type ValidationError,
  type ValidationResult,
} from "@/lib/graph-validator";
import { NODE_TYPES, START_NODE_ID, END_NODE_ID } from "@/lib/graph-types";

describe("graph-validator", () => {
  // ===== Test Fixtures =====

  /**
   * Valid minimal graph: START -> prompt -> output
   */
  function createValidGraph(): { nodes: Node[]; edges: Edge[] } {
    return {
      nodes: [
        {
          id: "prompt-1",
          type: NODE_TYPES.PROMPT,
          position: { x: 0, y: 0 },
          data: { label: "Prompt 1" },
        },
        {
          id: "output-1",
          type: NODE_TYPES.OUTPUT,
          position: { x: 200, y: 0 },
          data: { label: "Output 1" },
        },
      ],
      edges: [
        { id: "e1", source: START_NODE_ID, target: "prompt-1" },
        { id: "e2", source: "prompt-1", target: "output-1" },
      ],
    };
  }

  /**
   * Graph missing start edge (no connection from START)
   */
  function createGraphMissingStart(): { nodes: Node[]; edges: Edge[] } {
    return {
      nodes: [
        {
          id: "prompt-1",
          type: NODE_TYPES.PROMPT,
          position: { x: 0, y: 0 },
          data: { label: "Prompt 1" },
        },
        {
          id: "output-1",
          type: NODE_TYPES.OUTPUT,
          position: { x: 200, y: 0 },
          data: { label: "Output 1" },
        },
      ],
      edges: [{ id: "e1", source: "prompt-1", target: "output-1" }],
    };
  }

  /**
   * Graph missing output node
   */
  function createGraphMissingOutput(): { nodes: Node[]; edges: Edge[] } {
    return {
      nodes: [
        {
          id: "prompt-1",
          type: NODE_TYPES.PROMPT,
          position: { x: 0, y: 0 },
          data: { label: "Prompt 1" },
        },
        {
          id: "prompt-2",
          type: NODE_TYPES.PROMPT,
          position: { x: 200, y: 0 },
          data: { label: "Prompt 2" },
        },
      ],
      edges: [
        { id: "e1", source: START_NODE_ID, target: "prompt-1" },
        { id: "e2", source: "prompt-1", target: "prompt-2" },
      ],
    };
  }

  /**
   * Graph with a disconnected node
   */
  function createGraphWithDisconnectedNode(): { nodes: Node[]; edges: Edge[] } {
    return {
      nodes: [
        {
          id: "prompt-1",
          type: NODE_TYPES.PROMPT,
          position: { x: 0, y: 0 },
          data: { label: "Prompt 1" },
        },
        {
          id: "output-1",
          type: NODE_TYPES.OUTPUT,
          position: { x: 200, y: 0 },
          data: { label: "Output 1" },
        },
        {
          id: "prompt-2",
          type: NODE_TYPES.PROMPT,
          position: { x: 0, y: 200 },
          data: { label: "Disconnected Prompt" },
        },
      ],
      edges: [
        { id: "e1", source: START_NODE_ID, target: "prompt-1" },
        { id: "e2", source: "prompt-1", target: "output-1" },
      ],
    };
  }

  /**
   * Graph with a cycle (A -> B -> C -> A)
   */
  function createGraphWithCycle(): { nodes: Node[]; edges: Edge[] } {
    return {
      nodes: [
        {
          id: "prompt-1",
          type: NODE_TYPES.PROMPT,
          position: { x: 0, y: 0 },
          data: { label: "Prompt 1" },
        },
        {
          id: "prompt-2",
          type: NODE_TYPES.PROMPT,
          position: { x: 200, y: 0 },
          data: { label: "Prompt 2" },
        },
        {
          id: "output-1",
          type: NODE_TYPES.OUTPUT,
          position: { x: 400, y: 0 },
          data: { label: "Output 1" },
        },
      ],
      edges: [
        { id: "e1", source: START_NODE_ID, target: "prompt-1" },
        { id: "e2", source: "prompt-1", target: "prompt-2" },
        { id: "e3", source: "prompt-2", target: "output-1" },
        { id: "e4", source: "output-1", target: "prompt-1" }, // Creates cycle
      ],
    };
  }

  // ===== Validation Tests =====

  describe("validateGraph", () => {
    describe("Happy Path - Valid Graphs", () => {
      it("should validate a minimal valid graph", () => {
        const { nodes, edges } = createValidGraph();
        const result = validateGraph(nodes, edges);

        expect(result.isValid).toBe(true);
        expect(result.errors).toHaveLength(0);
        expect(result.hasStartNode).toBe(true);
        expect(result.hasOutputNode).toBe(true);
      });

      it("should validate a graph with trigger node instead of START edge", () => {
        const nodes: Node[] = [
          {
            id: "prompt-1",
            type: NODE_TYPES.PROMPT,
            position: { x: 0, y: 0 },
            data: { label: "Prompt 1", isTrigger: true },
          },
          {
            id: "output-1",
            type: NODE_TYPES.OUTPUT,
            position: { x: 200, y: 0 },
            data: { label: "Output 1" },
          },
        ];
        const edges: Edge[] = [{ id: "e1", source: "prompt-1", target: "output-1" }];

        const result = validateGraph(nodes, edges);

        expect(result.isValid).toBe(true);
        expect(result.errors).toHaveLength(0);
        expect(result.hasStartNode).toBe(true);
        expect(result.hasOutputNode).toBe(true);
      });

      it("should validate a complex multi-node graph", () => {
        const nodes: Node[] = [
          {
            id: "prompt-1",
            type: NODE_TYPES.PROMPT,
            position: { x: 0, y: 0 },
            data: { label: "Prompt 1" },
          },
          {
            id: "transform-1",
            type: NODE_TYPES.TRANSFORM,
            position: { x: 200, y: 0 },
            data: { label: "Transform 1" },
          },
          {
            id: "http-1",
            type: NODE_TYPES.HTTP,
            position: { x: 400, y: 0 },
            data: { label: "HTTP 1" },
          },
          {
            id: "output-1",
            type: NODE_TYPES.OUTPUT,
            position: { x: 600, y: 0 },
            data: { label: "Output 1" },
          },
        ];
        const edges: Edge[] = [
          { id: "e1", source: START_NODE_ID, target: "prompt-1" },
          { id: "e2", source: "prompt-1", target: "transform-1" },
          { id: "e3", source: "transform-1", target: "http-1" },
          { id: "e4", source: "http-1", target: "output-1" },
        ];

        const result = validateGraph(nodes, edges);

        expect(result.isValid).toBe(true);
        expect(result.errors).toHaveLength(0);
      });

      it("should ignore note nodes in validation", () => {
        const nodes: Node[] = [
          {
            id: "prompt-1",
            type: NODE_TYPES.PROMPT,
            position: { x: 0, y: 0 },
            data: { label: "Prompt 1" },
          },
          {
            id: "output-1",
            type: NODE_TYPES.OUTPUT,
            position: { x: 200, y: 0 },
            data: { label: "Output 1" },
          },
          {
            id: "note-1",
            type: "note",
            position: { x: 100, y: 200 },
            data: { text: "This is a note" },
          },
        ];
        const edges: Edge[] = [
          { id: "e1", source: START_NODE_ID, target: "prompt-1" },
          { id: "e2", source: "prompt-1", target: "output-1" },
        ];

        const result = validateGraph(nodes, edges);

        expect(result.isValid).toBe(true);
        expect(result.errors).toHaveLength(0);
      });
    });

    describe("NO_START_NODE Detection", () => {
      it("should detect missing start node", () => {
        const { nodes, edges } = createGraphMissingStart();
        const result = validateGraph(nodes, edges);

        expect(result.isValid).toBe(false);
        expect(result.hasStartNode).toBe(false);
        expect(result.errors).toHaveLength(1);
        expect(result.errors[0].code).toBe(ValidationErrorCode.NO_START_NODE);
        expect(result.errors[0].severity).toBe("error");
        expect(result.errors[0].message).toContain("start node");
      });

      it("should not report NO_START_NODE when START edge exists", () => {
        const { nodes, edges } = createValidGraph();
        const result = validateGraph(nodes, edges);

        const startError = result.errors.find((e) => e.code === ValidationErrorCode.NO_START_NODE);
        expect(startError).toBeUndefined();
      });

      it("should not report NO_START_NODE when trigger node exists", () => {
        const nodes: Node[] = [
          {
            id: "prompt-1",
            type: NODE_TYPES.PROMPT,
            position: { x: 0, y: 0 },
            data: { label: "Prompt 1", isTrigger: true },
          },
          {
            id: "output-1",
            type: NODE_TYPES.OUTPUT,
            position: { x: 200, y: 0 },
            data: { label: "Output 1" },
          },
        ];
        const edges: Edge[] = [{ id: "e1", source: "prompt-1", target: "output-1" }];

        const result = validateGraph(nodes, edges);

        const startError = result.errors.find((e) => e.code === ValidationErrorCode.NO_START_NODE);
        expect(startError).toBeUndefined();
      });
    });

    describe("NO_OUTPUT_NODE Detection", () => {
      it("should detect missing output node", () => {
        const { nodes, edges } = createGraphMissingOutput();
        const result = validateGraph(nodes, edges);

        expect(result.isValid).toBe(false);
        expect(result.hasOutputNode).toBe(false);
        expect(result.errors).toHaveLength(1);
        expect(result.errors[0].code).toBe(ValidationErrorCode.NO_OUTPUT_NODE);
        expect(result.errors[0].severity).toBe("error");
        expect(result.errors[0].message).toContain("output node");
      });

      it("should not report NO_OUTPUT_NODE when output node exists", () => {
        const { nodes, edges } = createValidGraph();
        const result = validateGraph(nodes, edges);

        const outputError = result.errors.find((e) => e.code === ValidationErrorCode.NO_OUTPUT_NODE);
        expect(outputError).toBeUndefined();
      });
    });

    describe("DISCONNECTED_NODE Detection", () => {
      it("should detect disconnected node", () => {
        const { nodes, edges } = createGraphWithDisconnectedNode();
        const result = validateGraph(nodes, edges);

        // The graph is valid (has start and output), but has a warning about disconnected node
        expect(result.isValid).toBe(true);
        expect(result.warnings).toHaveLength(1);
        expect(result.warnings[0].code).toBe(ValidationErrorCode.DISCONNECTED_NODE);
        expect(result.warnings[0].severity).toBe("warning");
        expect(result.warnings[0].nodeId).toBe("prompt-2");
        expect(result.warnings[0].message).toContain("Disconnected Prompt");
      });

      it("should not report disconnected nodes in single node graphs", () => {
        const nodes: Node[] = [
          {
            id: "prompt-1",
            type: NODE_TYPES.PROMPT,
            position: { x: 0, y: 0 },
            data: { label: "Prompt 1" },
          },
        ];
        const edges: Edge[] = [{ id: "e1", source: START_NODE_ID, target: "prompt-1" }];

        const result = validateGraph(nodes, edges);

        const disconnectedWarnings = result.warnings.filter((w) => w.code === ValidationErrorCode.DISCONNECTED_NODE);
        expect(disconnectedWarnings).toHaveLength(0);
      });

      it("should consider trigger nodes as connected", () => {
        const nodes: Node[] = [
          {
            id: "prompt-1",
            type: NODE_TYPES.PROMPT,
            position: { x: 0, y: 0 },
            data: { label: "Prompt 1", isTrigger: true },
          },
          {
            id: "output-1",
            type: NODE_TYPES.OUTPUT,
            position: { x: 200, y: 0 },
            data: { label: "Output 1" },
          },
        ];
        const edges: Edge[] = [{ id: "e1", source: "prompt-1", target: "output-1" }];

        const result = validateGraph(nodes, edges);

        const disconnectedWarnings = result.warnings.filter((w) => w.code === ValidationErrorCode.DISCONNECTED_NODE);
        expect(disconnectedWarnings).toHaveLength(0);
      });

      it("should detect multiple disconnected nodes", () => {
        const nodes: Node[] = [
          {
            id: "prompt-1",
            type: NODE_TYPES.PROMPT,
            position: { x: 0, y: 0 },
            data: { label: "Prompt 1" },
          },
          {
            id: "output-1",
            type: NODE_TYPES.OUTPUT,
            position: { x: 200, y: 0 },
            data: { label: "Output 1" },
          },
          {
            id: "prompt-2",
            type: NODE_TYPES.PROMPT,
            position: { x: 0, y: 200 },
            data: { label: "Disconnected 1" },
          },
          {
            id: "prompt-3",
            type: NODE_TYPES.PROMPT,
            position: { x: 0, y: 400 },
            data: { label: "Disconnected 2" },
          },
        ];
        const edges: Edge[] = [
          { id: "e1", source: START_NODE_ID, target: "prompt-1" },
          { id: "e2", source: "prompt-1", target: "output-1" },
        ];

        const result = validateGraph(nodes, edges);

        const disconnectedWarnings = result.warnings.filter((w) => w.code === ValidationErrorCode.DISCONNECTED_NODE);
        expect(disconnectedWarnings).toHaveLength(2);
        expect(disconnectedWarnings.map((w) => w.nodeId)).toContain("prompt-2");
        expect(disconnectedWarnings.map((w) => w.nodeId)).toContain("prompt-3");
      });
    });

    describe("CYCLE_DETECTED Detection", () => {
      it("should detect a simple cycle", () => {
        const { nodes, edges } = createGraphWithCycle();
        const result = validateGraph(nodes, edges);

        expect(result.isValid).toBe(false);
        expect(result.errors).toHaveLength(1);
        expect(result.errors[0].code).toBe(ValidationErrorCode.CYCLE_DETECTED);
        expect(result.errors[0].severity).toBe("error");
        expect(result.errors[0].message).toContain("cycle");
      });

      it("should not report cycles in valid DAGs", () => {
        const { nodes, edges } = createValidGraph();
        const result = validateGraph(nodes, edges);

        const cycleError = result.errors.find((e) => e.code === ValidationErrorCode.CYCLE_DETECTED);
        expect(cycleError).toBeUndefined();
      });

      it("should detect a self-loop cycle", () => {
        const nodes: Node[] = [
          {
            id: "prompt-1",
            type: NODE_TYPES.PROMPT,
            position: { x: 0, y: 0 },
            data: { label: "Prompt 1" },
          },
          {
            id: "output-1",
            type: NODE_TYPES.OUTPUT,
            position: { x: 200, y: 0 },
            data: { label: "Output 1" },
          },
        ];
        const edges: Edge[] = [
          { id: "e1", source: START_NODE_ID, target: "prompt-1" },
          { id: "e2", source: "prompt-1", target: "prompt-1" }, // Self-loop
          { id: "e3", source: "prompt-1", target: "output-1" },
        ];

        const result = validateGraph(nodes, edges);

        expect(result.errors.some((e) => e.code === ValidationErrorCode.CYCLE_DETECTED)).toBe(true);
      });

      it("should handle complex cycles with multiple paths", () => {
        const nodes: Node[] = [
          {
            id: "prompt-1",
            type: NODE_TYPES.PROMPT,
            position: { x: 0, y: 0 },
            data: { label: "Prompt 1" },
          },
          {
            id: "prompt-2",
            type: NODE_TYPES.PROMPT,
            position: { x: 200, y: 0 },
            data: { label: "Prompt 2" },
          },
          {
            id: "prompt-3",
            type: NODE_TYPES.PROMPT,
            position: { x: 400, y: 0 },
            data: { label: "Prompt 3" },
          },
          {
            id: "output-1",
            type: NODE_TYPES.OUTPUT,
            position: { x: 600, y: 0 },
            data: { label: "Output 1" },
          },
        ];
        const edges: Edge[] = [
          { id: "e1", source: START_NODE_ID, target: "prompt-1" },
          { id: "e2", source: "prompt-1", target: "prompt-2" },
          { id: "e3", source: "prompt-2", target: "prompt-3" },
          { id: "e4", source: "prompt-3", target: "prompt-1" }, // Creates cycle
          { id: "e5", source: "prompt-3", target: "output-1" },
        ];

        const result = validateGraph(nodes, edges);

        expect(result.errors.some((e) => e.code === ValidationErrorCode.CYCLE_DETECTED)).toBe(true);
      });
    });

    describe("SELF_CONNECTION Detection", () => {
      it("should detect self-connections", () => {
        const nodes: Node[] = [
          {
            id: "prompt-1",
            type: NODE_TYPES.PROMPT,
            position: { x: 0, y: 0 },
            data: { label: "Prompt 1" },
          },
          {
            id: "output-1",
            type: NODE_TYPES.OUTPUT,
            position: { x: 200, y: 0 },
            data: { label: "Output 1" },
          },
        ];
        const edges: Edge[] = [
          { id: "e1", source: START_NODE_ID, target: "prompt-1" },
          { id: "e2", source: "prompt-1", target: "prompt-1" },
          { id: "e3", source: "prompt-1", target: "output-1" },
        ];

        const result = validateGraph(nodes, edges);

        expect(result.isValid).toBe(false);
        const selfConnectionError = result.errors.find((e) => e.code === ValidationErrorCode.SELF_CONNECTION);
        expect(selfConnectionError).toBeDefined();
        expect(selfConnectionError?.severity).toBe("error");
        expect(selfConnectionError?.edgeId).toBe("e2");
      });
    });

    describe("EMPTY_GRAPH Detection", () => {
      it("should detect empty graph", () => {
        const nodes: Node[] = [];
        const edges: Edge[] = [];

        const result = validateGraph(nodes, edges);

        expect(result.isValid).toBe(true); // Empty graph is a warning, not an error
        expect(result.warnings).toHaveLength(1);
        expect(result.warnings[0].code).toBe(ValidationErrorCode.EMPTY_GRAPH);
        expect(result.warnings[0].severity).toBe("warning");
      });

      it("should detect graph with only notes", () => {
        const nodes: Node[] = [
          {
            id: "note-1",
            type: "note",
            position: { x: 0, y: 0 },
            data: { text: "This is a note" },
          },
        ];
        const edges: Edge[] = [];

        const result = validateGraph(nodes, edges);

        expect(result.warnings.some((w) => w.code === ValidationErrorCode.EMPTY_GRAPH)).toBe(true);
      });
    });

    describe("Multiple Errors", () => {
      it("should detect multiple errors together", () => {
        const nodes: Node[] = [
          {
            id: "prompt-1",
            type: NODE_TYPES.PROMPT,
            position: { x: 0, y: 0 },
            data: { label: "Prompt 1" },
          },
          {
            id: "prompt-2",
            type: NODE_TYPES.PROMPT,
            position: { x: 200, y: 0 },
            data: { label: "Prompt 2" },
          },
          {
            id: "prompt-3",
            type: NODE_TYPES.PROMPT,
            position: { x: 400, y: 0 },
            data: { label: "Disconnected" },
          },
        ];
        const edges: Edge[] = [
          { id: "e1", source: "prompt-1", target: "prompt-2" }, // No START
          { id: "e2", source: "prompt-2", target: "prompt-1" }, // Cycle
        ];

        const result = validateGraph(nodes, edges);

        expect(result.isValid).toBe(false);

        // Should have NO_START_NODE, NO_OUTPUT_NODE, and CYCLE_DETECTED errors
        const errorCodes = result.errors.map((e) => e.code);
        expect(errorCodes).toContain(ValidationErrorCode.NO_START_NODE);
        expect(errorCodes).toContain(ValidationErrorCode.NO_OUTPUT_NODE);
        expect(errorCodes).toContain(ValidationErrorCode.CYCLE_DETECTED);

        // Should have DISCONNECTED_NODE warning
        const warningCodes = result.warnings.map((w) => w.code);
        expect(warningCodes).toContain(ValidationErrorCode.DISCONNECTED_NODE);
      });
    });

    describe("Edge Cases", () => {
      it("should handle single node with START edge only", () => {
        const nodes: Node[] = [
          {
            id: "prompt-1",
            type: NODE_TYPES.PROMPT,
            position: { x: 0, y: 0 },
            data: { label: "Prompt 1" },
          },
        ];
        const edges: Edge[] = [{ id: "e1", source: START_NODE_ID, target: "prompt-1" }];

        const result = validateGraph(nodes, edges);

        expect(result.hasStartNode).toBe(true);
        expect(result.hasOutputNode).toBe(false);
        expect(result.errors.some((e) => e.code === ValidationErrorCode.NO_OUTPUT_NODE)).toBe(true);
      });

      it("should handle graph with END edge", () => {
        const nodes: Node[] = [
          {
            id: "prompt-1",
            type: NODE_TYPES.PROMPT,
            position: { x: 0, y: 0 },
            data: { label: "Prompt 1" },
          },
          {
            id: "output-1",
            type: NODE_TYPES.OUTPUT,
            position: { x: 200, y: 0 },
            data: { label: "Output 1" },
          },
        ];
        const edges: Edge[] = [
          { id: "e1", source: START_NODE_ID, target: "prompt-1" },
          { id: "e2", source: "prompt-1", target: "output-1" },
          { id: "e3", source: "output-1", target: END_NODE_ID },
        ];

        const result = validateGraph(nodes, edges);

        expect(result.isValid).toBe(true);
        expect(result.hasEndNode).toBe(true);
      });

      it("should handle graph with only output node", () => {
        const nodes: Node[] = [
          {
            id: "output-1",
            type: NODE_TYPES.OUTPUT,
            position: { x: 0, y: 0 },
            data: { label: "Output 1" },
          },
        ];
        const edges: Edge[] = [{ id: "e1", source: START_NODE_ID, target: "output-1" }];

        const result = validateGraph(nodes, edges);

        expect(result.isValid).toBe(true);
        expect(result.hasStartNode).toBe(true);
        expect(result.hasOutputNode).toBe(true);
      });

      it("should handle graph with parallel branches converging", () => {
        const nodes: Node[] = [
          {
            id: "prompt-1",
            type: NODE_TYPES.PROMPT,
            position: { x: 0, y: 0 },
            data: { label: "Prompt 1" },
          },
          {
            id: "branch-1",
            type: NODE_TYPES.BRANCH,
            position: { x: 200, y: 0 },
            data: { label: "Branch" },
          },
          {
            id: "prompt-2",
            type: NODE_TYPES.PROMPT,
            position: { x: 400, y: -100 },
            data: { label: "Path A" },
          },
          {
            id: "prompt-3",
            type: NODE_TYPES.PROMPT,
            position: { x: 400, y: 100 },
            data: { label: "Path B" },
          },
          {
            id: "merge-1",
            type: NODE_TYPES.MERGE,
            position: { x: 600, y: 0 },
            data: { label: "Merge" },
          },
          {
            id: "output-1",
            type: NODE_TYPES.OUTPUT,
            position: { x: 800, y: 0 },
            data: { label: "Output" },
          },
        ];
        const edges: Edge[] = [
          { id: "e1", source: START_NODE_ID, target: "prompt-1" },
          { id: "e2", source: "prompt-1", target: "branch-1" },
          { id: "e3", source: "branch-1", target: "prompt-2" },
          { id: "e4", source: "branch-1", target: "prompt-3" },
          { id: "e5", source: "prompt-2", target: "merge-1" },
          { id: "e6", source: "prompt-3", target: "merge-1" },
          { id: "e7", source: "merge-1", target: "output-1" },
        ];

        const result = validateGraph(nodes, edges);

        expect(result.isValid).toBe(true);
        expect(result.errors).toHaveLength(0);
      });
    });

    describe("End Node Detection", () => {
      it("should detect end node with explicit isEnd flag", () => {
        const nodes: Node[] = [
          {
            id: "prompt-1",
            type: NODE_TYPES.PROMPT,
            position: { x: 0, y: 0 },
            data: { label: "Prompt 1" },
          },
          {
            id: "output-1",
            type: NODE_TYPES.OUTPUT,
            position: { x: 200, y: 0 },
            data: { label: "Output 1", isEnd: true },
          },
        ];
        const edges: Edge[] = [
          { id: "e1", source: START_NODE_ID, target: "prompt-1" },
          { id: "e2", source: "prompt-1", target: "output-1" },
        ];

        const result = validateGraph(nodes, edges);

        expect(result.hasEndNode).toBe(true);
      });

      it("should accept sink nodes without NO_END_NODE warning", () => {
        const nodes: Node[] = [
          {
            id: "prompt-1",
            type: NODE_TYPES.PROMPT,
            position: { x: 0, y: 0 },
            data: { label: "Prompt 1" },
          },
          {
            id: "output-1",
            type: NODE_TYPES.OUTPUT,
            position: { x: 200, y: 0 },
            data: { label: "Output 1" },
          },
        ];
        const edges: Edge[] = [
          { id: "e1", source: START_NODE_ID, target: "prompt-1" },
          { id: "e2", source: "prompt-1", target: "output-1" },
          // output-1 has no outgoing edges, so it's a sink node
        ];

        const result = validateGraph(nodes, edges);

        // hasEndNode is false because there's no explicit end marker,
        // but sink nodes are accepted so there's no NO_END_NODE warning
        expect(result.hasEndNode).toBe(false);
        const endWarning = result.warnings.find((w) => w.code === ValidationErrorCode.NO_END_NODE);
        expect(endWarning).toBeUndefined();
      });
    });
  });

  // ===== Quick Fixes Tests =====

  describe("getQuickFixesForError", () => {
    it("should return quick fix for NO_START_NODE", () => {
      const error: ValidationError = {
        code: ValidationErrorCode.NO_START_NODE,
        severity: "error",
        message: "Graph needs a start node",
      };

      const fixes = getQuickFixesForError(error);

      expect(fixes).toHaveLength(1);
      expect(fixes[0].errorCode).toBe(ValidationErrorCode.NO_START_NODE);
      expect(fixes[0].label).toBe("Add Start");
      expect(fixes[0].description).toContain("entry point");
    });

    it("should return quick fix for NO_OUTPUT_NODE", () => {
      const error: ValidationError = {
        code: ValidationErrorCode.NO_OUTPUT_NODE,
        severity: "error",
        message: "Graph needs an output node",
      };

      const fixes = getQuickFixesForError(error);

      expect(fixes).toHaveLength(1);
      expect(fixes[0].errorCode).toBe(ValidationErrorCode.NO_OUTPUT_NODE);
      expect(fixes[0].label).toBe("Add Output");
      expect(fixes[0].description).toContain("Output node");
    });

    it("should return multiple quick fixes for DISCONNECTED_NODE", () => {
      const error: ValidationError = {
        code: ValidationErrorCode.DISCONNECTED_NODE,
        severity: "warning",
        message: "Node is disconnected",
        nodeId: "prompt-1",
      };

      const fixes = getQuickFixesForError(error);

      expect(fixes).toHaveLength(2);
      expect(fixes[0].label).toBe("Connect");
      expect(fixes[1].label).toBe("Remove");
    });

    it("should return empty array for errors without quick fixes", () => {
      const error: ValidationError = {
        code: ValidationErrorCode.CYCLE_DETECTED,
        severity: "error",
        message: "Graph contains a cycle",
      };

      const fixes = getQuickFixesForError(error);

      expect(fixes).toHaveLength(0);
    });

    it("should return empty array for EMPTY_GRAPH", () => {
      const error: ValidationError = {
        code: ValidationErrorCode.EMPTY_GRAPH,
        severity: "warning",
        message: "Graph is empty",
      };

      const fixes = getQuickFixesForError(error);

      expect(fixes).toHaveLength(0);
    });

    it("should return empty array for TYPE_MISMATCH", () => {
      const error: ValidationError = {
        code: ValidationErrorCode.TYPE_MISMATCH,
        severity: "error",
        message: "Type mismatch detected",
      };

      const fixes = getQuickFixesForError(error);

      expect(fixes).toHaveLength(0);
    });
  });

  // ===== Validation Result Structure Tests =====

  describe("ValidationResult structure", () => {
    it("should return correct structure for valid graph", () => {
      const { nodes, edges } = createValidGraph();
      const result = validateGraph(nodes, edges);

      expect(result).toHaveProperty("isValid");
      expect(result).toHaveProperty("errors");
      expect(result).toHaveProperty("warnings");
      expect(result).toHaveProperty("hasStartNode");
      expect(result).toHaveProperty("hasOutputNode");
      expect(result).toHaveProperty("hasEndNode");

      expect(Array.isArray(result.errors)).toBe(true);
      expect(Array.isArray(result.warnings)).toBe(true);
      expect(typeof result.isValid).toBe("boolean");
      expect(typeof result.hasStartNode).toBe("boolean");
      expect(typeof result.hasOutputNode).toBe("boolean");
      expect(typeof result.hasEndNode).toBe("boolean");
    });

    it("should return correct structure for invalid graph", () => {
      const { nodes, edges } = createGraphMissingStart();
      const result = validateGraph(nodes, edges);

      expect(result.isValid).toBe(false);
      expect(result.errors.length).toBeGreaterThan(0);

      // Verify error structure
      const error = result.errors[0];
      expect(error).toHaveProperty("code");
      expect(error).toHaveProperty("severity");
      expect(error).toHaveProperty("message");
    });

    it("should separate errors and warnings", () => {
      // Create a graph with both errors and warnings
      const nodes: Node[] = [
        {
          id: "prompt-1",
          type: NODE_TYPES.PROMPT,
          position: { x: 0, y: 0 },
          data: { label: "Prompt 1" },
        },
        {
          id: "prompt-2",
          type: NODE_TYPES.PROMPT,
          position: { x: 200, y: 0 },
          data: { label: "Prompt 2" },
        },
        {
          id: "disconnected",
          type: NODE_TYPES.PROMPT,
          position: { x: 400, y: 0 },
          data: { label: "Disconnected" },
        },
      ];
      const edges: Edge[] = [
        { id: "e1", source: "prompt-1", target: "prompt-2" }, // No START edge
        // No output node
        // "disconnected" node is not connected
      ];

      const result = validateGraph(nodes, edges);

      // Should have errors (NO_START_NODE, NO_OUTPUT_NODE)
      expect(result.errors.length).toBeGreaterThan(0);

      // Should have DISCONNECTED_NODE warning
      expect(result.warnings.length).toBeGreaterThan(0);

      // Verify all errors have severity "error"
      result.errors.forEach((error) => {
        expect(error.severity).toBe("error");
      });

      // Verify all warnings have severity "warning"
      result.warnings.forEach((warning) => {
        expect(warning.severity).toBe("warning");
      });
    });
  });
});
