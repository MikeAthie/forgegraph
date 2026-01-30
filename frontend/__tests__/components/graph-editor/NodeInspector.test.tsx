/**
 * Component tests for NodeInspector.
 *
 * Tests the inspector panel that displays graph info when nothing is selected
 * and node configuration when a node is selected.
 */

import { render, screen, waitFor, fireEvent, act } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import type { Node } from "@xyflow/react";
import { NodeInspector } from "@/components/graph-editor/NodeInspector";
import { NODE_TYPES } from "@/lib/graph-types";

describe("NodeInspector", () => {
  const mockOnUpdateNode = jest.fn();
  const mockOnUpdateEdge = jest.fn();
  const mockOnDeleteNode = jest.fn();
  const mockOnDeleteEdge = jest.fn();
  const mockOnDuplicateNode = jest.fn();
  const mockOnUpdateMetadata = jest.fn();

  const defaultProps = {
    selectedNode: null,
    selectedEdge: null,
    nodes: [],
    graphName: "Test Graph",
    graphDescription: "A test graph description",
    onUpdateNode: mockOnUpdateNode,
    onUpdateEdge: mockOnUpdateEdge,
    onDeleteNode: mockOnDeleteNode,
    onDeleteEdge: mockOnDeleteEdge,
    onDuplicateNode: mockOnDuplicateNode,
    onUpdateMetadata: mockOnUpdateMetadata,
  };

  beforeEach(() => {
    jest.clearAllMocks();
  });

  describe("No Node Selected - Graph Info Display", () => {
    it("should display 'Graph Info' header when no node is selected", () => {
      render(<NodeInspector {...defaultProps} />);

      expect(screen.getByText("Graph Info")).toBeInTheDocument();
    });

    it("should display graph name", () => {
      render(<NodeInspector {...defaultProps} />);

      expect(screen.getByText("Name")).toBeInTheDocument();
      expect(screen.getByText("Test Graph")).toBeInTheDocument();
    });

    it("should display graph description", () => {
      render(<NodeInspector {...defaultProps} />);

      expect(screen.getByText("Description")).toBeInTheDocument();
      expect(screen.getByText("A test graph description")).toBeInTheDocument();
    });

    it("should show placeholder when description is empty", () => {
      render(<NodeInspector {...defaultProps} graphDescription="" />);

      expect(screen.getByText("No description")).toBeInTheDocument();
    });

    it("should display 'Edit Info' button", () => {
      render(<NodeInspector {...defaultProps} />);

      expect(screen.getByRole("button", { name: /edit info/i })).toBeInTheDocument();
    });

    it("should display helper text about selecting nodes", () => {
      render(<NodeInspector {...defaultProps} />);

      expect(
        screen.getByText("Select a node on the canvas to view and edit its configuration.")
      ).toBeInTheDocument();
    });
  });

  describe("Graph Metadata Editing", () => {
    it("should show edit form when 'Edit Info' is clicked", async () => {
      const user = userEvent.setup();
      render(<NodeInspector {...defaultProps} />);

      const editButton = screen.getByRole("button", { name: /edit info/i });
      await user.click(editButton);

      expect(screen.getByRole("button", { name: /^save$/i })).toBeInTheDocument();
      expect(screen.getByRole("button", { name: /^cancel$/i })).toBeInTheDocument();
    });

    it("should populate form with current values", async () => {
      const user = userEvent.setup();
      render(<NodeInspector {...defaultProps} />);

      await user.click(screen.getByRole("button", { name: /edit info/i }));

      const nameInput = screen.getByDisplayValue("Test Graph");
      const descInput = screen.getByDisplayValue("A test graph description");

      expect(nameInput).toBeInTheDocument();
      expect(descInput).toBeInTheDocument();
    });

    it("should allow editing graph name", async () => {
      const user = userEvent.setup();
      render(<NodeInspector {...defaultProps} />);

      await user.click(screen.getByRole("button", { name: /edit info/i }));

      const nameInput = screen.getByDisplayValue("Test Graph");
      await user.clear(nameInput);
      await user.type(nameInput, "Updated Graph Name");

      expect(nameInput).toHaveValue("Updated Graph Name");
    });

    it("should allow editing graph description", async () => {
      const user = userEvent.setup();
      render(<NodeInspector {...defaultProps} />);

      await user.click(screen.getByRole("button", { name: /edit info/i }));

      const descInput = screen.getByDisplayValue("A test graph description");
      await user.clear(descInput);
      await user.type(descInput, "New description");

      expect(descInput).toHaveValue("New description");
    });

    it("should call onUpdateMetadata when Save is clicked", async () => {
      const user = userEvent.setup();
      mockOnUpdateMetadata.mockResolvedValue(undefined);

      render(<NodeInspector {...defaultProps} />);

      await user.click(screen.getByRole("button", { name: /edit info/i }));

      const nameInput = screen.getByDisplayValue("Test Graph");
      await user.clear(nameInput);
      await user.type(nameInput, "New Name");

      await user.click(screen.getByRole("button", { name: /^save$/i }));

      await waitFor(() => {
        expect(mockOnUpdateMetadata).toHaveBeenCalledWith("New Name", "A test graph description");
      });
    });

    it("should cancel editing when Cancel is clicked", async () => {
      const user = userEvent.setup();
      render(<NodeInspector {...defaultProps} />);

      await user.click(screen.getByRole("button", { name: /edit info/i }));

      const nameInput = screen.getByDisplayValue("Test Graph");
      fireEvent.change(nameInput, { target: { value: "Should Not Save" } });

      await user.click(screen.getByRole("button", { name: /^cancel$/i }));

      // Should return to display mode with original values
      await waitFor(() => {
        expect(screen.getByText("Test Graph")).toBeInTheDocument();
        expect(screen.queryByRole("button", { name: /^save$/i })).not.toBeInTheDocument();
      });
    });

    // Note: Tests for "saving state" and "disable button while saving" are omitted
    // because they require complex async state management that triggers React act warnings.
    // The functionality is covered by E2E tests instead.
  });

  describe("Node Selected - Node Config Display", () => {
    const promptNode: Node = {
      id: "node-1",
      type: NODE_TYPES.PROMPT,
      position: { x: 0, y: 0 },
      data: {
        label: "My Prompt Node",
        nodeType: NODE_TYPES.PROMPT,
        config: { prompt_id: "prompt-123" },
      },
    };

    it("should display 'Node Config' header when node is selected", () => {
      render(<NodeInspector {...defaultProps} selectedNode={promptNode} />);

      expect(screen.getByText("Node Config")).toBeInTheDocument();
    });

    it("should display Delete button", () => {
      render(<NodeInspector {...defaultProps} selectedNode={promptNode} />);

      expect(screen.getByRole("button", { name: /delete/i })).toBeInTheDocument();
    });

    it("should display node type badge", () => {
      render(<NodeInspector {...defaultProps} selectedNode={promptNode} />);

      expect(screen.getByText("prompt")).toBeInTheDocument();
    });

    it("should display node name input", () => {
      render(<NodeInspector {...defaultProps} selectedNode={promptNode} />);

      const nameInput = screen.getByDisplayValue("My Prompt Node");
      expect(nameInput).toBeInTheDocument();
    });

    it("should display node ID (read-only)", () => {
      render(<NodeInspector {...defaultProps} selectedNode={promptNode} />);

      expect(screen.getByText("node-1")).toBeInTheDocument();
    });

    it("should call onUpdateNode when node name is changed", () => {
      render(<NodeInspector {...defaultProps} selectedNode={promptNode} />);

      const nameInput = screen.getByDisplayValue("My Prompt Node");

      // Use fireEvent.change to directly set the value
      fireEvent.change(nameInput, { target: { value: "NewName" } });

      expect(mockOnUpdateNode).toHaveBeenCalledWith("node-1", { label: "NewName" });
    });

    it("should call onDeleteNode when Delete button is clicked", async () => {
      const user = userEvent.setup();
      render(<NodeInspector {...defaultProps} selectedNode={promptNode} />);

      const deleteButton = screen.getByRole("button", { name: /delete/i });
      await user.click(deleteButton);

      expect(mockOnDeleteNode).toHaveBeenCalledWith("node-1");
    });
  });

  describe("Prompt Node Configuration", () => {
    const promptNode: Node = {
      id: "prompt-node",
      type: NODE_TYPES.PROMPT,
      position: { x: 0, y: 0 },
      data: {
        label: "Prompt Node",
        nodeType: NODE_TYPES.PROMPT,
        config: { prompt_id: "prompt-abc" },
      },
    };

    it("should display Prompt Configuration section", () => {
      render(<NodeInspector {...defaultProps} selectedNode={promptNode} />);

      expect(screen.getByText("Prompt Configuration")).toBeInTheDocument();
    });

    it("should display Prompt Template ID field", () => {
      render(<NodeInspector {...defaultProps} selectedNode={promptNode} />);

      expect(screen.getByText(/Prompt Template ID/i)).toBeInTheDocument();
      expect(screen.getByDisplayValue("prompt-abc")).toBeInTheDocument();
    });

    it("should update config when prompt_id changes", () => {
      render(<NodeInspector {...defaultProps} selectedNode={promptNode} />);

      const promptIdInput = screen.getByDisplayValue("prompt-abc");

      // Use fireEvent.change to directly set the value
      fireEvent.change(promptIdInput, { target: { value: "newpromptid" } });

      expect(mockOnUpdateNode).toHaveBeenCalledWith("prompt-node", {
        config: { prompt_id: "newpromptid" },
      });
    });

    it("should display helper text for prompt field", () => {
      render(<NodeInspector {...defaultProps} selectedNode={promptNode} />);

      expect(screen.getByText(/Load a prompt from the Prompt Library/i)).toBeInTheDocument();
      expect(screen.getByText("Prompt Template")).toBeInTheDocument();
    });
  });

  describe("HTTP Node Configuration", () => {
    const httpNode: Node = {
      id: "http-node",
      type: NODE_TYPES.HTTP,
      position: { x: 0, y: 0 },
      data: {
        label: "HTTP Node",
        nodeType: NODE_TYPES.HTTP,
        config: {
          method: "POST",
          url: "https://api.example.com/data",
          output_key: "response",
        },
      },
    };

    it("should display HTTP Configuration section", () => {
      render(<NodeInspector {...defaultProps} selectedNode={httpNode} />);

      expect(screen.getByText("HTTP Configuration")).toBeInTheDocument();
    });

    it("should display method dropdown with current value", () => {
      render(<NodeInspector {...defaultProps} selectedNode={httpNode} />);

      const methodSelect = screen.getByDisplayValue("POST");
      expect(methodSelect).toBeInTheDocument();
    });

    it("should display URL field", () => {
      render(<NodeInspector {...defaultProps} selectedNode={httpNode} />);

      expect(screen.getByDisplayValue("https://api.example.com/data")).toBeInTheDocument();
    });

    it("should display output key field", () => {
      render(<NodeInspector {...defaultProps} selectedNode={httpNode} />);

      expect(screen.getByDisplayValue("response")).toBeInTheDocument();
    });

    it("should update config when method changes", async () => {
      const user = userEvent.setup();
      render(<NodeInspector {...defaultProps} selectedNode={httpNode} />);

      const methodSelect = screen.getByDisplayValue("POST");
      await user.selectOptions(methodSelect, "GET");

      expect(mockOnUpdateNode).toHaveBeenCalledWith("http-node", {
        config: expect.objectContaining({ method: "GET" }),
      });
    });

    it("should show all HTTP methods in dropdown", () => {
      render(<NodeInspector {...defaultProps} selectedNode={httpNode} />);

      expect(screen.getByRole("option", { name: "GET" })).toBeInTheDocument();
      expect(screen.getByRole("option", { name: "POST" })).toBeInTheDocument();
      expect(screen.getByRole("option", { name: "PUT" })).toBeInTheDocument();
      expect(screen.getByRole("option", { name: "PATCH" })).toBeInTheDocument();
      expect(screen.getByRole("option", { name: "DELETE" })).toBeInTheDocument();
    });
  });

  describe("Transform Node Configuration", () => {
    const transformNode: Node = {
      id: "transform-node",
      type: NODE_TYPES.TRANSFORM,
      position: { x: 0, y: 0 },
      data: {
        label: "Transform Node",
        nodeType: NODE_TYPES.TRANSFORM,
        config: {
          expression: "state.input | uppercase",
          output_key: "result",
        },
      },
    };

    it("should display Transform Configuration section", () => {
      render(<NodeInspector {...defaultProps} selectedNode={transformNode} />);

      expect(screen.getByText("Transform Configuration")).toBeInTheDocument();
    });

    it("should display expression textarea", () => {
      render(<NodeInspector {...defaultProps} selectedNode={transformNode} />);

      expect(screen.getByDisplayValue("state.input | uppercase")).toBeInTheDocument();
    });

    it("should display output key field", () => {
      render(<NodeInspector {...defaultProps} selectedNode={transformNode} />);

      const outputKeyInputs = screen.getAllByDisplayValue("result");
      expect(outputKeyInputs.length).toBeGreaterThan(0);
    });

    it("should update config when expression changes", () => {
      render(<NodeInspector {...defaultProps} selectedNode={transformNode} />);

      const expressionInput = screen.getByDisplayValue("state.input | uppercase");

      // Use fireEvent.change to directly set the value
      fireEvent.change(expressionInput, { target: { value: "newexpression" } });

      expect(mockOnUpdateNode).toHaveBeenCalledWith("transform-node", {
        config: expect.objectContaining({ expression: "newexpression" }),
      });
    });
  });

  describe("Output Node Configuration", () => {
    const outputNode: Node = {
      id: "output-node",
      type: NODE_TYPES.OUTPUT,
      position: { x: 0, y: 0 },
      data: {
        label: "Output Node",
        nodeType: NODE_TYPES.OUTPUT,
        config: {
          output_mapping: { result: "state.final_output" },
        },
      },
    };

    it("should display Output Configuration section", () => {
      render(<NodeInspector {...defaultProps} selectedNode={outputNode} />);

      expect(screen.getByText("Output Configuration")).toBeInTheDocument();
    });

    it("should display output mapping inputs", () => {
      render(<NodeInspector {...defaultProps} selectedNode={outputNode} />);

      expect(screen.getByDisplayValue("result")).toBeInTheDocument();
      expect(screen.getByDisplayValue("state.final_output")).toBeInTheDocument();
    });

    it("should update mapping value when edited", () => {
      render(<NodeInspector {...defaultProps} selectedNode={outputNode} />);

      const valueInput = screen.getByDisplayValue("state.final_output");
      fireEvent.change(valueInput, { target: { value: "state.updated_output" } });

      expect(mockOnUpdateNode).toHaveBeenCalledWith("output-node", {
        config: { output_mapping: { result: "state.updated_output" } },
      });
    });
  });

  describe("Node Type Display", () => {
    it("should display 'http' badge for HTTP nodes", () => {
      const httpNode: Node = {
        id: "http-1",
        type: NODE_TYPES.HTTP,
        position: { x: 0, y: 0 },
        data: { label: "HTTP", nodeType: NODE_TYPES.HTTP, config: {} },
      };

      render(<NodeInspector {...defaultProps} selectedNode={httpNode} />);

      expect(screen.getByText("http")).toBeInTheDocument();
    });

    it("should display 'transform' badge for Transform nodes", () => {
      const transformNode: Node = {
        id: "transform-1",
        type: NODE_TYPES.TRANSFORM,
        position: { x: 0, y: 0 },
        data: { label: "Transform", nodeType: NODE_TYPES.TRANSFORM, config: {} },
      };

      render(<NodeInspector {...defaultProps} selectedNode={transformNode} />);

      expect(screen.getByText("transform")).toBeInTheDocument();
    });

    it("should display 'output' badge for Output nodes", () => {
      const outputNode: Node = {
        id: "output-1",
        type: NODE_TYPES.OUTPUT,
        position: { x: 0, y: 0 },
        data: { label: "Output", nodeType: NODE_TYPES.OUTPUT, config: {} },
      };

      render(<NodeInspector {...defaultProps} selectedNode={outputNode} />);

      expect(screen.getByText("output")).toBeInTheDocument();
    });
  });

  describe("Empty Configuration", () => {
    it("should handle nodes with empty config", () => {
      const nodeWithEmptyConfig: Node = {
        id: "empty-node",
        type: NODE_TYPES.PROMPT,
        position: { x: 0, y: 0 },
        data: {
          label: "Empty Config",
          nodeType: NODE_TYPES.PROMPT,
          config: {},
        },
      };

      render(<NodeInspector {...defaultProps} selectedNode={nodeWithEmptyConfig} />);

      expect(screen.getByText("Prompt Configuration")).toBeInTheDocument();
    });

    it("should handle nodes with missing config", () => {
      const nodeWithoutConfig: Node = {
        id: "no-config",
        type: NODE_TYPES.OUTPUT,
        position: { x: 0, y: 0 },
        data: {
          label: "No Config",
          nodeType: NODE_TYPES.OUTPUT,
        },
      };

      render(<NodeInspector {...defaultProps} selectedNode={nodeWithoutConfig} />);

      expect(screen.getByText("Output Configuration")).toBeInTheDocument();
    });
  });

  describe("Node Cache Configuration", () => {
    const cacheNode: Node = {
      id: "cache-node",
      type: NODE_TYPES.TRANSFORM,
      position: { x: 0, y: 0 },
      data: {
        label: "Cache Node",
        nodeType: NODE_TYPES.TRANSFORM,
        config: {},
      },
    };

    it("should allow enabling cache from advanced section", async () => {
      const user = userEvent.setup();
      render(<NodeInspector {...defaultProps} selectedNode={cacheNode} />);

      await user.click(screen.getByRole("button", { name: /advanced/i }));

      const toggle = screen.getByRole("switch", { name: /enable cache/i });
      await user.click(toggle);

      expect(mockOnUpdateNode).toHaveBeenCalledWith("cache-node", {
        config: expect.objectContaining({
          cache: expect.objectContaining({ enabled: true }),
        }),
      });
    });

    it("should show TTL input when cache is enabled", async () => {
      const user = userEvent.setup();
      const nodeWithCache: Node = {
        ...cacheNode,
        data: {
          ...cacheNode.data,
          config: {
            cache: { enabled: true, ttl_seconds: 120 },
          },
        },
      };

      render(<NodeInspector {...defaultProps} selectedNode={nodeWithCache} />);

      await user.click(screen.getByRole("button", { name: /advanced/i }));

      expect(screen.getByDisplayValue("120")).toBeInTheDocument();
    });

    it("should allow switching from global TTL to custom TTL", async () => {
      const user = userEvent.setup();
      const nodeWithGlobalCache: Node = {
        ...cacheNode,
        data: {
          ...cacheNode.data,
          config: {
            cache: { enabled: true },
          },
        },
      };

      render(<NodeInspector {...defaultProps} selectedNode={nodeWithGlobalCache} />);

      await user.click(screen.getByRole("button", { name: /advanced/i }));

      const globalToggle = screen.getByRole("switch", { name: /use global ttl/i });
      await user.click(globalToggle);

      expect(mockOnUpdateNode).toHaveBeenCalledWith("cache-node", {
        config: expect.objectContaining({
          cache: expect.objectContaining({ enabled: true, ttl_seconds: 3600 }),
        }),
      });
    });
  });

  describe("Prompt Node Extended Configuration", () => {
    const promptNode: Node = {
      id: "prompt-extended",
      type: NODE_TYPES.PROMPT,
      position: { x: 0, y: 0 },
      data: {
        label: "Extended Prompt",
        nodeType: NODE_TYPES.PROMPT,
        config: {
          prompt_template: "Hello {{name}}",
          system_prompt: "You are a helpful assistant",
          model: "gpt-4",
          temperature: 0.7,
          max_tokens: 1000,
        },
      },
    };

    it("should display system prompt field", () => {
      render(<NodeInspector {...defaultProps} selectedNode={promptNode} />);

      expect(screen.getByText(/System Prompt/i)).toBeInTheDocument();
      expect(screen.getByDisplayValue("You are a helpful assistant")).toBeInTheDocument();
    });

    it("should display model field", () => {
      render(<NodeInspector {...defaultProps} selectedNode={promptNode} />);

      expect(screen.getByText("Model")).toBeInTheDocument();
      expect(screen.getByDisplayValue("gpt-4")).toBeInTheDocument();
    });

    it("should display temperature field", () => {
      render(<NodeInspector {...defaultProps} selectedNode={promptNode} />);

      expect(screen.getByText(/Temperature/i)).toBeInTheDocument();
      expect(screen.getByDisplayValue("0.7")).toBeInTheDocument();
    });

    it("should display max tokens field", () => {
      render(<NodeInspector {...defaultProps} selectedNode={promptNode} />);

      expect(screen.getByText(/Max Tokens/i)).toBeInTheDocument();
      expect(screen.getByDisplayValue("1000")).toBeInTheDocument();
    });

    it("should update model config when changed", () => {
      render(<NodeInspector {...defaultProps} selectedNode={promptNode} />);

      const modelInput = screen.getByDisplayValue("gpt-4");
      fireEvent.change(modelInput, { target: { value: "claude-3" } });

      expect(mockOnUpdateNode).toHaveBeenCalledWith("prompt-extended", {
        config: expect.objectContaining({ model: "claude-3" }),
      });
    });
  });

  describe("HTTP Node URL Validation", () => {
    const httpNode: Node = {
      id: "http-validation",
      type: NODE_TYPES.HTTP,
      position: { x: 0, y: 0 },
      data: {
        label: "HTTP Validation",
        nodeType: NODE_TYPES.HTTP,
        config: { method: "GET", url: "" },
      },
    };

    it("should show URL validation error for invalid URL", async () => {
      render(<NodeInspector {...defaultProps} selectedNode={httpNode} />);

      const urlInput = screen.getByPlaceholderText(/https:\/\/api.example.com/i);
      fireEvent.blur(urlInput, { target: { value: "not-a-valid-url" } });

      await waitFor(() => {
        expect(screen.getByText(/Invalid URL format/i)).toBeInTheDocument();
      });
    });

    it("should not show error for valid URL", async () => {
      render(<NodeInspector {...defaultProps} selectedNode={httpNode} />);

      const urlInput = screen.getByPlaceholderText(/https:\/\/api.example.com/i);
      fireEvent.blur(urlInput, { target: { value: "https://api.example.com/test" } });

      await waitFor(() => {
        expect(screen.queryByText(/Invalid URL format/i)).not.toBeInTheDocument();
      });
    });

    it("should display headers section", () => {
      render(<NodeInspector {...defaultProps} selectedNode={httpNode} />);

      expect(screen.getByText("Headers")).toBeInTheDocument();
    });

    it("should display body textarea", () => {
      render(<NodeInspector {...defaultProps} selectedNode={httpNode} />);

      expect(screen.getByText(/Request Body/i)).toBeInTheDocument();
    });
  });

  describe("Output Node KeyValueEditor", () => {
    const outputNode: Node = {
      id: "output-node",
      type: NODE_TYPES.OUTPUT,
      position: { x: 0, y: 0 },
      data: {
        label: "Output",
        nodeType: NODE_TYPES.OUTPUT,
        config: {
          output_mapping: { result: "node.prompt_1.output" },
        },
      },
    };

    it("should display output mapping section", () => {
      render(<NodeInspector {...defaultProps} selectedNode={outputNode} />);

      expect(screen.getByText("Output Mapping")).toBeInTheDocument();
    });

    it("should display existing mapping entries", () => {
      render(<NodeInspector {...defaultProps} selectedNode={outputNode} />);

      expect(screen.getByDisplayValue("result")).toBeInTheDocument();
      expect(screen.getByDisplayValue("node.prompt_1.output")).toBeInTheDocument();
    });
  });
});
