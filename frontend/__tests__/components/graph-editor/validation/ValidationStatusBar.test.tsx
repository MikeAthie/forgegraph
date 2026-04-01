/**
 * Component tests for ValidationStatusBar.
 *
 * Tests the status bar that shows validation errors/warnings and provides
 * quick fix actions and navigation to problematic nodes/edges.
 */

import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { ValidationStatusBar } from "@/components/graph-editor/validation/ValidationStatusBar";
import { ValidationErrorCode } from "@/lib/graph-validator";
import type { ValidationError } from "@/lib/graph-validator";

// Mock the ValidationContext
const mockUseValidation = jest.fn();

jest.mock("@/contexts/ValidationContext", () => ({
  useValidation: () => mockUseValidation(),
}));

// Mock the quick fixes utility
jest.mock("@/lib/graph-validator", () => ({
  ...jest.requireActual("@/lib/graph-validator"),
  getQuickFixesForError: jest.fn((error: ValidationError) => {
    switch (error.code) {
      case "NO_START_NODE":
        return [
          {
            errorCode: error.code,
            label: "Add Start",
            description: "Mark the first node as the entry point",
          },
        ];
      case "NO_OUTPUT_NODE":
        return [
          {
            errorCode: error.code,
            label: "Add Output",
            description: "Add an Output node to define the result",
          },
        ];
      case "DISCONNECTED_NODE":
        return [
          {
            errorCode: error.code,
            label: "Connect",
            description: "Connect this node to the workflow",
          },
          {
            errorCode: error.code,
            label: "Remove",
            description: "Remove this disconnected node",
          },
        ];
      default:
        return [];
    }
  }),
}));

describe("ValidationStatusBar", () => {
  const mockOnFocusNode = jest.fn();
  const mockOnFocusEdge = jest.fn();
  const mockOnQuickFix = jest.fn();
  const mockSetStatusBarExpanded = jest.fn();

  beforeEach(() => {
    jest.clearAllMocks();
  });

  describe("Valid State", () => {
    it("should show green 'Graph Valid' status when isValid and no issues", () => {
      mockUseValidation.mockReturnValue({
        isValid: true,
        errors: [],
        warnings: [],
        isStatusBarExpanded: false,
        setStatusBarExpanded: mockSetStatusBarExpanded,
      });

      render(
        <ValidationStatusBar onFocusNode={mockOnFocusNode} onFocusEdge={mockOnFocusEdge} onQuickFix={mockOnQuickFix} />,
      );

      expect(screen.getByText("Graph Valid")).toBeInTheDocument();
    });

    it("should apply emerald styling when graph is valid", () => {
      mockUseValidation.mockReturnValue({
        isValid: true,
        errors: [],
        warnings: [],
        isStatusBarExpanded: false,
        setStatusBarExpanded: mockSetStatusBarExpanded,
      });

      const { container } = render(
        <ValidationStatusBar onFocusNode={mockOnFocusNode} onFocusEdge={mockOnFocusEdge} onQuickFix={mockOnQuickFix} />,
      );

      const statusBar = container.firstChild;
      expect(statusBar).toHaveClass("bg-emerald-500/10", "border-emerald-500/30");
    });

    it("should not be expandable when graph is valid", () => {
      mockUseValidation.mockReturnValue({
        isValid: true,
        errors: [],
        warnings: [],
        isStatusBarExpanded: false,
        setStatusBarExpanded: mockSetStatusBarExpanded,
      });

      render(
        <ValidationStatusBar onFocusNode={mockOnFocusNode} onFocusEdge={mockOnFocusEdge} onQuickFix={mockOnQuickFix} />,
      );

      expect(screen.queryByText("Show details")).not.toBeInTheDocument();
      expect(screen.queryByText("Hide details")).not.toBeInTheDocument();
    });
  });

  describe("Error State", () => {
    it("should show error count with red styling when errors exist", () => {
      const errors: ValidationError[] = [
        {
          code: ValidationErrorCode.NO_START_NODE,
          severity: "error",
          message: "Graph needs a start node",
        },
        {
          code: ValidationErrorCode.NO_OUTPUT_NODE,
          severity: "error",
          message: "Graph needs an output node",
        },
      ];

      mockUseValidation.mockReturnValue({
        isValid: false,
        errors,
        warnings: [],
        isStatusBarExpanded: false,
        setStatusBarExpanded: mockSetStatusBarExpanded,
      });

      render(
        <ValidationStatusBar onFocusNode={mockOnFocusNode} onFocusEdge={mockOnFocusEdge} onQuickFix={mockOnQuickFix} />,
      );

      expect(screen.getByText("2 errors")).toBeInTheDocument();
    });

    it("should show singular 'error' text when only one error", () => {
      const errors: ValidationError[] = [
        {
          code: ValidationErrorCode.NO_START_NODE,
          severity: "error",
          message: "Graph needs a start node",
        },
      ];

      mockUseValidation.mockReturnValue({
        isValid: false,
        errors,
        warnings: [],
        isStatusBarExpanded: false,
        setStatusBarExpanded: mockSetStatusBarExpanded,
      });

      render(
        <ValidationStatusBar onFocusNode={mockOnFocusNode} onFocusEdge={mockOnFocusEdge} onQuickFix={mockOnQuickFix} />,
      );

      expect(screen.getByText("1 error")).toBeInTheDocument();
    });

    it("should apply destructive styling when errors exist", () => {
      const errors: ValidationError[] = [
        {
          code: ValidationErrorCode.CYCLE_DETECTED,
          severity: "error",
          message: "Graph contains a cycle",
        },
      ];

      mockUseValidation.mockReturnValue({
        isValid: false,
        errors,
        warnings: [],
        isStatusBarExpanded: false,
        setStatusBarExpanded: mockSetStatusBarExpanded,
      });

      const { container } = render(
        <ValidationStatusBar onFocusNode={mockOnFocusNode} onFocusEdge={mockOnFocusEdge} onQuickFix={mockOnQuickFix} />,
      );

      expect(container.querySelector(".border-destructive\\/50")).toBeInTheDocument();
      expect(container.querySelector(".bg-destructive\\/10")).toBeInTheDocument();
    });

    it("should show warning count alongside error count", () => {
      const errors: ValidationError[] = [
        {
          code: ValidationErrorCode.NO_START_NODE,
          severity: "error",
          message: "Graph needs a start node",
        },
      ];

      const warnings: ValidationError[] = [
        {
          code: ValidationErrorCode.DISCONNECTED_NODE,
          severity: "warning",
          message: "Node is disconnected",
          nodeId: "node-1",
        },
        {
          code: ValidationErrorCode.DISCONNECTED_NODE,
          severity: "warning",
          message: "Node is disconnected",
          nodeId: "node-2",
        },
      ];

      mockUseValidation.mockReturnValue({
        isValid: false,
        errors,
        warnings,
        isStatusBarExpanded: false,
        setStatusBarExpanded: mockSetStatusBarExpanded,
      });

      render(
        <ValidationStatusBar onFocusNode={mockOnFocusNode} onFocusEdge={mockOnFocusEdge} onQuickFix={mockOnQuickFix} />,
      );

      expect(screen.getByText("1 error")).toBeInTheDocument();
      expect(screen.getByText("(2 warnings)")).toBeInTheDocument();
    });
  });

  describe("Warning State", () => {
    it("should show warning count with amber styling when only warnings exist", () => {
      const warnings: ValidationError[] = [
        {
          code: ValidationErrorCode.DISCONNECTED_NODE,
          severity: "warning",
          message: "Node is disconnected",
          nodeId: "node-1",
        },
      ];

      mockUseValidation.mockReturnValue({
        isValid: true,
        errors: [],
        warnings,
        isStatusBarExpanded: false,
        setStatusBarExpanded: mockSetStatusBarExpanded,
      });

      render(
        <ValidationStatusBar onFocusNode={mockOnFocusNode} onFocusEdge={mockOnFocusEdge} onQuickFix={mockOnQuickFix} />,
      );

      expect(screen.getByText("1 warning")).toBeInTheDocument();
    });

    it("should show plural 'warnings' text when multiple warnings", () => {
      const warnings: ValidationError[] = [
        {
          code: ValidationErrorCode.DISCONNECTED_NODE,
          severity: "warning",
          message: "Node A is disconnected",
          nodeId: "node-1",
        },
        {
          code: ValidationErrorCode.DISCONNECTED_NODE,
          severity: "warning",
          message: "Node B is disconnected",
          nodeId: "node-2",
        },
      ];

      mockUseValidation.mockReturnValue({
        isValid: true,
        errors: [],
        warnings,
        isStatusBarExpanded: false,
        setStatusBarExpanded: mockSetStatusBarExpanded,
      });

      render(
        <ValidationStatusBar onFocusNode={mockOnFocusNode} onFocusEdge={mockOnFocusEdge} onQuickFix={mockOnQuickFix} />,
      );

      expect(screen.getByText("2 warnings")).toBeInTheDocument();
    });

    it("should apply amber styling when only warnings exist", () => {
      const warnings: ValidationError[] = [
        {
          code: ValidationErrorCode.DISCONNECTED_NODE,
          severity: "warning",
          message: "Node is disconnected",
          nodeId: "node-1",
        },
      ];

      mockUseValidation.mockReturnValue({
        isValid: true,
        errors: [],
        warnings,
        isStatusBarExpanded: false,
        setStatusBarExpanded: mockSetStatusBarExpanded,
      });

      const { container } = render(
        <ValidationStatusBar onFocusNode={mockOnFocusNode} onFocusEdge={mockOnFocusEdge} onQuickFix={mockOnQuickFix} />,
      );

      expect(container.querySelector(".border-amber-500\\/50")).toBeInTheDocument();
      expect(container.querySelector(".bg-amber-500\\/10")).toBeInTheDocument();
    });
  });

  describe("Expandable Behavior", () => {
    it("should show 'Show details' when collapsed", () => {
      const errors: ValidationError[] = [
        {
          code: ValidationErrorCode.NO_START_NODE,
          severity: "error",
          message: "Graph needs a start node",
        },
      ];

      mockUseValidation.mockReturnValue({
        isValid: false,
        errors,
        warnings: [],
        isStatusBarExpanded: false,
        setStatusBarExpanded: mockSetStatusBarExpanded,
      });

      render(
        <ValidationStatusBar onFocusNode={mockOnFocusNode} onFocusEdge={mockOnFocusEdge} onQuickFix={mockOnQuickFix} />,
      );

      expect(screen.getByText("Show details")).toBeInTheDocument();
    });

    it("should show 'Hide details' when expanded", () => {
      const errors: ValidationError[] = [
        {
          code: ValidationErrorCode.NO_START_NODE,
          severity: "error",
          message: "Graph needs a start node",
        },
      ];

      mockUseValidation.mockReturnValue({
        isValid: false,
        errors,
        warnings: [],
        isStatusBarExpanded: true,
        setStatusBarExpanded: mockSetStatusBarExpanded,
      });

      render(
        <ValidationStatusBar onFocusNode={mockOnFocusNode} onFocusEdge={mockOnFocusEdge} onQuickFix={mockOnQuickFix} />,
      );

      expect(screen.getByText("Hide details")).toBeInTheDocument();
    });

    it("should call setStatusBarExpanded when summary bar is clicked", async () => {
      const user = userEvent.setup();
      const errors: ValidationError[] = [
        {
          code: ValidationErrorCode.NO_START_NODE,
          severity: "error",
          message: "Graph needs a start node",
        },
      ];

      mockUseValidation.mockReturnValue({
        isValid: false,
        errors,
        warnings: [],
        isStatusBarExpanded: false,
        setStatusBarExpanded: mockSetStatusBarExpanded,
      });

      render(
        <ValidationStatusBar onFocusNode={mockOnFocusNode} onFocusEdge={mockOnFocusEdge} onQuickFix={mockOnQuickFix} />,
      );

      const button = screen.getByRole("button", { name: /1 error.*Show details/i });
      await user.click(button);

      expect(mockSetStatusBarExpanded).toHaveBeenCalledTimes(1);
      expect(mockSetStatusBarExpanded).toHaveBeenCalledWith(true);
    });

    it("should toggle expansion state on multiple clicks", async () => {
      const user = userEvent.setup();
      const errors: ValidationError[] = [
        {
          code: ValidationErrorCode.NO_START_NODE,
          severity: "error",
          message: "Graph needs a start node",
        },
      ];

      mockUseValidation.mockReturnValue({
        isValid: false,
        errors,
        warnings: [],
        isStatusBarExpanded: false,
        setStatusBarExpanded: mockSetStatusBarExpanded,
      });

      const { rerender } = render(
        <ValidationStatusBar onFocusNode={mockOnFocusNode} onFocusEdge={mockOnFocusEdge} onQuickFix={mockOnQuickFix} />,
      );

      const button = screen.getByRole("button", { name: /1 error.*Show details/i });
      await user.click(button);

      expect(mockSetStatusBarExpanded).toHaveBeenCalledWith(true);

      // Simulate expanded state
      mockUseValidation.mockReturnValue({
        isValid: false,
        errors,
        warnings: [],
        isStatusBarExpanded: true,
        setStatusBarExpanded: mockSetStatusBarExpanded,
      });

      rerender(
        <ValidationStatusBar onFocusNode={mockOnFocusNode} onFocusEdge={mockOnFocusEdge} onQuickFix={mockOnQuickFix} />,
      );

      const expandedButton = screen.getByRole("button", { name: /1 error.*Hide details/i });
      await user.click(expandedButton);

      expect(mockSetStatusBarExpanded).toHaveBeenCalledWith(false);
    });
  });

  describe("Error List Display", () => {
    it("should show error list when expanded", () => {
      const errors: ValidationError[] = [
        {
          code: ValidationErrorCode.NO_START_NODE,
          severity: "error",
          message: "Graph needs a start node",
          suggestion: "Mark a node as the entry point or add an edge from START",
        },
        {
          code: ValidationErrorCode.NO_OUTPUT_NODE,
          severity: "error",
          message: "Graph needs an output node",
          suggestion: "Add an Output node to define the workflow result",
        },
      ];

      mockUseValidation.mockReturnValue({
        isValid: false,
        errors,
        warnings: [],
        isStatusBarExpanded: true,
        setStatusBarExpanded: mockSetStatusBarExpanded,
      });

      render(
        <ValidationStatusBar onFocusNode={mockOnFocusNode} onFocusEdge={mockOnFocusEdge} onQuickFix={mockOnQuickFix} />,
      );

      expect(screen.getByText("Graph needs a start node")).toBeInTheDocument();
      expect(screen.getByText("Graph needs an output node")).toBeInTheDocument();
    });

    it("should not show error list when collapsed", () => {
      const errors: ValidationError[] = [
        {
          code: ValidationErrorCode.NO_START_NODE,
          severity: "error",
          message: "Graph needs a start node",
        },
      ];

      mockUseValidation.mockReturnValue({
        isValid: false,
        errors,
        warnings: [],
        isStatusBarExpanded: false,
        setStatusBarExpanded: mockSetStatusBarExpanded,
      });

      render(
        <ValidationStatusBar onFocusNode={mockOnFocusNode} onFocusEdge={mockOnFocusEdge} onQuickFix={mockOnQuickFix} />,
      );

      expect(screen.queryByText("Graph needs a start node")).not.toBeInTheDocument();
    });

    it("should display error messages", () => {
      const errors: ValidationError[] = [
        {
          code: ValidationErrorCode.CYCLE_DETECTED,
          severity: "error",
          message: "Graph contains a cycle",
        },
      ];

      mockUseValidation.mockReturnValue({
        isValid: false,
        errors,
        warnings: [],
        isStatusBarExpanded: true,
        setStatusBarExpanded: mockSetStatusBarExpanded,
      });

      render(
        <ValidationStatusBar onFocusNode={mockOnFocusNode} onFocusEdge={mockOnFocusEdge} onQuickFix={mockOnQuickFix} />,
      );

      expect(screen.getByText("Graph contains a cycle")).toBeInTheDocument();
    });

    it("should display error suggestions when provided", () => {
      const errors: ValidationError[] = [
        {
          code: ValidationErrorCode.NO_START_NODE,
          severity: "error",
          message: "Graph needs a start node",
          suggestion: "Mark a node as the entry point",
        },
      ];

      mockUseValidation.mockReturnValue({
        isValid: false,
        errors,
        warnings: [],
        isStatusBarExpanded: true,
        setStatusBarExpanded: mockSetStatusBarExpanded,
      });

      render(
        <ValidationStatusBar onFocusNode={mockOnFocusNode} onFocusEdge={mockOnFocusEdge} onQuickFix={mockOnQuickFix} />,
      );

      expect(screen.getByText("Mark a node as the entry point")).toBeInTheDocument();
    });

    it("should display warnings after errors", () => {
      const errors: ValidationError[] = [
        {
          code: ValidationErrorCode.NO_START_NODE,
          severity: "error",
          message: "Error message",
        },
      ];

      const warnings: ValidationError[] = [
        {
          code: ValidationErrorCode.DISCONNECTED_NODE,
          severity: "warning",
          message: "Warning message",
          nodeId: "node-1",
        },
      ];

      mockUseValidation.mockReturnValue({
        isValid: false,
        errors,
        warnings,
        isStatusBarExpanded: true,
        setStatusBarExpanded: mockSetStatusBarExpanded,
      });

      render(
        <ValidationStatusBar onFocusNode={mockOnFocusNode} onFocusEdge={mockOnFocusEdge} onQuickFix={mockOnQuickFix} />,
      );

      expect(screen.getByText("Error message")).toBeInTheDocument();
      expect(screen.getByText("Warning message")).toBeInTheDocument();
    });

    it("should use destructive text color for errors", () => {
      const errors: ValidationError[] = [
        {
          code: ValidationErrorCode.CYCLE_DETECTED,
          severity: "error",
          message: "Graph contains a cycle",
        },
      ];

      mockUseValidation.mockReturnValue({
        isValid: false,
        errors,
        warnings: [],
        isStatusBarExpanded: true,
        setStatusBarExpanded: mockSetStatusBarExpanded,
      });

      render(
        <ValidationStatusBar onFocusNode={mockOnFocusNode} onFocusEdge={mockOnFocusEdge} onQuickFix={mockOnQuickFix} />,
      );

      const errorText = screen.getByText("Graph contains a cycle");
      expect(errorText).toHaveClass("text-destructive");
    });

    it("should use amber text color for warnings", () => {
      const warnings: ValidationError[] = [
        {
          code: ValidationErrorCode.DISCONNECTED_NODE,
          severity: "warning",
          message: "Node is disconnected",
          nodeId: "node-1",
        },
      ];

      mockUseValidation.mockReturnValue({
        isValid: true,
        errors: [],
        warnings,
        isStatusBarExpanded: true,
        setStatusBarExpanded: mockSetStatusBarExpanded,
      });

      render(
        <ValidationStatusBar onFocusNode={mockOnFocusNode} onFocusEdge={mockOnFocusEdge} onQuickFix={mockOnQuickFix} />,
      );

      const warningText = screen.getByText("Node is disconnected");
      expect(warningText).toHaveClass("text-amber-600");
    });
  });

  describe("Go To Button", () => {
    it("should show 'Go to' button when error has nodeId", () => {
      const errors: ValidationError[] = [
        {
          code: ValidationErrorCode.DISCONNECTED_NODE,
          severity: "error",
          message: "Node is disconnected",
          nodeId: "node-1",
        },
      ];

      mockUseValidation.mockReturnValue({
        isValid: false,
        errors,
        warnings: [],
        isStatusBarExpanded: true,
        setStatusBarExpanded: mockSetStatusBarExpanded,
      });

      render(
        <ValidationStatusBar onFocusNode={mockOnFocusNode} onFocusEdge={mockOnFocusEdge} onQuickFix={mockOnQuickFix} />,
      );

      expect(screen.getByText("Go to")).toBeInTheDocument();
    });

    it("should show 'Go to' button when error has edgeId", () => {
      const errors: ValidationError[] = [
        {
          code: ValidationErrorCode.SELF_CONNECTION,
          severity: "error",
          message: "Self connection detected",
          edgeId: "edge-1",
        },
      ];

      mockUseValidation.mockReturnValue({
        isValid: false,
        errors,
        warnings: [],
        isStatusBarExpanded: true,
        setStatusBarExpanded: mockSetStatusBarExpanded,
      });

      render(
        <ValidationStatusBar onFocusNode={mockOnFocusNode} onFocusEdge={mockOnFocusEdge} onQuickFix={mockOnQuickFix} />,
      );

      expect(screen.getByText("Go to")).toBeInTheDocument();
    });

    it("should not show 'Go to' button when error has neither nodeId nor edgeId", () => {
      const errors: ValidationError[] = [
        {
          code: ValidationErrorCode.CYCLE_DETECTED,
          severity: "error",
          message: "Graph contains a cycle",
        },
      ];

      mockUseValidation.mockReturnValue({
        isValid: false,
        errors,
        warnings: [],
        isStatusBarExpanded: true,
        setStatusBarExpanded: mockSetStatusBarExpanded,
      });

      render(
        <ValidationStatusBar onFocusNode={mockOnFocusNode} onFocusEdge={mockOnFocusEdge} onQuickFix={mockOnQuickFix} />,
      );

      expect(screen.queryByText("Go to")).not.toBeInTheDocument();
    });

    it("should call onFocusNode when 'Go to' is clicked for node error", async () => {
      const user = userEvent.setup();
      const errors: ValidationError[] = [
        {
          code: ValidationErrorCode.DISCONNECTED_NODE,
          severity: "error",
          message: "Node is disconnected",
          nodeId: "node-123",
        },
      ];

      mockUseValidation.mockReturnValue({
        isValid: false,
        errors,
        warnings: [],
        isStatusBarExpanded: true,
        setStatusBarExpanded: mockSetStatusBarExpanded,
      });

      render(
        <ValidationStatusBar onFocusNode={mockOnFocusNode} onFocusEdge={mockOnFocusEdge} onQuickFix={mockOnQuickFix} />,
      );

      const goToButton = screen.getByText("Go to");
      await user.click(goToButton);

      expect(mockOnFocusNode).toHaveBeenCalledTimes(1);
      expect(mockOnFocusNode).toHaveBeenCalledWith("node-123");
    });

    it("should call onFocusEdge when 'Go to' is clicked for edge error", async () => {
      const user = userEvent.setup();
      const errors: ValidationError[] = [
        {
          code: ValidationErrorCode.SELF_CONNECTION,
          severity: "error",
          message: "Self connection detected",
          edgeId: "edge-456",
        },
      ];

      mockUseValidation.mockReturnValue({
        isValid: false,
        errors,
        warnings: [],
        isStatusBarExpanded: true,
        setStatusBarExpanded: mockSetStatusBarExpanded,
      });

      render(
        <ValidationStatusBar onFocusNode={mockOnFocusNode} onFocusEdge={mockOnFocusEdge} onQuickFix={mockOnQuickFix} />,
      );

      const goToButton = screen.getByText("Go to");
      await user.click(goToButton);

      expect(mockOnFocusEdge).toHaveBeenCalledTimes(1);
      expect(mockOnFocusEdge).toHaveBeenCalledWith("edge-456");
    });

    it("should prioritize nodeId over edgeId when both exist", async () => {
      const user = userEvent.setup();
      const errors: ValidationError[] = [
        {
          code: ValidationErrorCode.DISCONNECTED_NODE,
          severity: "error",
          message: "Issue with connection",
          nodeId: "node-123",
          edgeId: "edge-456",
        },
      ];

      mockUseValidation.mockReturnValue({
        isValid: false,
        errors,
        warnings: [],
        isStatusBarExpanded: true,
        setStatusBarExpanded: mockSetStatusBarExpanded,
      });

      render(
        <ValidationStatusBar onFocusNode={mockOnFocusNode} onFocusEdge={mockOnFocusEdge} onQuickFix={mockOnQuickFix} />,
      );

      const goToButton = screen.getByText("Go to");
      await user.click(goToButton);

      expect(mockOnFocusNode).toHaveBeenCalledWith("node-123");
      expect(mockOnFocusEdge).not.toHaveBeenCalled();
    });
  });

  describe("Quick Fix Buttons", () => {
    it("should show quick fix buttons for errors with fixes", () => {
      const errors: ValidationError[] = [
        {
          code: ValidationErrorCode.NO_START_NODE,
          severity: "error",
          message: "Graph needs a start node",
        },
      ];

      mockUseValidation.mockReturnValue({
        isValid: false,
        errors,
        warnings: [],
        isStatusBarExpanded: true,
        setStatusBarExpanded: mockSetStatusBarExpanded,
      });

      render(
        <ValidationStatusBar onFocusNode={mockOnFocusNode} onFocusEdge={mockOnFocusEdge} onQuickFix={mockOnQuickFix} />,
      );

      expect(screen.getByText("Add Start")).toBeInTheDocument();
    });

    it("should show multiple quick fix buttons when available", () => {
      const errors: ValidationError[] = [
        {
          code: ValidationErrorCode.DISCONNECTED_NODE,
          severity: "error",
          message: "Node is disconnected",
          nodeId: "node-1",
        },
      ];

      mockUseValidation.mockReturnValue({
        isValid: false,
        errors,
        warnings: [],
        isStatusBarExpanded: true,
        setStatusBarExpanded: mockSetStatusBarExpanded,
      });

      render(
        <ValidationStatusBar onFocusNode={mockOnFocusNode} onFocusEdge={mockOnFocusEdge} onQuickFix={mockOnQuickFix} />,
      );

      expect(screen.getByText("Connect")).toBeInTheDocument();
      expect(screen.getByText("Remove")).toBeInTheDocument();
    });

    it("should call onQuickFix when quick fix button is clicked", async () => {
      const user = userEvent.setup();
      const errors: ValidationError[] = [
        {
          code: ValidationErrorCode.NO_OUTPUT_NODE,
          severity: "error",
          message: "Graph needs an output node",
        },
      ];

      mockUseValidation.mockReturnValue({
        isValid: false,
        errors,
        warnings: [],
        isStatusBarExpanded: true,
        setStatusBarExpanded: mockSetStatusBarExpanded,
      });

      render(
        <ValidationStatusBar onFocusNode={mockOnFocusNode} onFocusEdge={mockOnFocusEdge} onQuickFix={mockOnQuickFix} />,
      );

      const quickFixButton = screen.getByText("Add Output");
      await user.click(quickFixButton);

      expect(mockOnQuickFix).toHaveBeenCalledTimes(1);
      expect(mockOnQuickFix).toHaveBeenCalledWith(errors[0], "Add Output");
    });

    it("should not show quick fix buttons for errors without fixes", () => {
      const errors: ValidationError[] = [
        {
          code: ValidationErrorCode.CYCLE_DETECTED,
          severity: "error",
          message: "Graph contains a cycle",
        },
      ];

      mockUseValidation.mockReturnValue({
        isValid: false,
        errors,
        warnings: [],
        isStatusBarExpanded: true,
        setStatusBarExpanded: mockSetStatusBarExpanded,
      });

      render(
        <ValidationStatusBar onFocusNode={mockOnFocusNode} onFocusEdge={mockOnFocusEdge} onQuickFix={mockOnQuickFix} />,
      );

      // Should only have "Go to" button if nodeId/edgeId present, no quick fix buttons
      expect(screen.queryByText("Add Start")).not.toBeInTheDocument();
      expect(screen.queryByText("Add Output")).not.toBeInTheDocument();
      expect(screen.queryByText("Connect")).not.toBeInTheDocument();
    });
  });

  describe("Edge Cases", () => {
    it("should handle empty errors and warnings array", () => {
      mockUseValidation.mockReturnValue({
        isValid: true,
        errors: [],
        warnings: [],
        isStatusBarExpanded: false,
        setStatusBarExpanded: mockSetStatusBarExpanded,
      });

      render(
        <ValidationStatusBar onFocusNode={mockOnFocusNode} onFocusEdge={mockOnFocusEdge} onQuickFix={mockOnQuickFix} />,
      );

      expect(screen.getByText("Graph Valid")).toBeInTheDocument();
    });

    it("should handle undefined callback props", () => {
      const errors: ValidationError[] = [
        {
          code: ValidationErrorCode.NO_START_NODE,
          severity: "error",
          message: "Graph needs a start node",
        },
      ];

      mockUseValidation.mockReturnValue({
        isValid: false,
        errors,
        warnings: [],
        isStatusBarExpanded: true,
        setStatusBarExpanded: mockSetStatusBarExpanded,
      });

      render(<ValidationStatusBar />);

      expect(screen.getByText("Graph needs a start node")).toBeInTheDocument();
    });

    it("should handle errors without suggestions", () => {
      const errors: ValidationError[] = [
        {
          code: ValidationErrorCode.CYCLE_DETECTED,
          severity: "error",
          message: "Graph contains a cycle",
        },
      ];

      mockUseValidation.mockReturnValue({
        isValid: false,
        errors,
        warnings: [],
        isStatusBarExpanded: true,
        setStatusBarExpanded: mockSetStatusBarExpanded,
      });

      render(
        <ValidationStatusBar onFocusNode={mockOnFocusNode} onFocusEdge={mockOnFocusEdge} onQuickFix={mockOnQuickFix} />,
      );

      expect(screen.getByText("Graph contains a cycle")).toBeInTheDocument();
    });

    it("should handle large number of errors", () => {
      const errors: ValidationError[] = Array.from({ length: 10 }, (_, i) => ({
        code: ValidationErrorCode.DISCONNECTED_NODE,
        severity: "error" as const,
        message: `Node ${i} is disconnected`,
        nodeId: `node-${i}`,
      }));

      mockUseValidation.mockReturnValue({
        isValid: false,
        errors,
        warnings: [],
        isStatusBarExpanded: true,
        setStatusBarExpanded: mockSetStatusBarExpanded,
      });

      render(
        <ValidationStatusBar onFocusNode={mockOnFocusNode} onFocusEdge={mockOnFocusEdge} onQuickFix={mockOnQuickFix} />,
      );

      expect(screen.getByText("10 errors")).toBeInTheDocument();
      errors.forEach((error) => {
        expect(screen.getByText(error.message)).toBeInTheDocument();
      });
    });
  });

  describe("Styling and Layout", () => {
    it("should apply custom className when provided", () => {
      const errors: ValidationError[] = [
        {
          code: ValidationErrorCode.NO_START_NODE,
          severity: "error",
          message: "Graph needs a start node",
        },
      ];

      mockUseValidation.mockReturnValue({
        isValid: false,
        errors,
        warnings: [],
        isStatusBarExpanded: false,
        setStatusBarExpanded: mockSetStatusBarExpanded,
      });

      const { container } = render(
        <ValidationStatusBar
          onFocusNode={mockOnFocusNode}
          onFocusEdge={mockOnFocusEdge}
          onQuickFix={mockOnQuickFix}
          className="custom-status-bar"
        />,
      );

      expect(container.firstChild).toHaveClass("custom-status-bar");
    });

    it("should apply max-height and scrolling to error list", () => {
      const errors: ValidationError[] = [
        {
          code: ValidationErrorCode.NO_START_NODE,
          severity: "error",
          message: "Graph needs a start node",
        },
      ];

      mockUseValidation.mockReturnValue({
        isValid: false,
        errors,
        warnings: [],
        isStatusBarExpanded: true,
        setStatusBarExpanded: mockSetStatusBarExpanded,
      });

      const { container } = render(
        <ValidationStatusBar onFocusNode={mockOnFocusNode} onFocusEdge={mockOnFocusEdge} onQuickFix={mockOnQuickFix} />,
      );

      const errorList = container.querySelector(".max-h-48");
      expect(errorList).toBeInTheDocument();
      expect(errorList).toHaveClass("overflow-y-auto");
    });

    it("should apply border-t class to status bar", () => {
      const errors: ValidationError[] = [
        {
          code: ValidationErrorCode.NO_START_NODE,
          severity: "error",
          message: "Graph needs a start node",
        },
      ];

      mockUseValidation.mockReturnValue({
        isValid: false,
        errors,
        warnings: [],
        isStatusBarExpanded: false,
        setStatusBarExpanded: mockSetStatusBarExpanded,
      });

      const { container } = render(
        <ValidationStatusBar onFocusNode={mockOnFocusNode} onFocusEdge={mockOnFocusEdge} onQuickFix={mockOnQuickFix} />,
      );

      expect(container.firstChild).toHaveClass("border-t");
    });
  });

  describe("Accessibility", () => {
    it("should have accessible button for summary bar", () => {
      const errors: ValidationError[] = [
        {
          code: ValidationErrorCode.NO_START_NODE,
          severity: "error",
          message: "Graph needs a start node",
        },
      ];

      mockUseValidation.mockReturnValue({
        isValid: false,
        errors,
        warnings: [],
        isStatusBarExpanded: false,
        setStatusBarExpanded: mockSetStatusBarExpanded,
      });

      render(
        <ValidationStatusBar onFocusNode={mockOnFocusNode} onFocusEdge={mockOnFocusEdge} onQuickFix={mockOnQuickFix} />,
      );

      const button = screen.getByRole("button", { name: /1 error.*Show details/i });
      expect(button).toHaveAttribute("type", "button");
    });

    it("should have accessible quick fix buttons with title attributes", () => {
      const errors: ValidationError[] = [
        {
          code: ValidationErrorCode.NO_START_NODE,
          severity: "error",
          message: "Graph needs a start node",
        },
      ];

      mockUseValidation.mockReturnValue({
        isValid: false,
        errors,
        warnings: [],
        isStatusBarExpanded: true,
        setStatusBarExpanded: mockSetStatusBarExpanded,
      });

      render(
        <ValidationStatusBar onFocusNode={mockOnFocusNode} onFocusEdge={mockOnFocusEdge} onQuickFix={mockOnQuickFix} />,
      );

      const quickFixButton = screen.getByText("Add Start");
      expect(quickFixButton.closest("button")).toHaveAttribute("title", "Mark the first node as the entry point");
    });
  });
});
