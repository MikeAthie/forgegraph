/**
 * Component tests for NodePalette.
 *
 * Tests node type rendering, enabled/disabled states, and click handlers.
 */

import { act, render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { NodePalette } from "@/components/graph-editor/NodePalette";
import type { MarketplacePackage } from "@/lib/api";
import { NODE_TYPES, PHASE2_NODE_TYPES } from "@/lib/graph-types";

describe("NodePalette", () => {
  const mockOnAddNode = jest.fn();
  const setupUser = () => {
    const user = userEvent.setup();
    return {
      click: (element: HTMLElement) => act(async () => user.click(element)),
      type: (element: HTMLElement, text: string) => act(async () => user.type(element, text)),
      keyboard: (text: string) => act(async () => user.keyboard(text)),
    };
  };

  beforeEach(() => {
    jest.clearAllMocks();
  });

  const buildMarketplacePackage = (
    overrides: Partial<MarketplacePackage> = {},
  ): MarketplacePackage => ({
    id: "pkg-1",
    slug: "crm-lookup",
    name: "CRM Lookup",
    summary: "Runtime-backed CRM lookup package.",
    category: "developer",
    icon: "sparkles",
    docs_url: "",
    homepage_url: "",
    latest_release: {
      id: "rel-1",
      version: "1.0.0",
      changelog: "",
      status: "approved",
      package_kind: "runtime_tool",
      execution_node_type: "tool",
      ui_schema: { label: "CRM Lookup" },
      config_schema: { type: "object" },
      config_defaults: { tool: "crm_lookup" },
      runtime_manifest: {
        name: "crm_lookup",
        version: "1.0.0",
        kind: "http",
        http: { url: "https://example.com/crm", method: "POST" },
      },
      manifest_version: 1,
      cloud_allowed: true,
      review_notes: "",
      created_at: "2026-02-05T12:00:00Z",
    },
    installed_release: {
      id: "rel-1",
      version: "1.0.0",
      changelog: "",
      status: "approved",
      package_kind: "runtime_tool",
      execution_node_type: "tool",
      ui_schema: { label: "CRM Lookup" },
      config_schema: { type: "object" },
      config_defaults: { tool: "crm_lookup" },
      runtime_manifest: {
        name: "crm_lookup",
        version: "1.0.0",
        kind: "http",
        http: { url: "https://example.com/crm", method: "POST" },
      },
      manifest_version: 1,
      cloud_allowed: true,
      review_notes: "",
      created_at: "2026-02-05T12:00:00Z",
    },
    runtime_delivery: {
      state: "ready",
      reason: "ready",
      package_kind: "runtime_tool",
      cloud_allowed: true,
      manifest_version: 1,
      checksum: "abc123",
    },
    ...overrides,
  });

  describe("Rendering", () => {
    it("should render palette header and description", () => {
      render(<NodePalette onAddNode={mockOnAddNode} />);

      expect(screen.getByText("Add Nodes")).toBeInTheDocument();
      expect(screen.getByText("Click to add a node to the canvas")).toBeInTheDocument();
    });

    it("should render all node types from PHASE2_NODE_TYPES", () => {
      render(<NodePalette onAddNode={mockOnAddNode} />);

      PHASE2_NODE_TYPES.forEach((nodeType) => {
        expect(
          screen.getAllByRole("button", { name: new RegExp(`^${nodeType.label}$`, "i") })
            .length
        ).toBeGreaterThan(0);
        expect(screen.getByText(nodeType.description)).toBeInTheDocument();
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

      // Should show "Coming soon" label for disabled nodes
      if (disabledNodeTypes.length > 0) {
        expect(screen.getAllByText("(Coming soon)").length).toBeGreaterThan(0);
      } else {
        expect(screen.queryByText("(Coming soon)")).not.toBeInTheDocument();
      }
    });

    it("should display keyboard shortcuts section", () => {
      render(<NodePalette onAddNode={mockOnAddNode} />);

      expect(screen.getByText("Keyboard Shortcuts")).toBeInTheDocument();
      expect(screen.getByText("Open wizard")).toBeInTheDocument();
      expect(screen.getByText("Save")).toBeInTheDocument();
      expect(screen.getByText("Select all")).toBeInTheDocument();
      expect(screen.getByText("Delete node")).toBeInTheDocument();
      expect(screen.getByText("Ctrl+W")).toBeInTheDocument();
      expect(screen.getByText("Ctrl+S")).toBeInTheDocument();
      expect(screen.getByText("Ctrl+A")).toBeInTheDocument();
      expect(screen.getByText("Delete")).toBeInTheDocument();
      expect(screen.getByText("Esc")).toBeInTheDocument();
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
      const user = setupUser();
      render(<NodePalette onAddNode={mockOnAddNode} />);

      const promptButton = screen.getByRole("button", { name: /^prompt$/i });
      await user.click(promptButton);

      expect(mockOnAddNode).toHaveBeenCalledTimes(1);
      expect(mockOnAddNode).toHaveBeenCalledWith(NODE_TYPES.PROMPT, false);
    });

    it("should call onAddNode with HTTP type when HTTP button is clicked", async () => {
      const user = setupUser();
      render(<NodePalette onAddNode={mockOnAddNode} />);

      const httpButton = screen.getByRole("button", { name: /^http$/i });
      await user.click(httpButton);

      expect(mockOnAddNode).toHaveBeenCalledTimes(1);
      expect(mockOnAddNode).toHaveBeenCalledWith(NODE_TYPES.HTTP, false);
    });

    it("should call onAddNode with Transform type when Transform button is clicked", async () => {
      const user = setupUser();
      render(<NodePalette onAddNode={mockOnAddNode} />);

      const transformButton = screen.getByRole("button", { name: /^transform$/i });
      await user.click(transformButton);

      expect(mockOnAddNode).toHaveBeenCalledTimes(1);
      expect(mockOnAddNode).toHaveBeenCalledWith(NODE_TYPES.TRANSFORM, false);
    });

    it("should call onAddNode with Output type when Output button is clicked", async () => {
      const user = setupUser();
      render(<NodePalette onAddNode={mockOnAddNode} />);

      const outputButton = screen.getByRole("button", { name: /^output$/i });
      await user.click(outputButton);

      expect(mockOnAddNode).toHaveBeenCalledTimes(1);
      expect(mockOnAddNode).toHaveBeenCalledWith(NODE_TYPES.OUTPUT, false);
    });

    it("should call onAddNode with connectToSelected=true when hasSelectedNode is true", async () => {
      const user = setupUser();
      render(<NodePalette onAddNode={mockOnAddNode} hasSelectedNode={true} />);

      const promptButton = screen.getByRole("button", { name: /^prompt$/i });
      await user.click(promptButton);

      expect(mockOnAddNode).toHaveBeenCalledTimes(1);
      expect(mockOnAddNode).toHaveBeenCalledWith(NODE_TYPES.PROMPT, true);
    });

    it("should call onAddNode when Observation Context is clicked", async () => {
      const user = setupUser();
      render(<NodePalette onAddNode={mockOnAddNode} />);

      const button = screen.getByRole("button", { name: /^observation context$/i });
      await user.click(button);

      expect(mockOnAddNode).toHaveBeenCalledWith(
        NODE_TYPES.OBSERVATION_CONTEXT,
        false,
      );
    });

    it("should call onAddNode when Human Gate button is clicked", async () => {
      const user = setupUser();
      render(<NodePalette onAddNode={mockOnAddNode} />);

      const humanGateButton = screen.getByRole("button", { name: /^human gate$/i });
      await user.click(humanGateButton);

      expect(mockOnAddNode).toHaveBeenCalledTimes(1);
      expect(mockOnAddNode).toHaveBeenCalledWith(NODE_TYPES.HUMAN_GATE, false);
    });

    it("should allow multiple clicks on enabled nodes", async () => {
      const user = setupUser();
      render(<NodePalette onAddNode={mockOnAddNode} />);

      const promptButton = screen.getByRole("button", { name: /^prompt$/i });
      await user.click(promptButton);
      await user.click(promptButton);
      await user.click(promptButton);

      expect(mockOnAddNode).toHaveBeenCalledTimes(3);
    });

    it("should support keyboard-first quick add from search", async () => {
      const user = setupUser();
      render(<NodePalette onAddNode={mockOnAddNode} />);

      const searchInput = screen.getByRole("textbox", { name: /search nodes/i });
      await user.type(searchInput, "http");
      await user.keyboard("{Enter}");

      expect(mockOnAddNode).toHaveBeenCalledWith(NODE_TYPES.HTTP, false);
    });

    it("should track recently used nodes after selection", async () => {
      const user = setupUser();
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

    it("should display correct icon letters for node types", () => {
      render(<NodePalette onAddNode={mockOnAddNode} />);

      // Check for specific icon letters (M for Prompt, H for HTTP, etc.)
      // Some letters appear multiple times (M for both Prompt and Merge)
      expect(screen.getAllByText("M").length).toBeGreaterThan(0); // Prompt and Merge
      expect(screen.getAllByText("H").length).toBeGreaterThan(0); // HTTP
      expect(screen.getAllByText("T").length).toBeGreaterThan(0); // Transform
      expect(screen.getAllByText("O").length).toBeGreaterThan(0); // Output
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

  describe("Content Display", () => {
    it("should truncate long descriptions with line-clamp", () => {
      render(<NodePalette onAddNode={mockOnAddNode} />);

      // Find elements with description text
      const descriptions = screen.getAllByText(/Call an LLM|Make an HTTP|Transform data|Define the final|Conditional routing|Join parallel|Pause for/);

      descriptions.forEach((desc) => {
        expect(desc).toHaveClass("line-clamp-1");
      });
    });

    it("should display node descriptions in correct format", () => {
      render(<NodePalette onAddNode={mockOnAddNode} />);

      expect(screen.getByText("Call an LLM with a prompt template")).toBeInTheDocument();
      expect(screen.getByText("Make an HTTP request to an external API")).toBeInTheDocument();
      expect(screen.getByText("Transform data with an expression")).toBeInTheDocument();
      expect(screen.getByText("Define the final output of the workflow")).toBeInTheDocument();
    });

    it("should show badges in search results", async () => {
      const user = setupUser();
      render(<NodePalette onAddNode={mockOnAddNode} />);

      const searchInput = screen.getByRole("textbox", { name: /search nodes/i });
      await user.type(searchInput, "prompt");

      expect(screen.getAllByText("Credential").length).toBeGreaterThan(0);
      expect(screen.getAllByText("LLM").length).toBeGreaterThan(0);
    });

    it("should display recommended quick picks", () => {
      render(<NodePalette onAddNode={mockOnAddNode} />);

      expect(screen.getByText("Recommended")).toBeInTheDocument();
      expect(screen.getByRole("button", { name: /^recommended prompt$/i })).toBeInTheDocument();
    });

    it("shows blocked marketplace packages as unavailable", () => {
      render(
        <NodePalette
          onAddNode={mockOnAddNode}
          marketplaceNodes={[
            buildMarketplacePackage({
              name: "Blocked CRM",
              runtime_delivery: {
                state: "blocked",
                reason: "exec_not_supported_in_cloud",
                package_kind: "runtime_tool",
                cloud_allowed: true,
                manifest_version: 1,
                checksum: "abc123",
              },
            }),
          ]}
        />,
      );

      const button = screen.getByRole("button", { name: /^CRM Lookup$/i });
      expect(button).toBeDisabled();
      expect(screen.getByText("(Unavailable)")).toBeInTheDocument();
      expect(screen.getByText(/exec tools are blocked in cloud/i)).toBeInTheDocument();
    });
  });
});
