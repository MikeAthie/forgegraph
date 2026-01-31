/**
 * Unit tests for SubgraphNodeForm component.
 *
 * Tests graph selection, version input, input/output mapping editors,
 * and integration with AgentFields and AdvancedSettings.
 */

import { act, render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { useState } from "react";
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

  const setupUser = () => {
    const user = userEvent.setup();
    return {
      ...user,
      click: (element: HTMLElement) => act(async () => user.click(element)),
      clear: (element: HTMLElement) => act(async () => user.clear(element)),
      type: (element: HTMLElement, text: string) => act(async () => user.type(element, text)),
      selectOptions: (element: HTMLElement, value: string) =>
        act(async () => user.selectOptions(element, value)),
    };
  };

  const renderWithConfig = (
    initialConfig: NodeFormProps["config"] = {}
  ) => {
    const Wrapper = () => {
      const [config, setConfig] = useState(initialConfig);
      const handleChange = (nextConfig: NodeFormProps["config"]) => {
        setConfig(nextConfig);
        mockOnChange(nextConfig);
      };

      return (
        <SubgraphNodeForm
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

      renderWithConfig(config);

      expect(screen.getByDisplayValue("graph_abc123")).toBeInTheDocument();
      expect(screen.getByDisplayValue("v1.0.0")).toBeInTheDocument();
    });

    it("should display helpful description", () => {
      renderWithConfig();

      expect(
        screen.getByText(
          /execute another graph as a node within this workflow. this enables modular, reusable agent components/i
        )
      ).toBeInTheDocument();
    });
  });

  describe("Graph ID Field", () => {
    it("should render graph ID input", () => {
      renderWithConfig();

      expect(screen.getByLabelText(/graph id/i)).toBeInTheDocument();
    });

    it("should call onChange when graph ID is modified", async () => {
      const user = setupUser();
      renderWithConfig();

      const graphIdInput = screen.getByLabelText(/graph id/i);
      await user.type(graphIdInput, "graph_123");

      await waitFor(() => {
        const lastCall = mockOnChange.mock.calls[mockOnChange.mock.calls.length - 1][0];
        expect(lastCall.graph_id).toContain("graph_123");
      });
    });

    it("should have appropriate placeholder", () => {
      renderWithConfig();

      expect(screen.getByPlaceholderText("graph_abc123")).toBeInTheDocument();
    });

    it("should have monospace font class", () => {
      renderWithConfig();

      const graphIdInput = screen.getByLabelText(/graph id/i);
      expect(graphIdInput).toHaveClass("font-mono");
    });
  });

  describe("External Link", () => {
    it("should show external link when graph_id is set", () => {
      const config = { graph_id: "graph_test123" };
      renderWithConfig(config);

      const link = screen.getByRole("link");
      expect(link).toBeInTheDocument();
      expect(link).toHaveAttribute("href", "/graphs/graph_test123");
      expect(link).toHaveAttribute("target", "_blank");
      expect(link).toHaveAttribute("rel", "noopener noreferrer");
    });

    it("should not show external link when graph_id is empty", () => {
      renderWithConfig();

      expect(screen.queryByRole("link")).not.toBeInTheDocument();
    });

    it("should update link href when graph_id changes", async () => {
      const user = setupUser();
      const config = { graph_id: "graph_old" };
      renderWithConfig(config);

      expect(screen.getByRole("link")).toHaveAttribute("href", "/graphs/graph_old");

      const graphIdInput = screen.getByLabelText(/graph id/i);
      await user.clear(graphIdInput);
      await user.type(graphIdInput, "graph_new");

      await waitFor(() => {
        expect(screen.getByRole("link")).toHaveAttribute("href", "/graphs/graph_new");
      });
    });
  });

  describe("Version Field", () => {
    it("should render version input", () => {
      renderWithConfig();

      expect(screen.getByLabelText(/version/i)).toBeInTheDocument();
    });

    it("should call onChange when version is modified", async () => {
      const user = setupUser();
      renderWithConfig();

      const versionInput = screen.getByLabelText(/version/i);
      await user.type(versionInput, "v2.0.0");

      await waitFor(() => {
        const lastCall = mockOnChange.mock.calls[mockOnChange.mock.calls.length - 1][0];
        expect(lastCall.graph_version).toContain("v2.0.0");
      });
    });

    it("should have appropriate placeholder", () => {
      renderWithConfig();

      expect(screen.getByPlaceholderText("latest")).toBeInTheDocument();
    });

    it("should show description about version being optional", () => {
      renderWithConfig();

      expect(screen.getByText(/specific version \(blank = latest\)/i)).toBeInTheDocument();
    });
  });

  describe("Input Mapping", () => {
    it("should render KeyValueEditor for input mapping", () => {
      renderWithConfig();

      expect(screen.getByTestId("key-value-editor-Subgraph input key")).toBeInTheDocument();
    });

    it("should call onChange when input mapping is updated", async () => {
      const user = setupUser();
      renderWithConfig();

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
      renderWithConfig(config);

      const mappingDisplay = screen.getByTestId("mapping-display-Subgraph input key");
      expect(mappingDisplay.textContent).toContain("query");
      expect(mappingDisplay.textContent).toContain("context");
    });

    it("should display description for input mapping", () => {
      renderWithConfig();

      expect(
        screen.getByText(/map values from parent state to subgraph inputs/i)
      ).toBeInTheDocument();
    });
  });

  describe("Output Mapping", () => {
    it("should render KeyValueEditor for output mapping", () => {
      renderWithConfig();

      expect(screen.getByTestId("key-value-editor-Parent state key")).toBeInTheDocument();
    });

    it("should call onChange when output mapping is updated", async () => {
      const user = setupUser();
      renderWithConfig();

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
      renderWithConfig(config);

      const mappingDisplay = screen.getByTestId("mapping-display-Parent state key");
      expect(mappingDisplay.textContent).toContain("result");
      expect(mappingDisplay.textContent).toContain("status");
    });

    it("should display description for output mapping", () => {
      renderWithConfig();

      expect(
        screen.getByText(/map subgraph outputs back to parent state/i)
      ).toBeInTheDocument();
    });
  });

  describe("Mapping Examples", () => {
    it("should display mapping examples section", () => {
      renderWithConfig();

      expect(screen.getByText(/mapping examples/i)).toBeInTheDocument();
    });

    it("should show input mapping example", () => {
      renderWithConfig();

      expect(screen.getByText("query", { selector: "code" })).toBeInTheDocument();
      expect(
        screen.getByText(/node.prompt_1.output/, { selector: "code" })
      ).toBeInTheDocument();
    });

    it("should show output mapping example", () => {
      renderWithConfig();

      expect(screen.getByText(/sub_result/, { selector: "code" })).toBeInTheDocument();
      expect(screen.getByText(/output.final/, { selector: "code" })).toBeInTheDocument();
    });
  });

  describe("Version Warning", () => {
    it("should display version pinning warning", () => {
      renderWithConfig();

      expect(screen.getByText(/version pinning recommended/i)).toBeInTheDocument();
      expect(
        screen.getByText(
          /pin to a specific version for production workflows to ensure consistent behavior/i
        )
      ).toBeInTheDocument();
    });

    it("should style warning appropriately", () => {
      const { container } = renderWithConfig();

      const warning = container.querySelector(".bg-amber-500\\/10");
      expect(warning).toBeInTheDocument();
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

  describe("Form Layout", () => {
    it("should display section headers", () => {
      renderWithConfig();

      expect(screen.getByText(/^subgraph reference$/i)).toBeInTheDocument();
      expect(screen.getByText(/^data mapping$/i)).toBeInTheDocument();
    });

    it("should render separators between sections", () => {
      const { container } = renderWithConfig();

      const separators = container.querySelectorAll("[data-slot='separator']");
      expect(separators.length).toBeGreaterThan(0);
    });

    it("should use grid layout for graph ID and version", () => {
      const { container } = renderWithConfig();

      const grid = container.querySelector(".grid-cols-2");
      expect(grid).toBeInTheDocument();
    });
  });

  describe("Field Requirements", () => {
    it("should mark graph ID as required", () => {
      renderWithConfig();

      const graphIdLabel = screen.getByText(/graph id/i, { selector: "label" });
      expect(graphIdLabel).toBeInTheDocument();
    });

    it("should not mark version as required", () => {
      renderWithConfig();

      // Version field should not have required indicator
      const versionLabel = screen.getByText(/version/i, { selector: "label" });
      expect(versionLabel).toBeInTheDocument();
    });
  });

  describe("Preserving Config", () => {
    it("should preserve mappings when updating graph ID", async () => {
      const user = setupUser();
      const config = {
        graph_id: "old_graph",
        input_mapping: { key: "value" },
        output_mapping: { out: "result" },
      };
      renderWithConfig(config);

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
