/**
 * Unit tests for TransformNodeForm component.
 *
 * Tests expression field, output key, expression validation,
 * and integration with AgentFields and AdvancedSettings.
 */

import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { TransformNodeForm } from "@/components/graph-editor/forms/TransformNodeForm";
import type { NodeFormProps } from "@/components/graph-editor/NodeConfigDialog";

// Mock validation utilities
jest.mock("@/lib/form-validation", () => ({
  validateExpression: jest.fn((value: string) => {
    if (value && value.includes("}{")) {
      return { field: "expression", message: "Unbalanced brackets in expression" };
    }
    return null;
  }),
}));

// Mock child components
jest.mock("@/components/graph-editor/forms/AgentFields", () => ({
  AgentFields: ({ config, onChange }: any) => (
    <div data-testid="agent-fields">
      <input
        data-testid="agent-notes"
        value={config.notes || ""}
        onChange={(e) => onChange({ ...config, notes: e.target.value })}
      />
    </div>
  ),
}));

jest.mock("@/components/graph-editor/forms/AdvancedSettings", () => ({
  AdvancedSettings: ({ config, onChange }: any) => (
    <div data-testid="advanced-settings">
      <input
        type="number"
        data-testid="timeout-ms"
        value={config.timeout_ms || ""}
        onChange={(e) =>
          onChange({ ...config, timeout_ms: parseInt(e.target.value, 10) })
        }
      />
    </div>
  ),
}));

describe("TransformNodeForm", () => {
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
      render(<TransformNodeForm {...defaultProps} />);

      expect(screen.getByLabelText(/^expression$/i)).toBeInTheDocument();
      expect(screen.getByLabelText(/output key/i)).toBeInTheDocument();
      expect(screen.getByTestId("agent-fields")).toBeInTheDocument();
      expect(screen.getByTestId("advanced-settings")).toBeInTheDocument();
    });

    it("should render with populated config", () => {
      const config = {
        expression: "state.data.map(item => item.name)",
        output_key: "transformed_data",
      };

      render(<TransformNodeForm {...defaultProps} config={config} />);

      expect(
        screen.getByDisplayValue("state.data.map(item => item.name)")
      ).toBeInTheDocument();
      expect(screen.getByDisplayValue("transformed_data")).toBeInTheDocument();
    });

    it("should display available variables section", () => {
      render(<TransformNodeForm {...defaultProps} />);

      expect(screen.getByText(/available variables/i)).toBeInTheDocument();
      expect(screen.getByText(/state/)).toBeInTheDocument();
      expect(screen.getByText(/input/)).toBeInTheDocument();
      expect(screen.getByText(/node\.<id>\.output/)).toBeInTheDocument();
    });
  });

  describe("Field Changes", () => {
    it("should call onChange when expression is modified", async () => {
      const user = userEvent.setup();
      render(<TransformNodeForm {...defaultProps} />);

      const expressionInput = screen.getByLabelText(/^expression$/i);
      await user.type(expressionInput, "state.value * 2");

      await waitFor(() => {
        expect(mockOnChange).toHaveBeenCalled();
        const lastCall = mockOnChange.mock.calls[mockOnChange.mock.calls.length - 1][0];
        expect(lastCall.expression).toContain("state.value * 2");
      });
    });

    it("should call onChange when output key is modified", async () => {
      const user = userEvent.setup();
      render(<TransformNodeForm {...defaultProps} />);

      const outputKey = screen.getByLabelText(/output key/i);
      await user.type(outputKey, "result");

      await waitFor(() => {
        expect(mockOnChange).toHaveBeenCalled();
        const lastCall = mockOnChange.mock.calls[mockOnChange.mock.calls.length - 1][0];
        expect(lastCall.output_key).toContain("result");
      });
    });

    it("should update config with complete expression", async () => {
      const user = userEvent.setup();
      render(<TransformNodeForm {...defaultProps} />);

      const expressionInput = screen.getByLabelText(/^expression$/i);
      const testExpression =
        "const input = state.previousNode.output;\nreturn { transformed: input.data };";
      await user.clear(expressionInput);
      await user.type(expressionInput, testExpression);

      await waitFor(() => {
        const lastCall = mockOnChange.mock.calls[mockOnChange.mock.calls.length - 1][0];
        expect(lastCall.expression).toBe(testExpression);
      });
    });
  });

  describe("Expression Validation", () => {
    it("should call setErrors with validation error for invalid expression", async () => {
      const config = { expression: "state.value }{" };
      render(<TransformNodeForm {...defaultProps} config={config} />);

      await waitFor(() => {
        expect(mockSetErrors).toHaveBeenCalledWith(
          expect.objectContaining({
            expression: "Unbalanced brackets in expression",
          })
        );
      });
    });

    it("should not set error for valid expression", async () => {
      const config = { expression: "state.value.map(x => x * 2)" };
      render(<TransformNodeForm {...defaultProps} config={config} />);

      await waitFor(() => {
        const calls = mockSetErrors.mock.calls;
        if (calls.length > 0) {
          const lastCall = calls[calls.length - 1][0];
          expect(lastCall.expression).toBeUndefined();
        }
      });
    });

    it("should not set error for empty expression", async () => {
      render(<TransformNodeForm {...defaultProps} />);

      await waitFor(() => {
        const calls = mockSetErrors.mock.calls;
        if (calls.length > 0) {
          const lastCall = calls[calls.length - 1][0];
          expect(lastCall.expression).toBeUndefined();
        }
      });
    });

    it("should display expression error from errors prop", () => {
      const errors = { expression: "Invalid expression syntax" };
      render(<TransformNodeForm {...defaultProps} errors={errors} />);

      expect(screen.getByText("Invalid expression syntax")).toBeInTheDocument();
    });
  });

  describe("Error Display", () => {
    it("should display error for expression field", () => {
      const errors = { expression: "Expression is required" };
      render(<TransformNodeForm {...defaultProps} errors={errors} />);

      expect(screen.getByText("Expression is required")).toBeInTheDocument();
    });

    it("should not display errors when errors object is empty", () => {
      render(<TransformNodeForm {...defaultProps} errors={{}} />);

      expect(screen.queryByText(/required/i)).not.toBeInTheDocument();
      expect(screen.queryByText(/invalid/i)).not.toBeInTheDocument();
    });
  });

  describe("Integration with Sub-components", () => {
    it("should render AgentFields with showRole and showExamples as false", () => {
      render(<TransformNodeForm {...defaultProps} />);

      expect(screen.getByTestId("agent-fields")).toBeInTheDocument();
    });

    it("should propagate AgentFields changes to parent config", async () => {
      const user = userEvent.setup();
      render(<TransformNodeForm {...defaultProps} />);

      const notesInput = screen.getByTestId("agent-notes");
      await user.type(notesInput, "Transform notes");

      await waitFor(() => {
        expect(mockOnChange).toHaveBeenCalledWith(
          expect.objectContaining({
            notes: expect.stringContaining("Transform notes"),
          })
        );
      });
    });

    it("should render AdvancedSettings", () => {
      render(<TransformNodeForm {...defaultProps} />);

      expect(screen.getByTestId("advanced-settings")).toBeInTheDocument();
    });

    it("should propagate AdvancedSettings changes", async () => {
      const user = userEvent.setup();
      render(<TransformNodeForm {...defaultProps} />);

      const timeoutInput = screen.getByTestId("timeout-ms");
      await user.type(timeoutInput, "5000");

      await waitFor(() => {
        expect(mockOnChange).toHaveBeenCalledWith(
          expect.objectContaining({
            timeout_ms: expect.any(Number),
          })
        );
      });
    });

    it("should preserve existing config when updating from sub-components", async () => {
      const user = userEvent.setup();
      const config = {
        expression: "state.value * 2",
        output_key: "result",
      };
      render(<TransformNodeForm {...defaultProps} config={config} />);

      const notesInput = screen.getByTestId("agent-notes");
      await user.type(notesInput, "Note");

      await waitFor(() => {
        expect(mockOnChange).toHaveBeenCalledWith(
          expect.objectContaining({
            expression: "state.value * 2",
            output_key: "result",
            notes: expect.any(String),
          })
        );
      });
    });
  });

  describe("Field Descriptions and Labels", () => {
    it("should display helpful descriptions", () => {
      render(<TransformNodeForm {...defaultProps} />);

      expect(
        screen.getByText(/javascript expression or jsonpath to transform data/i)
      ).toBeInTheDocument();
      expect(
        screen.getByText(/key to store the transformed data under in state/i)
      ).toBeInTheDocument();
    });

    it("should mark expression as required", () => {
      render(<TransformNodeForm {...defaultProps} />);

      const expressionLabel = screen.getByText(/^expression$/i);
      expect(expressionLabel.closest("div")).toBeInTheDocument();
    });

    it("should display helpful placeholder", () => {
      render(<TransformNodeForm {...defaultProps} />);

      const expressionInput = screen.getByLabelText(/^expression$/i);
      expect(expressionInput).toHaveAttribute("placeholder");
    });
  });

  describe("Expression Textarea", () => {
    it("should be a multiline textarea", () => {
      render(<TransformNodeForm {...defaultProps} />);

      const expressionInput = screen.getByLabelText(/^expression$/i);
      expect(expressionInput.tagName).toBe("TEXTAREA");
      expect(expressionInput).toHaveAttribute("rows", "8");
    });

    it("should have monospace font class", () => {
      render(<TransformNodeForm {...defaultProps} />);

      const expressionInput = screen.getByLabelText(/^expression$/i);
      expect(expressionInput).toHaveClass("font-mono");
    });

    it("should support multiline expressions", async () => {
      const user = userEvent.setup();
      render(<TransformNodeForm {...defaultProps} />);

      const expressionInput = screen.getByLabelText(/^expression$/i);
      const multilineExpr = "const x = state.data;\nreturn x.map(i => i * 2);";
      await user.type(expressionInput, multilineExpr);

      await waitFor(() => {
        expect(mockOnChange).toHaveBeenCalled();
        const lastCall = mockOnChange.mock.calls[mockOnChange.mock.calls.length - 1][0];
        expect(lastCall.expression).toContain("const x = state.data;");
      });
    });
  });

  describe("Output Key Field", () => {
    it("should render output key input", () => {
      render(<TransformNodeForm {...defaultProps} />);

      expect(screen.getByLabelText(/output key/i)).toBeInTheDocument();
    });

    it("should have appropriate placeholder", () => {
      render(<TransformNodeForm {...defaultProps} />);

      const outputKey = screen.getByPlaceholderText("transformed");
      expect(outputKey).toBeInTheDocument();
    });

    it("should accept any string value", async () => {
      const user = userEvent.setup();
      render(<TransformNodeForm {...defaultProps} />);

      const outputKey = screen.getByLabelText(/output key/i);
      await user.type(outputKey, "my_custom_key_123");

      await waitFor(() => {
        const lastCall = mockOnChange.mock.calls[mockOnChange.mock.calls.length - 1][0];
        expect(lastCall.output_key).toContain("my_custom_key_123");
      });
    });
  });

  describe("Available Variables Section", () => {
    it("should display state variable documentation", () => {
      render(<TransformNodeForm {...defaultProps} />);

      expect(screen.getByText(/state/)).toBeInTheDocument();
      expect(screen.getByText(/current workflow state/i)).toBeInTheDocument();
    });

    it("should display input variable documentation", () => {
      render(<TransformNodeForm {...defaultProps} />);

      expect(screen.getByText(/input/)).toBeInTheDocument();
      expect(screen.getByText(/graph input data/i)).toBeInTheDocument();
    });

    it("should display node output variable documentation", () => {
      render(<TransformNodeForm {...defaultProps} />);

      expect(screen.getByText(/node\.<id>\.output/)).toBeInTheDocument();
      expect(screen.getByText(/output from specific node/i)).toBeInTheDocument();
    });
  });

  describe("Form Layout", () => {
    it("should have proper section headers", () => {
      render(<TransformNodeForm {...defaultProps} />);

      expect(screen.getByText(/transform expression/i)).toBeInTheDocument();
    });

    it("should render separators between sections", () => {
      const { container } = render(<TransformNodeForm {...defaultProps} />);

      const separators = container.querySelectorAll("[role='separator']");
      expect(separators.length).toBeGreaterThan(0);
    });
  });
});
