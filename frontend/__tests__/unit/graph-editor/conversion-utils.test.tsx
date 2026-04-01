/**
 * Unit tests for graph conversion utilities.
 *
 * Tests the conversion between GraphJson and React Flow formats.
 * These functions are critical for maintaining data integrity when
 * users edit graphs in the visual editor.
 */

import type { Node, Edge } from "@xyflow/react";
import type { GraphJson } from "@/lib/graph-types";
import { NODE_TYPES, createEmptyGraphJson } from "@/lib/graph-types";
import { graphJsonToReactFlow, reactFlowToGraphJson } from "@/lib/graph-conversion";

describe("Graph Conversion Utilities", () => {
  describe("graphJsonToReactFlow", () => {
    it("should convert an empty graph", () => {
      const emptyGraph = createEmptyGraphJson();
      const result = graphJsonToReactFlow(emptyGraph);

      expect(result.nodes).toEqual([]);
      expect(result.edges).toEqual([]);
    });

    it("should convert a single node with all required fields", () => {
      const graphJson: GraphJson = {
        nodes: [
          {
            id: "node-1",
            type: NODE_TYPES.PROMPT,
            name: "Test Prompt",
            config: { prompt_id: "test-prompt" },
          },
        ],
        edges: [],
        metadata: {},
      };

      const result = graphJsonToReactFlow(graphJson);

      expect(result.nodes).toHaveLength(1);
      expect(result.nodes[0]).toMatchObject({
        id: "node-1",
        type: NODE_TYPES.PROMPT,
        data: {
          label: "Test Prompt",
          nodeType: NODE_TYPES.PROMPT,
          config: { prompt_id: "test-prompt" },
        },
      });
      expect(result.nodes[0].position).toBeDefined();
    });

    it("should convert nodes with custom positions from editor state", () => {
      const graphJson: GraphJson = {
        nodes: [
          {
            id: "node-1",
            type: NODE_TYPES.HTTP,
            name: "HTTP Request",
            config: {},
          },
        ],
        edges: [],
        metadata: {},
        editor_state: {
          nodePositions: {
            "node-1": { x: 500, y: 300 },
          },
        },
      };

      const result = graphJsonToReactFlow(graphJson);

      expect(result.nodes[0].position).toEqual({ x: 500, y: 300 });
    });

    it("should use default positions when editor state is missing", () => {
      const graphJson: GraphJson = {
        nodes: [
          {
            id: "node-1",
            type: NODE_TYPES.TRANSFORM,
            name: "Transform",
            config: {},
          },
          {
            id: "node-2",
            type: NODE_TYPES.OUTPUT,
            name: "Output",
            config: {},
          },
        ],
        edges: [],
        metadata: {},
      };

      const result = graphJsonToReactFlow(graphJson);

      expect(result.nodes[0].position).toEqual({ x: 100, y: 100 });
      expect(result.nodes[1].position).toEqual({ x: 350, y: 100 });
    });

    it("should convert nodes with optional fields", () => {
      const graphJson: GraphJson = {
        nodes: [
          {
            id: "node-1",
            type: NODE_TYPES.PROMPT,
            name: "Retryable Prompt",
            disabled: true,
            config: {},
            retry_policy: {
              max_attempts: 3,
              backoff_ms: 1000,
              backoff_strategy: "exponential",
            },
            timeout_ms: 30000,
            outputs: [{ name: "success" }, { name: "failure" }],
          },
        ],
        edges: [],
        metadata: {},
      };

      const result = graphJsonToReactFlow(graphJson);

      expect(result.nodes[0].data).toMatchObject({
        disabled: true,
        retry_policy: {
          max_attempts: 3,
          backoff_ms: 1000,
          backoff_strategy: "exponential",
        },
        timeout_ms: 30000,
        outputs: [{ name: "success" }, { name: "failure" }],
      });
    });

    it("should convert edges with all fields", () => {
      const graphJson: GraphJson = {
        nodes: [
          {
            id: "node-1",
            type: NODE_TYPES.PROMPT,
            name: "Start",
            config: {},
          },
          {
            id: "node-2",
            type: NODE_TYPES.OUTPUT,
            name: "End",
            config: {},
          },
        ],
        edges: [
          {
            id: "edge-1",
            from: "node-1",
            to: "node-2",
            label: "Success Path",
            condition: "result.success === true",
          },
        ],
        metadata: {},
      };

      const result = graphJsonToReactFlow(graphJson);

      expect(result.edges).toHaveLength(1);
      expect(result.edges[0]).toEqual({
        id: "edge-1",
        source: "node-1",
        target: "node-2",
        label: "Success Path",
        data: {
          condition: "result.success === true",
        },
      });
    });

    it("should handle edges without optional fields", () => {
      const graphJson: GraphJson = {
        nodes: [
          {
            id: "node-1",
            type: NODE_TYPES.HTTP,
            name: "API Call",
            config: {},
          },
          {
            id: "node-2",
            type: NODE_TYPES.TRANSFORM,
            name: "Process",
            config: {},
          },
        ],
        edges: [
          {
            id: "edge-1",
            from: "node-1",
            to: "node-2",
          },
        ],
        metadata: {},
      };

      const result = graphJsonToReactFlow(graphJson);

      expect(result.edges[0]).toEqual({
        id: "edge-1",
        source: "node-1",
        target: "node-2",
        label: undefined,
        data: {
          condition: undefined,
        },
      });
    });

    it("should handle multiple nodes and edges", () => {
      const graphJson: GraphJson = {
        nodes: [
          {
            id: "node-1",
            type: NODE_TYPES.PROMPT,
            name: "Start",
            config: {},
          },
          {
            id: "node-2",
            type: NODE_TYPES.HTTP,
            name: "API",
            config: {},
          },
          {
            id: "node-3",
            type: NODE_TYPES.TRANSFORM,
            name: "Transform",
            config: {},
          },
          {
            id: "node-4",
            type: NODE_TYPES.OUTPUT,
            name: "Output",
            config: {},
          },
        ],
        edges: [
          {
            id: "edge-1",
            from: "node-1",
            to: "node-2",
          },
          {
            id: "edge-2",
            from: "node-2",
            to: "node-3",
          },
          {
            id: "edge-3",
            from: "node-3",
            to: "node-4",
          },
        ],
        metadata: {},
      };

      const result = graphJsonToReactFlow(graphJson);

      expect(result.nodes).toHaveLength(4);
      expect(result.edges).toHaveLength(3);
    });
  });

  describe("reactFlowToGraphJson", () => {
    it("should convert empty React Flow state", () => {
      const result = reactFlowToGraphJson([], [], { name: "Test Graph" });

      expect(result.nodes).toEqual([]);
      expect(result.edges).toEqual([]);
      expect(result.metadata).toEqual({ name: "Test Graph" });
      expect(result.editor_state?.nodePositions).toEqual({});
    });

    it("should convert a single React Flow node to GraphNode", () => {
      const rfNodes: Node[] = [
        {
          id: "node-1",
          type: NODE_TYPES.PROMPT,
          position: { x: 100, y: 200 },
          data: {
            label: "My Prompt",
            nodeType: NODE_TYPES.PROMPT,
            config: { prompt_id: "abc-123" },
          },
        },
      ];

      const result = reactFlowToGraphJson(rfNodes, [], {});

      expect(result.nodes).toHaveLength(1);
      expect(result.nodes[0]).toMatchObject({
        id: "node-1",
        type: NODE_TYPES.PROMPT,
        name: "My Prompt",
        config: { prompt_id: "abc-123" },
      });
    });

    it("should preserve node positions in editor state", () => {
      const rfNodes: Node[] = [
        {
          id: "node-1",
          type: NODE_TYPES.HTTP,
          position: { x: 500, y: 300 },
          data: {
            label: "HTTP Node",
            nodeType: NODE_TYPES.HTTP,
            config: {},
          },
        },
      ];

      const result = reactFlowToGraphJson(rfNodes, [], {});

      expect(result.editor_state?.nodePositions).toEqual({
        "node-1": { x: 500, y: 300 },
      });
    });

    it("should convert nodes with optional fields", () => {
      const rfNodes: Node[] = [
        {
          id: "node-1",
          type: NODE_TYPES.PROMPT,
          position: { x: 0, y: 0 },
          data: {
            label: "Retryable Node",
            nodeType: NODE_TYPES.PROMPT,
            config: {},
            retry_policy: {
              max_attempts: 5,
              backoff_ms: 2000,
            },
            timeout_ms: 60000,
            outputs: [{ name: "success" }],
          },
        },
      ];

      const result = reactFlowToGraphJson(rfNodes, [], {});

      expect(result.nodes[0]).toMatchObject({
        retry_policy: {
          max_attempts: 5,
          backoff_ms: 2000,
        },
        timeout_ms: 60000,
        outputs: [{ name: "success" }],
      });
    });

    it("should convert React Flow edges to GraphEdges", () => {
      const rfNodes: Node[] = [
        {
          id: "node-1",
          type: NODE_TYPES.PROMPT,
          position: { x: 0, y: 0 },
          data: {
            label: "Start",
            nodeType: NODE_TYPES.PROMPT,
            config: {},
          },
        },
        {
          id: "node-2",
          type: NODE_TYPES.OUTPUT,
          position: { x: 300, y: 0 },
          data: {
            label: "End",
            nodeType: NODE_TYPES.OUTPUT,
            config: {},
          },
        },
      ];

      const rfEdges: Edge[] = [
        {
          id: "edge-1",
          source: "node-1",
          target: "node-2",
          label: "Next",
          data: {
            condition: "state.ready",
          },
        },
      ];

      const result = reactFlowToGraphJson(rfNodes, rfEdges, {});

      expect(result.edges).toHaveLength(1);
      expect(result.edges[0]).toEqual({
        id: "edge-1",
        from: "node-1",
        to: "node-2",
        label: "Next",
        condition: "state.ready",
      });
    });

    it("should include graph_id and version_id when provided", () => {
      const result = reactFlowToGraphJson([], [], {}, "graph-123", "version-456");

      expect(result.graph_id).toBe("graph-123");
      expect(result.version_id).toBe("version-456");
    });

    it("should omit graph_id and version_id when not provided", () => {
      const result = reactFlowToGraphJson([], [], {});

      expect(result.graph_id).toBeUndefined();
      expect(result.version_id).toBeUndefined();
    });

    it("should handle missing config gracefully", () => {
      const rfNodes: Node[] = [
        {
          id: "node-1",
          type: NODE_TYPES.OUTPUT,
          position: { x: 0, y: 0 },
          data: {
            label: "Output",
            nodeType: NODE_TYPES.OUTPUT,
          },
        },
      ];

      const result = reactFlowToGraphJson(rfNodes, [], {});

      expect(result.nodes[0].config).toEqual({});
    });
  });

  describe("Round-trip conversion", () => {
    it("should preserve data through GraphJson -> ReactFlow -> GraphJson", () => {
      const originalGraph: GraphJson = {
        graph_id: "test-graph",
        version_id: "v1",
        nodes: [
          {
            id: "node-1",
            type: NODE_TYPES.PROMPT,
            name: "Start Prompt",
            config: { prompt_id: "prompt-1" },
            retry_policy: {
              max_attempts: 3,
              backoff_ms: 1000,
            },
          },
          {
            id: "node-2",
            type: NODE_TYPES.HTTP,
            name: "API Call",
            disabled: true,
            config: {
              method: "POST",
              url: "https://api.example.com/data",
            },
            timeout_ms: 5000,
          },
          {
            id: "node-3",
            type: NODE_TYPES.OUTPUT,
            name: "Final Output",
            config: {
              output_mapping: { result: "state.data" },
            },
          },
        ],
        edges: [
          {
            id: "edge-1",
            from: "node-1",
            to: "node-2",
            label: "Next",
          },
          {
            id: "edge-2",
            from: "node-2",
            to: "node-3",
            condition: "response.ok",
          },
        ],
        metadata: {
          name: "Test Workflow",
          description: "A test workflow",
        },
        editor_state: {
          nodePositions: {
            "node-1": { x: 100, y: 100 },
            "node-2": { x: 400, y: 100 },
            "node-3": { x: 700, y: 100 },
          },
        },
      };

      // Convert to React Flow format
      const { nodes: rfNodes, edges: rfEdges } = graphJsonToReactFlow(originalGraph);

      // Convert back to GraphJson
      const convertedGraph = reactFlowToGraphJson(
        rfNodes,
        rfEdges,
        originalGraph.metadata ?? {},
        originalGraph.graph_id,
        originalGraph.version_id,
      );

      // Verify all critical data is preserved
      expect(convertedGraph.graph_id).toBe(originalGraph.graph_id);
      expect(convertedGraph.version_id).toBe(originalGraph.version_id);
      expect(convertedGraph.nodes).toHaveLength(originalGraph.nodes.length);
      expect(convertedGraph.edges).toHaveLength(originalGraph.edges.length);

      // Check node data
      for (let i = 0; i < originalGraph.nodes.length; i++) {
        const original = originalGraph.nodes[i];
        const converted = convertedGraph.nodes[i];

        expect(converted.id).toBe(original.id);
        expect(converted.type).toBe(original.type);
        expect(converted.name).toBe(original.name);
        expect(converted.disabled).toBe(original.disabled);
        expect(converted.config).toEqual(original.config);
        expect(converted.retry_policy).toEqual(original.retry_policy);
        expect(converted.timeout_ms).toEqual(original.timeout_ms);
      }

      // Check edge data
      for (let i = 0; i < originalGraph.edges.length; i++) {
        const original = originalGraph.edges[i];
        const converted = convertedGraph.edges[i];

        expect(converted.id).toBe(original.id);
        expect(converted.from).toBe(original.from);
        expect(converted.to).toBe(original.to);
        expect(converted.label).toBe(original.label);
        expect(converted.condition).toBe(original.condition);
      }

      // Check positions are preserved
      expect(convertedGraph.editor_state?.nodePositions).toEqual(originalGraph.editor_state?.nodePositions);
    });

    it("should handle graphs with no edges", () => {
      const graphJson: GraphJson = {
        nodes: [
          {
            id: "node-1",
            type: NODE_TYPES.PROMPT,
            name: "Isolated Node",
            config: {},
          },
        ],
        edges: [],
        metadata: {},
      };

      const { nodes, edges } = graphJsonToReactFlow(graphJson);
      const converted = reactFlowToGraphJson(nodes, edges, {});

      expect(converted.nodes).toHaveLength(1);
      expect(converted.edges).toHaveLength(0);
    });

    it("should handle graphs with missing optional fields", () => {
      const graphJson: GraphJson = {
        nodes: [
          {
            id: "node-1",
            type: NODE_TYPES.OUTPUT,
            name: "Output",
            config: {},
          },
        ],
        edges: [],
        metadata: {},
      };

      const { nodes, edges } = graphJsonToReactFlow(graphJson);
      const converted = reactFlowToGraphJson(nodes, edges, {});

      expect(converted.nodes[0]).toMatchObject({
        id: "node-1",
        type: NODE_TYPES.OUTPUT,
        name: "Output",
        config: {},
      });
      expect(converted.nodes[0].retry_policy).toBeUndefined();
      expect(converted.nodes[0].timeout_ms).toBeUndefined();
      expect(converted.nodes[0].outputs).toBeUndefined();
    });
  });

  describe("Edge cases", () => {
    it("should handle nodes with empty config objects", () => {
      const graphJson: GraphJson = {
        nodes: [
          {
            id: "node-1",
            type: NODE_TYPES.TRANSFORM,
            name: "Transform",
            config: {},
          },
        ],
        edges: [],
        metadata: {},
      };

      const { nodes } = graphJsonToReactFlow(graphJson);

      expect(nodes[0].data.config).toEqual({});
    });

    it("should handle metadata with various data types", () => {
      const metadata = {
        name: "Complex Graph",
        description: "A description",
        version: 2,
        tags: ["test", "demo"],
        isPublic: false,
        nested: { key: "value" },
      };

      const result = reactFlowToGraphJson([], [], metadata);

      expect(result.metadata).toEqual(metadata);
    });

    it("should handle nodes laid out in a grid", () => {
      const graphJson: GraphJson = {
        nodes: Array.from({ length: 8 }, (_, i) => ({
          id: `node-${i}`,
          type: NODE_TYPES.PROMPT,
          name: `Node ${i}`,
          config: {},
        })),
        edges: [],
        metadata: {},
      };

      const { nodes } = graphJsonToReactFlow(graphJson);

      // Check that default positions create a grid layout
      expect(nodes[0].position).toEqual({ x: 100, y: 100 });
      expect(nodes[4].position).toEqual({ x: 100, y: 250 });
      expect(nodes[3].position).toEqual({ x: 850, y: 100 });
    });

    it("should preserve required keys even with minimal data", () => {
      const graphJson: GraphJson = {
        nodes: [
          {
            id: "min-node",
            type: NODE_TYPES.OUTPUT,
            name: "Minimal",
            config: {},
          },
        ],
        edges: [],
      };

      const { nodes, edges } = graphJsonToReactFlow(graphJson);
      const converted = reactFlowToGraphJson(nodes, edges, {});

      // All required keys should be present
      expect(converted).toHaveProperty("nodes");
      expect(converted).toHaveProperty("edges");
      expect(converted.nodes[0]).toHaveProperty("id");
      expect(converted.nodes[0]).toHaveProperty("type");
      expect(converted.nodes[0]).toHaveProperty("name");
      expect(converted.nodes[0]).toHaveProperty("config");
    });
  });
});
