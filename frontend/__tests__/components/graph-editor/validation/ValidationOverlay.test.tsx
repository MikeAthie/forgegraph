/**
 * Component tests for ValidationOverlay.
 *
 * Tests the validation overlay that shows indicators for missing start/output nodes
 * and handles user interactions to add those nodes.
 */

import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { ValidationOverlay } from "@/components/graph-editor/validation/ValidationOverlay";
import { ValidationErrorCode } from "@/lib/graph-validator";
import type { ValidationError } from "@/lib/graph-validator";

// Mock the ValidationContext
const mockUseValidation = jest.fn();

jest.mock("@/contexts/ValidationContext", () => ({
  useValidation: () => mockUseValidation(),
}));

describe("ValidationOverlay", () => {
  const mockOnAddStartNode = jest.fn();
  const mockOnAddOutputNode = jest.fn();

  beforeEach(() => {
    jest.clearAllMocks();
  });

  describe("Rendering - Both Requirements Met", () => {
    it("should not render when hasStartNode and hasOutputNode are both true", () => {
      mockUseValidation.mockReturnValue({
        hasStartNode: true,
        hasOutputNode: true,
        errors: [],
      });

      const { container } = render(
        <ValidationOverlay onAddStartNode={mockOnAddStartNode} onAddOutputNode={mockOnAddOutputNode} />,
      );

      expect(container.firstChild).toBeNull();
    });

    it("should not render when hasStartNode is true and no NO_OUTPUT_NODE error", () => {
      mockUseValidation.mockReturnValue({
        hasStartNode: true,
        hasOutputNode: true,
        errors: [],
      });

      const { container } = render(
        <ValidationOverlay onAddStartNode={mockOnAddStartNode} onAddOutputNode={mockOnAddOutputNode} />,
      );

      expect(container.firstChild).toBeNull();
    });
  });

  describe("Start Node Indicator", () => {
    it("should show start node indicator when hasStartNode is false and NO_START_NODE error exists", () => {
      const errors: ValidationError[] = [
        {
          code: ValidationErrorCode.NO_START_NODE,
          severity: "error",
          message: "Graph needs a start node",
        },
      ];

      mockUseValidation.mockReturnValue({
        hasStartNode: false,
        hasOutputNode: true,
        errors,
      });

      render(<ValidationOverlay onAddStartNode={mockOnAddStartNode} onAddOutputNode={mockOnAddOutputNode} />);

      expect(screen.getByText("Add Start Node")).toBeInTheDocument();
      expect(screen.getByText("Click to add entry point")).toBeInTheDocument();
    });

    it("should not show start node indicator when hasStartNode is true", () => {
      mockUseValidation.mockReturnValue({
        hasStartNode: true,
        hasOutputNode: false,
        errors: [
          {
            code: ValidationErrorCode.NO_OUTPUT_NODE,
            severity: "error",
            message: "Graph needs an output node",
          },
        ],
      });

      render(<ValidationOverlay onAddStartNode={mockOnAddStartNode} onAddOutputNode={mockOnAddOutputNode} />);

      expect(screen.queryByText("Add Start Node")).not.toBeInTheDocument();
    });

    it("should not show start node indicator when NO_START_NODE error is absent", () => {
      mockUseValidation.mockReturnValue({
        hasStartNode: false,
        hasOutputNode: true,
        errors: [],
      });

      const { container } = render(
        <ValidationOverlay onAddStartNode={mockOnAddStartNode} onAddOutputNode={mockOnAddOutputNode} />,
      );

      expect(screen.queryByText("Add Start Node")).not.toBeInTheDocument();
      expect(container.firstChild).toBeNull();
    });

    it("should position start indicator on the left side", () => {
      const errors: ValidationError[] = [
        {
          code: ValidationErrorCode.NO_START_NODE,
          severity: "error",
          message: "Graph needs a start node",
        },
      ];

      mockUseValidation.mockReturnValue({
        hasStartNode: false,
        hasOutputNode: true,
        errors,
      });

      const { container } = render(
        <ValidationOverlay onAddStartNode={mockOnAddStartNode} onAddOutputNode={mockOnAddOutputNode} />,
      );

      const indicator = container.querySelector(".left-4");
      expect(indicator).toBeInTheDocument();
    });

    it("should display alert icon for start node indicator", () => {
      const errors: ValidationError[] = [
        {
          code: ValidationErrorCode.NO_START_NODE,
          severity: "error",
          message: "Graph needs a start node",
        },
      ];

      mockUseValidation.mockReturnValue({
        hasStartNode: false,
        hasOutputNode: true,
        errors,
      });

      render(<ValidationOverlay onAddStartNode={mockOnAddStartNode} onAddOutputNode={mockOnAddOutputNode} />);

      // Alert icon should be present (using lucide-react AlertCircle)
      expect(screen.getByText("Add Start Node").closest("button")).toBeInTheDocument();
    });

    it("should apply amber styling to start node indicator", () => {
      const errors: ValidationError[] = [
        {
          code: ValidationErrorCode.NO_START_NODE,
          severity: "error",
          message: "Graph needs a start node",
        },
      ];

      mockUseValidation.mockReturnValue({
        hasStartNode: false,
        hasOutputNode: true,
        errors,
      });

      const { container } = render(
        <ValidationOverlay onAddStartNode={mockOnAddStartNode} onAddOutputNode={mockOnAddOutputNode} />,
      );

      const button = screen.getByRole("button", { name: /Add Start Node/i });
      expect(button).toHaveClass("border-amber-500/50", "bg-amber-500/10");
    });
  });

  describe("Output Node Indicator", () => {
    it("should show output node indicator when hasOutputNode is false and NO_OUTPUT_NODE error exists", () => {
      const errors: ValidationError[] = [
        {
          code: ValidationErrorCode.NO_OUTPUT_NODE,
          severity: "error",
          message: "Graph needs an output node",
        },
      ];

      mockUseValidation.mockReturnValue({
        hasStartNode: true,
        hasOutputNode: false,
        errors,
      });

      render(<ValidationOverlay onAddStartNode={mockOnAddStartNode} onAddOutputNode={mockOnAddOutputNode} />);

      expect(screen.getByText("Add Output Node")).toBeInTheDocument();
      expect(screen.getByText("Click to define result")).toBeInTheDocument();
    });

    it("should not show output node indicator when hasOutputNode is true", () => {
      mockUseValidation.mockReturnValue({
        hasStartNode: false,
        hasOutputNode: true,
        errors: [
          {
            code: ValidationErrorCode.NO_START_NODE,
            severity: "error",
            message: "Graph needs a start node",
          },
        ],
      });

      render(<ValidationOverlay onAddStartNode={mockOnAddStartNode} onAddOutputNode={mockOnAddOutputNode} />);

      expect(screen.queryByText("Add Output Node")).not.toBeInTheDocument();
    });

    it("should not show output node indicator when NO_OUTPUT_NODE error is absent", () => {
      mockUseValidation.mockReturnValue({
        hasStartNode: true,
        hasOutputNode: false,
        errors: [],
      });

      const { container } = render(
        <ValidationOverlay onAddStartNode={mockOnAddStartNode} onAddOutputNode={mockOnAddOutputNode} />,
      );

      expect(screen.queryByText("Add Output Node")).not.toBeInTheDocument();
      expect(container.firstChild).toBeNull();
    });

    it("should position output indicator on the right side", () => {
      const errors: ValidationError[] = [
        {
          code: ValidationErrorCode.NO_OUTPUT_NODE,
          severity: "error",
          message: "Graph needs an output node",
        },
      ];

      mockUseValidation.mockReturnValue({
        hasStartNode: true,
        hasOutputNode: false,
        errors,
      });

      const { container } = render(
        <ValidationOverlay onAddStartNode={mockOnAddStartNode} onAddOutputNode={mockOnAddOutputNode} />,
      );

      const indicator = container.querySelector(".right-4");
      expect(indicator).toBeInTheDocument();
    });

    it("should apply rose styling to output node indicator", () => {
      const errors: ValidationError[] = [
        {
          code: ValidationErrorCode.NO_OUTPUT_NODE,
          severity: "error",
          message: "Graph needs an output node",
        },
      ];

      mockUseValidation.mockReturnValue({
        hasStartNode: true,
        hasOutputNode: false,
        errors,
      });

      render(<ValidationOverlay onAddStartNode={mockOnAddStartNode} onAddOutputNode={mockOnAddOutputNode} />);

      const button = screen.getByRole("button", { name: /Add Output Node/i });
      expect(button).toHaveClass("border-rose-500/50", "bg-rose-500/10");
    });
  });

  describe("Both Indicators", () => {
    it("should show both indicators when both requirements are missing", () => {
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
        hasStartNode: false,
        hasOutputNode: false,
        errors,
      });

      render(<ValidationOverlay onAddStartNode={mockOnAddStartNode} onAddOutputNode={mockOnAddOutputNode} />);

      expect(screen.getByText("Add Start Node")).toBeInTheDocument();
      expect(screen.getByText("Add Output Node")).toBeInTheDocument();
    });

    it("should position both indicators correctly when both are shown", () => {
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
        hasStartNode: false,
        hasOutputNode: false,
        errors,
      });

      const { container } = render(
        <ValidationOverlay onAddStartNode={mockOnAddStartNode} onAddOutputNode={mockOnAddOutputNode} />,
      );

      expect(container.querySelector(".left-4")).toBeInTheDocument();
      expect(container.querySelector(".right-4")).toBeInTheDocument();
    });
  });

  describe("User Interactions", () => {
    it("should call onAddStartNode when start indicator is clicked", async () => {
      const user = userEvent.setup();
      const errors: ValidationError[] = [
        {
          code: ValidationErrorCode.NO_START_NODE,
          severity: "error",
          message: "Graph needs a start node",
        },
      ];

      mockUseValidation.mockReturnValue({
        hasStartNode: false,
        hasOutputNode: true,
        errors,
      });

      render(<ValidationOverlay onAddStartNode={mockOnAddStartNode} onAddOutputNode={mockOnAddOutputNode} />);

      const button = screen.getByRole("button", { name: /Add Start Node/i });
      await user.click(button);

      expect(mockOnAddStartNode).toHaveBeenCalledTimes(1);
    });

    it("should call onAddOutputNode when output indicator is clicked", async () => {
      const user = userEvent.setup();
      const errors: ValidationError[] = [
        {
          code: ValidationErrorCode.NO_OUTPUT_NODE,
          severity: "error",
          message: "Graph needs an output node",
        },
      ];

      mockUseValidation.mockReturnValue({
        hasStartNode: true,
        hasOutputNode: false,
        errors,
      });

      render(<ValidationOverlay onAddStartNode={mockOnAddStartNode} onAddOutputNode={mockOnAddOutputNode} />);

      const button = screen.getByRole("button", { name: /Add Output Node/i });
      await user.click(button);

      expect(mockOnAddOutputNode).toHaveBeenCalledTimes(1);
    });

    it("should not call handlers when callbacks are undefined", async () => {
      const user = userEvent.setup();
      const errors: ValidationError[] = [
        {
          code: ValidationErrorCode.NO_START_NODE,
          severity: "error",
          message: "Graph needs a start node",
        },
      ];

      mockUseValidation.mockReturnValue({
        hasStartNode: false,
        hasOutputNode: true,
        errors,
      });

      render(<ValidationOverlay />);

      const button = screen.getByRole("button", { name: /Add Start Node/i });
      await user.click(button);

      // Should not throw error
      expect(mockOnAddStartNode).not.toHaveBeenCalled();
    });

    it("should allow multiple clicks on start indicator", async () => {
      const user = userEvent.setup();
      const errors: ValidationError[] = [
        {
          code: ValidationErrorCode.NO_START_NODE,
          severity: "error",
          message: "Graph needs a start node",
        },
      ];

      mockUseValidation.mockReturnValue({
        hasStartNode: false,
        hasOutputNode: true,
        errors,
      });

      render(<ValidationOverlay onAddStartNode={mockOnAddStartNode} onAddOutputNode={mockOnAddOutputNode} />);

      const button = screen.getByRole("button", { name: /Add Start Node/i });
      await user.click(button);
      await user.click(button);
      await user.click(button);

      expect(mockOnAddStartNode).toHaveBeenCalledTimes(3);
    });

    it("should allow clicking both indicators independently", async () => {
      const user = userEvent.setup();
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
        hasStartNode: false,
        hasOutputNode: false,
        errors,
      });

      render(<ValidationOverlay onAddStartNode={mockOnAddStartNode} onAddOutputNode={mockOnAddOutputNode} />);

      const startButton = screen.getByRole("button", { name: /Add Start Node/i });
      const outputButton = screen.getByRole("button", { name: /Add Output Node/i });

      await user.click(startButton);
      await user.click(outputButton);

      expect(mockOnAddStartNode).toHaveBeenCalledTimes(1);
      expect(mockOnAddOutputNode).toHaveBeenCalledTimes(1);
    });
  });

  describe("Edge Cases", () => {
    it("should handle other validation errors without showing indicators", () => {
      const errors: ValidationError[] = [
        {
          code: ValidationErrorCode.CYCLE_DETECTED,
          severity: "error",
          message: "Graph contains a cycle",
        },
        {
          code: ValidationErrorCode.DISCONNECTED_NODE,
          severity: "warning",
          message: "Node is disconnected",
          nodeId: "node-1",
        },
      ];

      mockUseValidation.mockReturnValue({
        hasStartNode: true,
        hasOutputNode: true,
        errors,
      });

      const { container } = render(
        <ValidationOverlay onAddStartNode={mockOnAddStartNode} onAddOutputNode={mockOnAddOutputNode} />,
      );

      expect(container.firstChild).toBeNull();
    });

    it("should handle mixed errors showing only relevant indicators", () => {
      const errors: ValidationError[] = [
        {
          code: ValidationErrorCode.NO_START_NODE,
          severity: "error",
          message: "Graph needs a start node",
        },
        {
          code: ValidationErrorCode.CYCLE_DETECTED,
          severity: "error",
          message: "Graph contains a cycle",
        },
      ];

      mockUseValidation.mockReturnValue({
        hasStartNode: false,
        hasOutputNode: true,
        errors,
      });

      render(<ValidationOverlay onAddStartNode={mockOnAddStartNode} onAddOutputNode={mockOnAddOutputNode} />);

      expect(screen.getByText("Add Start Node")).toBeInTheDocument();
      expect(screen.queryByText("Add Output Node")).not.toBeInTheDocument();
    });

    it("should handle empty errors array", () => {
      mockUseValidation.mockReturnValue({
        hasStartNode: false,
        hasOutputNode: false,
        errors: [],
      });

      const { container } = render(
        <ValidationOverlay onAddStartNode={mockOnAddStartNode} onAddOutputNode={mockOnAddOutputNode} />,
      );

      expect(container.firstChild).toBeNull();
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
        hasStartNode: false,
        hasOutputNode: true,
        errors,
      });

      const { container } = render(
        <ValidationOverlay
          onAddStartNode={mockOnAddStartNode}
          onAddOutputNode={mockOnAddOutputNode}
          className="custom-class"
        />,
      );

      expect(container.firstChild).toHaveClass("custom-class");
    });

    it("should have pointer-events-none on overlay container", () => {
      const errors: ValidationError[] = [
        {
          code: ValidationErrorCode.NO_START_NODE,
          severity: "error",
          message: "Graph needs a start node",
        },
      ];

      mockUseValidation.mockReturnValue({
        hasStartNode: false,
        hasOutputNode: true,
        errors,
      });

      const { container } = render(
        <ValidationOverlay onAddStartNode={mockOnAddStartNode} onAddOutputNode={mockOnAddOutputNode} />,
      );

      expect(container.firstChild).toHaveClass("pointer-events-none");
    });

    it("should have pointer-events-auto on indicator buttons", () => {
      const errors: ValidationError[] = [
        {
          code: ValidationErrorCode.NO_START_NODE,
          severity: "error",
          message: "Graph needs a start node",
        },
      ];

      mockUseValidation.mockReturnValue({
        hasStartNode: false,
        hasOutputNode: true,
        errors,
      });

      const { container } = render(
        <ValidationOverlay onAddStartNode={mockOnAddStartNode} onAddOutputNode={mockOnAddOutputNode} />,
      );

      const buttonContainer = container.querySelector(".pointer-events-auto");
      expect(buttonContainer).toBeInTheDocument();
    });

    it("should center indicators vertically", () => {
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
        hasStartNode: false,
        hasOutputNode: false,
        errors,
      });

      const { container } = render(
        <ValidationOverlay onAddStartNode={mockOnAddStartNode} onAddOutputNode={mockOnAddOutputNode} />,
      );

      const indicators = container.querySelectorAll(".top-1\\/2");
      expect(indicators.length).toBe(2);
    });

    it("should apply hover effects to buttons", () => {
      const errors: ValidationError[] = [
        {
          code: ValidationErrorCode.NO_START_NODE,
          severity: "error",
          message: "Graph needs a start node",
        },
      ];

      mockUseValidation.mockReturnValue({
        hasStartNode: false,
        hasOutputNode: true,
        errors,
      });

      render(<ValidationOverlay onAddStartNode={mockOnAddStartNode} onAddOutputNode={mockOnAddOutputNode} />);

      const button = screen.getByRole("button", { name: /Add Start Node/i });
      expect(button).toHaveClass("hover:bg-amber-500/20");
    });
  });

  describe("Accessibility", () => {
    it("should render buttons with type='button'", () => {
      const errors: ValidationError[] = [
        {
          code: ValidationErrorCode.NO_START_NODE,
          severity: "error",
          message: "Graph needs a start node",
        },
      ];

      mockUseValidation.mockReturnValue({
        hasStartNode: false,
        hasOutputNode: true,
        errors,
      });

      render(<ValidationOverlay onAddStartNode={mockOnAddStartNode} onAddOutputNode={mockOnAddOutputNode} />);

      const button = screen.getByRole("button", { name: /Add Start Node/i });
      expect(button).toHaveAttribute("type", "button");
    });

    it("should have accessible button text for start indicator", () => {
      const errors: ValidationError[] = [
        {
          code: ValidationErrorCode.NO_START_NODE,
          severity: "error",
          message: "Graph needs a start node",
        },
      ];

      mockUseValidation.mockReturnValue({
        hasStartNode: false,
        hasOutputNode: true,
        errors,
      });

      render(<ValidationOverlay onAddStartNode={mockOnAddStartNode} onAddOutputNode={mockOnAddOutputNode} />);

      expect(screen.getByRole("button", { name: /Add Start Node/i })).toBeInTheDocument();
    });

    it("should have accessible button text for output indicator", () => {
      const errors: ValidationError[] = [
        {
          code: ValidationErrorCode.NO_OUTPUT_NODE,
          severity: "error",
          message: "Graph needs an output node",
        },
      ];

      mockUseValidation.mockReturnValue({
        hasStartNode: true,
        hasOutputNode: false,
        errors,
      });

      render(<ValidationOverlay onAddStartNode={mockOnAddStartNode} onAddOutputNode={mockOnAddOutputNode} />);

      expect(screen.getByRole("button", { name: /Add Output Node/i })).toBeInTheDocument();
    });
  });
});
