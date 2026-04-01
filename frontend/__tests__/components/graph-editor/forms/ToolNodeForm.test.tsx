/**
 * Unit tests for ToolNodeForm component.
 *
 * Tests tool selection, parameters editor, custom tool fields,
 * JSON schema validation, and integration with AgentFields and AdvancedSettings.
 */

import { act, fireEvent, render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { useState } from "react";
import { ToolNodeForm } from "@/components/graph-editor/forms/ToolNodeForm";
import type { NodeFormProps } from "@/components/graph-editor/NodeConfigDialog";

const mockListCredentials = jest.fn();
const credentialFixtures = [
  {
    id: "cred-openai",
    provider: "openai",
    name: "OpenAI Primary",
    key_hint: "sk-...1234",
    token_expires_at: null,
    health_status: "healthy",
    requires_reauth: false,
    health_message: null,
    created_at: "2026-01-01T00:00:00Z",
  },
  {
    id: "cred-gmail-expired",
    provider: "gmail",
    name: "Gmail OAuth",
    key_hint: "oauth...1234",
    token_expires_at: null,
    health_status: "expired",
    requires_reauth: true,
    health_message: "OAuth token expired",
    created_at: "2026-01-01T00:00:00Z",
  },
];

// Mock validation utilities
jest.mock("@/lib/form-validation", () => ({
  validateJson: jest.fn((value: string) => {
    if (value) {
      try {
        JSON.parse(value);
        return null;
      } catch {
        return { field: "input_schema", message: "Invalid JSON format" };
      }
    }
    return null;
  }),
}));

jest.mock("@/lib/api", () => ({
  credentialsApi: {
    list: (...args: unknown[]) => mockListCredentials(...args),
  },
  getApiErrorMessage: jest.fn((_err: unknown, fallback: string) => fallback),
}));

// Mock child components
jest.mock("@/components/graph-editor/forms/AgentFields", () => ({
  AgentFields: () => <div data-testid="agent-fields">Agent Fields</div>,
}));

jest.mock("@/components/graph-editor/forms/AdvancedSettings", () => ({
  AdvancedSettings: () => <div data-testid="advanced-settings">Advanced Settings</div>,
}));

jest.mock("@/components/ui/key-value-editor", () => ({
  KeyValueEditor: ({ value, onChange }: any) => (
    <div data-testid="key-value-editor">
      <button data-testid="add-parameter" onClick={() => onChange({ ...value, param1: "value1" })}>
        Add Parameter
      </button>
      <div data-testid="parameters-display">{JSON.stringify(value)}</div>
    </div>
  ),
}));

describe("ToolNodeForm", () => {
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
        <ToolNodeForm config={config} onChange={handleChange} errors={options.errors ?? {}} setErrors={mockSetErrors} />
      );
    };

    return render(<Wrapper />);
  };

  beforeEach(() => {
    jest.clearAllMocks();
    mockListCredentials.mockImplementation(() => new Promise(() => {}));
  });

  describe("Initial Render", () => {
    it("should render with empty config", () => {
      renderWithConfig();

      expect(screen.getByText(/tool configuration/i)).toBeInTheDocument();
      expect(screen.getByLabelText(/^tool$/i)).toBeInTheDocument();
      expect(screen.getByLabelText(/credential provider/i)).toBeInTheDocument();
      expect(screen.getByLabelText(/^credential$/i)).toBeInTheDocument();
      expect(screen.getByLabelText(/output key/i)).toBeInTheDocument();
      expect(screen.getByTestId("agent-fields")).toBeInTheDocument();
      expect(screen.getByTestId("advanced-settings")).toBeInTheDocument();
    });

    it("should render all built-in tool options", () => {
      renderWithConfig();

      expect(screen.getByRole("option", { name: /custom tool/i })).toBeInTheDocument();
      expect(screen.getByRole("option", { name: /web search/i })).toBeInTheDocument();
      expect(screen.getByRole("option", { name: /code interpreter/i })).toBeInTheDocument();
      expect(screen.getByRole("option", { name: /file reader/i })).toBeInTheDocument();
      expect(screen.getByRole("option", { name: /calculator/i })).toBeInTheDocument();
      expect(screen.getByRole("option", { name: /database query/i })).toBeInTheDocument();
    });

    it("should default to custom tool", () => {
      renderWithConfig();

      const toolSelect = screen.getByLabelText(/^tool$/i);
      expect(toolSelect).toHaveValue("custom");
    });

    it("should render with populated config", () => {
      const config = {
        tool_name: "web_search",
        parameters: { query: "test" },
        output_key: "search_results",
      };

      renderWithConfig(config);

      expect(screen.getByLabelText(/^tool$/i)).toHaveValue("web_search");
      expect(screen.getByDisplayValue("search_results")).toBeInTheDocument();
    });
  });

  describe("Tool Selection", () => {
    it("should call onChange when tool is changed", async () => {
      const user = setupUser();
      renderWithConfig();

      const toolSelect = screen.getByLabelText(/^tool$/i);
      await user.selectOptions(toolSelect, "web_search");

      await waitFor(() => {
        expect(mockOnChange).toHaveBeenCalledWith(
          expect.objectContaining({
            tool_name: "web_search",
          }),
        );
      });
    });

    it("should select different built-in tools", async () => {
      const user = setupUser();
      renderWithConfig();

      const toolSelect = screen.getByLabelText(/^tool$/i);
      await user.selectOptions(toolSelect, "code_interpreter");

      await waitFor(() => {
        expect(mockOnChange).toHaveBeenCalledWith(
          expect.objectContaining({
            tool_name: "code_interpreter",
          }),
        );
      });
    });
  });

  describe("Custom Tool Fields", () => {
    it("should show tool description field for custom tool", () => {
      const config = { tool_name: "custom" };
      renderWithConfig(config);

      expect(screen.getByLabelText(/tool description/i)).toBeInTheDocument();
    });

    it("should show input schema field for custom tool", () => {
      const config = { tool_name: "custom" };
      renderWithConfig(config);

      expect(screen.getByLabelText(/input schema \(json\)/i)).toBeInTheDocument();
    });

    it("should not show custom fields for built-in tools", () => {
      const config = { tool_name: "web_search" };
      renderWithConfig(config);

      expect(screen.queryByLabelText(/tool description/i)).not.toBeInTheDocument();
      expect(screen.queryByLabelText(/input schema \(json\)/i)).not.toBeInTheDocument();
    });

    it("should show custom fields when tool is undefined", () => {
      renderWithConfig();

      expect(screen.getByLabelText(/tool description/i)).toBeInTheDocument();
      expect(screen.getByLabelText(/input schema \(json\)/i)).toBeInTheDocument();
    });

    it("should update tool description", async () => {
      const user = setupUser();
      const config = { tool_name: "custom" };
      renderWithConfig(config);

      const descriptionInput = screen.getByLabelText(/tool description/i);
      await user.type(descriptionInput, "Custom tool for testing");

      await waitFor(() => {
        const lastCall = mockOnChange.mock.calls[mockOnChange.mock.calls.length - 1][0];
        expect(lastCall.tool_description).toContain("Custom tool for testing");
      });
    });

    it("should update input schema", async () => {
      const config = { tool_name: "custom" };
      renderWithConfig(config);

      const schemaInput = screen.getByLabelText(/input schema \(json\)/i);
      fireEvent.change(schemaInput, { target: { value: '{"type": "object"}' } });

      await waitFor(() => {
        const lastCall = mockOnChange.mock.calls[mockOnChange.mock.calls.length - 1][0];
        expect(lastCall.input_schema).toContain("type");
      });
    });
  });

  describe("Parameters Editor", () => {
    it("should render KeyValueEditor for parameters", () => {
      renderWithConfig();

      expect(screen.getByTestId("key-value-editor")).toBeInTheDocument();
    });

    it("should display existing parameters", () => {
      const config = {
        parameters: { query: "search term", max_results: "10" },
      };
      renderWithConfig(config);

      const parametersDisplay = screen.getByTestId("parameters-display");
      expect(parametersDisplay.textContent).toContain("query");
      expect(parametersDisplay.textContent).toContain("search term");
    });

    it("should call onChange when parameters are updated", async () => {
      const user = setupUser();
      renderWithConfig();

      const addButton = screen.getByTestId("add-parameter");
      await user.click(addButton);

      await waitFor(() => {
        expect(mockOnChange).toHaveBeenCalledWith(
          expect.objectContaining({
            parameters: expect.objectContaining({ param1: "value1" }),
          }),
        );
      });
    });
  });

  describe("Output Key Field", () => {
    it("should render output key input", () => {
      renderWithConfig();

      expect(screen.getByLabelText(/output key/i)).toBeInTheDocument();
    });

    it("should call onChange when output key is modified", async () => {
      const user = setupUser();
      renderWithConfig();

      const outputKey = screen.getByLabelText(/output key/i);
      await user.type(outputKey, "result");

      await waitFor(() => {
        const lastCall = mockOnChange.mock.calls[mockOnChange.mock.calls.length - 1][0];
        expect(lastCall.output_key).toContain("result");
      });
    });

    it("should have appropriate placeholder", () => {
      renderWithConfig();

      expect(screen.getByPlaceholderText("tool_result")).toBeInTheDocument();
    });
  });

  describe("JSON Schema Validation", () => {
    it("should validate input schema as JSON", async () => {
      const config = { tool_name: "custom", input_schema: "{invalid json" };
      renderWithConfig(config);

      await waitFor(() => {
        expect(mockSetErrors).toHaveBeenCalledWith(
          expect.objectContaining({
            input_schema: "Invalid JSON format",
          }),
        );
      });
    });

    it("should not set error for valid JSON schema", async () => {
      const config = {
        tool_name: "custom",
        input_schema: '{"type": "object", "properties": {}}',
      };
      renderWithConfig(config);

      await waitFor(() => {
        const calls = mockSetErrors.mock.calls;
        if (calls.length > 0) {
          const lastCall = calls[calls.length - 1][0];
          expect(lastCall.input_schema).toBeUndefined();
        }
      });
    });

    it("should not validate schema for built-in tools", async () => {
      const config = { tool_name: "web_search" };
      renderWithConfig(config);

      await waitFor(() => {
        const calls = mockSetErrors.mock.calls;
        if (calls.length > 0) {
          const lastCall = calls[calls.length - 1][0];
          expect(lastCall.input_schema).toBeUndefined();
        }
      });
    });

    it("should display schema validation error", () => {
      const config = { tool_name: "custom" };
      const errors = { input_schema: "Invalid JSON schema" };
      renderWithConfig(config, { errors });

      expect(screen.getByText("Invalid JSON schema")).toBeInTheDocument();
    });
  });

  describe("Conditional Field Rendering", () => {
    it("should hide custom fields when switching from custom to built-in tool", async () => {
      const user = setupUser();
      const config = { tool_name: "custom" };
      renderWithConfig(config);

      expect(screen.getByLabelText(/tool description/i)).toBeInTheDocument();

      const toolSelect = screen.getByLabelText(/^tool$/i);
      await user.selectOptions(toolSelect, "web_search");

      await waitFor(() => {
        expect(screen.queryByLabelText(/tool description/i)).not.toBeInTheDocument();
      });
    });

    it("should show custom fields when switching from built-in to custom tool", async () => {
      const user = setupUser();
      const config = { tool_name: "web_search" };
      renderWithConfig(config);

      expect(screen.queryByLabelText(/tool description/i)).not.toBeInTheDocument();

      const toolSelect = screen.getByLabelText(/^tool$/i);
      await user.selectOptions(toolSelect, "custom");

      await waitFor(() => {
        expect(screen.getByLabelText(/tool description/i)).toBeInTheDocument();
      });
    });
  });

  describe("Field Descriptions", () => {
    it("should display helpful description for tool selection", () => {
      renderWithConfig();

      expect(screen.getByText(/select a built-in tool or create a custom one/i)).toBeInTheDocument();
    });

    it("should display description for tool description field", () => {
      const config = { tool_name: "custom" };
      renderWithConfig(config);

      expect(screen.getByText(/describe what this tool does \(helps llm decide when to use it\)/i)).toBeInTheDocument();
    });

    it("should display description for parameters", () => {
      renderWithConfig();

      expect(screen.getByText(/map parameter names to values or state paths/i)).toBeInTheDocument();
    });

    it("should display tool usage documentation", () => {
      renderWithConfig();

      expect(screen.getByText(/tool usage/i)).toBeInTheDocument();
      expect(
        screen.getByText(/tools are functions the agent can call to interact with external systems/i),
      ).toBeInTheDocument();
    });
  });

  describe("Integration with Sub-components", () => {
    it("should render AgentFields", () => {
      renderWithConfig();

      expect(screen.getByTestId("agent-fields")).toBeInTheDocument();
    });

    it("should render AdvancedSettings", () => {
      renderWithConfig();

      expect(screen.getByTestId("advanced-settings")).toBeInTheDocument();
    });
  });

  describe("Input Schema Textarea", () => {
    it("should be a multiline textarea", () => {
      const config = { tool_name: "custom" };
      renderWithConfig(config);

      const schemaInput = screen.getByLabelText(/input schema \(json\)/i);
      expect(schemaInput.tagName).toBe("TEXTAREA");
      expect(schemaInput).toHaveAttribute("rows", "6");
    });

    it("should have monospace font class", () => {
      const config = { tool_name: "custom" };
      renderWithConfig(config);

      const schemaInput = screen.getByLabelText(/input schema \(json\)/i);
      expect(schemaInput).toHaveClass("font-mono");
    });

    it("should have helpful placeholder", () => {
      const config = { tool_name: "custom" };
      renderWithConfig(config);

      const schemaInput = screen.getByLabelText(/input schema \(json\)/i);
      expect(schemaInput).toHaveAttribute("placeholder");
      expect(schemaInput.getAttribute("placeholder")).toContain("type");
      expect(schemaInput.getAttribute("placeholder")).toContain("object");
    });
  });

  describe("Tool Description Textarea", () => {
    it("should mark tool description as required for custom tools", () => {
      const config = { tool_name: "custom" };
      renderWithConfig(config);

      const descriptionLabel = screen.getByText(/tool description/i);
      expect(descriptionLabel.closest("div")).toBeInTheDocument();
    });

    it("should have appropriate rows", () => {
      const config = { tool_name: "custom" };
      renderWithConfig(config);

      const descriptionInput = screen.getByLabelText(/tool description/i);
      expect(descriptionInput.tagName).toBe("TEXTAREA");
      expect(descriptionInput).toHaveAttribute("rows", "3");
    });
  });

  describe("Form Layout", () => {
    it("should display section headers", () => {
      renderWithConfig();

      expect(screen.getByText(/^tool configuration$/i)).toBeInTheDocument();
    });

    it("should render separators between sections", () => {
      const { container } = renderWithConfig();

      const separators = container.querySelectorAll("[data-slot='separator']");
      expect(separators.length).toBeGreaterThan(0);
    });
  });

  describe("Preserving Config", () => {
    it("should preserve parameters when changing tool type", async () => {
      const user = setupUser();
      const config = {
        tool_name: "custom",
        parameters: { key: "value" },
      };
      renderWithConfig(config);

      const toolSelect = screen.getByLabelText(/^tool$/i);
      await user.selectOptions(toolSelect, "web_search");

      await waitFor(() => {
        expect(mockOnChange).toHaveBeenCalledWith(
          expect.objectContaining({
            tool_name: "web_search",
            parameters: { key: "value" },
          }),
        );
      });
    });
  });

  describe("Credential Assignment", () => {
    it("shows provider-specific credentials", async () => {
      mockListCredentials.mockResolvedValueOnce(credentialFixtures);
      renderWithConfig({ provider: "openai" });

      await waitFor(() => {
        expect(screen.getByRole("option", { name: /openai primary/i })).toBeInTheDocument();
      });
      expect(screen.queryByRole("option", { name: /gmail oauth/i })).not.toBeInTheDocument();
    });

    it("clears selected credential when provider changes", async () => {
      const user = setupUser();
      mockListCredentials.mockResolvedValueOnce(credentialFixtures);
      renderWithConfig({ provider: "openai", credential_id: "cred-openai" });

      const providerSelect = screen.getByLabelText(/credential provider/i);
      await user.selectOptions(providerSelect, "gmail");

      await waitFor(() => {
        expect(mockOnChange).toHaveBeenCalled();
      });
      const lastCall = mockOnChange.mock.calls[mockOnChange.mock.calls.length - 1][0];
      expect(lastCall.provider).toBe("gmail");
      expect("credential_id" in lastCall).toBe(false);
    });

    it("shows reauth guidance for unhealthy selected credential", async () => {
      mockListCredentials.mockResolvedValueOnce(credentialFixtures);
      renderWithConfig({
        provider: "gmail",
        credential_id: "cred-gmail-expired",
      });

      await waitFor(() => {
        expect(screen.getByText(/selected credential is expired/i)).toBeInTheDocument();
      });
      expect(screen.getByText(/reconnect this credential in credentials/i)).toBeInTheDocument();
    });
  });
});
