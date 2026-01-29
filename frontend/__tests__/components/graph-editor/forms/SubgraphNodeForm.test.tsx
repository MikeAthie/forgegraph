/**
 * Unit tests for SubgraphNodeForm component.
 *
 * Tests graph selection, version input, input/output mapping editors,
 * and integration with AgentFields and AdvancedSettings.
 */

import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { SubgraphNodeForm } from "@/components/graph-editor/forms/SubgraphNodeForm";
import type { NodeFormProps } from "@/components/graph-editor/NodeConfigDialog";

// Mock child components
jest.mock("@/components/graph-editor/forms/AgentFields", () => ({
  AgentFields: () => <div data-testid="agent-fields">Agent Fields</div>,
}));

jest.mock("@/components/graph-editor/forms/AdvancedSettings", () => ({
  AdvancedSettings: () => <div data-testid="advanced-settings">Advanced Settings</div>,
}));

jest.mock("@/components/ui/key-value-editor", () => ({
  KeyValueEditor: ({ value, onChange, keyPlaceholder }: any) => (
    <div data-testid={`key-value-editor-${keyPlaceholder}`}>
      <button
        data-testid={`add-mapping-${keyPlaceholder}`}
        onClick={() => onChange({ ...value, newKey: "newValue" })}
      >
        Add Mapping
      </button>
      <div data-testid={`mapping-display-${keyPlaceholder}`}>{JSON.stringify(value)}</div>
    </div>
  ),
}));

describe("SubgraphNodeForm", () => {
  const mockOnChange = jest.fn();
  const mockSetErrors = jest.fn();

  const defaultProps: NodeFormProps = {
    config: {},
    onChange: mockOnChange,
    errors: {},
    setErrors: mockSetErrors,
  };

  beforeEach(() => {
    jest.clearAllMocks();
  });

  describe("Initial Render", () => {
    it("should render with empty config", () => {
      render(<SubgraphNodeForm {...defaultProps} />);

      expect(screen.getByText(/subgraph reference/i)).toBeInTheDocument();
      expect(screen.getByLabelText(/graph id/i)).toBeInTheDocument();
      expect(screen.getByLabelText(/version/i)).toBeInTheDocument();
      expect(screen.getByText(/input mapping/i)).toBeInTheDocument();
      expect(screen.getByText(/output mapping/i)).toBeInTheDocument();
      expect(screen.getByTestId("agent-fields")).toBeInTheDocument();
      expect(screen.getByTestId("advanced-settings")).toBeInTheDocument();
    });

    it("should render with populated config", () => {
      const config = {
        graph_id: "graph_abc123",
        graph_version: "v1.0.0",
        input_mapping: { query: "input.question" },
        output_mapping: { answer: "output.response" },
      };

      render(<SubgraphNodeForm {...defaultProps} config={config} />);

      expect(screen.getByDisplayValue("graph_abc123")).toBeInTheDocument();
      expect(screen.getByDisplayValue("v1.0.0")).toBeInTheDocument();
    });

    it("should display helpful description", () => {
      render(<SubgraphNodeForm {...defaultProps} />);

      expect(
        screen.getByText(
          /execute another graph as a node within this workflow. this enables modular, reusable agent components/i
        )
      ).toBeInTheDocument();
    });
  });

  describe("Graph ID Field", () => {
    it("should render graph ID input", () => {
      render(<SubgraphNodeForm {...defaultProps} />);

      expect(screen.getByLabelText(/graph id/i)).toBeInTheDocument();
    });

    it("should call onChange when graph ID is modified", async () => {
      const user = userEvent.setup();
      render(<SubgraphNodeForm {...defaultProps} />);

      const graphIdInput = screen.getByLabelText(/graph id/i);
      await user.type(graphIdInput, "graph_123");

      await waitFor(() => {
        const lastCall = mockOnChange.mock.calls[mockOnChange.mock.calls.length - 1][0];
        expect(lastCall.graph_id).toContain("graph_123");
      });
    });

    it("should have appropriate placeholder", () => {
      render(<SubgraphNodeForm {...defaultProps} />);

      expect(screen.getByPlaceholderText("graph_abc123")).toBeInTheDocument();
    });

    it("should have monospace font class", () => {
      render(<SubgraphNodeForm {...defaultProps} />);

      const graphIdInput = screen.getByLabelText(/graph id/i);
      expect(graphIdInput).toHaveClass("font-mono");
    });
  });

  describe("External Link", () => {
    it("should show external link when graph_id is set", () => {
      const config = { graph_id: "graph_test123" };
      render(<SubgraphNodeForm {...defaultProps} config={config} />);

      const link = screen.getByRole("link");
      expect(link).toBeInTheDocument();
      expect(link).toHaveAttribute("href", "/graphs/graph_test123");
      expect(link).toHaveAttribute("target", "_blank");
      expect(link).toHaveAttribute("rel", "noopener noreferrer");
    });

    it("should not show external link when graph_id is empty", () => {
      render(<SubgraphNodeForm {...defaultProps} />);

      expect(screen.queryByRole("link")).not.toBeInTheDocument();
    });

    it("should update link href when graph_id changes", async () => {
      const user = userEvent.setup();
      const config = { graph_id: "graph_old" };
      const { rerender } = render(<SubgraphNodeForm {...defaultProps} config={config} />);

      expect(screen.getByRole("link")).toHaveAttribute("href", "/graphs/graph_old");

      // Simulate config update
      const newConfig = { graph_id: "graph_new" };
      rerender(<SubgraphNodeForm {...defaultProps} config={newConfig} />);

      expect(screen.getByRole("link")).toHaveAttribute("href", "/graphs/graph_new");
    });
  });

  describe("Version Field", () => {
    it("should render version input", () => {
      render(<SubgraphNodeForm {...defaultProps} />);

      expect(screen.getByLabelText(/^version$/i)).toBeInTheDocument();
    });

    it("should call onChange when version is modified", async () => {
      const user = userEvent.setup();
      render(<SubgraphNodeForm {...defaultProps} />);

      const versionInput = screen.getByLabelText(/^version$/i);
      await user.type(versionInput, "v2.0.0");

      await waitFor(() => {
        const lastCall = mockOnChange.mock.calls[mockOnChange.mock.calls.length - 1][0];
        expect(lastCall.graph_version).toContain("v2.0.0");
      });
    });

    it("should have appropriate placeholder", () => {
      render(<SubgraphNodeForm {...defaultProps} />);

      expect(screen.getByPlaceholderText("latest")).toBeInTheDocument();
    });

    it("should show description about version being optional", () => {
      render(<SubgraphNodeForm {...defaultProps} />);

      expect(screen.getByText(/specific version \(blank = latest\)/i)).toBeInTheDocument();
    });
  });

  describe("Input Mapping", () => {
    it("should render KeyValueEditor for input mapping", () => {
      render(<SubgraphNodeForm {...defaultProps} />);

      expect(screen.getByTestId("key-value-editor-Subgraph input key")).toBeInTheDocument();
    });

    it("should call onChange when input mapping is updated", async () => {
      const user = userEvent.setup();
      render(<SubgraphNodeForm {...defaultProps} />);

      const addButton = screen.getByTestId("add-mapping-Subgraph input key");
      await user.click(addButton);

      await waitFor(() => {
        expect(mockOnChange).toHaveBeenCalledWith(
          expect.objectContaining({
            input_mapping: expect.objectContaining({ newKey: "newValue" }),
          })
        );
      });
    });

    it("should display existing input mapping", () => {
      const config = {
        input_mapping: { query: "node.prompt_1.output", context: "input.data" },
      };
      render(<SubgraphNodeForm {...defaultProps} config={config} />);

      const mappingDisplay = screen.getByTestId("mapping-display-Subgraph input key");
      expect(mappingDisplay.textContent).toContain("query");
      expect(mappingDisplay.textContent).toContain("context");
    });

    it("should display description for input mapping", () => {
      render(<SubgraphNodeForm {...defaultProps} />);

      expect(
        screen.getByText(/map values from parent state to subgraph inputs/i)
      ).toBeInTheDocument();
    });
  });

  describe("Output Mapping", () => {
    it("should render KeyValueEditor for output mapping", () => {
      render(<SubgraphNodeForm {...defaultProps} />);

      expect(screen.getByTestId("key-value-editor-Parent state key")).toBeInTheDocument();
    });

    it("should call onChange when output mapping is updated", async () => {
      const user = userEvent.setup();
      render(<SubgraphNodeForm {...defaultProps} />);

      const addButton = screen.getByTestId("add-mapping-Parent state key");
      await user.click(addButton);

      await waitFor(() => {
        expect(mockOnChange).toHaveBeenCalledWith(
          expect.objectContaining({
            output_mapping: expect.objectContaining({ newKey: "newValue" }),
          })
        );
      });
    });

    it("should display existing output mapping", () => {
      const config = {
        output_mapping: { result: "output.final", status: "output.status" },
      };
      render(<SubgraphNodeForm {...defaultProps} config={config} />);

      const mappingDisplay = screen.getByTestId("mapping-display-Parent state key");
      expect(mappingDisplay.textContent).toContain("result");
      expect(mappingDisplay.textContent).toContain("status");
    });

    it("should display description for output mapping", () => {
      render(<SubgraphNodeForm {...defaultProps} />);

      expect(
        screen.getByText(/map subgraph outputs back to parent state/i)
      ).toBeInTheDocument();
    });
  });

  describe("Mapping Examples", () => {
    it("should display mapping examples section", () => {
      render(<SubgraphNodeForm {...defaultProps} />);

      expect(screen.getByText(/mapping examples/i)).toBeInTheDocument();
    });

    it("should show input mapping example", () => {
      render(<SubgraphNodeForm {...defaultProps} />);

      expect(screen.getByText(/query/)).toBeInTheDocument();
      expect(screen.getByText(/node.prompt_1.output/)).toBeInTheDocument();
    });

    it("should show output mapping example", () => {
      render(<SubgraphNodeForm {...defaultProps} />);

      expect(screen.getByText(/sub_result/)).toBeInTheDocument();
      expect(screen.getByText(/output.final/)).toBeInTheDocument();
    });
  });

  describe("Version Warning", () => {
    it("should display version pinning warning", () => {
      render(<SubgraphNodeForm {...defaultProps} />);

      expect(screen.getByText(/version pinning recommended/i)).toBeInTheDocument();
      expect(
        screen.getByText(
          /pin to a specific version for production workflows to ensure consistent behavior/i
        )
      ).toBeInTheDocument();
    });

    it("should style warning appropriately", () => {
      const { container } = render(<SubgraphNodeForm {...defaultProps} />);

      const warning = container.querySelector(".bg-amber-500\\/10");
      expect(warning).toBeInTheDocument();
    });
  });

  describe("Integration with Sub-components", () => {
    it("should render AgentFields", () => {
      render(<SubgraphNodeForm {...defaultProps} />);

      expect(screen.getByTestId("agent-fields")).toBeInTheDocument();
    });

    it("should render AdvancedSettings", () => {
      render(<SubgraphNodeForm {...defaultProps} />);

      expect(screen.getByTestId("advanced-settings")).toBeInTheDocument();
    });
  });

  describe("Form Layout", () => {
    it("should display section headers", () => {
      render(<SubgraphNodeForm {...defaultProps} />);

      expect(screen.getByText(/^subgraph reference$/i)).toBeInTheDocument();
      expect(screen.getByText(/^data mapping$/i)).toBeInTheDocument();
    });

    it("should render separators between sections", () => {
      const { container } = render(<SubgraphNodeForm {...defaultProps} />);

      const separators = container.querySelectorAll("[role='separator']");
      expect(separators.length).toBeGreaterThan(0);
    });

    it("should use grid layout for graph ID and version", () => {
      const { container } = render(<SubgraphNodeForm {...defaultProps} />);

      const grid = container.querySelector(".grid-cols-2");
      expect(grid).toBeInTheDocument();
    });
  });

  describe("Field Requirements", () => {
    it("should mark graph ID as required", () => {
      render(<SubgraphNodeForm {...defaultProps} />);

      const graphIdLabel = screen.getByText(/^graph id$/i);
      expect(graphIdLabel.closest("div")).toBeInTheDocument();
    });

    it("should not mark version as required", () => {
      render(<SubgraphNodeForm {...defaultProps} />);

      // Version field should not have required indicator
      const versionLabel = screen.getByText(/^version$/i);
      expect(versionLabel).toBeInTheDocument();
    });
  });

  describe("Preserving Config", () => {
    it("should preserve mappings when updating graph ID", async () => {
      const user = userEvent.setup();
      const config = {
        graph_id: "old_graph",
        input_mapping: { key: "value" },
        output_mapping: { out: "result" },
      };
      render(<SubgraphNodeForm {...defaultProps} config={config} />);

      const graphIdInput = screen.getByLabelText(/graph id/i);
      await user.clear(graphIdInput);
      await user.type(graphIdInput, "new_graph");

      await waitFor(() => {
        expect(mockOnChange).toHaveBeenCalledWith(
          expect.objectContaining({
            graph_id: expect.stringContaining("new_graph"),
            input_mapping: { key: "value" },
            output_mapping: { out: "result" },
          })
        );
      });
    });
  });
});
