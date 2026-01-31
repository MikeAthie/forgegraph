/**
 * Unit tests for MemoryNodeForm component.
 *
 * Tests memory type selection, conditional fields based on memory type,
 * memory key, and integration with AgentFields and AdvancedSettings.
 */

import { act, fireEvent, render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { useState } from "react";
import { MemoryNodeForm } from "@/components/graph-editor/forms/MemoryNodeForm";
import type { NodeFormProps } from "@/components/graph-editor/NodeConfigDialog";

// Mock child components
jest.mock("@/components/graph-editor/forms/AgentFields", () => ({
  AgentFields: () => <div data-testid="agent-fields">Agent Fields</div>,
}));

jest.mock("@/components/graph-editor/forms/AdvancedSettings", () => ({
  AdvancedSettings: () => <div data-testid="advanced-settings">Advanced Settings</div>,
}));

describe("MemoryNodeForm", () => {
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

  const renderWithConfig = (initialConfig: NodeFormProps["config"] = {}) => {
    const Wrapper = () => {
      const [config, setConfig] = useState(initialConfig);
      const handleChange = (nextConfig: NodeFormProps["config"]) => {
        setConfig(nextConfig);
        mockOnChange(nextConfig);
      };

      return (
        <MemoryNodeForm
          config={config}
          onChange={handleChange}
          errors={{}}
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

      expect(screen.getByText(/memory configuration/i)).toBeInTheDocument();
      expect(screen.getByLabelText(/memory type/i)).toBeInTheDocument();
      expect(screen.getByLabelText(/memory key/i)).toBeInTheDocument();
      expect(screen.getByTestId("agent-fields")).toBeInTheDocument();
      expect(screen.getByTestId("advanced-settings")).toBeInTheDocument();
    });

    it("should render all memory type options", () => {
      renderWithConfig();

      expect(screen.getByRole("option", { name: /conversation buffer/i })).toBeInTheDocument();
      expect(screen.getByRole("option", { name: /rolling buffer/i })).toBeInTheDocument();
      expect(screen.getByRole("option", { name: /summary memory/i })).toBeInTheDocument();
      expect(screen.getByRole("option", { name: /vector store/i })).toBeInTheDocument();
    });

    it("should default to conversation memory type", () => {
      renderWithConfig();

      const memoryTypeSelect = screen.getByLabelText(/memory type/i);
      expect(memoryTypeSelect).toHaveValue("conversation");
    });

    it("should render with populated config", () => {
      const config = {
        memory_type: "buffer" as const,
        memory_key: "chat_history",
        max_messages: 50,
      };

      renderWithConfig(config);

      const memoryTypeSelect = screen.getByLabelText(/memory type/i);
      expect(memoryTypeSelect).toHaveValue("buffer");
      expect(screen.getByDisplayValue("chat_history")).toBeInTheDocument();
      expect(screen.getByLabelText(/memory depth/i)).toHaveValue("long");
    });
  });

  describe("Memory Type Selection", () => {
    it("should call onChange when memory type is changed", async () => {
      const user = setupUser();
      renderWithConfig();

      const memoryTypeSelect = screen.getByLabelText(/memory type/i);
      await user.selectOptions(memoryTypeSelect, "buffer");

      await waitFor(() => {
        expect(mockOnChange).toHaveBeenCalledWith(
          expect.objectContaining({
            memory_type: "buffer",
          })
        );
      });
    });

    it("should display memory type description", () => {
      const config = { memory_type: "vector" as const };
      renderWithConfig(config);

      expect(
        screen.getByText(/semantic search over stored memories/i)
      ).toBeInTheDocument();
    });
  });

  describe("Conditional Fields - Buffer Memory", () => {
    it("should show memory depth field for buffer memory type", () => {
      const config = { memory_type: "buffer" as const };
      renderWithConfig(config);

      expect(screen.getByLabelText(/memory depth/i)).toBeInTheDocument();
      expect(screen.getByLabelText(/custom buffer size/i)).toBeInTheDocument();
    });

    it("should not show buffer fields for conversation type", () => {
      const config = { memory_type: "conversation" as const };
      renderWithConfig(config);

      expect(screen.queryByLabelText(/memory depth/i)).not.toBeInTheDocument();
      expect(screen.queryByLabelText(/custom buffer size/i)).not.toBeInTheDocument();
    });

    it("should update custom buffer size value", async () => {
      const user = setupUser();
      const config = { memory_type: "buffer" as const };
      renderWithConfig(config);

      const customBufferSize = screen.getByLabelText(/custom buffer size/i);
      await user.type(customBufferSize, "55");

      await waitFor(() => {
        const lastCall = mockOnChange.mock.calls[mockOnChange.mock.calls.length - 1][0];
        expect(lastCall.max_messages).toBe(55);
      });
    });
  });

  describe("Conditional Fields - Summary Memory", () => {
    it("should show max tokens field for summary memory type", () => {
      const config = { memory_type: "summary" as const };
      renderWithConfig(config);

      expect(screen.getByLabelText(/max tokens/i)).toBeInTheDocument();
    });

    it("should not show max tokens field for buffer type", () => {
      const config = { memory_type: "buffer" as const };
      renderWithConfig(config);

      expect(screen.queryByLabelText(/max tokens/i)).not.toBeInTheDocument();
    });

    it("should update max tokens value", async () => {
      const user = setupUser();
      const config = { memory_type: "summary" as const };
      renderWithConfig(config);

      const maxTokens = screen.getByLabelText(/max tokens/i);
      await user.type(maxTokens, "4000");

      await waitFor(() => {
        const lastCall = mockOnChange.mock.calls[mockOnChange.mock.calls.length - 1][0];
        expect(lastCall.max_tokens).toBe(4000);
      });
    });
  });

  describe("Conditional Fields - Vector Memory", () => {
    it("should show retrieval query and top k fields for vector memory", () => {
      const config = { memory_type: "vector" as const };
      renderWithConfig(config);

      expect(screen.getByLabelText(/retrieval query/i)).toBeInTheDocument();
      expect(screen.getByLabelText(/top k results/i)).toBeInTheDocument();
    });

    it("should not show vector fields for conversation type", () => {
      const config = { memory_type: "conversation" as const };
      renderWithConfig(config);

      expect(screen.queryByLabelText(/retrieval query/i)).not.toBeInTheDocument();
      expect(screen.queryByLabelText(/top k results/i)).not.toBeInTheDocument();
    });

    it("should update retrieval query", async () => {
      const config = { memory_type: "vector" as const };
      renderWithConfig(config);

      const retrievalQuery = screen.getByLabelText(/retrieval query/i);
      fireEvent.change(retrievalQuery, { target: { value: "{{input.question}}" } });

      await waitFor(() => {
        const lastCall = mockOnChange.mock.calls[mockOnChange.mock.calls.length - 1][0];
        expect(lastCall.retrieval_query).toContain("{{input.question}}");
      });
    });

    it("should update top k value", async () => {
      const user = setupUser();
      const config = { memory_type: "vector" as const };
      renderWithConfig(config);

      const topK = screen.getByLabelText(/top k results/i);
      await user.type(topK, "10");

      await waitFor(() => {
        const lastCall = mockOnChange.mock.calls[mockOnChange.mock.calls.length - 1][0];
        expect(lastCall.top_k).toBe(10);
      });
    });
  });

  describe("Memory Key Field", () => {
    it("should render memory key input", () => {
      renderWithConfig();

      expect(screen.getByLabelText(/memory key/i)).toBeInTheDocument();
    });

    it("should call onChange when memory key is modified", async () => {
      const user = setupUser();
      renderWithConfig();

      const memoryKey = screen.getByLabelText(/memory key/i);
      await user.type(memoryKey, "session_memory");

      await waitFor(() => {
        const lastCall = mockOnChange.mock.calls[mockOnChange.mock.calls.length - 1][0];
        expect(lastCall.memory_key).toContain("session_memory");
      });
    });

    it("should have appropriate placeholder", () => {
      renderWithConfig();

      expect(screen.getByPlaceholderText("conversation_history")).toBeInTheDocument();
    });
  });

  describe("Switching Memory Types", () => {
    it("should hide buffer fields when switching from buffer to conversation", async () => {
      const user = setupUser();
      const config = { memory_type: "buffer" as const, max_messages: 50 };
      renderWithConfig(config);

      expect(screen.getByLabelText(/memory depth/i)).toBeInTheDocument();

      const memoryTypeSelect = screen.getByLabelText(/memory type/i);
      await user.selectOptions(memoryTypeSelect, "conversation");

      await waitFor(() => {
        expect(screen.queryByLabelText(/memory depth/i)).not.toBeInTheDocument();
      });
    });

    it("should show vector fields when switching to vector memory", async () => {
      const user = setupUser();
      renderWithConfig();

      expect(screen.queryByLabelText(/retrieval query/i)).not.toBeInTheDocument();

      const memoryTypeSelect = screen.getByLabelText(/memory type/i);
      await user.selectOptions(memoryTypeSelect, "vector");

      await waitFor(() => {
        expect(screen.getByLabelText(/retrieval query/i)).toBeInTheDocument();
        expect(screen.getByLabelText(/top k results/i)).toBeInTheDocument();
      });
    });
  });

  describe("Field Descriptions", () => {
    it("should display helpful description for memory type", () => {
      renderWithConfig();

      expect(
        screen.getByText(/strategy for storing and managing memory/i)
      ).toBeInTheDocument();
    });

    it("should display description for memory key", () => {
      renderWithConfig();

      expect(
        screen.getByText(/state key to store\/retrieve memory from/i)
      ).toBeInTheDocument();
    });

    it("should display description for max messages", () => {
      const config = { memory_type: "buffer" as const };
      renderWithConfig(config);

      expect(
        screen.getByText(/maximum number of messages to keep in buffer/i)
      ).toBeInTheDocument();
    });

    it("should display description for max tokens", () => {
      const config = { memory_type: "summary" as const };
      renderWithConfig(config);

      expect(
        screen.getByText(/token limit before triggering summarization/i)
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

  describe("Input Constraints", () => {
    it("should have appropriate constraints on custom buffer size", () => {
      const config = { memory_type: "buffer" as const };
      renderWithConfig(config);

      const customBufferSize = screen.getByLabelText(/custom buffer size/i);
      expect(customBufferSize).toHaveAttribute("type", "number");
      expect(customBufferSize).toHaveAttribute("min", "1");
      expect(customBufferSize).toHaveAttribute("max", "1000");
    });

    it("should have appropriate constraints on max tokens", () => {
      const config = { memory_type: "summary" as const };
      renderWithConfig(config);

      const maxTokens = screen.getByLabelText(/max tokens/i);
      expect(maxTokens).toHaveAttribute("type", "number");
      expect(maxTokens).toHaveAttribute("min", "100");
      expect(maxTokens).toHaveAttribute("max", "100000");
    });

    it("should have appropriate constraints on top k", () => {
      const config = { memory_type: "vector" as const };
      renderWithConfig(config);

      const topK = screen.getByLabelText(/top k results/i);
      expect(topK).toHaveAttribute("type", "number");
      expect(topK).toHaveAttribute("min", "1");
      expect(topK).toHaveAttribute("max", "100");
    });
  });

  describe("Form Layout", () => {
    it("should display section headers", () => {
      renderWithConfig();

      expect(screen.getByText(/^memory configuration$/i)).toBeInTheDocument();
    });

    it("should display helpful main description", () => {
      renderWithConfig();

      expect(
        screen.getByText(
          /configure how the agent stores and retrieves information across interactions/i
        )
      ).toBeInTheDocument();
    });
  });
});
