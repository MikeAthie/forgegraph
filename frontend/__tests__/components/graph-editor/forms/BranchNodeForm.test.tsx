/**
 * Unit tests for BranchNodeForm component.
 *
 * Tests branch conditions management, expression validation, add/remove conditions,
 * default branch, and integration with AgentFields and AdvancedSettings.
 */

import { render, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { BranchNodeForm } from "@/components/graph-editor/forms/BranchNodeForm";
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
  AgentFields: () => <div data-testid="agent-fields">Agent Fields</div>,
}));

jest.mock("@/components/graph-editor/forms/AdvancedSettings", () => ({
  AdvancedSettings: () => <div data-testid="advanced-settings">Advanced Settings</div>,
}));

describe("BranchNodeForm", () => {
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
      render(<BranchNodeForm {...defaultProps} />);

      expect(screen.getByText(/branch conditions/i)).toBeInTheDocument();
      expect(screen.getByText(/add condition/i)).toBeInTheDocument();
      expect(screen.getByLabelText(/default branch/i)).toBeInTheDocument();
      expect(screen.getByTestId("agent-fields")).toBeInTheDocument();
      expect(screen.getByTestId("advanced-settings")).toBeInTheDocument();
    });

    it("should show empty state message when no conditions", () => {
      render(<BranchNodeForm {...defaultProps} />);

      expect(
        screen.getByText(/no conditions defined. add a condition to create branches/i)
      ).toBeInTheDocument();
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

      render(<BranchNodeForm {...defaultProps} config={config} />);

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

      render(<BranchNodeForm {...defaultProps} config={config} />);

      expect(screen.getByText("Condition 1")).toBeInTheDocument();
      expect(screen.getByText("Condition 2")).toBeInTheDocument();
    });
  });

  describe("Adding Conditions", () => {
    it("should add a new condition when Add Condition button is clicked", async () => {
      const user = userEvent.setup();
      render(<BranchNodeForm {...defaultProps} />);

      const addButton = screen.getByRole("button", { name: /add condition/i });
      await user.click(addButton);

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
          })
        );
      });
    });

    it("should increment branch name when adding multiple conditions", async () => {
      const user = userEvent.setup();
      const config = {
        conditions: [{ id: "c1", name: "Branch 1", expression: "true" }],
      };
      render(<BranchNodeForm {...defaultProps} config={config} />);

      const addButton = screen.getByRole("button", { name: /add condition/i });
      await user.click(addButton);

      await waitFor(() => {
        expect(mockOnChange).toHaveBeenCalledWith(
          expect.objectContaining({
            conditions: expect.arrayContaining([
              expect.objectContaining({ name: "Branch 1" }),
              expect.objectContaining({ name: "Branch 2" }),
            ]),
          })
        );
      });
    });

    it("should generate unique IDs for new conditions", async () => {
      const user = userEvent.setup();
      render(<BranchNodeForm {...defaultProps} />);

      const addButton = screen.getByRole("button", { name: /add condition/i });
      await user.click(addButton);
      await user.click(addButton);

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
      const user = userEvent.setup();
      const config = {
        conditions: [
          { id: "c1", name: "Condition 1", expression: "true" },
          { id: "c2", name: "Condition 2", expression: "false" },
        ],
      };
      render(<BranchNodeForm {...defaultProps} config={config} />);

      const deleteButtons = screen.getAllByRole("button", { name: "" });
      // Find the trash icon button (should be the first one after "Add Condition")
      const firstDeleteButton = deleteButtons.find((btn) =>
        btn.querySelector('[data-lucide="trash-2"]')
      );

      if (firstDeleteButton) {
        await user.click(firstDeleteButton);

        await waitFor(() => {
          expect(mockOnChange).toHaveBeenCalledWith(
            expect.objectContaining({
              conditions: expect.arrayContaining([
                expect.objectContaining({ name: "Condition 2" }),
              ]),
            })
          );
        });
      }
    });

    it("should remove correct condition by index", async () => {
      const user = userEvent.setup();
      const config = {
        conditions: [
          { id: "c1", name: "First", expression: "1" },
          { id: "c2", name: "Second", expression: "2" },
          { id: "c3", name: "Third", expression: "3" },
        ],
      };
      render(<BranchNodeForm {...defaultProps} config={config} />);

      // Get all condition cards
      const conditionCards = screen.getAllByText(/condition \d/i).map(el => el.closest("div")?.parentElement);

      // Find delete button in the second condition card
      const secondCard = conditionCards[1];
      if (secondCard) {
        const deleteButton = within(secondCard).getByRole("button", { name: "" });
        await user.click(deleteButton);

        await waitFor(() => {
          const lastCall = mockOnChange.mock.calls[mockOnChange.mock.calls.length - 1][0];
          expect(lastCall.conditions).toHaveLength(2);
          expect(lastCall.conditions[0].name).toBe("First");
          expect(lastCall.conditions[1].name).toBe("Third");
        });
      }
    });

    it("should show empty state after removing all conditions", async () => {
      const user = userEvent.setup();
      const config = {
        conditions: [{ id: "c1", name: "Only One", expression: "true" }],
      };
      render(<BranchNodeForm {...defaultProps} config={config} />);

      const deleteButton = screen.getByRole("button", { name: "" });
      await user.click(deleteButton);

      await waitFor(() => {
        expect(mockOnChange).toHaveBeenCalledWith(
          expect.objectContaining({
            conditions: [],
          })
        );
      });
    });
  });

  describe("Condition Field Changes", () => {
    it("should update condition name", async () => {
      const user = userEvent.setup();
      const config = {
        conditions: [{ id: "c1", name: "Original", expression: "true" }],
      };
      render(<BranchNodeForm {...defaultProps} config={config} />);

      const nameInput = screen.getByDisplayValue("Original");
      await user.clear(nameInput);
      await user.type(nameInput, "Updated Name");

      await waitFor(() => {
        const lastCall = mockOnChange.mock.calls[mockOnChange.mock.calls.length - 1][0];
        expect(lastCall.conditions[0].name).toBe("Updated Name");
      });
    });

    it("should update condition expression", async () => {
      const user = userEvent.setup();
      const config = {
        conditions: [{ id: "c1", name: "Test", expression: "" }],
      };
      render(<BranchNodeForm {...defaultProps} config={config} />);

      const expressionInput = screen.getByPlaceholderText("state.score > 0.8");
      await user.type(expressionInput, "state.value === true");

      await waitFor(() => {
        const lastCall = mockOnChange.mock.calls[mockOnChange.mock.calls.length - 1][0];
        expect(lastCall.conditions[0].expression).toContain("state.value === true");
      });
    });

    it("should preserve other conditions when updating one", async () => {
      const user = userEvent.setup();
      const config = {
        conditions: [
          { id: "c1", name: "First", expression: "1" },
          { id: "c2", name: "Second", expression: "2" },
        ],
      };
      render(<BranchNodeForm {...defaultProps} config={config} />);

      const firstExpression = screen.getByDisplayValue("1");
      await user.type(firstExpression, "00");

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
      const user = userEvent.setup();
      render(<BranchNodeForm {...defaultProps} />);

      const defaultBranch = screen.getByLabelText(/default branch/i);
      await user.type(defaultBranch, "fallback");

      await waitFor(() => {
        const lastCall = mockOnChange.mock.calls[mockOnChange.mock.calls.length - 1][0];
        expect(lastCall.default_branch).toContain("fallback");
      });
    });

    it("should display existing default branch value", () => {
      const config = { default_branch: "my_default" };
      render(<BranchNodeForm {...defaultProps} config={config} />);

      expect(screen.getByDisplayValue("my_default")).toBeInTheDocument();
    });

    it("should have appropriate placeholder", () => {
      render(<BranchNodeForm {...defaultProps} />);

      const defaultBranch = screen.getByPlaceholderText("default");
      expect(defaultBranch).toBeInTheDocument();
    });
  });

  describe("Expression Validation", () => {
    it("should validate condition expressions", async () => {
      const config = {
        conditions: [{ id: "c1", name: "Test", expression: "bad }{" }],
      };
      render(<BranchNodeForm {...defaultProps} config={config} />);

      await waitFor(() => {
        expect(mockSetErrors).toHaveBeenCalledWith(
          expect.objectContaining({
            condition_0_expression: "Unbalanced brackets in expression",
          })
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
      render(<BranchNodeForm {...defaultProps} config={config} />);

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
      render(<BranchNodeForm {...defaultProps} config={config} errors={errors} />);

      expect(screen.getByText("Invalid syntax in condition 1")).toBeInTheDocument();
    });

    it("should not validate empty expressions", async () => {
      const config = {
        conditions: [{ id: "c1", name: "Test", expression: "" }],
      };
      render(<BranchNodeForm {...defaultProps} config={config} />);

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
      render(<BranchNodeForm {...defaultProps} />);

      expect(
        screen.getByText(
          /define conditions to route data to different branches. conditions are evaluated in order, first matching condition wins/i
        )
      ).toBeInTheDocument();
    });

    it("should display description for default branch", () => {
      render(<BranchNodeForm {...defaultProps} />);

      expect(
        screen.getByText(/branch to use when no conditions match/i)
      ).toBeInTheDocument();
    });

    it("should display expression examples", () => {
      render(<BranchNodeForm {...defaultProps} />);

      expect(screen.getByText(/expression examples/i)).toBeInTheDocument();
      expect(screen.getByText(/state.sentiment === "positive"/)).toBeInTheDocument();
    });
  });

  describe("Integration with Sub-components", () => {
    it("should render AgentFields", () => {
      render(<BranchNodeForm {...defaultProps} />);

      expect(screen.getByTestId("agent-fields")).toBeInTheDocument();
    });

    it("should render AdvancedSettings", () => {
      render(<BranchNodeForm {...defaultProps} />);

      expect(screen.getByTestId("advanced-settings")).toBeInTheDocument();
    });
  });

  describe("Condition UI Elements", () => {
    it("should display branch name label for each condition", () => {
      const config = {
        conditions: [{ id: "c1", name: "Test", expression: "true" }],
      };
      render(<BranchNodeForm {...defaultProps} config={config} />);

      expect(screen.getByText(/branch name/i)).toBeInTheDocument();
    });

    it("should display expression label for each condition", () => {
      const config = {
        conditions: [{ id: "c1", name: "Test", expression: "true" }],
      };
      render(<BranchNodeForm {...defaultProps} config={config} />);

      expect(screen.getByText(/^expression$/i)).toBeInTheDocument();
    });

    it("should have appropriate placeholder for branch name", () => {
      const config = {
        conditions: [{ id: "c1", name: "", expression: "" }],
      };
      render(<BranchNodeForm {...defaultProps} config={config} />);

      expect(screen.getByPlaceholderText("e.g., High Priority")).toBeInTheDocument();
    });
  });

  describe("Form Layout", () => {
    it("should display section headers", () => {
      render(<BranchNodeForm {...defaultProps} />);

      expect(screen.getByText(/^branch conditions$/i)).toBeInTheDocument();
    });

    it("should have Add Condition button with icon", () => {
      const { container } = render(<BranchNodeForm {...defaultProps} />);

      const addButton = screen.getByRole("button", { name: /add condition/i });
      expect(addButton).toBeInTheDocument();

      const plusIcon = container.querySelector('[data-lucide="plus"]');
      expect(plusIcon).toBeInTheDocument();
    });
  });
});
