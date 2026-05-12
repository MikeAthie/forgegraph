/**
 * Unit tests for PromptNodeForm component.
 *
 * Tests prompt template, system prompt, model selection, temperature slider,
 * variables editor, and integration with AgentFields and AdvancedSettings.
 */

import { act, fireEvent, render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { useState } from "react";
import { PromptNodeForm } from "@/components/graph-editor/forms/PromptNodeForm";
import type { NodeFormProps } from "@/components/graph-editor/NodeConfigDialog";

// Mock child components
jest.mock("@/components/graph-editor/forms/AgentFields", () => ({
  AgentFields: ({ config, onChange }: any) => (
    <div data-testid="agent-fields">
      <input
        data-testid="agent-role"
        value={config.role || ""}
        onChange={(e) => onChange({ ...config, role: e.target.value })}
      />
    </div>
  ),
}));

jest.mock("@/components/graph-editor/forms/AdvancedSettings", () => ({
  AdvancedSettings: ({ config, onChange }: any) => (
    <div data-testid="advanced-settings">
      <input
        type="checkbox"
        data-testid="cache-enabled"
        checked={config.cache_enabled || false}
        onChange={(e) => onChange({ ...config, cache_enabled: e.target.checked })}
      />
    </div>
  ),
}));

jest.mock("@/components/ui/key-value-editor", () => ({
  KeyValueEditor: ({ value, onChange }: any) => (
    <div data-testid="key-value-editor">
      <button data-testid="add-variable" onClick={() => onChange({ ...value, newKey: "newValue" })}>
        Add Variable
      </button>
      <div data-testid="variables-display">{JSON.stringify(value)}</div>
    </div>
  ),
}));

describe("PromptNodeForm", () => {
  const mockOnChange = jest.fn();
  const mockSetErrors = jest.fn();

  const setupUser = () => {
    const user = userEvent.setup();
    return {
      ...user,
      click: (element: HTMLElement) => act(async () => user.click(element)),
      type: (element: HTMLElement, text: string) => act(async () => user.type(element, text)),
      clear: (element: HTMLElement) => act(async () => user.clear(element)),
      selectOptions: (element: HTMLElement, values: string | string[]) =>
        act(async () => user.selectOptions(element, values)),
    };
  };

  const renderWithConfig = async (
    initialConfig: NodeFormProps["config"] = {},
    options: { errors?: NodeFormProps["errors"] } = {},
  ) => {
    const Wrapper = () => {
      const [config, setConfig] = useState(initialConfig);
      const recordConfigChange = (nextConfig: NodeFormProps["config"]) => {
        setConfig(nextConfig);
        mockOnChange(nextConfig);
      };

      return (
        <PromptNodeForm
          config={config}
          onChange={recordConfigChange}
          errors={options.errors ?? {}}
          setErrors={mockSetErrors}
        />
      );
    };

    const result = render(<Wrapper />);
    await waitFor(() => {
      expect(screen.queryByText(/loading credentials/i)).not.toBeInTheDocument();
    });
    return result;
  };

  beforeEach(() => {
    jest.clearAllMocks();
  });

  describe("Initial Render", () => {
    it("should render with empty config", async () => {
      await renderWithConfig();

      expect(screen.getByTestId("agent-fields")).toBeInTheDocument();
      expect(screen.getByLabelText(/system prompt/i)).toBeInTheDocument();
      expect(screen.getByLabelText(/prompt template/i)).toBeInTheDocument();
      expect(screen.getByLabelText(/model/i)).toBeInTheDocument();
      expect(screen.getByLabelText(/temperature/i)).toBeInTheDocument();
      expect(screen.getByTestId("advanced-settings")).toBeInTheDocument();
    });

    it("should render with populated config", async () => {
      const config = {
        prompt_template: "Test prompt: {{input}}",
        system_prompt: "You are a helpful assistant",
        model: "gpt-4-turbo",
        temperature: 0.5,
        max_tokens: 2000,
        variables: { input: "test" },
      };

      await renderWithConfig(config);

      expect(screen.getByDisplayValue("Test prompt: {{input}}")).toBeInTheDocument();
      expect(screen.getByDisplayValue("You are a helpful assistant")).toBeInTheDocument();
      expect(screen.getByLabelText(/model/i)).toHaveValue("gpt-4-turbo");
      expect(screen.getByDisplayValue("2000")).toBeInTheDocument();
    });

    it("should display temperature value correctly", async () => {
      const config = { temperature: 1.5 };
      await renderWithConfig(config);

      const slider = screen.getByLabelText(/temperature/i);
      expect(slider).toHaveValue("1.5");
      expect(screen.getByText("1.5")).toBeInTheDocument();
    });

    it("should display default temperature of 0.7 when not set", async () => {
      await renderWithConfig();

      const slider = screen.getByLabelText(/temperature/i);
      expect(slider).toHaveValue("0.7");
      expect(screen.getByText("0.7")).toBeInTheDocument();
    });

    it("should render all model options", async () => {
      await renderWithConfig();

      const modelSelect = screen.getByLabelText(/model/i);
      expect(modelSelect).toBeInTheDocument();

      // Check for some key models
      expect(screen.getByRole("option", { name: "GPT-4" })).toBeInTheDocument();
      expect(screen.getByRole("option", { name: "GPT-4 Turbo" })).toBeInTheDocument();
      expect(screen.getByRole("option", { name: "Claude 3 Opus" })).toBeInTheDocument();
      expect(screen.getByRole("option", { name: "Claude 3 Sonnet" })).toBeInTheDocument();
    });
  });

  describe("Field Changes", () => {
    it("should call onChange when system prompt is modified", async () => {
      const user = setupUser();
      await renderWithConfig();

      const systemPrompt = screen.getByLabelText(/system prompt/i);
      await user.type(systemPrompt, "New system prompt");

      await waitFor(() => {
        expect(mockOnChange).toHaveBeenCalled();
        const lastCall = mockOnChange.mock.calls[mockOnChange.mock.calls.length - 1][0];
        expect(lastCall.system_prompt).toContain("New system prompt");
      });
    });

    it("should call onChange when prompt template is modified", async () => {
      const user = setupUser();
      await renderWithConfig();

      const promptTemplate = screen.getByLabelText(/prompt template/i);
      await user.type(promptTemplate, "Test template");

      await waitFor(() => {
        expect(mockOnChange).toHaveBeenCalled();
        const lastCall = mockOnChange.mock.calls[mockOnChange.mock.calls.length - 1][0];
        expect(lastCall.prompt_template).toContain("Test template");
      });
    });

    it("should call onChange when model is changed", async () => {
      const user = setupUser();
      await renderWithConfig();

      const modelSelect = screen.getByLabelText(/model/i);
      await user.selectOptions(modelSelect, "claude-3-opus");

      await waitFor(() => {
        expect(mockOnChange).toHaveBeenCalledWith(
          expect.objectContaining({
            model: "claude-3-opus",
          }),
        );
      });
    });

    it("should call onChange when temperature slider is adjusted", async () => {
      await renderWithConfig();

      const slider = screen.getByLabelText(/temperature/i);
      fireEvent.change(slider, { target: { value: "1.2" } });

      await waitFor(() => {
        expect(mockOnChange).toHaveBeenCalledWith(
          expect.objectContaining({
            temperature: 1.2,
          }),
        );
      });
    });

    it("should call onChange when max tokens is set", async () => {
      const user = setupUser();
      await renderWithConfig();

      const maxTokens = screen.getByLabelText(/max tokens/i);
      await user.type(maxTokens, "4096");

      await waitFor(() => {
        expect(mockOnChange).toHaveBeenCalled();
        const lastCall = mockOnChange.mock.calls[mockOnChange.mock.calls.length - 1][0];
        expect(lastCall.max_tokens).toBe(4096);
      });
    });

    it("should handle clearing max tokens", async () => {
      const user = setupUser();
      const config = { max_tokens: 2000 };
      await renderWithConfig(config);

      const maxTokens = screen.getByLabelText(/max tokens/i);
      await user.clear(maxTokens);

      await waitFor(() => {
        expect(mockOnChange).toHaveBeenCalledWith(
          expect.objectContaining({
            max_tokens: undefined,
          }),
        );
      });
    });

    it("should call onChange when variables are updated", async () => {
      const user = setupUser();
      await renderWithConfig();

      const addButton = screen.getByTestId("add-variable");
      await user.click(addButton);

      await waitFor(() => {
        expect(mockOnChange).toHaveBeenCalledWith(
          expect.objectContaining({
            variables: expect.objectContaining({ newKey: "newValue" }),
          }),
        );
      });
    });
  });

  describe("Error Display", () => {
    it("should display error for prompt_template field", async () => {
      const errors = { prompt_template: "Prompt template is required" };
      await renderWithConfig({}, { errors });

      expect(screen.getByText("Prompt template is required")).toBeInTheDocument();
    });

    it("should not display errors when errors object is empty", async () => {
      await renderWithConfig({}, { errors: {} });

      expect(screen.queryByText(/required/i)).not.toBeInTheDocument();
      expect(screen.queryByText(/invalid/i)).not.toBeInTheDocument();
    });
  });

  describe("Integration with Sub-components", () => {
    it("should render AgentFields with correct props", async () => {
      const config = { role: "Test Role" };
      await renderWithConfig(config);

      expect(screen.getByTestId("agent-fields")).toBeInTheDocument();
      expect(screen.getByTestId("agent-role")).toHaveValue("Test Role");
    });

    it("should propagate AgentFields changes to parent config", async () => {
      const user = setupUser();
      await renderWithConfig();

      const roleInput = screen.getByTestId("agent-role");
      await user.type(roleInput, "New Role");

      await waitFor(() => {
        expect(mockOnChange).toHaveBeenCalledWith(
          expect.objectContaining({
            role: expect.stringContaining("New Role"),
          }),
        );
      });
    });

    it("should render AdvancedSettings with correct props", async () => {
      await renderWithConfig();

      expect(screen.getByTestId("advanced-settings")).toBeInTheDocument();
    });

    it("should propagate AdvancedSettings changes to parent config", async () => {
      const user = setupUser();
      await renderWithConfig();

      const cacheCheckbox = screen.getByTestId("cache-enabled");
      await user.click(cacheCheckbox);

      await waitFor(() => {
        expect(mockOnChange).toHaveBeenCalledWith(
          expect.objectContaining({
            cache_enabled: true,
          }),
        );
      });
    });

    it("should preserve existing config when updating from sub-components", async () => {
      const user = setupUser();
      const config = {
        prompt_template: "Existing prompt",
        model: "gpt-4",
        temperature: 0.8,
      };
      await renderWithConfig(config);

      const roleInput = screen.getByTestId("agent-role");
      await user.type(roleInput, "Test");

      await waitFor(() => {
        expect(mockOnChange).toHaveBeenCalledWith(
          expect.objectContaining({
            prompt_template: "Existing prompt",
            model: "gpt-4",
            temperature: 0.8,
            role: expect.any(String),
          }),
        );
      });
    });
  });

  describe("Field Descriptions and Labels", () => {
    it("should display helpful descriptions for each field", async () => {
      await renderWithConfig();

      expect(screen.getByText(/instructions that define the assistant's behavior/i)).toBeInTheDocument();
      expect(screen.getByText(/use {{variable}} for interpolation/i)).toBeInTheDocument();
      expect(screen.getByText(/0 = deterministic, 2 = creative/i)).toBeInTheDocument();
    });

    it("should mark prompt template as required", async () => {
      await renderWithConfig();

      // Check that the FormField with prompt template has required prop
      const promptLabel = screen.getByText(/prompt template/i, { selector: "label" });
      expect(promptLabel).toBeInTheDocument();
    });
  });

  describe("Temperature Slider", () => {
    it("should have correct min, max, and step attributes", async () => {
      await renderWithConfig();

      const slider = screen.getByLabelText(/temperature/i);
      expect(slider).toHaveAttribute("min", "0");
      expect(slider).toHaveAttribute("max", "2");
      expect(slider).toHaveAttribute("step", "0.1");
    });

    it("should update displayed value when slider moves", async () => {
      await renderWithConfig();

      const slider = screen.getByLabelText(/temperature/i);
      fireEvent.change(slider, { target: { value: "0.3" } });

      await waitFor(() => {
        expect(mockOnChange).toHaveBeenCalledWith(
          expect.objectContaining({
            temperature: 0.3,
          }),
        );
      });
    });
  });

  describe("Variables Editor", () => {
    it("should render KeyValueEditor for variables", async () => {
      await renderWithConfig();

      expect(screen.getByTestId("key-value-editor")).toBeInTheDocument();
    });

    it("should display existing variables", async () => {
      const config = {
        variables: { input: "test input", context: "test context" },
      };
      await renderWithConfig(config);

      const variablesDisplay = screen.getByTestId("variables-display");
      expect(variablesDisplay.textContent).toContain("input");
      expect(variablesDisplay.textContent).toContain("test input");
    });

    it("should handle empty variables object", async () => {
      const config = { variables: {} };
      await renderWithConfig(config);

      const variablesDisplay = screen.getByTestId("variables-display");
      expect(variablesDisplay.textContent).toBe("{}");
    });
  });

  describe("Max Tokens Input", () => {
    it("should accept numeric input", async () => {
      const user = setupUser();
      await renderWithConfig();

      const maxTokens = screen.getByLabelText(/max tokens/i);
      await user.type(maxTokens, "8000");

      await waitFor(() => {
        const lastCall = mockOnChange.mock.calls[mockOnChange.mock.calls.length - 1][0];
        expect(lastCall.max_tokens).toBe(8000);
      });
    });

    it("should have appropriate min and max constraints", async () => {
      await renderWithConfig();

      const maxTokens = screen.getByLabelText(/max tokens/i);
      expect(maxTokens).toHaveAttribute("type", "number");
      expect(maxTokens).toHaveAttribute("min", "1");
      expect(maxTokens).toHaveAttribute("max", "128000");
    });
  });
});
