import {
  inferOutputType,
  inferInputTypes,
  getPrimaryInputType,
  getPrimaryOutputType,
  analyzeEdgeTypes,
  getAvailableData,
  getUpstreamNodes,
  buildTypeMap,
  nodeProducesType,
  nodeAcceptsType,
  getSuggestedNextNodes,
} from "@/lib/type-inference";
import { DataType } from "@/lib/data-types";
import { NODE_TYPES, type GraphNode, type GraphEdge, START_NODE_ID, END_NODE_ID } from "@/lib/graph-types";

describe("type-inference", () => {
  describe("inferOutputType", () => {
    it("should infer ANY for AGENT node", () => {
      const node: GraphNode = {
        id: "agent1",
        type: NODE_TYPES.AGENT,
        name: "Test Agent",
        config: { model: "gpt-4.1-mini", tools: ["lookup_customer"] },
      };
      const result = inferOutputType(node);
      expect(result.type).toBe(DataType.ANY);
      expect(result.isInferred).toBe(true);
      expect(result.description).toContain("Agent final output");
    });

    it("should infer TEXT for PROMPT node", () => {
      const node: GraphNode = {
        id: "prompt1",
        type: NODE_TYPES.PROMPT,
        name: "Test Prompt",
        config: {},
      };
      const result = inferOutputType(node);
      expect(result.type).toBe(DataType.TEXT);
      expect(result.isInferred).toBe(true);
      expect(result.description).toContain("LLM response");
    });

    it("should infer JSON for HTTP node", () => {
      const node: GraphNode = {
        id: "http1",
        type: NODE_TYPES.HTTP,
        name: "Test HTTP",
        config: { method: "GET", url: "https://api.example.com" },
      };
      const result = inferOutputType(node);
      expect(result.type).toBe(DataType.JSON);
      expect(result.isInferred).toBe(true);
      expect(result.description).toContain("HTTP response");
    });

    describe("TRANSFORM node type inference", () => {
      it("should infer TEXT when expression contains JSON.stringify", () => {
        const node: GraphNode = {
          id: "transform1",
          type: NODE_TYPES.TRANSFORM,
          name: "Stringify",
          config: { expression: "JSON.stringify(input)" },
        };
        const result = inferOutputType(node);
        expect(result.type).toBe(DataType.TEXT);
        expect(result.isInferred).toBe(true);
      });

      it("should infer TEXT when expression contains .toString()", () => {
        const node: GraphNode = {
          id: "transform1",
          type: NODE_TYPES.TRANSFORM,
          name: "ToString",
          config: { expression: "input.toString()" },
        };
        const result = inferOutputType(node);
        expect(result.type).toBe(DataType.TEXT);
        expect(result.isInferred).toBe(true);
      });

      it("should infer JSON when expression contains JSON.parse", () => {
        const node: GraphNode = {
          id: "transform1",
          type: NODE_TYPES.TRANSFORM,
          name: "Parse",
          config: { expression: "JSON.parse(input)" },
        };
        const result = inferOutputType(node);
        expect(result.type).toBe(DataType.JSON);
        expect(result.isInferred).toBe(true);
      });

      it("should infer ARRAY when expression contains .map(", () => {
        const node: GraphNode = {
          id: "transform1",
          type: NODE_TYPES.TRANSFORM,
          name: "Map",
          config: { expression: "input.map(x => x * 2)" },
        };
        const result = inferOutputType(node);
        expect(result.type).toBe(DataType.ARRAY);
        expect(result.isInferred).toBe(true);
      });

      it("should infer ARRAY when expression contains .filter(", () => {
        const node: GraphNode = {
          id: "transform1",
          type: NODE_TYPES.TRANSFORM,
          name: "Filter",
          config: { expression: "input.filter(x => x > 0)" },
        };
        const result = inferOutputType(node);
        expect(result.type).toBe(DataType.ARRAY);
        expect(result.isInferred).toBe(true);
      });

      it("should infer ARRAY when expression contains array literal", () => {
        const node: GraphNode = {
          id: "transform1",
          type: NODE_TYPES.TRANSFORM,
          name: "Array",
          config: { expression: "[input.a, input.b]" },
        };
        const result = inferOutputType(node);
        expect(result.type).toBe(DataType.ARRAY);
        expect(result.isInferred).toBe(true);
      });

      it("should default to JSON for generic transform", () => {
        const node: GraphNode = {
          id: "transform1",
          type: NODE_TYPES.TRANSFORM,
          name: "Generic",
          config: { expression: "{ result: input.value }" },
        };
        const result = inferOutputType(node);
        expect(result.type).toBe(DataType.JSON);
        expect(result.isInferred).toBe(true);
      });

      it("should default to JSON when no expression is provided", () => {
        const node: GraphNode = {
          id: "transform1",
          type: NODE_TYPES.TRANSFORM,
          name: "No Expression",
          config: {},
        };
        const result = inferOutputType(node);
        expect(result.type).toBe(DataType.JSON);
        expect(result.isInferred).toBe(true);
      });
    });

    it("should infer ANY for BRANCH node", () => {
      const node: GraphNode = {
        id: "branch1",
        type: NODE_TYPES.BRANCH,
        name: "Test Branch",
        config: {},
      };
      const result = inferOutputType(node);
      expect(result.type).toBe(DataType.ANY);
      expect(result.isInferred).toBe(true);
    });

    it("should infer JSON for MERGE node", () => {
      const node: GraphNode = {
        id: "merge1",
        type: NODE_TYPES.MERGE,
        name: "Test Merge",
        config: {},
      };
      const result = inferOutputType(node);
      expect(result.type).toBe(DataType.JSON);
      expect(result.isInferred).toBe(true);
      expect(result.description).toContain("Merged data");
    });

    describe("MEMORY node type inference", () => {
      it("should infer JSON for set action", () => {
        const node: GraphNode = {
          id: "memory1",
          type: NODE_TYPES.MEMORY,
          name: "Set Memory",
          config: { action: "set" },
        };
        const result = inferOutputType(node);
        expect(result.type).toBe(DataType.JSON);
        expect(result.isInferred).toBe(true);
      });

      it("should infer JSON for delete action", () => {
        const node: GraphNode = {
          id: "memory1",
          type: NODE_TYPES.MEMORY,
          name: "Delete Memory",
          config: { action: "delete" },
        };
        const result = inferOutputType(node);
        expect(result.type).toBe(DataType.JSON);
        expect(result.isInferred).toBe(true);
      });

      it("should infer ANY for get action", () => {
        const node: GraphNode = {
          id: "memory1",
          type: NODE_TYPES.MEMORY,
          name: "Get Memory",
          config: { action: "get" },
        };
        const result = inferOutputType(node);
        expect(result.type).toBe(DataType.ANY);
        expect(result.isInferred).toBe(true);
      });

      it("should infer ANY when no action is specified", () => {
        const node: GraphNode = {
          id: "memory1",
          type: NODE_TYPES.MEMORY,
          name: "Memory",
          config: {},
        };
        const result = inferOutputType(node);
        expect(result.type).toBe(DataType.ANY);
        expect(result.isInferred).toBe(true);
      });
    });

    it("should infer JSON for TOOL node", () => {
      const node: GraphNode = {
        id: "tool1",
        type: NODE_TYPES.TOOL,
        name: "Test Tool",
        config: {},
      };
      const result = inferOutputType(node);
      expect(result.type).toBe(DataType.JSON);
      expect(result.isInferred).toBe(true);
    });

    it("should infer JSON for SUBGRAPH node", () => {
      const node: GraphNode = {
        id: "subgraph1",
        type: NODE_TYPES.SUBGRAPH,
        name: "Test Subgraph",
        config: {},
      };
      const result = inferOutputType(node);
      expect(result.type).toBe(DataType.JSON);
      expect(result.isInferred).toBe(true);
    });

    it("should infer ANY for HUMAN_GATE node", () => {
      const node: GraphNode = {
        id: "gate1",
        type: NODE_TYPES.HUMAN_GATE,
        name: "Test Gate",
        config: {},
      };
      const result = inferOutputType(node);
      expect(result.type).toBe(DataType.ANY);
      expect(result.isInferred).toBe(true);
    });

    it("should infer VOID for OUTPUT node", () => {
      const node: GraphNode = {
        id: "output1",
        type: NODE_TYPES.OUTPUT,
        name: "Test Output",
        config: {},
      };
      const result = inferOutputType(node);
      expect(result.type).toBe(DataType.VOID);
      expect(result.isInferred).toBe(true);
    });
  });

  describe("inferInputTypes", () => {
    it("should infer JSON input for AGENT node", () => {
      const node: GraphNode = {
        id: "agent1",
        type: NODE_TYPES.AGENT,
        name: "Agent",
        config: {},
      };
      const result = inferInputTypes(node);
      expect(result).toHaveLength(1);
      expect(result[0].type).toBe(DataType.JSON);
    });

    it("should return correct input types for PROMPT node", () => {
      const node: GraphNode = {
        id: "prompt1",
        type: NODE_TYPES.PROMPT,
        name: "Test",
        config: {},
      };
      const result = inferInputTypes(node);
      expect(result.length).toBe(1);
      expect(result[0].type).toBe(DataType.JSON);
      expect(result[0].isInferred).toBe(false);
      expect(result[0].description).toContain("Variables");
    });

    it("should return correct input types for HTTP node", () => {
      const node: GraphNode = {
        id: "http1",
        type: NODE_TYPES.HTTP,
        name: "Test",
        config: {},
      };
      const result = inferInputTypes(node);
      expect(result.length).toBe(2);
      expect(result[0].type).toBe(DataType.JSON);
      expect(result[1].type).toBe(DataType.JSON);
    });

    it("should return correct input types for TRANSFORM node", () => {
      const node: GraphNode = {
        id: "transform1",
        type: NODE_TYPES.TRANSFORM,
        name: "Test",
        config: {},
      };
      const result = inferInputTypes(node);
      expect(result.length).toBe(1);
      expect(result[0].type).toBe(DataType.ANY);
    });

    it("should return correct input types for BRANCH node", () => {
      const node: GraphNode = {
        id: "branch1",
        type: NODE_TYPES.BRANCH,
        name: "Test",
        config: {},
      };
      const result = inferInputTypes(node);
      expect(result.length).toBe(1);
      expect(result[0].type).toBe(DataType.ANY);
    });

    it("should return correct input types for MERGE node", () => {
      const node: GraphNode = {
        id: "merge1",
        type: NODE_TYPES.MERGE,
        name: "Test",
        config: {},
      };
      const result = inferInputTypes(node);
      expect(result.length).toBe(1);
      expect(result[0].type).toBe(DataType.ANY);
    });

    it("should return ANY for nodes with invalid type", () => {
      const node: GraphNode = {
        id: "invalid1",
        type: "invalid" as any,
        name: "Test",
        config: {},
      };
      const result = inferInputTypes(node);
      expect(result.length).toBe(1);
      expect(result[0].type).toBe(DataType.ANY);
      expect(result[0].isInferred).toBe(true);
    });
  });

  describe("getPrimaryInputType", () => {
    it("should return the first input type", () => {
      const node: GraphNode = {
        id: "http1",
        type: NODE_TYPES.HTTP,
        name: "Test",
        config: {},
      };
      expect(getPrimaryInputType(node)).toBe(DataType.JSON);
    });

    it("should return ANY for nodes with no inputs", () => {
      const node: GraphNode = {
        id: "invalid1",
        type: "invalid" as any,
        name: "Test",
        config: {},
      };
      expect(getPrimaryInputType(node)).toBe(DataType.ANY);
    });
  });

  describe("getPrimaryOutputType", () => {
    it("should return the inferred output type", () => {
      const node: GraphNode = {
        id: "prompt1",
        type: NODE_TYPES.PROMPT,
        name: "Test",
        config: {},
      };
      expect(getPrimaryOutputType(node)).toBe(DataType.TEXT);
    });

    it("should return VOID for OUTPUT node", () => {
      const node: GraphNode = {
        id: "output1",
        type: NODE_TYPES.OUTPUT,
        name: "Test",
        config: {},
      };
      expect(getPrimaryOutputType(node)).toBe(DataType.VOID);
    });
  });

  describe("analyzeEdgeTypes", () => {
    it("should find no mismatches for compatible types", () => {
      const nodes: GraphNode[] = [
        {
          id: "prompt1",
          type: NODE_TYPES.PROMPT,
          name: "Prompt",
          config: {},
        },
        {
          id: "output1",
          type: NODE_TYPES.OUTPUT,
          name: "Output",
          config: {},
        },
      ];
      const edges: GraphEdge[] = [
        {
          id: "edge1",
          from: "prompt1",
          to: "output1",
        },
      ];
      const mismatches = analyzeEdgeTypes(nodes, edges);
      expect(mismatches.length).toBe(0);
    });

    it("should detect type mismatches", () => {
      const nodes: GraphNode[] = [
        {
          id: "prompt1",
          type: NODE_TYPES.PROMPT,
          name: "Prompt",
          config: {},
        },
        {
          id: "http1",
          type: NODE_TYPES.HTTP,
          name: "HTTP",
          config: {},
        },
      ];
      const edges: GraphEdge[] = [
        {
          id: "edge1",
          from: "prompt1", // outputs TEXT
          to: "http1", // expects JSON
        },
      ];
      const mismatches = analyzeEdgeTypes(nodes, edges);
      expect(mismatches.length).toBe(1);
      expect(mismatches[0].edgeId).toBe("edge1");
      expect(mismatches[0].sourceType).toBe(DataType.TEXT);
      expect(mismatches[0].targetType).toBe(DataType.JSON);
      expect(mismatches[0].compatibility.compatible).toBe(false);
    });

    it("should skip sentinel edges (START and END)", () => {
      const nodes: GraphNode[] = [
        {
          id: "prompt1",
          type: NODE_TYPES.PROMPT,
          name: "Prompt",
          config: {},
        },
      ];
      const edges: GraphEdge[] = [
        {
          id: "edge1",
          from: START_NODE_ID,
          to: "prompt1",
        },
        {
          id: "edge2",
          from: "prompt1",
          to: END_NODE_ID,
        },
      ];
      const mismatches = analyzeEdgeTypes(nodes, edges);
      expect(mismatches.length).toBe(0);
    });

    it("should skip edges with missing nodes", () => {
      const nodes: GraphNode[] = [
        {
          id: "prompt1",
          type: NODE_TYPES.PROMPT,
          name: "Prompt",
          config: {},
        },
      ];
      const edges: GraphEdge[] = [
        {
          id: "edge1",
          from: "prompt1",
          to: "nonexistent",
        },
      ];
      const mismatches = analyzeEdgeTypes(nodes, edges);
      expect(mismatches.length).toBe(0);
    });

    it("should handle multiple edges", () => {
      const nodes: GraphNode[] = [
        {
          id: "prompt1",
          type: NODE_TYPES.PROMPT,
          name: "Prompt",
          config: {},
        },
        {
          id: "transform1",
          type: NODE_TYPES.TRANSFORM,
          name: "Transform",
          config: {},
        },
        {
          id: "http1",
          type: NODE_TYPES.HTTP,
          name: "HTTP",
          config: {},
        },
      ];
      const edges: GraphEdge[] = [
        {
          id: "edge1",
          from: "prompt1",
          to: "transform1", // Compatible: TEXT -> ANY
        },
        {
          id: "edge2",
          from: "transform1",
          to: "http1", // Compatible: JSON -> JSON (transform defaults to JSON)
        },
      ];
      const mismatches = analyzeEdgeTypes(nodes, edges);
      expect(mismatches.length).toBe(0);
    });
  });

  describe("getAvailableData", () => {
    it("should return empty array when no incoming edges", () => {
      const nodes: GraphNode[] = [
        {
          id: "prompt1",
          type: NODE_TYPES.PROMPT,
          name: "Prompt",
          config: {},
        },
      ];
      const edges: GraphEdge[] = [];
      const available = getAvailableData("prompt1", nodes, edges);
      expect(available.length).toBe(0);
    });

    it("should return START input when connected from START", () => {
      const nodes: GraphNode[] = [
        {
          id: "prompt1",
          type: NODE_TYPES.PROMPT,
          name: "Prompt",
          config: {},
        },
      ];
      const edges: GraphEdge[] = [
        {
          id: "edge1",
          from: START_NODE_ID,
          to: "prompt1",
        },
      ];
      const available = getAvailableData("prompt1", nodes, edges);
      expect(available.length).toBe(1);
      expect(available[0].nodeId).toBe(START_NODE_ID);
      expect(available[0].nodeName).toBe("Input");
      expect(available[0].outputType).toBe(DataType.JSON);
      expect(available[0].path).toBe("input");
    });

    it("should return upstream node data", () => {
      const nodes: GraphNode[] = [
        {
          id: "prompt1",
          type: NODE_TYPES.PROMPT,
          name: "My Prompt",
          config: {},
        },
        {
          id: "transform1",
          type: NODE_TYPES.TRANSFORM,
          name: "Transform",
          config: {},
        },
      ];
      const edges: GraphEdge[] = [
        {
          id: "edge1",
          from: "prompt1",
          to: "transform1",
        },
      ];
      const available = getAvailableData("transform1", nodes, edges);
      expect(available.length).toBe(1);
      expect(available[0].nodeId).toBe("prompt1");
      expect(available[0].nodeName).toBe("My Prompt");
      expect(available[0].outputType).toBe(DataType.TEXT);
      expect(available[0].path).toBe("state.prompt1.output");
    });

    it("should return multiple upstream nodes", () => {
      const nodes: GraphNode[] = [
        {
          id: "prompt1",
          type: NODE_TYPES.PROMPT,
          name: "Prompt 1",
          config: {},
        },
        {
          id: "http1",
          type: NODE_TYPES.HTTP,
          name: "HTTP 1",
          config: {},
        },
        {
          id: "merge1",
          type: NODE_TYPES.MERGE,
          name: "Merge",
          config: {},
        },
      ];
      const edges: GraphEdge[] = [
        {
          id: "edge1",
          from: "prompt1",
          to: "merge1",
        },
        {
          id: "edge2",
          from: "http1",
          to: "merge1",
        },
      ];
      const available = getAvailableData("merge1", nodes, edges);
      expect(available.length).toBe(2);
      expect(available.some((a) => a.nodeId === "prompt1")).toBe(true);
      expect(available.some((a) => a.nodeId === "http1")).toBe(true);
    });

    it("should skip edges from missing nodes", () => {
      const nodes: GraphNode[] = [
        {
          id: "transform1",
          type: NODE_TYPES.TRANSFORM,
          name: "Transform",
          config: {},
        },
      ];
      const edges: GraphEdge[] = [
        {
          id: "edge1",
          from: "nonexistent",
          to: "transform1",
        },
      ];
      const available = getAvailableData("transform1", nodes, edges);
      expect(available.length).toBe(0);
    });
  });

  describe("getUpstreamNodes", () => {
    it("should return empty array when no upstream nodes", () => {
      const nodes: GraphNode[] = [
        {
          id: "prompt1",
          type: NODE_TYPES.PROMPT,
          name: "Prompt",
          config: {},
        },
      ];
      const edges: GraphEdge[] = [];
      const upstream = getUpstreamNodes("prompt1", nodes, edges);
      expect(upstream.length).toBe(0);
    });

    it("should return direct upstream node", () => {
      const nodes: GraphNode[] = [
        {
          id: "prompt1",
          type: NODE_TYPES.PROMPT,
          name: "Prompt",
          config: {},
        },
        {
          id: "transform1",
          type: NODE_TYPES.TRANSFORM,
          name: "Transform",
          config: {},
        },
      ];
      const edges: GraphEdge[] = [
        {
          id: "edge1",
          from: "prompt1",
          to: "transform1",
        },
      ];
      const upstream = getUpstreamNodes("transform1", nodes, edges);
      expect(upstream.length).toBe(1);
      expect(upstream[0].id).toBe("prompt1");
    });

    it("should return all upstream nodes recursively", () => {
      const nodes: GraphNode[] = [
        {
          id: "http1",
          type: NODE_TYPES.HTTP,
          name: "HTTP",
          config: {},
        },
        {
          id: "transform1",
          type: NODE_TYPES.TRANSFORM,
          name: "Transform",
          config: {},
        },
        {
          id: "output1",
          type: NODE_TYPES.OUTPUT,
          name: "Output",
          config: {},
        },
      ];
      const edges: GraphEdge[] = [
        {
          id: "edge1",
          from: "http1",
          to: "transform1",
        },
        {
          id: "edge2",
          from: "transform1",
          to: "output1",
        },
      ];
      const upstream = getUpstreamNodes("output1", nodes, edges);
      expect(upstream.length).toBe(2);
      expect(upstream.some((n) => n.id === "transform1")).toBe(true);
      expect(upstream.some((n) => n.id === "http1")).toBe(true);
    });

    it("should handle cycles (visited set prevents infinite loop)", () => {
      const nodes: GraphNode[] = [
        {
          id: "node1",
          type: NODE_TYPES.TRANSFORM,
          name: "Node 1",
          config: {},
        },
        {
          id: "node2",
          type: NODE_TYPES.TRANSFORM,
          name: "Node 2",
          config: {},
        },
      ];
      const edges: GraphEdge[] = [
        {
          id: "edge1",
          from: "node1",
          to: "node2",
        },
        {
          id: "edge2",
          from: "node2",
          to: "node1",
        },
      ];
      const upstream = getUpstreamNodes("node1", nodes, edges);
      // Should not crash or loop infinitely
      expect(Array.isArray(upstream)).toBe(true);
    });

    it("should skip START node", () => {
      const nodes: GraphNode[] = [
        {
          id: "prompt1",
          type: NODE_TYPES.PROMPT,
          name: "Prompt",
          config: {},
        },
      ];
      const edges: GraphEdge[] = [
        {
          id: "edge1",
          from: START_NODE_ID,
          to: "prompt1",
        },
      ];
      const upstream = getUpstreamNodes("prompt1", nodes, edges);
      expect(upstream.length).toBe(0);
    });

    it("should skip missing nodes", () => {
      const nodes: GraphNode[] = [
        {
          id: "transform1",
          type: NODE_TYPES.TRANSFORM,
          name: "Transform",
          config: {},
        },
      ];
      const edges: GraphEdge[] = [
        {
          id: "edge1",
          from: "nonexistent",
          to: "transform1",
        },
      ];
      const upstream = getUpstreamNodes("transform1", nodes, edges);
      expect(upstream.length).toBe(0);
    });
  });

  describe("buildTypeMap", () => {
    it("should build type map for all nodes", () => {
      const nodes: GraphNode[] = [
        {
          id: "prompt1",
          type: NODE_TYPES.PROMPT,
          name: "Prompt",
          config: {},
        },
        {
          id: "transform1",
          type: NODE_TYPES.TRANSFORM,
          name: "Transform",
          config: {},
        },
      ];
      const edges: GraphEdge[] = [];
      const typeMap = buildTypeMap(nodes, edges);
      expect(typeMap.size).toBe(2);
      expect(typeMap.has("prompt1")).toBe(true);
      expect(typeMap.has("transform1")).toBe(true);
    });

    it("should include correct type info for each node", () => {
      const nodes: GraphNode[] = [
        {
          id: "prompt1",
          type: NODE_TYPES.PROMPT,
          name: "Prompt",
          config: {},
        },
      ];
      const edges: GraphEdge[] = [];
      const typeMap = buildTypeMap(nodes, edges);
      const info = typeMap.get("prompt1");
      expect(info).toBeDefined();
      expect(info?.nodeId).toBe("prompt1");
      expect(info?.outputType.type).toBe(DataType.TEXT);
      expect(info?.inputTypes.length).toBeGreaterThan(0);
      expect(info?.signature).toBeDefined();
    });

    it("should handle empty graph", () => {
      const typeMap = buildTypeMap([], []);
      expect(typeMap.size).toBe(0);
    });
  });

  describe("nodeProducesType", () => {
    it("should return true when node produces the exact type", () => {
      const node: GraphNode = {
        id: "prompt1",
        type: NODE_TYPES.PROMPT,
        name: "Prompt",
        config: {},
      };
      expect(nodeProducesType(node, DataType.TEXT)).toBe(true);
    });

    it("should return false when node produces different type", () => {
      const node: GraphNode = {
        id: "prompt1",
        type: NODE_TYPES.PROMPT,
        name: "Prompt",
        config: {},
      };
      expect(nodeProducesType(node, DataType.JSON)).toBe(false);
    });

    it("should return true when node produces ANY", () => {
      const node: GraphNode = {
        id: "transform1",
        type: NODE_TYPES.TRANSFORM,
        name: "Transform",
        config: { expression: "{ result: input }" },
      };
      expect(nodeProducesType(node, DataType.TEXT)).toBe(false);
      expect(nodeProducesType(node, DataType.JSON)).toBe(true);
    });

    it("should return true when checking for ANY type", () => {
      const node: GraphNode = {
        id: "prompt1",
        type: NODE_TYPES.PROMPT,
        name: "Prompt",
        config: {},
      };
      expect(nodeProducesType(node, DataType.ANY)).toBe(true);
    });

    it("should return true when node output is ANY", () => {
      const node: GraphNode = {
        id: "branch1",
        type: NODE_TYPES.BRANCH,
        name: "Branch",
        config: {},
      };
      expect(nodeProducesType(node, DataType.TEXT)).toBe(true);
      expect(nodeProducesType(node, DataType.JSON)).toBe(true);
    });
  });

  describe("nodeAcceptsType", () => {
    it("should return true when node accepts the exact type", () => {
      const node: GraphNode = {
        id: "http1",
        type: NODE_TYPES.HTTP,
        name: "HTTP",
        config: {},
      };
      expect(nodeAcceptsType(node, DataType.JSON)).toBe(true);
    });

    it("should return false when node doesn't accept the type", () => {
      const node: GraphNode = {
        id: "http1",
        type: NODE_TYPES.HTTP,
        name: "HTTP",
        config: {},
      };
      expect(nodeAcceptsType(node, DataType.TEXT)).toBe(false);
    });

    it("should return true when node accepts ANY", () => {
      const node: GraphNode = {
        id: "transform1",
        type: NODE_TYPES.TRANSFORM,
        name: "Transform",
        config: {},
      };
      expect(nodeAcceptsType(node, DataType.TEXT)).toBe(true);
      expect(nodeAcceptsType(node, DataType.JSON)).toBe(true);
    });

    it("should return true when checking with ANY type", () => {
      const node: GraphNode = {
        id: "http1",
        type: NODE_TYPES.HTTP,
        name: "HTTP",
        config: {},
      };
      expect(nodeAcceptsType(node, DataType.ANY)).toBe(true);
    });

    it("should respect compatibility rules", () => {
      const node: GraphNode = {
        id: "output1",
        type: NODE_TYPES.OUTPUT,
        name: "Output",
        config: {},
      };
      // OUTPUT accepts ANY, so it should accept TEXT
      expect(nodeAcceptsType(node, DataType.TEXT)).toBe(true);
    });
  });

  describe("getSuggestedNextNodes", () => {
    it("should suggest nodes that accept the output type", () => {
      const node: GraphNode = {
        id: "prompt1",
        type: NODE_TYPES.PROMPT,
        name: "Prompt",
        config: {},
      };
      const availableNodeTypes = [NODE_TYPES.TRANSFORM, NODE_TYPES.OUTPUT, NODE_TYPES.HTTP];
      const suggested = getSuggestedNextNodes(node, availableNodeTypes);
      // TRANSFORM and OUTPUT accept TEXT (via ANY)
      expect(suggested).toContain(NODE_TYPES.TRANSFORM);
      expect(suggested).toContain(NODE_TYPES.OUTPUT);
      // HTTP expects JSON, not compatible with TEXT
      expect(suggested).not.toContain(NODE_TYPES.HTTP);
    });

    it("should suggest all nodes when output is ANY", () => {
      const node: GraphNode = {
        id: "branch1",
        type: NODE_TYPES.BRANCH,
        name: "Branch",
        config: {},
      };
      const availableNodeTypes = [NODE_TYPES.PROMPT, NODE_TYPES.HTTP, NODE_TYPES.TRANSFORM];
      const suggested = getSuggestedNextNodes(node, availableNodeTypes);
      expect(suggested.length).toBe(availableNodeTypes.length);
    });

    it("should suggest nodes with no inputs", () => {
      const node: GraphNode = {
        id: "output1",
        type: NODE_TYPES.OUTPUT,
        name: "Output",
        config: {},
      };
      const availableNodeTypes = [NODE_TYPES.PROMPT];
      const suggested = getSuggestedNextNodes(node, availableNodeTypes);
      // Even though OUTPUT produces VOID, nodes with inputs can still be suggested
      // based on the compatibility check
      expect(Array.isArray(suggested)).toBe(true);
    });

    it("should handle empty available node types", () => {
      const node: GraphNode = {
        id: "prompt1",
        type: NODE_TYPES.PROMPT,
        name: "Prompt",
        config: {},
      };
      const suggested = getSuggestedNextNodes(node, []);
      expect(suggested.length).toBe(0);
    });

    it("should filter based on type compatibility", () => {
      const node: GraphNode = {
        id: "http1",
        type: NODE_TYPES.HTTP,
        name: "HTTP",
        config: {},
      };
      const availableNodeTypes = [
        NODE_TYPES.HTTP, // Accepts JSON
        NODE_TYPES.TRANSFORM, // Accepts ANY
        NODE_TYPES.OUTPUT, // Accepts ANY
      ];
      const suggested = getSuggestedNextNodes(node, availableNodeTypes);
      expect(suggested).toContain(NODE_TYPES.HTTP);
      expect(suggested).toContain(NODE_TYPES.TRANSFORM);
      expect(suggested).toContain(NODE_TYPES.OUTPUT);
    });
  });
});
