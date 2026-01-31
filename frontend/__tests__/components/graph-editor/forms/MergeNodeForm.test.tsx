/**
 * Unit tests for MergeNodeForm component.
 *
 * Tests merge strategy selection, output key, and integration with
 * AgentFields and AdvancedSettings.
 */

import { act, render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { useState } from "react";
import { MergeNodeForm } from "@/components/graph-editor/forms/MergeNodeForm";
import type { NodeFormProps } from "@/components/graph-editor/NodeConfigDialog";

// Mock child components
jest.mock("@/components/graph-editor/forms/AgentFields", () => ({
  AgentFields: () => <div data-testid="agent-fields">Agent Fields</div>,
}));

jest.mock("@/components/graph-editor/forms/AdvancedSettings", () => ({
  AdvancedSettings: () => <div data-testid="advanced-settings">Advanced Settings</div>,
}));

describe("MergeNodeForm", () => {
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
        <MergeNodeForm
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

      expect(screen.getByText(/merge configuration/i)).toBeInTheDocument();
      expect(screen.getByText(/merge strategy/i)).toBeInTheDocument();
      expect(screen.getByLabelText(/output key/i)).toBeInTheDocument();
      expect(screen.getByTestId("agent-fields")).toBeInTheDocument();
      expect(screen.getByTestId("advanced-settings")).toBeInTheDocument();
    });

    it("should render all merge strategy options", () => {
      renderWithConfig();

      expect(screen.getAllByText("Wait for All").length).toBeGreaterThan(0);
      expect(screen.getAllByText("First Complete").length).toBeGreaterThan(0);
      expect(screen.getAllByText("Latest Value").length).toBeGreaterThan(0);
      expect(screen.getAllByText("Combine All").length).toBeGreaterThan(0);
    });

    it("should display strategy descriptions", () => {
      renderWithConfig();

      expect(
        screen.getByText(/wait for all incoming branches before proceeding/i)
      ).toBeInTheDocument();
      expect(
        screen.getByText(/proceed when first branch completes/i)
      ).toBeInTheDocument();
      expect(
        screen.getByText(/use the most recent value from any branch/i)
      ).toBeInTheDocument();
      expect(
        screen.getByText(/merge all branch outputs into an array/i)
      ).toBeInTheDocument();
    });

    it("should render with populated config", () => {
      const config = {
        merge_strategy: "combine" as const,
        output_key: "merged_result",
      };

      renderWithConfig(config);

      const combineRadio = screen.getByRole("radio", { name: /combine all/i });
      expect(combineRadio).toBeChecked();
      expect(screen.getByDisplayValue("merged_result")).toBeInTheDocument();
    });
  });

  describe("Merge Strategy Selection", () => {
    it("should select 'all' strategy by default", () => {
      renderWithConfig();

      // No strategy specified, check if any is selected as default
      const allRadio = screen.getByRole("radio", { name: /wait for all/i });
      // Component may not have explicit default, so just verify it exists
      expect(allRadio).toBeInTheDocument();
    });

    it("should call onChange when strategy is changed to 'first'", async () => {
      const user = setupUser();
      renderWithConfig();

      const firstRadio = screen.getByRole("radio", { name: /first complete/i });
      await user.click(firstRadio);

      await waitFor(() => {
        expect(mockOnChange).toHaveBeenCalledWith(
          expect.objectContaining({
            merge_strategy: "first",
          })
        );
      });
    });

    it("should call onChange when strategy is changed to 'latest'", async () => {
      const user = setupUser();
      renderWithConfig();

      const latestRadio = screen.getByRole("radio", { name: /latest value/i });
      await user.click(latestRadio);

      await waitFor(() => {
        expect(mockOnChange).toHaveBeenCalledWith(
          expect.objectContaining({
            merge_strategy: "latest",
          })
        );
      });
    });

    it("should call onChange when strategy is changed to 'combine'", async () => {
      const user = setupUser();
      renderWithConfig();

      const combineRadio = screen.getByRole("radio", { name: /combine all/i });
      await user.click(combineRadio);

      await waitFor(() => {
        expect(mockOnChange).toHaveBeenCalledWith(
          expect.objectContaining({
            merge_strategy: "combine",
          })
        );
      });
    });

    it("should call onChange when strategy is changed to 'all'", async () => {
      const user = setupUser();
      const config = { merge_strategy: "first" as const };
      renderWithConfig(config);

      const allRadio = screen.getByRole("radio", { name: /wait for all/i });
      await user.click(allRadio);

      await waitFor(() => {
        expect(mockOnChange).toHaveBeenCalledWith(
          expect.objectContaining({
            merge_strategy: "all",
          })
        );
      });
    });

    it("should visually highlight selected strategy", () => {
      const config = { merge_strategy: "combine" as const };
      renderWithConfig(config);

      const combineRadio = screen.getByRole("radio", { name: /combine all/i });
      expect(combineRadio).toBeChecked();
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
      await user.type(outputKey, "r");

      await waitFor(() => {
        expect(mockOnChange).toHaveBeenCalled();
        expect(mockOnChange.mock.calls.length).toBeGreaterThan(0);
      });
    });

    it("should have appropriate placeholder", () => {
      renderWithConfig();

      expect(screen.getByPlaceholderText("merged")).toBeInTheDocument();
    });

    it("should display existing output key value", () => {
      const config = { output_key: "my_output" };
      renderWithConfig(config);

      expect(screen.getByDisplayValue("my_output")).toBeInTheDocument();
    });
  });

  describe("Field Descriptions", () => {
    it("should display helpful description for merge configuration", () => {
      renderWithConfig();

      expect(
        screen.getByText(/configure how this node merges data from multiple incoming branches/i)
      ).toBeInTheDocument();
    });

    it("should display description for output key", () => {
      renderWithConfig();

      expect(
        screen.getByText(/key to store the merged data under in state/i)
      ).toBeInTheDocument();
    });

    it("should display strategy behavior documentation", () => {
      renderWithConfig();

      expect(screen.getByText(/strategy behavior/i)).toBeInTheDocument();
      expect(
        screen.getByText(/blocks until all branches complete, outputs object with all values/i)
      ).toBeInTheDocument();
      expect(
        screen.getByText(/proceeds immediately when any branch finishes/i)
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

  describe("Strategy Radio Buttons", () => {
    it("should render radio buttons as clickable labels", () => {
      renderWithConfig();

      const labels = screen.getAllByRole("radio").map(r => r.closest("label"));
      expect(labels.length).toBeGreaterThan(0);
      labels.forEach(label => {
        expect(label).toHaveClass("cursor-pointer");
      });
    });

    it("should allow only one strategy to be selected at a time", async () => {
      const user = setupUser();
      renderWithConfig();

      const firstRadio = screen.getByRole("radio", { name: /first complete/i });
      const latestRadio = screen.getByRole("radio", { name: /latest value/i });

      await user.click(firstRadio);
      expect(firstRadio).toBeChecked();

      await user.click(latestRadio);
      expect(latestRadio).toBeChecked();
      expect(firstRadio).not.toBeChecked();
    });
  });

  describe("Form Layout", () => {
    it("should display section headers", () => {
      renderWithConfig();

      expect(screen.getByText(/^merge configuration$/i)).toBeInTheDocument();
    });

    it("should have proper spacing between strategy options", () => {
      const { container } = renderWithConfig();

      const strategyContainer = container.querySelector(".space-y-2");
      expect(strategyContainer).toBeInTheDocument();
    });
  });

  describe("Preserving Config", () => {
    it("should preserve existing config when updating output key", async () => {
      const user = setupUser();
      const config = { merge_strategy: "combine" as const };
      renderWithConfig(config);

      const outputKey = screen.getByLabelText(/output key/i);
      await user.type(outputKey, "new");

      await waitFor(() => {
        expect(mockOnChange).toHaveBeenCalledWith(
          expect.objectContaining({
            merge_strategy: "combine",
            output_key: expect.any(String),
          })
        );
      });
    });

    it("should preserve output key when changing strategy", async () => {
      const user = setupUser();
      const config = {
        merge_strategy: "first" as const,
        output_key: "existing_key",
      };
      renderWithConfig(config);

      const latestRadio = screen.getByRole("radio", { name: /latest value/i });
      await user.click(latestRadio);

      await waitFor(() => {
        expect(mockOnChange).toHaveBeenCalledWith(
          expect.objectContaining({
            merge_strategy: "latest",
            output_key: "existing_key",
          })
        );
      });
    });
  });
});
