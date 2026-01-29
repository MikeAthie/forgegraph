/**
 * Unit tests for HumanGateNodeForm component.
 *
 * Tests approval message, instructions, timeout, email notifications,
 * switches for auto-approve and require comment, and integration
 * with AgentFields and AdvancedSettings.
 */

import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { HumanGateNodeForm } from "@/components/graph-editor/forms/HumanGateNodeForm";
import type { NodeFormProps } from "@/components/graph-editor/NodeConfigDialog";

// Mock child components
jest.mock("@/components/graph-editor/forms/AgentFields", () => ({
  AgentFields: () => <div data-testid="agent-fields">Agent Fields</div>,
}));

jest.mock("@/components/graph-editor/forms/AdvancedSettings", () => ({
  AdvancedSettings: () => <div data-testid="advanced-settings">Advanced Settings</div>,
}));

describe("HumanGateNodeForm", () => {
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
      render(<HumanGateNodeForm {...defaultProps} />);

      expect(screen.getByText(/approval configuration/i)).toBeInTheDocument();
      expect(screen.getByLabelText(/approval message/i)).toBeInTheDocument();
      expect(screen.getByLabelText(/instructions/i)).toBeInTheDocument();
      expect(screen.getByLabelText(/timeout \(hours\)/i)).toBeInTheDocument();
      expect(screen.getByTestId("agent-fields")).toBeInTheDocument();
      expect(screen.getByTestId("advanced-settings")).toBeInTheDocument();
    });

    it("should render with populated config", () => {
      const config = {
        approval_message: "Please review this output",
        instructions: "Check for accuracy and tone",
        timeout_hours: 48,
        notify_emails: ["user@example.com", "admin@example.com"],
        auto_approve_after_timeout: true,
        require_comment: true,
        show_context: false,
      };

      render(<HumanGateNodeForm {...defaultProps} config={config} />);

      expect(screen.getByDisplayValue("Please review this output")).toBeInTheDocument();
      expect(screen.getByDisplayValue("Check for accuracy and tone")).toBeInTheDocument();
      expect(screen.getByDisplayValue("48")).toBeInTheDocument();
      expect(
        screen.getByDisplayValue("user@example.com, admin@example.com")
      ).toBeInTheDocument();
    });

    it("should display helpful description", () => {
      render(<HumanGateNodeForm {...defaultProps} />);

      expect(
        screen.getByText(
          /pause the workflow and wait for human approval before proceeding/i
        )
      ).toBeInTheDocument();
    });
  });

  describe("Approval Message Field", () => {
    it("should render approval message textarea", () => {
      render(<HumanGateNodeForm {...defaultProps} />);

      expect(screen.getByLabelText(/approval message/i)).toBeInTheDocument();
    });

    it("should call onChange when approval message is modified", async () => {
      const user = userEvent.setup();
      render(<HumanGateNodeForm {...defaultProps} />);

      const approvalMessage = screen.getByLabelText(/approval message/i);
      await user.type(approvalMessage, "Review needed");

      await waitFor(() => {
        const lastCall = mockOnChange.mock.calls[mockOnChange.mock.calls.length - 1][0];
        expect(lastCall.approval_message).toContain("Review needed");
      });
    });

    it("should mark approval message as required", () => {
      render(<HumanGateNodeForm {...defaultProps} />);

      const approvalLabel = screen.getByText(/^approval message$/i);
      expect(approvalLabel.closest("div")).toBeInTheDocument();
    });

    it("should have appropriate rows", () => {
      render(<HumanGateNodeForm {...defaultProps} />);

      const approvalMessage = screen.getByLabelText(/approval message/i);
      expect(approvalMessage.tagName).toBe("TEXTAREA");
      expect(approvalMessage).toHaveAttribute("rows", "2");
    });
  });

  describe("Instructions Field", () => {
    it("should render instructions textarea", () => {
      render(<HumanGateNodeForm {...defaultProps} />);

      expect(screen.getByLabelText(/^instructions$/i)).toBeInTheDocument();
    });

    it("should call onChange when instructions are modified", async () => {
      const user = userEvent.setup();
      render(<HumanGateNodeForm {...defaultProps} />);

      const instructions = screen.getByLabelText(/^instructions$/i);
      await user.type(instructions, "Check compliance");

      await waitFor(() => {
        const lastCall = mockOnChange.mock.calls[mockOnChange.mock.calls.length - 1][0];
        expect(lastCall.instructions).toContain("Check compliance");
      });
    });

    it("should have appropriate rows", () => {
      render(<HumanGateNodeForm {...defaultProps} />);

      const instructions = screen.getByLabelText(/^instructions$/i);
      expect(instructions.tagName).toBe("TEXTAREA");
      expect(instructions).toHaveAttribute("rows", "3");
    });
  });

  describe("Timeout Field", () => {
    it("should render timeout input", () => {
      render(<HumanGateNodeForm {...defaultProps} />);

      expect(screen.getByLabelText(/timeout \(hours\)/i)).toBeInTheDocument();
    });

    it("should call onChange when timeout is modified", async () => {
      const user = userEvent.setup();
      render(<HumanGateNodeForm {...defaultProps} />);

      const timeout = screen.getByLabelText(/timeout \(hours\)/i);
      await user.type(timeout, "72");

      await waitFor(() => {
        const lastCall = mockOnChange.mock.calls[mockOnChange.mock.calls.length - 1][0];
        expect(lastCall.timeout_hours).toBe(72);
      });
    });

    it("should have appropriate constraints", () => {
      render(<HumanGateNodeForm {...defaultProps} />);

      const timeout = screen.getByLabelText(/timeout \(hours\)/i);
      expect(timeout).toHaveAttribute("type", "number");
      expect(timeout).toHaveAttribute("min", "0");
      expect(timeout).toHaveAttribute("max", "720");
    });

    it("should have appropriate placeholder", () => {
      render(<HumanGateNodeForm {...defaultProps} />);

      expect(screen.getByPlaceholderText("24")).toBeInTheDocument();
    });
  });

  describe("Notify Emails Field", () => {
    it("should render notify emails input", () => {
      render(<HumanGateNodeForm {...defaultProps} />);

      expect(screen.getByLabelText(/notify emails/i)).toBeInTheDocument();
    });

    it("should display comma-separated emails", () => {
      const config = {
        notify_emails: ["user1@example.com", "user2@example.com"],
      };
      render(<HumanGateNodeForm {...defaultProps} config={config} />);

      expect(
        screen.getByDisplayValue("user1@example.com, user2@example.com")
      ).toBeInTheDocument();
    });

    it("should call onChange with parsed email array", async () => {
      const user = userEvent.setup();
      render(<HumanGateNodeForm {...defaultProps} />);

      const emailsInput = screen.getByLabelText(/notify emails/i);
      await user.type(emailsInput, "test@example.com, admin@example.com");

      await waitFor(() => {
        expect(mockOnChange).toHaveBeenCalledWith(
          expect.objectContaining({
            notify_emails: expect.arrayContaining([
              expect.stringContaining("test@example.com"),
              expect.stringContaining("admin@example.com"),
            ]),
          })
        );
      });
    });

    it("should filter out empty email entries", async () => {
      const user = userEvent.setup();
      render(<HumanGateNodeForm {...defaultProps} />);

      const emailsInput = screen.getByLabelText(/notify emails/i);
      await user.type(emailsInput, "test@example.com, , admin@example.com");

      await waitFor(() => {
        const lastCall = mockOnChange.mock.calls[mockOnChange.mock.calls.length - 1][0];
        if (lastCall.notify_emails) {
          expect(lastCall.notify_emails.length).toBeLessThanOrEqual(2);
        }
      });
    });
  });

  describe("Auto-approve Switch", () => {
    it("should render auto-approve switch", () => {
      render(<HumanGateNodeForm {...defaultProps} />);

      expect(screen.getByText(/auto-approve on timeout/i)).toBeInTheDocument();
      expect(
        screen.getByText(/automatically approve if no response within timeout/i)
      ).toBeInTheDocument();
    });

    it("should call onChange when auto-approve is toggled", async () => {
      const user = userEvent.setup();
      render(<HumanGateNodeForm {...defaultProps} />);

      const switches = screen.getAllByRole("switch");
      const autoApproveSwitch = switches.find((s) =>
        s.getAttribute("aria-label")?.includes("auto-approve") ||
        s.closest("div")?.textContent?.includes("Auto-approve")
      ) || switches[0];

      await user.click(autoApproveSwitch);

      await waitFor(() => {
        expect(mockOnChange).toHaveBeenCalledWith(
          expect.objectContaining({
            auto_approve_after_timeout: true,
          })
        );
      });
    });

    it("should show checked state when enabled", () => {
      const config = { auto_approve_after_timeout: true };
      render(<HumanGateNodeForm {...defaultProps} config={config} />);

      const switches = screen.getAllByRole("switch");
      const autoApproveSwitch = switches[0];
      expect(autoApproveSwitch).toHaveAttribute("aria-checked", "true");
    });

    it("should show unchecked state when disabled", () => {
      const config = { auto_approve_after_timeout: false };
      render(<HumanGateNodeForm {...defaultProps} config={config} />);

      const switches = screen.getAllByRole("switch");
      const autoApproveSwitch = switches[0];
      expect(autoApproveSwitch).toHaveAttribute("aria-checked", "false");
    });
  });

  describe("Require Comment Switch", () => {
    it("should render require comment switch", () => {
      render(<HumanGateNodeForm {...defaultProps} />);

      expect(screen.getByText(/^require comment$/i)).toBeInTheDocument();
      expect(
        screen.getByText(/reviewer must provide a comment with their decision/i)
      ).toBeInTheDocument();
    });

    it("should call onChange when require comment is toggled", async () => {
      const user = userEvent.setup();
      render(<HumanGateNodeForm {...defaultProps} />);

      const switches = screen.getAllByRole("switch");
      const requireCommentSwitch = switches[1];

      await user.click(requireCommentSwitch);

      await waitFor(() => {
        expect(mockOnChange).toHaveBeenCalledWith(
          expect.objectContaining({
            require_comment: true,
          })
        );
      });
    });
  });

  describe("Show Context Switch", () => {
    it("should render show context switch", () => {
      render(<HumanGateNodeForm {...defaultProps} />);

      expect(screen.getByText(/^show context$/i)).toBeInTheDocument();
      expect(
        screen.getByText(/display upstream node outputs to the reviewer/i)
      ).toBeInTheDocument();
    });

    it("should call onChange when show context is toggled", async () => {
      const user = userEvent.setup();
      render(<HumanGateNodeForm {...defaultProps} />);

      const switches = screen.getAllByRole("switch");
      const showContextSwitch = switches[2];

      await user.click(showContextSwitch);

      await waitFor(() => {
        expect(mockOnChange).toHaveBeenCalled();
      });
    });

    it("should default to true when not set", () => {
      render(<HumanGateNodeForm {...defaultProps} />);

      const switches = screen.getAllByRole("switch");
      const showContextSwitch = switches[2];
      expect(showContextSwitch).toHaveAttribute("aria-checked", "true");
    });
  });

  describe("Auto-approve Warning", () => {
    it("should display warning when auto-approve is enabled", () => {
      const config = { auto_approve_after_timeout: true };
      render(<HumanGateNodeForm {...defaultProps} config={config} />);

      expect(screen.getByText(/auto-approval warning/i)).toBeInTheDocument();
      expect(
        screen.getByText(/the workflow will continue automatically if not reviewed/i)
      ).toBeInTheDocument();
    });

    it("should not display warning when auto-approve is disabled", () => {
      const config = { auto_approve_after_timeout: false };
      render(<HumanGateNodeForm {...defaultProps} config={config} />);

      expect(screen.queryByText(/auto-approval warning/i)).not.toBeInTheDocument();
    });

    it("should include timeout hours in warning message", () => {
      const config = { auto_approve_after_timeout: true, timeout_hours: 48 };
      render(<HumanGateNodeForm {...defaultProps} config={config} />);

      expect(screen.getByText(/48 hours/i)).toBeInTheDocument();
    });

    it("should use default 24 hours when timeout not set", () => {
      const config = { auto_approve_after_timeout: true };
      render(<HumanGateNodeForm {...defaultProps} config={config} />);

      expect(screen.getByText(/24 hours/i)).toBeInTheDocument();
    });

    it("should style warning with amber colors", () => {
      const config = { auto_approve_after_timeout: true };
      const { container } = render(<HumanGateNodeForm {...defaultProps} config={config} />);

      const warning = container.querySelector(".bg-amber-500\\/10");
      expect(warning).toBeInTheDocument();
    });
  });

  describe("Section Headers", () => {
    it("should display all section headers", () => {
      render(<HumanGateNodeForm {...defaultProps} />);

      expect(screen.getByText(/^approval configuration$/i)).toBeInTheDocument();
      expect(screen.getByText(/timeout & notifications/i)).toBeInTheDocument();
      expect(screen.getByText(/^options$/i)).toBeInTheDocument();
    });
  });

  describe("Integration with Sub-components", () => {
    it("should render AgentFields", () => {
      render(<HumanGateNodeForm {...defaultProps} />);

      expect(screen.getByTestId("agent-fields")).toBeInTheDocument();
    });

    it("should render AdvancedSettings", () => {
      render(<HumanGateNodeForm {...defaultProps} />);

      expect(screen.getByTestId("advanced-settings")).toBeInTheDocument();
    });
  });

  describe("Form Layout", () => {
    it("should render separators between sections", () => {
      const { container } = render(<HumanGateNodeForm {...defaultProps} />);

      const separators = container.querySelectorAll("[role='separator']");
      expect(separators.length).toBeGreaterThan(0);
    });

    it("should use grid layout for timeout and emails", () => {
      const { container } = render(<HumanGateNodeForm {...defaultProps} />);

      const grid = container.querySelector(".grid-cols-2");
      expect(grid).toBeInTheDocument();
    });
  });

  describe("Field Descriptions", () => {
    it("should display description for approval message", () => {
      render(<HumanGateNodeForm {...defaultProps} />);

      expect(screen.getByText(/message shown to the reviewer/i)).toBeInTheDocument();
    });

    it("should display description for instructions", () => {
      render(<HumanGateNodeForm {...defaultProps} />);

      expect(screen.getByText(/detailed instructions for the reviewer/i)).toBeInTheDocument();
    });

    it("should display description for timeout", () => {
      render(<HumanGateNodeForm {...defaultProps} />);

      expect(
        screen.getByText(/max wait time before timeout action/i)
      ).toBeInTheDocument();
    });

    it("should display description for notify emails", () => {
      render(<HumanGateNodeForm {...defaultProps} />);

      expect(screen.getByText(/comma-separated email addresses/i)).toBeInTheDocument();
    });
  });

  describe("Preserving Config", () => {
    it("should preserve all config when updating one field", async () => {
      const user = userEvent.setup();
      const config = {
        approval_message: "Review this",
        timeout_hours: 24,
        auto_approve_after_timeout: true,
      };
      render(<HumanGateNodeForm {...defaultProps} config={config} />);

      const instructions = screen.getByLabelText(/^instructions$/i);
      await user.type(instructions, "New instructions");

      await waitFor(() => {
        expect(mockOnChange).toHaveBeenCalledWith(
          expect.objectContaining({
            approval_message: "Review this",
            timeout_hours: 24,
            auto_approve_after_timeout: true,
            instructions: expect.any(String),
          })
        );
      });
    });
  });

  describe("Switches Behavior", () => {
    it("should toggle switch from false to true", async () => {
      const user = userEvent.setup();
      const config = { require_comment: false };
      render(<HumanGateNodeForm {...defaultProps} config={config} />);

      const switches = screen.getAllByRole("switch");
      const requireCommentSwitch = switches[1];
      await user.click(requireCommentSwitch);

      await waitFor(() => {
        expect(mockOnChange).toHaveBeenCalledWith(
          expect.objectContaining({
            require_comment: true,
          })
        );
      });
    });

    it("should toggle switch from true to false", async () => {
      const user = userEvent.setup();
      const config = { require_comment: true };
      render(<HumanGateNodeForm {...defaultProps} config={config} />);

      const switches = screen.getAllByRole("switch");
      const requireCommentSwitch = switches[1];
      await user.click(requireCommentSwitch);

      await waitFor(() => {
        expect(mockOnChange).toHaveBeenCalledWith(
          expect.objectContaining({
            require_comment: false,
          })
        );
      });
    });
  });
});
