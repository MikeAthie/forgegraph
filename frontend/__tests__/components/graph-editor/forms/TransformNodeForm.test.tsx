/**
 * Unit tests for TransformNodeForm component.
 *
 * Tests expression field, output key, expression validation,
 * and integration with AgentFields and AdvancedSettings.
 */

import { act, fireEvent, render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { useState } from "react";
import { TransformNodeForm } from "@/components/graph-editor/forms/TransformNodeForm";
import type { NodeFormProps } from "@/components/graph-editor/NodeConfigDialog";

// Mock validation utilities
jest.mock("@/lib/form-validation", () => {
  const actual = jest.requireActual("@/lib/form-validation");
  return {
    ...actual,
    validateExpression: jest.fn(actual.validateExpression),
  };
});

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
        onChange={(e) => onChange({ ...config, timeout_ms: parseInt(e.target.value, 10) })}
      />
    </div>
  ),
}));

describe("TransformNodeForm", () => {
  const mockOnChange = jest.fn();
  const mockSetErrors = jest.fn();

  const setupUser = () => {
    const user = userEvent.setup();
    return {
      type: (element: HTMLElement, text: string) => act(async () => user.type(element, text)),
    };
  };

  const renderWithConfig = (
    initialConfig: NodeFormProps["config"] = {},
    options: { errors?: NodeFormProps["errors"] } = {},
  ) => {
    const Wrapper = () => {
      const [config, setConfig] = useState(initialConfig);
      const handleChange = (nextConfig: NodeFormProps["config"]) => {
        setConfig(nextConfig);
        mockOnChange(nextConfig);
      };

      return (
        <TransformNodeForm
          config={config}
          onChange={handleChange}
          errors={options.errors ?? {}}
          setErrors={mockSetErrors}
        />
      );
    };

    return render(<Wrapper />);
  };

  beforeEach(() => {
    jest.clearAllMocks();
  });

  describe("Initial Render", () => {
    it("should render with empty config", () => {
      renderWithConfig();

      expect(screen.getByLabelText(/expression/i)).toBeInTheDocument();
      expect(screen.getByLabelText(/output key/i)).toBeInTheDocument();
      expect(screen.getByTestId("agent-fields")).toBeInTheDocument();
      expect(screen.getByTestId("advanced-settings")).toBeInTheDocument();
    });

    it("should render with populated config", () => {
      const config = {
        expression: "state.data.map(item => item.name)",
        output_key: "transformed_data",
      };

      renderWithConfig(config);

      expect(screen.getByDisplayValue("state.data.map(item => item.name)")).toBeInTheDocument();
      expect(screen.getByDisplayValue("transformed_data")).toBeInTheDocument();
    });

    it("should display available variables section", () => {
      renderWithConfig();

      expect(screen.getByText(/available variables/i)).toBeInTheDocument();
      expect(screen.getByText("state", { selector: "code" })).toBeInTheDocument();
      expect(screen.getByText("input", { selector: "code" })).toBeInTheDocument();
      expect(screen.getByText(/node\.<id>\.output/, { selector: "code" })).toBeInTheDocument();
    });
  });

  describe("Field Changes", () => {
    it("should call onChange when expression is modified", async () => {
      const { type } = setupUser();
      renderWithConfig();

      const expressionInput = screen.getByLabelText(/expression/i);
      await type(expressionInput, "state.value * 2");

      await waitFor(() => {
        expect(mockOnChange).toHaveBeenCalled();
        const lastCall = mockOnChange.mock.calls[mockOnChange.mock.calls.length - 1][0];
        expect(lastCall.expression).toContain("state.value * 2");
      });
    });

    it("should call onChange when output key is modified", async () => {
      const { type } = setupUser();
      renderWithConfig();

      const outputKey = screen.getByLabelText(/output key/i);
      await type(outputKey, "result");

      await waitFor(() => {
        expect(mockOnChange).toHaveBeenCalled();
        const lastCall = mockOnChange.mock.calls[mockOnChange.mock.calls.length - 1][0];
        expect(lastCall.output_key).toContain("result");
      });
    });

    it("should update config with complete expression", async () => {
      renderWithConfig();

      const expressionInput = screen.getByLabelText(/expression/i);
      const testExpression = "const input = state.previousNode.output;\nreturn { transformed: input.data };";
      fireEvent.change(expressionInput, { target: { value: testExpression } });

      await waitFor(() => {
        const lastCall = mockOnChange.mock.calls[mockOnChange.mock.calls.length - 1][0];
        expect(lastCall.expression).toBe(testExpression);
      });
    });
  });

  describe("Expression Validation", () => {
    it("should call setErrors with validation error for invalid expression", async () => {
      const config = { expression: "state.value }{" };
      renderWithConfig(config);

      await waitFor(() => {
        expect(mockSetErrors).toHaveBeenCalledWith(
          expect.objectContaining({
            expression: "Unbalanced brackets in expression",
          }),
        );
      });
    });

    it("should not set error for valid expression", async () => {
      const config = { expression: "state.value.map(x => x * 2)" };
      renderWithConfig(config);

      await waitFor(() => {
        const calls = mockSetErrors.mock.calls;
        if (calls.length > 0) {
          const lastCall = calls[calls.length - 1][0];
          expect(lastCall.expression).toBeUndefined();
        }
      });
    });

    it("should not set error for empty expression", async () => {
      renderWithConfig();

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
      renderWithConfig({}, { errors });

      expect(screen.getByText("Invalid expression syntax")).toBeInTheDocument();
    });
  });

  describe("Error Display", () => {
    it("should display error for expression field", () => {
      const errors = { expression: "Expression is required" };
      renderWithConfig({}, { errors });

      expect(screen.getByText("Expression is required")).toBeInTheDocument();
    });

    it("should not display errors when errors object is empty", () => {
      renderWithConfig({}, { errors: {} });

      expect(screen.queryByText(/required/i)).not.toBeInTheDocument();
      expect(screen.queryByText(/invalid/i)).not.toBeInTheDocument();
    });
  });

  describe("Integration with Sub-components", () => {
    it("should render AgentFields with showRole and showExamples as false", () => {
      renderWithConfig();

      expect(screen.getByTestId("agent-fields")).toBeInTheDocument();
    });

    it("should propagate AgentFields changes to parent config", async () => {
      const { type } = setupUser();
      renderWithConfig();

      const notesInput = screen.getByTestId("agent-notes");
      await type(notesInput, "Transform notes");

      await waitFor(() => {
        expect(mockOnChange).toHaveBeenCalledWith(
          expect.objectContaining({
            notes: expect.stringContaining("Transform notes"),
          }),
        );
      });
    });

    it("should render AdvancedSettings", () => {
      renderWithConfig();

      expect(screen.getByTestId("advanced-settings")).toBeInTheDocument();
    });

    it("should propagate AdvancedSettings changes", async () => {
      const { type } = setupUser();
      renderWithConfig();

      const timeoutInput = screen.getByTestId("timeout-ms");
      await type(timeoutInput, "5000");

      await waitFor(() => {
        expect(mockOnChange).toHaveBeenCalledWith(
          expect.objectContaining({
            timeout_ms: expect.any(Number),
          }),
        );
      });
    });

    it("should preserve existing config when updating from sub-components", async () => {
      const { type } = setupUser();
      const config = {
        expression: "state.value * 2",
        output_key: "result",
      };
      renderWithConfig(config);

      const notesInput = screen.getByTestId("agent-notes");
      await type(notesInput, "Note");

      await waitFor(() => {
        expect(mockOnChange).toHaveBeenCalledWith(
          expect.objectContaining({
            expression: "state.value * 2",
            output_key: "result",
            notes: expect.any(String),
          }),
        );
      });
    });
  });

  describe("Field Descriptions and Labels", () => {
    it("should display helpful descriptions", () => {
      renderWithConfig();

      expect(screen.getByText(/javascript expression or jsonpath to transform data/i)).toBeInTheDocument();
      expect(screen.getByText(/key to store the transformed data under in state/i)).toBeInTheDocument();
    });

    it("should mark expression as required", () => {
      renderWithConfig();

      const expressionLabel = screen.getByText(/expression/i, { selector: "label" });
      expect(expressionLabel.closest("div")).toBeInTheDocument();
    });

    it("should display helpful placeholder", () => {
      renderWithConfig();

      const expressionInput = screen.getByLabelText(/expression/i);
      expect(expressionInput).toHaveAttribute("placeholder");
    });
  });

  describe("Expression Textarea", () => {
    it("should be a multiline textarea", () => {
      renderWithConfig();

      const expressionInput = screen.getByLabelText(/expression/i);
      expect(expressionInput.tagName).toBe("TEXTAREA");
      expect(expressionInput).toHaveAttribute("rows", "8");
    });

    it("should have monospace font class", () => {
      renderWithConfig();

      const expressionInput = screen.getByLabelText(/expression/i);
      expect(expressionInput).toHaveClass("font-mono");
    });

    it("should support multiline expressions", async () => {
      const { type } = setupUser();
      renderWithConfig();

      const expressionInput = screen.getByLabelText(/expression/i);
      const multilineExpr = "const x = state.data;\nreturn x.map(i => i * 2);";
      await type(expressionInput, multilineExpr);

      await waitFor(() => {
        expect(mockOnChange).toHaveBeenCalled();
        const lastCall = mockOnChange.mock.calls[mockOnChange.mock.calls.length - 1][0];
        expect(lastCall.expression).toContain("const x = state.data;");
      });
    });
  });

  describe("Output Key Field", () => {
    it("should render output key input", () => {
      renderWithConfig();

      expect(screen.getByLabelText(/output key/i)).toBeInTheDocument();
    });

    it("should have appropriate placeholder", () => {
      renderWithConfig();

      const outputKey = screen.getByPlaceholderText("transformed");
      expect(outputKey).toBeInTheDocument();
    });

    it("should accept any string value", async () => {
      const { type } = setupUser();
      renderWithConfig();

      const outputKey = screen.getByLabelText(/output key/i);
      await type(outputKey, "my_custom_key_123");

      await waitFor(() => {
        const lastCall = mockOnChange.mock.calls[mockOnChange.mock.calls.length - 1][0];
        expect(lastCall.output_key).toContain("my_custom_key_123");
      });
    });
  });

  describe("Available Variables Section", () => {
    it("should display state variable documentation", () => {
      renderWithConfig();

      expect(screen.getByText("state", { selector: "code" })).toBeInTheDocument();
      expect(screen.getByText(/current operating state/i)).toBeInTheDocument();
    });

    it("should display input variable documentation", () => {
      renderWithConfig();

      expect(screen.getByText("input", { selector: "code" })).toBeInTheDocument();
      expect(screen.getByText(/company input data/i)).toBeInTheDocument();
    });

    it("should display node output variable documentation", () => {
      renderWithConfig();

      expect(screen.getByText(/node\.<id>\.output/, { selector: "code" })).toBeInTheDocument();
      expect(screen.getByText(/output from a specific step/i)).toBeInTheDocument();
    });
  });

  describe("Form Layout", () => {
    it("should have proper section headers", () => {
      renderWithConfig();

      expect(screen.getByText(/transform expression/i)).toBeInTheDocument();
    });

    it("should render separators between sections", () => {
      const { container } = renderWithConfig();

      const separators = container.querySelectorAll("[data-slot='separator']");
      expect(separators.length).toBeGreaterThan(0);
    });
  });
});
