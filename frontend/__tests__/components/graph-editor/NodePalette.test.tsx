/**
 * Component tests for NodePalette.
 *
 * Tests node type rendering, enabled/disabled states, and click handlers.
 */

import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { NodePalette } from "@/components/graph-editor/NodePalette";
import { NODE_TYPES, PHASE2_NODE_TYPES } from "@/lib/graph-types";

describe("NodePalette", () => {
  const mockOnAddNode = jest.fn();

  beforeEach(() => {
    jest.clearAllMocks();
  });

  describe("Rendering", () => {
    it("should render palette header", () => {
      render(<NodePalette onAddNode={mockOnAddNode} />);

      expect(screen.getByText("Nodes")).toBeInTheDocument();
    });

    it("should render search input with correct placeholder", () => {
      render(<NodePalette onAddNode={mockOnAddNode} />);

      const searchInput = screen.getByPlaceholderText("Search tools...");
      expect(searchInput).toBeInTheDocument();
    });

    it("should render all node types from PHASE2_NODE_TYPES", () => {
      render(<NodePalette onAddNode={mockOnAddNode} />);

      PHASE2_NODE_TYPES.forEach((nodeType) => {
        expect(
          screen.getAllByRole("button", { name: new RegExp(`^${nodeType.label}$`, "i") })
            .length
        ).toBeGreaterThan(0);
      });
    });

    it("should render enabled node types with proper styling", () => {
      render(<NodePalette onAddNode={mockOnAddNode} />);

      const enabledNodeTypes = PHASE2_NODE_TYPES.filter((nt) => nt.enabled);

      enabledNodeTypes.forEach((nodeType) => {
        const button = screen.getByRole("button", { name: new RegExp(`^${nodeType.label}$`, "i") });
        expect(button).not.toBeDisabled();
        expect(button).toHaveClass("cursor-pointer");
      });
    });

    it("should render disabled node types with proper styling and label", () => {
      render(<NodePalette onAddNode={mockOnAddNode} />);

      const disabledNodeTypes = PHASE2_NODE_TYPES.filter((nt) => !nt.enabled);

      disabledNodeTypes.forEach((nodeType) => {
        const buttons = screen.getAllByRole("button", { name: new RegExp(`^${nodeType.label}$`, "i") });
        // Should find at least one button with this name
        expect(buttons.length).toBeGreaterThan(0);
        // All matching buttons should be disabled
        buttons.forEach((button) => {
          expect(button).toBeDisabled();
          expect(button).toHaveClass("cursor-not-allowed");
        });
      });

      // Should show "Soon" label for disabled nodes
      if (disabledNodeTypes.length > 0) {
        expect(screen.getAllByText("Soon").length).toBeGreaterThan(0);
      } else {
        expect(screen.queryByText("Soon")).not.toBeInTheDocument();
      }
    });
  });

  describe("Enabled Node Types", () => {
    it("should render Prompt node type as enabled", () => {
      render(<NodePalette onAddNode={mockOnAddNode} />);

      const promptButton = screen.getByRole("button", { name: /^prompt$/i });
      expect(promptButton).not.toBeDisabled();
    });

    it("should render HTTP node type as enabled", () => {
      render(<NodePalette onAddNode={mockOnAddNode} />);

      const httpButton = screen.getByRole("button", { name: /^http$/i });
      expect(httpButton).not.toBeDisabled();
    });

    it("should render Transform node type as enabled", () => {
      render(<NodePalette onAddNode={mockOnAddNode} />);

      const transformButton = screen.getByRole("button", { name: /^transform$/i });
      expect(transformButton).not.toBeDisabled();
    });

    it("should render Output node type as enabled", () => {
      render(<NodePalette onAddNode={mockOnAddNode} />);

      const outputButton = screen.getByRole("button", { name: /^output$/i });
      expect(outputButton).not.toBeDisabled();
    });

    it("should render Branch node type as enabled", () => {
      render(<NodePalette onAddNode={mockOnAddNode} />);

      const branchButton = screen.getByRole("button", { name: /^branch$/i });
      expect(branchButton).not.toBeDisabled();
    });

    it("should render Merge node type as enabled", () => {
      render(<NodePalette onAddNode={mockOnAddNode} />);

      const mergeButton = screen.getByRole("button", { name: /^merge$/i });
      expect(mergeButton).not.toBeDisabled();
    });
  });

  describe("Phase 6 Node Types", () => {
    it("should render Human Gate node type as enabled", () => {
      render(<NodePalette onAddNode={mockOnAddNode} />);

      const humanGateButton = screen.getByRole("button", { name: /^human gate$/i });
      expect(humanGateButton).not.toBeDisabled();
    });
  });

  describe("User Interactions", () => {
    it("should call onAddNode with Prompt type when Prompt button is clicked", async () => {
      const user = userEvent.setup();
      render(<NodePalette onAddNode={mockOnAddNode} />);

      const promptButton = screen.getByRole("button", { name: /^prompt$/i });
      await user.click(promptButton);

      expect(mockOnAddNode).toHaveBeenCalledTimes(1);
      expect(mockOnAddNode).toHaveBeenCalledWith(NODE_TYPES.PROMPT, false);
    });

    it("should call onAddNode with HTTP type when HTTP button is clicked", async () => {
      const user = userEvent.setup();
      render(<NodePalette onAddNode={mockOnAddNode} />);

      const httpButton = screen.getByRole("button", { name: /^http$/i });
      await user.click(httpButton);

      expect(mockOnAddNode).toHaveBeenCalledTimes(1);
      expect(mockOnAddNode).toHaveBeenCalledWith(NODE_TYPES.HTTP, false);
    });

    it("should call onAddNode with Transform type when Transform button is clicked", async () => {
      const user = userEvent.setup();
      render(<NodePalette onAddNode={mockOnAddNode} />);

      const transformButton = screen.getByRole("button", { name: /^transform$/i });
      await user.click(transformButton);

      expect(mockOnAddNode).toHaveBeenCalledTimes(1);
      expect(mockOnAddNode).toHaveBeenCalledWith(NODE_TYPES.TRANSFORM, false);
    });

    it("should call onAddNode with Output type when Output button is clicked", async () => {
      const user = userEvent.setup();
      render(<NodePalette onAddNode={mockOnAddNode} />);

      const outputButton = screen.getByRole("button", { name: /^output$/i });
      await user.click(outputButton);

      expect(mockOnAddNode).toHaveBeenCalledTimes(1);
      expect(mockOnAddNode).toHaveBeenCalledWith(NODE_TYPES.OUTPUT, false);
    });

    it("should call onAddNode with connectToSelected=true when hasSelectedNode is true", async () => {
      const user = userEvent.setup();
      render(<NodePalette onAddNode={mockOnAddNode} hasSelectedNode={true} />);

      const promptButton = screen.getByRole("button", { name: /^prompt$/i });
      await user.click(promptButton);

      expect(mockOnAddNode).toHaveBeenCalledTimes(1);
      expect(mockOnAddNode).toHaveBeenCalledWith(NODE_TYPES.PROMPT, true);
    });

    it("should call onAddNode when Human Gate button is clicked", async () => {
      const user = userEvent.setup();
      render(<NodePalette onAddNode={mockOnAddNode} />);

      const humanGateButton = screen.getByRole("button", { name: /^human gate$/i });
      await user.click(humanGateButton);

      expect(mockOnAddNode).toHaveBeenCalledTimes(1);
      expect(mockOnAddNode).toHaveBeenCalledWith(NODE_TYPES.HUMAN_GATE, false);
    });

    it("should allow multiple clicks on enabled nodes", async () => {
      const user = userEvent.setup();
      render(<NodePalette onAddNode={mockOnAddNode} />);

      const promptButton = screen.getByRole("button", { name: /^prompt$/i });
      await user.click(promptButton);
      await user.click(promptButton);
      await user.click(promptButton);

      expect(mockOnAddNode).toHaveBeenCalledTimes(3);
    });

    it("should support keyboard-first quick add from search", async () => {
      const user = userEvent.setup();
      render(<NodePalette onAddNode={mockOnAddNode} />);

      const searchInput = screen.getByRole("textbox", { name: /search nodes/i });
      await user.type(searchInput, "http");
      await user.keyboard("{Enter}");

      expect(mockOnAddNode).toHaveBeenCalledWith(NODE_TYPES.HTTP, false);
    });

    it("should track recently used nodes after selection", async () => {
      const user = userEvent.setup();
      render(<NodePalette onAddNode={mockOnAddNode} />);

      await user.click(screen.getByRole("button", { name: /^prompt$/i }));

      expect(screen.getByText("Recently used")).toBeInTheDocument();
      expect(screen.getByRole("button", { name: /^recent prompt$/i })).toBeInTheDocument();
    });
  });

  describe("Visual Indicators", () => {
    it("should display colored icon for each node type", () => {
      const { container } = render(<NodePalette onAddNode={mockOnAddNode} />);

      // Each node button should have a colored icon badge
      const iconBadges = container.querySelectorAll(
        ".bg-violet-500, .bg-amber-500, .bg-blue-500, .bg-indigo-500, .bg-rose-500, .bg-emerald-500, .bg-orange-500"
      );
      expect(iconBadges.length).toBeGreaterThan(0);
    });

    it("should display Lucide icons for node types", () => {
      const { container } = render(<NodePalette onAddNode={mockOnAddNode} />);

      // Each node type renders an icon inside a colored icon container
      // The icons are rendered as SVG elements from Lucide
      const iconContainers = container.querySelectorAll(
        ".bg-violet-500, .bg-amber-500, .bg-blue-500, .bg-indigo-500, .bg-orange-500, .bg-emerald-500, .bg-teal-500, .bg-cyan-500, .bg-fuchsia-500"
      );
      expect(iconContainers.length).toBeGreaterThan(0);

      // Each icon container should have an SVG child (Lucide icon)
      iconContainers.forEach((container) => {
        const svg = container.querySelector("svg");
        expect(svg).toBeTruthy();
      });
    });
  });

  describe("Accessibility", () => {
    it("should have accessible button elements", () => {
      render(<NodePalette onAddNode={mockOnAddNode} />);

      const buttons = screen.getAllByRole("button");
      expect(buttons.length).toBeGreaterThan(0);

      buttons.forEach((button) => {
        expect(button).toHaveAttribute("type", "button");
      });
    });

    it("should properly disable buttons that are not enabled", () => {
      render(<NodePalette onAddNode={mockOnAddNode} />);

      const disabledNodeTypes = PHASE2_NODE_TYPES.filter((nt) => !nt.enabled);

      disabledNodeTypes.forEach((nodeType) => {
        // Use more specific pattern to match the node type icon + label
        const buttons = screen.getAllByRole("button", { name: new RegExp(`^${nodeType.label}$`, "i") });
        // At least one button with this label should be disabled
        const hasDisabledButton = buttons.some((btn) => btn.hasAttribute("disabled"));
        expect(hasDisabledButton).toBe(true);
      });
    });
  });
});
