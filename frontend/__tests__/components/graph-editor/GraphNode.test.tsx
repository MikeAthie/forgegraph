/**
 * Component tests for GraphNode.
 *
 * Tests the custom node component rendering with different node types,
 * selected states, and configuration previews.
 */

import { render, screen } from "@testing-library/react";
import type { NodeProps } from "@xyflow/react";
import { GraphNode } from "@/components/graph-editor/nodes/GraphNode";
import { NODE_TYPES } from "@/lib/graph-types";

// Mock @xyflow/react Handle component and hooks
jest.mock("@xyflow/react", () => ({
  Handle: ({ type, position, id }: { type: string; position: string; id?: string }) => (
    <div data-testid={`handle-${type}-${position}${id ? `-${id}` : ""}`} />
  ),
  Position: {
    Top: "top",
    Bottom: "bottom",
    Left: "left",
    Right: "right",
  },
  useReactFlow: () => ({
    setNodes: jest.fn(),
    setEdges: jest.fn(),
  }),
}));

// Mock ValidationContext
jest.mock("@/contexts/ValidationContext", () => ({
  useNodeValidation: () => ({
    hasError: false,
    hasWarning: false,
    errors: [],
    warnings: [],
  }),
  ValidationProvider: ({ children }: { children: React.ReactNode }) => <>{children}</>,
}));

describe("GraphNode", () => {
  const createNodeProps = (
    nodeType: string,
    label: string,
    config: Record<string, unknown> = {},
    selected: boolean = false
  ): NodeProps => ({
    id: "test-node",
    type: nodeType,
    data: {
      label,
      nodeType,
      config,
    },
    selected,
    dragging: false,
    isConnectable: true,
    zIndex: 0,
    xPos: 0,
    yPos: 0,
    xPosOrigin: 0,
    yPosOrigin: 0,
  } as NodeProps);

  describe("Basic Rendering", () => {
    it("should render node with label", () => {
      const props = createNodeProps(NODE_TYPES.PROMPT, "Test Prompt Node");
      render(<GraphNode {...props} />);

      expect(screen.getByText("Test Prompt Node")).toBeInTheDocument();
    });

    it("should render node type badge", () => {
      const props = createNodeProps(NODE_TYPES.PROMPT, "My Node");
      render(<GraphNode {...props} />);

      // Badge shows "Prompt" as the node type label
      const badges = screen.getAllByText("Prompt");
      expect(badges.length).toBeGreaterThan(0);
    });

    it("should render input handle", () => {
      const props = createNodeProps(NODE_TYPES.PROMPT, "Node");
      const { container } = render(<GraphNode {...props} />);

      // Handles are now positioned Left/Right instead of Top/Bottom
      expect(container.querySelector('[data-testid="handle-target-left"]')).toBeInTheDocument();
    });

    it("should render output handle", () => {
      const props = createNodeProps(NODE_TYPES.PROMPT, "Node");
      const { container } = render(<GraphNode {...props} />);

      // Handles are now positioned Left/Right instead of Top/Bottom
      expect(container.querySelector('[data-testid="handle-source-right"]')).toBeInTheDocument();
    });

    it("should show 'Unnamed Node' when label is missing", () => {
      const props = createNodeProps(NODE_TYPES.OUTPUT, "");
      render(<GraphNode {...props} />);

      expect(screen.getByText("Unnamed Node")).toBeInTheDocument();
    });
  });

  describe("Node Type Styling", () => {
    it("should apply violet accent styling for Prompt nodes", () => {
      const props = createNodeProps(NODE_TYPES.PROMPT, "Prompt");
      render(<GraphNode {...props} />);

      expect(screen.getByTestId("node-accent-strip")).toHaveClass("bg-violet-500");
    });

    it("should apply amber accent styling for HTTP nodes", () => {
      const props = createNodeProps(NODE_TYPES.HTTP, "HTTP");
      render(<GraphNode {...props} />);

      expect(screen.getByTestId("node-accent-strip")).toHaveClass("bg-amber-500");
    });

    it("should apply blue accent styling for Transform nodes", () => {
      const props = createNodeProps(NODE_TYPES.TRANSFORM, "Transform");
      render(<GraphNode {...props} />);

      expect(screen.getByTestId("node-accent-strip")).toHaveClass("bg-blue-500");
    });

    it("should apply indigo accent styling for Output nodes", () => {
      const props = createNodeProps(NODE_TYPES.OUTPUT, "Output");
      render(<GraphNode {...props} />);

      expect(screen.getByTestId("node-accent-strip")).toHaveClass("bg-indigo-500");
    });

    it("should apply orange accent styling for Branch nodes", () => {
      const props = createNodeProps(NODE_TYPES.BRANCH, "Branch");
      render(<GraphNode {...props} />);

      // Branch is now a diamond shape with orange accent
      expect(screen.getByTestId("node-accent-strip")).toHaveClass("bg-orange-500");
    });

    it("should apply emerald accent styling for Merge nodes", () => {
      const props = createNodeProps(NODE_TYPES.MERGE, "Merge");
      render(<GraphNode {...props} />);

      expect(screen.getByTestId("node-accent-strip")).toHaveClass("bg-emerald-500");
    });

    it("should apply orange accent styling for Human Gate nodes", () => {
      const props = createNodeProps(NODE_TYPES.HUMAN_GATE, "Human Gate");
      render(<GraphNode {...props} />);

      expect(screen.getByTestId("node-accent-strip")).toHaveClass("bg-orange-500");
    });
  });

  describe("Selected State", () => {
    it("should show ring styling when node is selected", () => {
      const props = createNodeProps(NODE_TYPES.PROMPT, "Selected Node", {}, true);
      const { container } = render(<GraphNode {...props} />);

      const nodeElement = container.firstChild;
      expect(nodeElement).toHaveClass("ring-2", "ring-primary", "ring-offset-2");
    });

    it("should not show ring styling when node is not selected", () => {
      const props = createNodeProps(NODE_TYPES.PROMPT, "Unselected Node", {}, false);
      const { container } = render(<GraphNode {...props} />);

      const nodeElement = container.firstChild;
      expect(nodeElement).not.toHaveClass("ring-2");
    });
  });

  describe("Config Preview - Prompt Node", () => {
    it("should show prompt ID when configured", () => {
      const props = createNodeProps(NODE_TYPES.PROMPT, "My Prompt", {
        prompt_id: "my-prompt-123",
      });
      render(<GraphNode {...props} />);

      expect(screen.getByText("Prompt: my-prompt-123")).toBeInTheDocument();
    });

    it("should not show config preview when config is empty", () => {
      const props = createNodeProps(NODE_TYPES.PROMPT, "My Prompt", {});
      render(<GraphNode {...props} />);

      expect(screen.queryByTestId("node-config-preview")).not.toBeInTheDocument();
    });
  });

  describe("Config Preview - HTTP Node", () => {
    it("should show method and URL when configured", () => {
      const props = createNodeProps(NODE_TYPES.HTTP, "HTTP", {
        method: "POST",
        url: "https://api.example.com/endpoint",
      });
      render(<GraphNode {...props} />);

      expect(screen.getByTestId("node-config-preview")).toHaveTextContent(
        /POST https:\/\/api\.example\.com\/endpoi/,
      );
    });

    it("should default to GET method when not specified", () => {
      const props = createNodeProps(NODE_TYPES.HTTP, "HTTP", {
        url: "https://api.test.com",
      });
      render(<GraphNode {...props} />);

      expect(screen.getByTestId("node-config-preview")).toHaveTextContent(/GET https:\/\/api\.test\.com/);
    });

    it("should truncate long URLs", () => {
      const longUrl = "https://api.example.com/very/long/path/to/endpoint/that/should/be/truncated";
      const props = createNodeProps(NODE_TYPES.HTTP, "HTTP", {
        method: "GET",
        url: longUrl,
      });
      render(<GraphNode {...props} />);

      // Should show truncated version with ellipsis
      const preview = screen.getByTestId("node-config-preview");
      expect(preview.textContent).toContain("GET https://api.example.com/very");
      expect(preview.textContent).toContain("...");
    });

    it("should not show config preview when config is empty", () => {
      const props = createNodeProps(NODE_TYPES.HTTP, "HTTP", {});
      render(<GraphNode {...props} />);

      expect(screen.queryByTestId("node-config-preview")).not.toBeInTheDocument();
    });
  });

  describe("Config Preview - Transform Node", () => {
    it("should show expression when configured", () => {
      const props = createNodeProps(NODE_TYPES.TRANSFORM, "My Transform", {
        expression: "state.input | uppercase",
      });
      render(<GraphNode {...props} />);

      const preview = screen.getByTestId("node-config-preview");
      expect(preview.textContent).toContain("state.input | uppercase");
      expect(preview.textContent).toContain("...");
    });

    it("should truncate long expressions", () => {
      const longExpression = "state.very.long.expression.that.should.be.truncated.for.display";
      const props = createNodeProps(NODE_TYPES.TRANSFORM, "My Transform", {
        expression: longExpression,
      });
      render(<GraphNode {...props} />);

      const preview = screen.getByTestId("node-config-preview");
      expect(preview.textContent).toContain("state.very.long.expression");
      expect(preview.textContent).toContain("...");
    });

    it("should not show config preview when config is empty", () => {
      const props = createNodeProps(NODE_TYPES.TRANSFORM, "My Transform", {});
      render(<GraphNode {...props} />);

      expect(screen.queryByTestId("node-config-preview")).not.toBeInTheDocument();
    });
  });

  describe("Config Preview - Output Node", () => {
    it("should show 'Final output' for output nodes", () => {
      const props = createNodeProps(NODE_TYPES.OUTPUT, "Output", {
        output_mapping: { result: "state.data" },
      });
      render(<GraphNode {...props} />);

      expect(screen.getByTestId("node-config-preview")).toHaveTextContent("Final output");
    });

    it("should not show config preview when config is empty", () => {
      const props = createNodeProps(NODE_TYPES.OUTPUT, "Output", {});
      render(<GraphNode {...props} />);

      expect(screen.queryByTestId("node-config-preview")).not.toBeInTheDocument();
    });
  });

  describe("Empty Config", () => {
    it("should not show config preview when config is empty and no preview is defined", () => {
      const props = createNodeProps(NODE_TYPES.BRANCH, "Branch", {});
      render(<GraphNode {...props} />);

      expect(screen.queryByTestId("node-config-preview")).not.toBeInTheDocument();
    });

    it("should handle undefined config", () => {
      const props: NodeProps = {
        id: "test-node",
        type: NODE_TYPES.MERGE,
        data: {
          label: "Merge Node",
          nodeType: NODE_TYPES.MERGE,
        },
        selected: false,
        dragging: false,
        isConnectable: true,
        zIndex: 0,
        xPos: 0,
        yPos: 0,
        xPosOrigin: 0,
        yPosOrigin: 0,
      } as NodeProps;

      render(<GraphNode {...props} />);

      expect(screen.getByText("Merge Node")).toBeInTheDocument();
    });
  });

  describe("Node Type Labels", () => {
    it("should display correct label for Prompt type", () => {
      const props = createNodeProps(NODE_TYPES.PROMPT, "Node");
      render(<GraphNode {...props} />);

      expect(screen.getByText("Prompt")).toBeInTheDocument();
    });

    it("should display correct label for HTTP type", () => {
      const props = createNodeProps(NODE_TYPES.HTTP, "Node");
      render(<GraphNode {...props} />);

      expect(screen.getByText("HTTP")).toBeInTheDocument();
    });

    it("should display correct label for Transform type", () => {
      const props = createNodeProps(NODE_TYPES.TRANSFORM, "Node");
      render(<GraphNode {...props} />);

      expect(screen.getByText("Transform")).toBeInTheDocument();
    });

    it("should display correct label for Output type", () => {
      const props = createNodeProps(NODE_TYPES.OUTPUT, "Node");
      render(<GraphNode {...props} />);

      expect(screen.getByText("Output")).toBeInTheDocument();
    });

    it("should display correct label for Branch type", () => {
      // Diamond shape shows nodeData.label or falls back to typeLabel ("Conditional")
      const props = createNodeProps(NODE_TYPES.BRANCH, "");
      render(<GraphNode {...props} />);

      expect(screen.getByText("Conditional")).toBeInTheDocument();
    });

    it("should display correct label for Merge type", () => {
      const props = createNodeProps(NODE_TYPES.MERGE, "Node");
      render(<GraphNode {...props} />);

      expect(screen.getByText("Merge")).toBeInTheDocument();
    });

    it("should display correct label for Human Gate type", () => {
      const props = createNodeProps(NODE_TYPES.HUMAN_GATE, "Node");
      render(<GraphNode {...props} />);

      expect(screen.getByText("Human Gate")).toBeInTheDocument();
    });
  });

  describe("Layout and Structure", () => {
    it("should have minimum width", () => {
      const props = createNodeProps(NODE_TYPES.PROMPT, "Node");
      const { container } = render(<GraphNode {...props} />);

      const nodeElement = container.firstChild;
      expect(nodeElement).toHaveClass("min-w-[180px]");
    });

    it("should have rounded corners", () => {
      const props = createNodeProps(NODE_TYPES.PROMPT, "Node");
      const { container } = render(<GraphNode {...props} />);

      const nodeElement = container.firstChild;
      expect(nodeElement).toHaveClass("rounded-xl");
    });

    it("should have border and shadow", () => {
      const props = createNodeProps(NODE_TYPES.PROMPT, "Node");
      const { container } = render(<GraphNode {...props} />);

      const nodeElement = container.firstChild;
      expect(nodeElement).toHaveClass("border", "shadow-sm");
    });

    it("should have transition effects", () => {
      const props = createNodeProps(NODE_TYPES.PROMPT, "Node");
      const { container } = render(<GraphNode {...props} />);

      const nodeElement = container.firstChild;
      expect(nodeElement).toHaveClass("transition-all");
    });
  });

  describe("Badge Styling", () => {
    it("should render type label with appropriate styling", () => {
      const props = createNodeProps(NODE_TYPES.PROMPT, "Node");
      render(<GraphNode {...props} />);

      // Type label is now shown as a subtle caption below the node name
      const badge = screen.getByText("Prompt");
      expect(badge).toHaveClass("text-[11px]", "text-muted-foreground", "capitalize");
    });
  });

  describe("Multiple Nodes", () => {
    it("should render multiple node types correctly", () => {
      const { rerender } = render(
        <GraphNode {...createNodeProps(NODE_TYPES.PROMPT, "Prompt Node")} />
      );
      expect(screen.getByText("Prompt Node")).toBeInTheDocument();

      rerender(<GraphNode {...createNodeProps(NODE_TYPES.HTTP, "HTTP Node")} />);
      expect(screen.getByText("HTTP Node")).toBeInTheDocument();

      rerender(<GraphNode {...createNodeProps(NODE_TYPES.OUTPUT, "Output Node")} />);
      expect(screen.getByText("Output Node")).toBeInTheDocument();
    });
  });
});
