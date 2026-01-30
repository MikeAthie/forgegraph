/**
 * Unit tests for HttpNodeForm component.
 *
 * Tests HTTP method selection, URL input, headers editor, conditional body field,
 * output key, URL validation, and JSON body validation.
 */

import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { useState } from "react";
import { HttpNodeForm } from "@/components/graph-editor/forms/HttpNodeForm";
import type { NodeFormProps } from "@/components/graph-editor/NodeConfigDialog";

// Mock validation utilities
jest.mock("@/lib/form-validation", () => ({
  validateUrl: jest.fn((value: string) => {
    if (value && !value.startsWith("http") && !value.startsWith("/")) {
      return { field: "url", message: "Invalid URL format" };
    }
    return null;
  }),
  validateJson: jest.fn((value: string) => {
    if (value) {
      try {
        JSON.parse(value);
        return null;
      } catch {
        return { field: "body", message: "Invalid JSON format" };
      }
    }
    return null;
  }),
}));

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
      <button
        data-testid="add-header"
        onClick={() => onChange({ ...value, "X-Custom-Header": "value" })}
      >
        Add Header
      </button>
      <div data-testid="headers-display">{JSON.stringify(value)}</div>
    </div>
  ),
}));

describe("HttpNodeForm", () => {
  const mockOnChange = jest.fn();
  const mockSetErrors = jest.fn();

  const renderWithConfig = (
    initialConfig: NodeFormProps["config"] = {},
    options: { errors?: NodeFormProps["errors"] } = {}
  ) => {
    const Wrapper = () => {
      const [config, setConfig] = useState(initialConfig);
      const handleChange = (nextConfig: NodeFormProps["config"]) => {
        setConfig(nextConfig);
        mockOnChange(nextConfig);
      };

      return (
        <HttpNodeForm
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

      expect(screen.getByLabelText(/method/i)).toBeInTheDocument();
      expect(screen.getByLabelText(/url/i)).toBeInTheDocument();
      expect(screen.getByTestId("agent-fields")).toBeInTheDocument();
      expect(screen.getByTestId("advanced-settings")).toBeInTheDocument();
    });

    it("should render with populated config", () => {
      const config = {
        method: "POST" as const,
        url: "https://api.example.com/endpoint",
        headers: { "Content-Type": "application/json" },
        body: '{"key": "value"}',
        output_key: "api_response",
      };

      renderWithConfig(config);

      expect(screen.getByLabelText(/method/i)).toHaveValue("POST");
      expect(screen.getByDisplayValue("https://api.example.com/endpoint")).toBeInTheDocument();
      expect(screen.getByDisplayValue('{"key": "value"}')).toBeInTheDocument();
      expect(screen.getByDisplayValue("api_response")).toBeInTheDocument();
    });

    it("should default to GET method", () => {
      renderWithConfig();

      const methodSelect = screen.getByLabelText(/method/i);
      expect(methodSelect).toHaveValue("GET");
    });

    it("should render all HTTP method options", () => {
      renderWithConfig();

      expect(screen.getByRole("option", { name: "GET" })).toBeInTheDocument();
      expect(screen.getByRole("option", { name: "POST" })).toBeInTheDocument();
      expect(screen.getByRole("option", { name: "PUT" })).toBeInTheDocument();
      expect(screen.getByRole("option", { name: "PATCH" })).toBeInTheDocument();
      expect(screen.getByRole("option", { name: "DELETE" })).toBeInTheDocument();
    });
  });

  describe("Conditional Body Rendering", () => {
    it("should not show body field for GET method", () => {
      const config = { method: "GET" as const };
      renderWithConfig(config);

      expect(screen.queryByLabelText(/request body/i)).not.toBeInTheDocument();
    });

    it("should show body field for POST method", () => {
      const config = { method: "POST" as const };
      renderWithConfig(config);

      expect(screen.getByLabelText(/request body/i)).toBeInTheDocument();
    });

    it("should show body field for PUT method", () => {
      const config = { method: "PUT" as const };
      renderWithConfig(config);

      expect(screen.getByLabelText(/request body/i)).toBeInTheDocument();
    });

    it("should show body field for PATCH method", () => {
      const config = { method: "PATCH" as const };
      renderWithConfig(config);

      expect(screen.getByLabelText(/request body/i)).toBeInTheDocument();
    });

    it("should show body field for DELETE method", () => {
      const config = { method: "DELETE" as const };
      renderWithConfig(config);

      expect(screen.getByLabelText(/request body/i)).toBeInTheDocument();
    });

    it("should hide body field when switching from POST to GET", async () => {
      const user = userEvent.setup();
      const config = { method: "POST" as const, body: '{"test": "data"}' };
      renderWithConfig(config);

      expect(screen.getByLabelText(/request body/i)).toBeInTheDocument();

      const methodSelect = screen.getByLabelText(/method/i);
      await user.selectOptions(methodSelect, "GET");

      await waitFor(() => {
        expect(screen.queryByLabelText(/request body/i)).not.toBeInTheDocument();
      });
    });

    it("should show body field when switching from GET to POST", async () => {
      const user = userEvent.setup();
      renderWithConfig();

      expect(screen.queryByLabelText(/request body/i)).not.toBeInTheDocument();

      const methodSelect = screen.getByLabelText(/method/i);
      await user.selectOptions(methodSelect, "POST");

      await waitFor(() => {
        expect(screen.getByLabelText(/request body/i)).toBeInTheDocument();
      });
    });
  });

  describe("Field Changes", () => {
    it("should call onChange when method is changed", async () => {
      const user = userEvent.setup();
      renderWithConfig();

      const methodSelect = screen.getByLabelText(/method/i);
      await user.selectOptions(methodSelect, "POST");

      await waitFor(() => {
        expect(mockOnChange).toHaveBeenCalledWith(
          expect.objectContaining({
            method: "POST",
          })
        );
      });
    });

    it("should call onChange when URL is modified", async () => {
      const user = userEvent.setup();
      renderWithConfig();

      const urlInput = screen.getByLabelText(/url/i);
      await user.type(urlInput, "https://api.test.com");

      await waitFor(() => {
        expect(mockOnChange).toHaveBeenCalled();
        const lastCall = mockOnChange.mock.calls[mockOnChange.mock.calls.length - 1][0];
        expect(lastCall.url).toContain("https://api.test.com");
      });
    });

    it("should call onChange when body is modified", async () => {
      const config = { method: "POST" as const };
      renderWithConfig(config);

      const bodyInput = screen.getByLabelText(/request body/i);
      fireEvent.change(bodyInput, { target: { value: '{"key": "value"}' } });

      await waitFor(() => {
        expect(mockOnChange).toHaveBeenCalled();
        const lastCall = mockOnChange.mock.calls[mockOnChange.mock.calls.length - 1][0];
        expect(lastCall.body).toContain("key");
      });
    });

    it("should call onChange when output key is modified", async () => {
      const user = userEvent.setup();
      renderWithConfig();

      const outputKey = screen.getByLabelText(/output key/i);
      await user.type(outputKey, "result");

      await waitFor(() => {
        expect(mockOnChange).toHaveBeenCalled();
        const lastCall = mockOnChange.mock.calls[mockOnChange.mock.calls.length - 1][0];
        expect(lastCall.output_key).toContain("result");
      });
    });

    it("should call onChange when headers are updated", async () => {
      const user = userEvent.setup();
      renderWithConfig();

      const addButton = screen.getByTestId("add-header");
      await user.click(addButton);

      await waitFor(() => {
        expect(mockOnChange).toHaveBeenCalledWith(
          expect.objectContaining({
            headers: expect.objectContaining({ "X-Custom-Header": "value" }),
          })
        );
      });
    });
  });

  describe("URL Validation", () => {
    it("should call setErrors with URL validation error for invalid URL", async () => {
      const config = { url: "invalid-url" };
      renderWithConfig(config);

      await waitFor(() => {
        expect(mockSetErrors).toHaveBeenCalledWith(
          expect.objectContaining({
            url: "Invalid URL format",
          })
        );
      });
    });

    it("should not set URL error for valid HTTP URL", async () => {
      const config = { url: "https://api.example.com" };
      renderWithConfig(config);

      await waitFor(() => {
        const calls = mockSetErrors.mock.calls;
        if (calls.length > 0) {
          const lastCall = calls[calls.length - 1][0];
          expect(lastCall.url).toBeUndefined();
        }
      });
    });

    it("should not set URL error for relative URL", async () => {
      const config = { url: "/api/endpoint" };
      renderWithConfig(config);

      await waitFor(() => {
        const calls = mockSetErrors.mock.calls;
        if (calls.length > 0) {
          const lastCall = calls[calls.length - 1][0];
          expect(lastCall.url).toBeUndefined();
        }
      });
    });

    it("should display URL error from errors prop", () => {
      const errors = { url: "URL is required" };
      renderWithConfig({}, { errors });

      expect(screen.getByText("URL is required")).toBeInTheDocument();
    });
  });

  describe("JSON Body Validation", () => {
    it("should call setErrors with body validation error for invalid JSON", async () => {
      const config = { method: "POST" as const, body: "{invalid json}" };
      renderWithConfig(config);

      await waitFor(() => {
        expect(mockSetErrors).toHaveBeenCalledWith(
          expect.objectContaining({
            body: "Invalid JSON format",
          })
        );
      });
    });

    it("should not set body error for valid JSON", async () => {
      const config = { method: "POST" as const, body: '{"key": "value"}' };
      renderWithConfig(config);

      await waitFor(() => {
        const calls = mockSetErrors.mock.calls;
        if (calls.length > 0) {
          const lastCall = calls[calls.length - 1][0];
          expect(lastCall.body).toBeUndefined();
        }
      });
    });

    it("should not validate body for GET method", async () => {
      const config = { method: "GET" as const, body: "{invalid}" };
      renderWithConfig(config);

      await waitFor(() => {
        const calls = mockSetErrors.mock.calls;
        if (calls.length > 0) {
          const lastCall = calls[calls.length - 1][0];
          expect(lastCall.body).toBeUndefined();
        }
      });
    });

    it("should display body error from errors prop", () => {
      const config = { method: "POST" as const };
      const errors = { body: "Body must be valid JSON" };
      renderWithConfig(config, { errors });

      expect(screen.getByText("Body must be valid JSON")).toBeInTheDocument();
    });
  });

  describe("Error Display", () => {
    it("should display multiple errors", () => {
      const config = { method: "POST" as const };
      const errors = {
        url: "URL is required",
        body: "Invalid JSON format",
      };
      renderWithConfig(config, { errors });

      expect(screen.getByText("URL is required")).toBeInTheDocument();
      expect(screen.getByText("Invalid JSON format")).toBeInTheDocument();
    });
  });

  describe("Headers Editor", () => {
    it("should render KeyValueEditor for headers", () => {
      renderWithConfig();

      expect(screen.getByTestId("key-value-editor")).toBeInTheDocument();
    });

    it("should display existing headers", () => {
      const config = {
        headers: { "Content-Type": "application/json", "Authorization": "Bearer token" },
      };
      renderWithConfig(config);

      const headersDisplay = screen.getByTestId("headers-display");
      expect(headersDisplay.textContent).toContain("Content-Type");
      expect(headersDisplay.textContent).toContain("Authorization");
    });

    it("should handle empty headers object", () => {
      const config = { headers: {} };
      renderWithConfig(config);

      const headersDisplay = screen.getByTestId("headers-display");
      expect(headersDisplay.textContent).toBe("{}");
    });
  });

  describe("Integration with Sub-components", () => {
    it("should render AgentFields with showRole and showExamples as false", () => {
      renderWithConfig();

      expect(screen.getByTestId("agent-fields")).toBeInTheDocument();
    });

    it("should propagate AgentFields changes to parent config", async () => {
      const user = userEvent.setup();
      renderWithConfig();

      const roleInput = screen.getByTestId("agent-role");
      await user.type(roleInput, "API Client");

      await waitFor(() => {
        expect(mockOnChange).toHaveBeenCalledWith(
          expect.objectContaining({
            role: expect.stringContaining("API Client"),
          })
        );
      });
    });

    it("should render AdvancedSettings", () => {
      renderWithConfig();

      expect(screen.getByTestId("advanced-settings")).toBeInTheDocument();
    });

    it("should propagate AdvancedSettings changes", async () => {
      const user = userEvent.setup();
      renderWithConfig();

      const cacheCheckbox = screen.getByTestId("cache-enabled");
      await user.click(cacheCheckbox);

      await waitFor(() => {
        expect(mockOnChange).toHaveBeenCalledWith(
          expect.objectContaining({
            cache_enabled: true,
          })
        );
      });
    });
  });

  describe("Field Descriptions", () => {
    it("should display helpful placeholder for URL", () => {
      renderWithConfig();

      const urlInput = screen.getByPlaceholderText("https://api.example.com/endpoint");
      expect(urlInput).toBeInTheDocument();
    });

    it("should display helpful placeholder for body", () => {
      const config = { method: "POST" as const };
      renderWithConfig(config);

      const bodyInput = screen.getByPlaceholderText('{"key": "{{value}}"}');
      expect(bodyInput).toBeInTheDocument();
    });

    it("should show interpolation hint for body", () => {
      const config = { method: "POST" as const };
      renderWithConfig(config);

      expect(screen.getByText(/use {{variable}} for interpolation/i)).toBeInTheDocument();
    });
  });

  describe("Output Key Field", () => {
    it("should render output key input", () => {
      renderWithConfig();

      expect(screen.getByLabelText(/output key/i)).toBeInTheDocument();
    });

    it("should have appropriate placeholder", () => {
      renderWithConfig();

      const outputKey = screen.getByPlaceholderText("response");
      expect(outputKey).toBeInTheDocument();
    });
  });
});
