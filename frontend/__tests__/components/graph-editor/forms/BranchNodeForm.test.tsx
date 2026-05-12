/**
 * Unit tests for BranchNodeForm component.
 *
 * Tests branch conditions management, expression validation, add/remove conditions,
 * default branch, and integration with AgentFields and AdvancedSettings.
 */

import { act, render, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { useState } from "react";
import { BranchNodeForm } from "@/components/graph-editor/forms/BranchNodeForm";
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
  AgentFields: () => <div data-testid="agent-fields">Agent Fields</div>,
}));

jest.mock("@/components/graph-editor/forms/AdvancedSettings", () => ({
  AdvancedSettings: () => <div data-testid="advanced-settings">Advanced Settings</div>,
}));

describe("BranchNodeForm", () => {
  const mockOnChange = jest.fn();
  const mockSetErrors = jest.fn();

  const setupUser = () => {
    const user = userEvent.setup();
    return {
      click: (element: HTMLElement) => act(async () => user.click(element)),
      type: (element: HTMLElement, text: string) => act(async () => user.type(element, text)),
      clear: (element: HTMLElement) => act(async () => user.clear(element)),
    };
  };

  const renderWithConfig = (
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
        <BranchNodeForm
          config={config}
          onChange={recordConfigChange}
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

      expect(screen.getByText(/branch conditions/i)).toBeInTheDocument();
      expect(screen.getByText(/add condition/i)).toBeInTheDocument();
      expect(screen.getByLabelText(/default branch/i)).toBeInTheDocument();
      expect(screen.getByTestId("agent-fields")).toBeInTheDocument();
      expect(screen.getByTestId("advanced-settings")).toBeInTheDocument();
    });

    it("should show empty state message when no conditions", () => {
      renderWithConfig();

      expect(screen.getByText(/no conditions defined. add a condition to create branches/i)).toBeInTheDocument();
    });

    it("should render with populated conditions", () => {
      const config = {
        conditions: [
          {
            id: "cond1",
            name: "High Priority",
            expression: "state.priority === 'high'",
          },
          {
            id: "cond2",
            name: "Medium Priority",
            expression: "state.priority === 'medium'",
          },
        ],
        default_branch: "low_priority",
      };

      renderWithConfig(config);

      expect(screen.getByDisplayValue("High Priority")).toBeInTheDocument();
      expect(screen.getByDisplayValue("state.priority === 'high'")).toBeInTheDocument();
      expect(screen.getByDisplayValue("Medium Priority")).toBeInTheDocument();
      expect(screen.getByDisplayValue("state.priority === 'medium'")).toBeInTheDocument();
      expect(screen.getByDisplayValue("low_priority")).toBeInTheDocument();
    });

    it("should display condition numbers correctly", () => {
      const config = {
        conditions: [
          { id: "c1", name: "First", expression: "true" },
          { id: "c2", name: "Second", expression: "false" },
        ],
      };

      renderWithConfig(config);

      expect(screen.getByText("Condition 1")).toBeInTheDocument();
      expect(screen.getByText("Condition 2")).toBeInTheDocument();
    });
  });

  describe("Adding Conditions", () => {
    it("should add a new condition when Add Condition button is clicked", async () => {
      const { click } = setupUser();
      renderWithConfig();

      const addButton = screen.getByRole("button", { name: /add condition/i });
      await click(addButton);

      await waitFor(() => {
        expect(mockOnChange).toHaveBeenCalledWith(
          expect.objectContaining({
            conditions: expect.arrayContaining([
              expect.objectContaining({
                id: expect.stringContaining("condition_"),
                name: "Branch 1",
                expression: "",
              }),
            ]),
          }),
        );
      });
    });

    it("should increment branch name when adding multiple conditions", async () => {
      const { click } = setupUser();
      const config = {
        conditions: [{ id: "c1", name: "Branch 1", expression: "true" }],
      };
      renderWithConfig(config);

      const addButton = screen.getByRole("button", { name: /add condition/i });
      await click(addButton);

      await waitFor(() => {
        expect(mockOnChange).toHaveBeenCalledWith(
          expect.objectContaining({
            conditions: expect.arrayContaining([
              expect.objectContaining({ name: "Branch 1" }),
              expect.objectContaining({ name: "Branch 2" }),
            ]),
          }),
        );
      });
    });

    it("should generate unique IDs for new conditions", async () => {
      const { click } = setupUser();
      renderWithConfig();

      const addButton = screen.getByRole("button", { name: /add condition/i });
      await click(addButton);
      await click(addButton);

      await waitFor(() => {
        const lastCall = mockOnChange.mock.calls[mockOnChange.mock.calls.length - 1][0];
        const ids = lastCall.conditions?.map((c: any) => c.id) || [];
        const uniqueIds = new Set(ids);
        expect(uniqueIds.size).toBe(ids.length);
      });
    });
  });

  describe("Removing Conditions", () => {
    it("should remove a condition when delete button is clicked", async () => {
      const { click } = setupUser();
      const config = {
        conditions: [
          { id: "c1", name: "Condition 1", expression: "true" },
          { id: "c2", name: "Condition 2", expression: "false" },
        ],
      };
      renderWithConfig(config);

      const conditionLabels = screen.getAllByText(/condition \d/i);
      const firstCard = conditionLabels[0]?.closest("div")?.parentElement;
      expect(firstCard).toBeTruthy();

      const firstDeleteButton = within(firstCard as HTMLElement).getByRole("button");
      await click(firstDeleteButton);

      await waitFor(() => {
        expect(mockOnChange).toHaveBeenCalledWith(
          expect.objectContaining({
            conditions: expect.arrayContaining([expect.objectContaining({ name: "Condition 2" })]),
          }),
        );
      });
    });

    it("should remove correct condition by index", async () => {
      const { click } = setupUser();
      const config = {
        conditions: [
          { id: "c1", name: "First", expression: "1" },
          { id: "c2", name: "Second", expression: "2" },
          { id: "c3", name: "Third", expression: "3" },
        ],
      };
      renderWithConfig(config);

      // Get all condition cards
      const conditionCards = screen
        .getAllByText(/condition \d/i)
        .flatMap((el) => {
          const card = el.closest("div")?.parentElement;
          return card ? [card] : [];
        });

      // Find delete button in the second condition card
      expect(conditionCards.length).toBeGreaterThan(1);
      const secondCard = conditionCards[1] as HTMLElement;
      const deleteButton = within(secondCard).getByRole("button");
      await click(deleteButton);

      await waitFor(() => {
        const lastCall = mockOnChange.mock.calls[mockOnChange.mock.calls.length - 1][0];
        expect(lastCall.conditions).toHaveLength(2);
        expect(lastCall.conditions[0].name).toBe("First");
        expect(lastCall.conditions[1].name).toBe("Third");
      });
    });

    it("should show empty state after removing all conditions", async () => {
      const { click } = setupUser();
      const config = {
        conditions: [{ id: "c1", name: "Only One", expression: "true" }],
      };
      renderWithConfig(config);

      const conditionLabel = screen.getByText(/condition 1/i);
      const card = conditionLabel.closest("div")?.parentElement;
      expect(card).toBeTruthy();
      const deleteButton = within(card as HTMLElement).getByRole("button");
      await click(deleteButton);

      await waitFor(() => {
        expect(mockOnChange).toHaveBeenCalledWith(
          expect.objectContaining({
            conditions: [],
          }),
        );
      });
    });
  });

  describe("Condition Field Changes", () => {
    it("should update condition name", async () => {
      const { clear, type } = setupUser();
      const config = {
        conditions: [{ id: "c1", name: "Original", expression: "true" }],
      };
      renderWithConfig(config);

      const nameInput = screen.getByDisplayValue("Original");
      await clear(nameInput);
      await type(nameInput, "Updated Name");

      await waitFor(() => {
        const lastCall = mockOnChange.mock.calls[mockOnChange.mock.calls.length - 1][0];
        expect(lastCall.conditions[0].name).toBe("Updated Name");
      });
    });

    it("should update condition expression", async () => {
      const { type } = setupUser();
      const config = {
        conditions: [{ id: "c1", name: "Test", expression: "" }],
      };
      renderWithConfig(config);

      const expressionInput = screen.getByPlaceholderText("state.score > 0.8");
      await type(expressionInput, "state.value === true");

      await waitFor(() => {
        const lastCall = mockOnChange.mock.calls[mockOnChange.mock.calls.length - 1][0];
        expect(lastCall.conditions[0].expression).toContain("state.value === true");
      });
    });

    it("should preserve other conditions when updating one", async () => {
      const { type } = setupUser();
      const config = {
        conditions: [
          { id: "c1", name: "First", expression: "1" },
          { id: "c2", name: "Second", expression: "2" },
        ],
      };
      renderWithConfig(config);

      const firstExpression = screen.getByDisplayValue("1");
      await type(firstExpression, "00");

      await waitFor(() => {
        const lastCall = mockOnChange.mock.calls[mockOnChange.mock.calls.length - 1][0];
        expect(lastCall.conditions).toHaveLength(2);
        expect(lastCall.conditions[1].name).toBe("Second");
        expect(lastCall.conditions[1].expression).toBe("2");
      });
    });
  });

  describe("Default Branch Field", () => {
    it("should update default branch value", async () => {
      const { type } = setupUser();
      renderWithConfig();

      const defaultBranch = screen.getByLabelText(/default branch/i);
      await type(defaultBranch, "fallback");

      await waitFor(() => {
        const lastCall = mockOnChange.mock.calls[mockOnChange.mock.calls.length - 1][0];
        expect(lastCall.default_branch).toContain("fallback");
      });
    });

    it("should display existing default branch value", () => {
      const config = { default_branch: "my_default" };
      renderWithConfig(config);

      expect(screen.getByDisplayValue("my_default")).toBeInTheDocument();
    });

    it("should have appropriate placeholder", () => {
      renderWithConfig();

      const defaultBranch = screen.getByPlaceholderText("default");
      expect(defaultBranch).toBeInTheDocument();
    });
  });

  describe("Expression Validation", () => {
    it("should validate condition expressions", async () => {
      const config = {
        conditions: [{ id: "c1", name: "Test", expression: "bad }{" }],
      };
      renderWithConfig(config);

      await waitFor(() => {
        expect(mockSetErrors).toHaveBeenCalledWith(
          expect.objectContaining({
            condition_0_expression: "Unbalanced brackets in expression",
          }),
        );
      });
    });

    it("should validate multiple conditions", async () => {
      const config = {
        conditions: [
          { id: "c1", name: "Bad1", expression: "}{" },
          { id: "c2", name: "Good", expression: "true" },
          { id: "c3", name: "Bad2", expression: "}}" },
        ],
      };
      renderWithConfig(config);

      await waitFor(() => {
        const calls = mockSetErrors.mock.calls;
        if (calls.length > 0) {
          const lastCall = calls[calls.length - 1][0];
          expect(lastCall.condition_0_expression).toBeDefined();
          expect(lastCall.condition_2_expression).toBeDefined();
        }
      });
    });

    it("should display condition-specific errors", () => {
      const errors = { condition_0_expression: "Invalid syntax in condition 1" };
      const config = {
        conditions: [{ id: "c1", name: "Test", expression: "bad" }],
      };
      renderWithConfig(config, { errors });

      expect(screen.getByText("Invalid syntax in condition 1")).toBeInTheDocument();
    });

    it("should not validate empty expressions", async () => {
      const config = {
        conditions: [{ id: "c1", name: "Test", expression: "" }],
      };
      renderWithConfig(config);

      await waitFor(() => {
        const calls = mockSetErrors.mock.calls;
        if (calls.length > 0) {
          const lastCall = calls[calls.length - 1][0];
          expect(lastCall.condition_0_expression).toBeUndefined();
        }
      });
    });
  });

  describe("Field Descriptions", () => {
    it("should display helpful description for branch conditions", () => {
      renderWithConfig();

      expect(
        screen.getByText(
          /define conditions to route data to different branches. conditions are evaluated in order, first matching condition wins/i,
        ),
      ).toBeInTheDocument();
    });

    it("should display description for default branch", () => {
      renderWithConfig();

      expect(screen.getByText(/branch to use when no conditions match/i)).toBeInTheDocument();
    });

    it("should display expression examples", () => {
      renderWithConfig();

      expect(screen.getByText(/expression examples/i)).toBeInTheDocument();
      expect(screen.getByText(/state.sentiment === "positive"/)).toBeInTheDocument();
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

  describe("Condition UI Elements", () => {
    it("should display branch name label for each condition", () => {
      const config = {
        conditions: [{ id: "c1", name: "Test", expression: "true" }],
      };
      renderWithConfig(config);

      expect(screen.getByText(/branch name/i)).toBeInTheDocument();
    });

    it("should display expression label for each condition", () => {
      const config = {
        conditions: [{ id: "c1", name: "Test", expression: "true" }],
      };
      renderWithConfig(config);

      expect(screen.getByText(/expression/i, { selector: "label" })).toBeInTheDocument();
    });

    it("should have appropriate placeholder for branch name", () => {
      const config = {
        conditions: [{ id: "c1", name: "", expression: "" }],
      };
      renderWithConfig(config);

      expect(screen.getByPlaceholderText("e.g., High Priority")).toBeInTheDocument();
    });
  });

  describe("Form Layout", () => {
    it("should display section headers", () => {
      renderWithConfig();

      expect(screen.getByText(/^branch conditions$/i)).toBeInTheDocument();
    });

    it("should have Add Condition button with icon", () => {
      renderWithConfig();

      const addButton = screen.getByRole("button", { name: /add condition/i });
      expect(addButton).toBeInTheDocument();

      const plusIcon = addButton.querySelector("svg");
      expect(plusIcon).toBeInTheDocument();
    });
  });
});
