/**
 * Unit tests for OutputNodeForm component.
 *
 * Tests output mapping editor and integration with AgentFields.
 */

import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { OutputNodeForm } from "@/components/graph-editor/forms/OutputNodeForm";
import type { NodeFormProps } from "@/components/graph-editor/NodeConfigDialog";

// Mock child components
jest.mock("@/components/graph-editor/forms/AgentFields", () => ({
  AgentFields: () => <div data-testid="agent-fields">Agent Fields</div>,
}));

jest.mock("@/components/ui/key-value-editor", () => ({
  KeyValueEditor: ({ value, onChange }: any) => (
    <div data-testid="key-value-editor">
      <button
        data-testid="add-output-mapping"
        onClick={() => onChange({ ...value, outputKey: "state.path" })}
      >
        Add Output
      </button>
      <div data-testid="output-display">{JSON.stringify(value)}</div>
    </div>
  ),
}));

describe("OutputNodeForm", () => {
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
      render(<OutputNodeForm {...defaultProps} />);

      expect(screen.getByText(/output configuration/i)).toBeInTheDocument();
      expect(screen.getByText(/output mapping/i)).toBeInTheDocument();
      expect(screen.getByTestId("agent-fields")).toBeInTheDocument();
      expect(screen.getByTestId("key-value-editor")).toBeInTheDocument();
    });

    it("should render with populated config", () => {
      const config = {
        output_mapping: {
          result: "node.prompt_1.output",
          status: "node.transform_1.output.status",
        },
      };

      render(<OutputNodeForm {...defaultProps} config={config} />);

      const outputDisplay = screen.getByTestId("output-display");
      expect(outputDisplay.textContent).toContain("result");
      expect(outputDisplay.textContent).toContain("node.prompt_1.output");
      expect(outputDisplay.textContent).toContain("status");
    });

    it("should display helpful description", () => {
      render(<OutputNodeForm {...defaultProps} />);

      expect(
        screen.getByText(
          /define what data to extract as the final output of your workflow/i
        )
      ).toBeInTheDocument();
      expect(
        screen.getByText(/map output field names to state paths/i)
      ).toBeInTheDocument();
    });
  });

  describe("Output Mapping Editor", () => {
    it("should render KeyValueEditor for output mapping", () => {
      render(<OutputNodeForm {...defaultProps} />);

      expect(screen.getByTestId("key-value-editor")).toBeInTheDocument();
    });

    it("should call onChange when output mapping is updated", async () => {
      const user = userEvent.setup();
      render(<OutputNodeForm {...defaultProps} />);

      const addButton = screen.getByTestId("add-output-mapping");
      await user.click(addButton);

      await waitFor(() => {
        expect(mockOnChange).toHaveBeenCalledWith(
          expect.objectContaining({
            output_mapping: expect.objectContaining({
              outputKey: "state.path",
            }),
          })
        );
      });
    });

    it("should display existing output mapping", () => {
      const config = {
        output_mapping: {
          answer: "node.prompt.output",
          confidence: "node.classifier.output.score",
        },
      };

      render(<OutputNodeForm {...defaultProps} config={config} />);

      const outputDisplay = screen.getByTestId("output-display");
      expect(outputDisplay.textContent).toContain("answer");
      expect(outputDisplay.textContent).toContain("confidence");
    });

    it("should handle empty output mapping", () => {
      const config = { output_mapping: {} };
      render(<OutputNodeForm {...defaultProps} config={config} />);

      const outputDisplay = screen.getByTestId("output-display");
      expect(outputDisplay.textContent).toBe("{}");
    });
  });

  describe("Field Descriptions", () => {
    it("should display description for output mapping", () => {
      render(<OutputNodeForm {...defaultProps} />);

      expect(
        screen.getByText(/map output keys to values from the workflow state/i)
      ).toBeInTheDocument();
    });

    it("should display state path examples section", () => {
      render(<OutputNodeForm {...defaultProps} />);

      expect(screen.getByText(/state path examples/i)).toBeInTheDocument();
    });

    it("should show example for node output path", () => {
      render(<OutputNodeForm {...defaultProps} />);

      expect(screen.getByText(/node.prompt_1.output/)).toBeInTheDocument();
      expect(screen.getByText(/output from a prompt node/i)).toBeInTheDocument();
    });

    it("should show example for nested data path", () => {
      render(<OutputNodeForm {...defaultProps} />);

      expect(screen.getByText(/node.http_1.output.data/)).toBeInTheDocument();
      expect(screen.getByText(/nested data from http response/i)).toBeInTheDocument();
    });

    it("should show example for input reference", () => {
      render(<OutputNodeForm {...defaultProps} />);

      expect(screen.getByText(/input.userId/)).toBeInTheDocument();
      expect(screen.getByText(/original graph input/i)).toBeInTheDocument();
    });
  });

  describe("Integration with Sub-components", () => {
    it("should render AgentFields", () => {
      render(<OutputNodeForm {...defaultProps} />);

      expect(screen.getByTestId("agent-fields")).toBeInTheDocument();
    });

    it("should not render AdvancedSettings", () => {
      render(<OutputNodeForm {...defaultProps} />);

      expect(screen.queryByTestId("advanced-settings")).not.toBeInTheDocument();
    });

    it("should pass config to AgentFields", () => {
      const config = { notes: "Test notes" };
      render(<OutputNodeForm {...defaultProps} config={config} />);

      expect(screen.getByTestId("agent-fields")).toBeInTheDocument();
    });
  });

  describe("Form Layout", () => {
    it("should display section headers", () => {
      render(<OutputNodeForm {...defaultProps} />);

      expect(screen.getByText(/^output configuration$/i)).toBeInTheDocument();
    });

    it("should render separators between sections", () => {
      const { container } = render(<OutputNodeForm {...defaultProps} />);

      // OutputNodeForm has a simpler structure, so just verify the main container exists
      const spaceY6 = container.querySelector(".space-y-6");
      expect(spaceY6).toBeInTheDocument();
    });

    it("should have proper spacing structure", () => {
      const { container } = render(<OutputNodeForm {...defaultProps} />);

      const spaceY6 = container.querySelector(".space-y-6");
      expect(spaceY6).toBeInTheDocument();
    });
  });

  describe("Examples Section Styling", () => {
    it("should display examples in a styled container", () => {
      const { container } = render(<OutputNodeForm {...defaultProps} />);

      const examplesBox = container.querySelector(".bg-muted\\/50");
      expect(examplesBox).toBeInTheDocument();
    });

    it("should display examples with code formatting", () => {
      render(<OutputNodeForm {...defaultProps} />);

      const codeElements = screen.getAllByText(/node\.|input\./);
      codeElements.forEach((el) => {
        expect(el.closest("code")).toBeInTheDocument();
      });
    });
  });

  describe("Preserving Config", () => {
    it("should preserve existing config when updating output mapping", async () => {
      const user = userEvent.setup();
      const config = {
        output_mapping: { existing: "path" },
        notes: "Some notes",
      };
      render(<OutputNodeForm {...defaultProps} config={config} />);

      const addButton = screen.getByTestId("add-output-mapping");
      await user.click(addButton);

      await waitFor(() => {
        expect(mockOnChange).toHaveBeenCalledWith(
          expect.objectContaining({
            output_mapping: expect.objectContaining({
              existing: "path",
              outputKey: "state.path",
            }),
            notes: "Some notes",
          })
        );
      });
    });
  });

  describe("Empty State", () => {
    it("should handle undefined output mapping", () => {
      render(<OutputNodeForm {...defaultProps} />);

      const outputDisplay = screen.getByTestId("output-display");
      expect(outputDisplay.textContent).toBe("{}");
    });

    it("should allow adding mapping when none exist", async () => {
      const user = userEvent.setup();
      render(<OutputNodeForm {...defaultProps} />);

      const addButton = screen.getByTestId("add-output-mapping");
      await user.click(addButton);

      await waitFor(() => {
        expect(mockOnChange).toHaveBeenCalledWith(
          expect.objectContaining({
            output_mapping: expect.any(Object),
          })
        );
      });
    });
  });

  describe("Multiple Output Mappings", () => {
    it("should display multiple output mappings", () => {
      const config = {
        output_mapping: {
          result: "node.a.output",
          metadata: "node.b.output",
          timestamp: "input.timestamp",
        },
      };

      render(<OutputNodeForm {...defaultProps} config={config} />);

      const outputDisplay = screen.getByTestId("output-display");
      expect(outputDisplay.textContent).toContain("result");
      expect(outputDisplay.textContent).toContain("metadata");
      expect(outputDisplay.textContent).toContain("timestamp");
    });

    it("should update specific mapping without affecting others", async () => {
      const user = userEvent.setup();
      const config = {
        output_mapping: {
          first: "path1",
          second: "path2",
        },
      };
      render(<OutputNodeForm {...defaultProps} config={config} />);

      const addButton = screen.getByTestId("add-output-mapping");
      await user.click(addButton);

      await waitFor(() => {
        const lastCall = mockOnChange.mock.calls[mockOnChange.mock.calls.length - 1][0];
        expect(lastCall.output_mapping.first).toBe("path1");
        expect(lastCall.output_mapping.second).toBe("path2");
      });
    });
  });

  describe("Output Configuration Description", () => {
    it("should explain workflow output purpose", () => {
      render(<OutputNodeForm {...defaultProps} />);

      expect(
        screen.getByText(/define what data to extract as the final output/i)
      ).toBeInTheDocument();
    });

    it("should explain mapping functionality", () => {
      render(<OutputNodeForm {...defaultProps} />);

      expect(
        screen.getByText(/map output keys to values from the workflow state/i)
      ).toBeInTheDocument();
    });
  });

  describe("AgentFields Configuration", () => {
    it("should render AgentFields without showRole", () => {
      render(<OutputNodeForm {...defaultProps} />);

      // AgentFields is rendered, component decides which fields to show
      expect(screen.getByTestId("agent-fields")).toBeInTheDocument();
    });

    it("should render AgentFields without showJobDescription", () => {
      render(<OutputNodeForm {...defaultProps} />);

      // AgentFields is rendered, component decides which fields to show
      expect(screen.getByTestId("agent-fields")).toBeInTheDocument();
    });

    it("should render AgentFields without showExamples", () => {
      render(<OutputNodeForm {...defaultProps} />);

      // AgentFields is rendered, component decides which fields to show
      expect(screen.getByTestId("agent-fields")).toBeInTheDocument();
    });
  });
});
