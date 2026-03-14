/**
 * Component tests for NodeConfigDialog.
 *
 * Tests dialog behavior, node type display, form rendering, error states,
 * unsaved changes handling, keyboard shortcuts, and save callbacks.
 */

import { act, render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { useEffect } from "react";
import { NodeConfigDialog, type NodeFormProps } from "@/components/graph-editor/NodeConfigDialog";
import { NODE_TYPES } from "@/lib/graph-types";

// Mock Dialog components from shadcn/ui
jest.mock("@/components/ui/dialog", () => ({
  Dialog: ({ children, open, onOpenChange }: any) => (
    <div data-testid="dialog" data-open={open}>
      {open && children}
      {open && onOpenChange && (
        <button data-testid="dialog-backdrop" onClick={() => onOpenChange(false)}>
          Close backdrop
        </button>
      )}
    </div>
  ),
  DialogContent: ({ children }: any) => <div data-testid="dialog-content">{children}</div>,
  DialogHeader: ({ children }: any) => <div data-testid="dialog-header">{children}</div>,
  DialogTitle: ({ children }: any) => <h2 data-testid="dialog-title">{children}</h2>,
  DialogDescription: ({ children }: any) => <p data-testid="dialog-description">{children}</p>,
  DialogFooter: ({ children }: any) => <div data-testid="dialog-footer">{children}</div>,
}));

// Mock Button component
jest.mock("@/components/ui/button", () => ({
  Button: ({ children, onClick, disabled, variant }: any) => (
    <button onClick={onClick} disabled={disabled} data-variant={variant}>
      {children}
    </button>
  ),
}));

// Mock lucide-react icons
jest.mock("lucide-react", () => ({
  AlertCircle: () => <div data-testid="alert-icon">!</div>,
}));

describe("NodeConfigDialog", () => {
  const mockOnClose = jest.fn();
  const mockOnSave = jest.fn();

  const setupUser = () => {
    const user = userEvent.setup();
    return {
      ...user,
      click: (element: HTMLElement) => act(async () => user.click(element)),
      type: (element: HTMLElement, text: string) => act(async () => user.type(element, text)),
      clear: (element: HTMLElement) => act(async () => user.clear(element)),
      keyboard: (text: string) => act(async () => user.keyboard(text)),
    };
  };

  // Use stable config objects to avoid infinite loops in component's useEffect
  const emptyConfig = {};
  const promptConfig = { prompt_id: "test-prompt", model: "gpt-4" };
  const httpConfig = { url: "https://api.example.com" };

  beforeEach(() => {
    jest.clearAllMocks();
  });

  describe("Dialog Open/Close Behavior", () => {
    it("should not render when isOpen is false", () => {
      render(
        <NodeConfigDialog isOpen={false} onClose={mockOnClose} nodeType={NODE_TYPES.PROMPT} onSave={mockOnSave} />,
      );

      const dialogs = screen.getAllByTestId("dialog");
      expect(dialogs.every((dialog) => dialog.getAttribute("data-open") === "false")).toBe(true);
    });

    it("should render when isOpen is true", () => {
      render(<NodeConfigDialog isOpen={true} onClose={mockOnClose} nodeType={NODE_TYPES.PROMPT} onSave={mockOnSave} />);

      const dialogs = screen.getAllByTestId("dialog");
      expect(dialogs.some((dialog) => dialog.getAttribute("data-open") === "true")).toBe(true);
      expect(screen.getByTestId("dialog-content")).toBeInTheDocument();
    });

    it("should not render when nodeType is null", () => {
      render(<NodeConfigDialog isOpen={true} onClose={mockOnClose} nodeType={null} onSave={mockOnSave} />);

      expect(screen.queryByTestId("dialog-content")).not.toBeInTheDocument();
    });

    it("should call onClose when Cancel button is clicked", async () => {
      const user = setupUser();
      render(<NodeConfigDialog isOpen={true} onClose={mockOnClose} nodeType={NODE_TYPES.PROMPT} onSave={mockOnSave} />);

      const cancelButton = screen.getByRole("button", { name: /cancel/i });
      await user.click(cancelButton);

      expect(mockOnClose).toHaveBeenCalledTimes(1);
    });

    it("should call onClose when backdrop is clicked without changes", async () => {
      const user = setupUser();
      render(<NodeConfigDialog isOpen={true} onClose={mockOnClose} nodeType={NODE_TYPES.PROMPT} onSave={mockOnSave} />);

      const backdrop = screen.getByTestId("dialog-backdrop");
      await user.click(backdrop);

      expect(mockOnClose).toHaveBeenCalledTimes(1);
    });
  });

  describe("Node Type Info Display", () => {
    it("should display correct label for Prompt node", () => {
      render(<NodeConfigDialog isOpen={true} onClose={mockOnClose} nodeType={NODE_TYPES.PROMPT} onSave={mockOnSave} />);

      expect(screen.getByTestId("dialog-title")).toHaveTextContent("Configure Prompt Node");
    });

    it("should display correct label for HTTP node", () => {
      render(<NodeConfigDialog isOpen={true} onClose={mockOnClose} nodeType={NODE_TYPES.HTTP} onSave={mockOnSave} />);

      expect(screen.getByTestId("dialog-title")).toHaveTextContent("Configure HTTP Node");
    });

    it("should display correct label for Transform node", () => {
      render(
        <NodeConfigDialog isOpen={true} onClose={mockOnClose} nodeType={NODE_TYPES.TRANSFORM} onSave={mockOnSave} />,
      );

      expect(screen.getByTestId("dialog-title")).toHaveTextContent("Configure Transform Node");
    });

    it("should display correct label for Output node", () => {
      render(<NodeConfigDialog isOpen={true} onClose={mockOnClose} nodeType={NODE_TYPES.OUTPUT} onSave={mockOnSave} />);

      expect(screen.getByTestId("dialog-title")).toHaveTextContent("Configure Output Node");
    });

    it("should display correct label for Branch node", () => {
      render(<NodeConfigDialog isOpen={true} onClose={mockOnClose} nodeType={NODE_TYPES.BRANCH} onSave={mockOnSave} />);

      expect(screen.getByTestId("dialog-title")).toHaveTextContent("Configure Branch Node");
    });

    it("should display correct label for Merge node", () => {
      render(<NodeConfigDialog isOpen={true} onClose={mockOnClose} nodeType={NODE_TYPES.MERGE} onSave={mockOnSave} />);

      expect(screen.getByTestId("dialog-title")).toHaveTextContent("Configure Merge Node");
    });

    it("should display correct label for Human Gate node", () => {
      render(
        <NodeConfigDialog isOpen={true} onClose={mockOnClose} nodeType={NODE_TYPES.HUMAN_GATE} onSave={mockOnSave} />,
      );

      expect(screen.getByTestId("dialog-title")).toHaveTextContent("Configure Human Gate Node");
    });

    it("should display correct label for Memory node", () => {
      render(<NodeConfigDialog isOpen={true} onClose={mockOnClose} nodeType={NODE_TYPES.MEMORY} onSave={mockOnSave} />);

      expect(screen.getByTestId("dialog-title")).toHaveTextContent("Configure Memory Node");
    });

    it("should display correct label for Tool node", () => {
      render(<NodeConfigDialog isOpen={true} onClose={mockOnClose} nodeType={NODE_TYPES.TOOL} onSave={mockOnSave} />);

      expect(screen.getByTestId("dialog-title")).toHaveTextContent("Configure Tool Node");
    });

    it("should display correct label for Subgraph node", () => {
      render(
        <NodeConfigDialog isOpen={true} onClose={mockOnClose} nodeType={NODE_TYPES.SUBGRAPH} onSave={mockOnSave} />,
      );

      expect(screen.getByTestId("dialog-title")).toHaveTextContent("Configure Subgraph Node");
    });

    it("should display correct icon badge with color for Prompt node", () => {
      const { container } = render(
        <NodeConfigDialog isOpen={true} onClose={mockOnClose} nodeType={NODE_TYPES.PROMPT} onSave={mockOnSave} />,
      );

      const badge = container.querySelector(".bg-violet-500");
      expect(badge).toBeInTheDocument();
      expect(badge).toHaveTextContent("P");
    });

    it("should display correct icon badge with color for HTTP node", () => {
      const { container } = render(
        <NodeConfigDialog isOpen={true} onClose={mockOnClose} nodeType={NODE_TYPES.HTTP} onSave={mockOnSave} />,
      );

      const badge = container.querySelector(".bg-blue-500");
      expect(badge).toBeInTheDocument();
      expect(badge).toHaveTextContent("H");
    });

    it("should display correct icon badge with color for Transform node", () => {
      const { container } = render(
        <NodeConfigDialog isOpen={true} onClose={mockOnClose} nodeType={NODE_TYPES.TRANSFORM} onSave={mockOnSave} />,
      );

      const badge = container.querySelector(".bg-amber-500");
      expect(badge).toBeInTheDocument();
      expect(badge).toHaveTextContent("T");
    });

    it("should display correct icon badge with color for Output node", () => {
      const { container } = render(
        <NodeConfigDialog isOpen={true} onClose={mockOnClose} nodeType={NODE_TYPES.OUTPUT} onSave={mockOnSave} />,
      );

      const badge = container.querySelector(".bg-emerald-500");
      expect(badge).toBeInTheDocument();
      expect(badge).toHaveTextContent("O");
    });

    it("should display correct icon badge with color for Branch node", () => {
      const { container } = render(
        <NodeConfigDialog isOpen={true} onClose={mockOnClose} nodeType={NODE_TYPES.BRANCH} onSave={mockOnSave} />,
      );

      const badge = container.querySelector(".bg-orange-500");
      expect(badge).toBeInTheDocument();
      expect(badge).toHaveTextContent("B");
    });

    it("should display correct icon badge with color for Merge node", () => {
      const { container } = render(
        <NodeConfigDialog isOpen={true} onClose={mockOnClose} nodeType={NODE_TYPES.MERGE} onSave={mockOnSave} />,
      );

      const badge = container.querySelector(".bg-cyan-500");
      expect(badge).toBeInTheDocument();
      expect(badge).toHaveTextContent("M");
    });

    it("should display correct icon badge with color for Human Gate node", () => {
      const { container } = render(
        <NodeConfigDialog isOpen={true} onClose={mockOnClose} nodeType={NODE_TYPES.HUMAN_GATE} onSave={mockOnSave} />,
      );

      const badge = container.querySelector(".bg-rose-500");
      expect(badge).toBeInTheDocument();
      expect(badge).toHaveTextContent("G");
    });

    it("should display dialog description", () => {
      render(<NodeConfigDialog isOpen={true} onClose={mockOnClose} nodeType={NODE_TYPES.PROMPT} onSave={mockOnSave} />);

      expect(screen.getByTestId("dialog-description")).toHaveTextContent(
        "Set up the node configuration before adding it to your workflow.",
      );
    });
  });

  describe("Node Label Input", () => {
    it("should initialize label with node type label", () => {
      render(<NodeConfigDialog isOpen={true} onClose={mockOnClose} nodeType={NODE_TYPES.PROMPT} onSave={mockOnSave} />);

      const labelInput = screen.getByLabelText(/node label/i);
      expect(labelInput).toHaveValue("Prompt");
    });

    it("should allow editing node label", async () => {
      const user = setupUser();
      render(<NodeConfigDialog isOpen={true} onClose={mockOnClose} nodeType={NODE_TYPES.HTTP} onSave={mockOnSave} />);

      const labelInput = screen.getByLabelText(/node label/i);
      await user.clear(labelInput);
      await user.type(labelInput, "My Custom HTTP Node");

      expect(labelInput).toHaveValue("My Custom HTTP Node");
    });

    it("should mark dialog as dirty when label is edited", async () => {
      const user = setupUser();
      render(<NodeConfigDialog isOpen={true} onClose={mockOnClose} nodeType={NODE_TYPES.PROMPT} onSave={mockOnSave} />);

      const labelInput = screen.getByLabelText(/node label/i);
      await user.type(labelInput, " Extra");

      // Try to close - should show confirmation dialog
      const cancelButton = screen.getByRole("button", { name: /cancel/i });
      await user.click(cancelButton);

      // Confirmation dialog should appear
      expect(screen.getByText("Discard changes?")).toBeInTheDocument();
    });

    it("should use placeholder text from node type", () => {
      render(
        <NodeConfigDialog isOpen={true} onClose={mockOnClose} nodeType={NODE_TYPES.TRANSFORM} onSave={mockOnSave} />,
      );

      const labelInput = screen.getByLabelText(/node label/i);
      expect(labelInput).toHaveAttribute("placeholder", "Transform");
    });

    it("should trim whitespace from label on save", async () => {
      const user = setupUser();
      render(<NodeConfigDialog isOpen={true} onClose={mockOnClose} nodeType={NODE_TYPES.PROMPT} onSave={mockOnSave} />);

      const labelInput = screen.getByLabelText(/node label/i);
      await user.clear(labelInput);
      await user.type(labelInput, "  My Node  ");

      const saveButton = screen.getByRole("button", { name: /add node/i });
      await user.click(saveButton);

      expect(mockOnSave).toHaveBeenCalledWith(expect.any(Object), "My Node");
    });

    it("should use default label when label is empty on save", async () => {
      const user = setupUser();
      render(<NodeConfigDialog isOpen={true} onClose={mockOnClose} nodeType={NODE_TYPES.HTTP} onSave={mockOnSave} />);

      const labelInput = screen.getByLabelText(/node label/i);
      await user.clear(labelInput);

      const saveButton = screen.getByRole("button", { name: /add node/i });
      await user.click(saveButton);

      expect(mockOnSave).toHaveBeenCalledWith(expect.any(Object), "HTTP");
    });
  });

  describe("FormComponent Rendering", () => {
    it("should render DefaultNodeForm when no FormComponent is provided", () => {
      render(<NodeConfigDialog isOpen={true} onClose={mockOnClose} nodeType={NODE_TYPES.PROMPT} onSave={mockOnSave} />);

      expect(screen.getByText("Configure this node using the inspector panel after creation.")).toBeInTheDocument();
    });

    it("should render DefaultNodeForm with config preview", () => {
      render(
        <NodeConfigDialog
          isOpen={true}
          onClose={mockOnClose}
          nodeType={NODE_TYPES.PROMPT}
          initialConfig={promptConfig}
          onSave={mockOnSave}
        />,
      );

      expect(screen.getByText(/"prompt_id"/)).toBeInTheDocument();
      expect(screen.getByText(/"test-prompt"/)).toBeInTheDocument();
    });

    it("should render custom FormComponent when provided", () => {
      const CustomForm = ({ config, onChange }: NodeFormProps) => (
        <div>
          <label htmlFor="custom-field">Custom Field</label>
          <input
            id="custom-field"
            value={(config.customField as string) || ""}
            onChange={(e) => onChange({ ...config, customField: e.target.value })}
          />
        </div>
      );

      render(
        <NodeConfigDialog
          isOpen={true}
          onClose={mockOnClose}
          nodeType={NODE_TYPES.PROMPT}
          onSave={mockOnSave}
          FormComponent={CustomForm}
        />,
      );

      expect(screen.getByLabelText("Custom Field")).toBeInTheDocument();
      expect(
        screen.queryByText("Configure this node using the inspector panel after creation."),
      ).not.toBeInTheDocument();
    });

    it("should pass config to FormComponent", () => {
      const testConfig = { testField: "test-value" };
      const CustomForm = ({ config }: NodeFormProps) => <div data-testid="custom-form">{JSON.stringify(config)}</div>;

      render(
        <NodeConfigDialog
          isOpen={true}
          onClose={mockOnClose}
          nodeType={NODE_TYPES.PROMPT}
          initialConfig={testConfig}
          onSave={mockOnSave}
          FormComponent={CustomForm}
        />,
      );

      expect(screen.getByTestId("custom-form")).toHaveTextContent('"testField":"test-value"');
    });

    it("should call onChange when FormComponent updates config", async () => {
      const user = setupUser();
      const CustomForm = ({ config, onChange }: NodeFormProps) => (
        <button onClick={() => onChange({ ...config, updated: true })}>Update Config</button>
      );

      render(
        <NodeConfigDialog
          isOpen={true}
          onClose={mockOnClose}
          nodeType={NODE_TYPES.PROMPT}
          onSave={mockOnSave}
          FormComponent={CustomForm}
        />,
      );

      const updateButton = screen.getByRole("button", { name: /update config/i });
      await user.click(updateButton);

      const saveButton = screen.getByRole("button", { name: /add node/i });
      await user.click(saveButton);

      expect(mockOnSave).toHaveBeenCalledWith({ updated: true }, expect.any(String));
    });

    it("should pass errors and setErrors to FormComponent", () => {
      const CustomForm = ({ errors, setErrors }: NodeFormProps) => (
        <div>
          <div data-testid="errors">{JSON.stringify(errors)}</div>
          <button onClick={() => setErrors({ field1: "Error message" })}>Set Error</button>
        </div>
      );

      render(
        <NodeConfigDialog
          isOpen={true}
          onClose={mockOnClose}
          nodeType={NODE_TYPES.PROMPT}
          onSave={mockOnSave}
          FormComponent={CustomForm}
        />,
      );

      expect(screen.getByTestId("errors")).toHaveTextContent("{}");
      expect(screen.getByRole("button", { name: /set error/i })).toBeInTheDocument();
    });
  });

  describe("Error State and Save Button", () => {
    it("should not show error summary when no errors", () => {
      render(<NodeConfigDialog isOpen={true} onClose={mockOnClose} nodeType={NODE_TYPES.PROMPT} onSave={mockOnSave} />);

      expect(screen.queryByTestId("alert-icon")).not.toBeInTheDocument();
      expect(screen.queryByText("Please fix the following errors:")).not.toBeInTheDocument();
    });

    it("should show error summary when errors exist", async () => {
      const user = setupUser();
      const CustomForm = ({ setErrors }: NodeFormProps) => (
        <button onClick={() => setErrors({ url: "URL is required" })}>Add Error</button>
      );

      render(
        <NodeConfigDialog
          isOpen={true}
          onClose={mockOnClose}
          nodeType={NODE_TYPES.HTTP}
          onSave={mockOnSave}
          FormComponent={CustomForm}
        />,
      );

      const addErrorButton = screen.getByRole("button", { name: /add error/i });
      await user.click(addErrorButton);

      expect(screen.getByTestId("alert-icon")).toBeInTheDocument();
      expect(screen.getByText("Please fix the following errors:")).toBeInTheDocument();
      expect(screen.getByText("URL is required")).toBeInTheDocument();
    });

    it("should display multiple errors in summary", async () => {
      const user = setupUser();
      const CustomForm = ({ setErrors }: NodeFormProps) => (
        <button
          onClick={() =>
            setErrors({
              url: "URL is required",
              method: "Invalid method",
              headers: "Headers must be valid JSON",
            })
          }
        >
          Add Errors
        </button>
      );

      render(
        <NodeConfigDialog
          isOpen={true}
          onClose={mockOnClose}
          nodeType={NODE_TYPES.HTTP}
          onSave={mockOnSave}
          FormComponent={CustomForm}
        />,
      );

      const addErrorsButton = screen.getByRole("button", { name: /add errors/i });
      await user.click(addErrorsButton);

      expect(screen.getByText("URL is required")).toBeInTheDocument();
      expect(screen.getByText("Invalid method")).toBeInTheDocument();
      expect(screen.getByText("Headers must be valid JSON")).toBeInTheDocument();
    });

    it("should disable save button when errors exist", async () => {
      const user = setupUser();
      const CustomForm = ({ setErrors }: NodeFormProps) => (
        <button onClick={() => setErrors({ field: "Error" })}>Add Error</button>
      );

      render(
        <NodeConfigDialog
          isOpen={true}
          onClose={mockOnClose}
          nodeType={NODE_TYPES.PROMPT}
          onSave={mockOnSave}
          FormComponent={CustomForm}
        />,
      );

      const saveButton = screen.getByRole("button", { name: /add node/i });
      expect(saveButton).not.toBeDisabled();

      const addErrorButton = screen.getByRole("button", { name: /add error/i });
      await user.click(addErrorButton);

      expect(saveButton).toBeDisabled();
    });

    it("should not call onSave when save button is clicked with errors", async () => {
      const user = setupUser();
      const CustomForm = ({ setErrors }: NodeFormProps) => {
        useEffect(() => {
          setErrors({ field: "Error" });
        }, [setErrors]);
        return <div>Form with error</div>;
      };

      render(
        <NodeConfigDialog
          isOpen={true}
          onClose={mockOnClose}
          nodeType={NODE_TYPES.PROMPT}
          onSave={mockOnSave}
          FormComponent={CustomForm}
        />,
      );

      const saveButton = screen.getByRole("button", { name: /add node/i });
      expect(saveButton).toBeDisabled();

      // Try to click disabled button
      await user.click(saveButton);

      expect(mockOnSave).not.toHaveBeenCalled();
    });

    it("should enable save button when errors are cleared", async () => {
      const user = setupUser();
      const CustomForm = ({ errors, setErrors }: NodeFormProps) => (
        <div>
          <button onClick={() => setErrors({ field: "Error" })}>Add Error</button>
          <button onClick={() => setErrors({})}>Clear Errors</button>
        </div>
      );

      render(
        <NodeConfigDialog
          isOpen={true}
          onClose={mockOnClose}
          nodeType={NODE_TYPES.PROMPT}
          onSave={mockOnSave}
          FormComponent={CustomForm}
        />,
      );

      const saveButton = screen.getByRole("button", { name: /add node/i });
      const addErrorButton = screen.getByRole("button", { name: /add error/i });
      const clearErrorsButton = screen.getByRole("button", { name: /clear errors/i });

      await user.click(addErrorButton);
      expect(saveButton).toBeDisabled();

      await user.click(clearErrorsButton);
      expect(saveButton).not.toBeDisabled();
    });
  });

  describe("Unsaved Changes Confirmation", () => {
    it("should not show confirmation dialog when closing without changes", async () => {
      const user = setupUser();
      render(<NodeConfigDialog isOpen={true} onClose={mockOnClose} nodeType={NODE_TYPES.PROMPT} onSave={mockOnSave} />);

      const cancelButton = screen.getByRole("button", { name: /cancel/i });
      await user.click(cancelButton);

      expect(screen.queryByText("Discard changes?")).not.toBeInTheDocument();
      expect(mockOnClose).toHaveBeenCalled();
    });

    it("should show confirmation dialog when closing with unsaved label changes", async () => {
      const user = setupUser();
      render(<NodeConfigDialog isOpen={true} onClose={mockOnClose} nodeType={NODE_TYPES.PROMPT} onSave={mockOnSave} />);

      const labelInput = screen.getByLabelText(/node label/i);
      await user.type(labelInput, " Modified");

      const cancelButton = screen.getByRole("button", { name: /cancel/i });
      await user.click(cancelButton);

      expect(screen.getByText("Discard changes?")).toBeInTheDocument();
      expect(screen.getByText(/you have unsaved changes/i)).toBeInTheDocument();
      expect(mockOnClose).not.toHaveBeenCalled();
    });

    it("should show confirmation dialog when closing with unsaved config changes", async () => {
      const user = setupUser();
      const CustomForm = ({ onChange, config }: NodeFormProps) => (
        <button onClick={() => onChange({ ...config, field: "value" })}>Update</button>
      );

      render(
        <NodeConfigDialog
          isOpen={true}
          onClose={mockOnClose}
          nodeType={NODE_TYPES.PROMPT}
          onSave={mockOnSave}
          FormComponent={CustomForm}
        />,
      );

      const updateButton = screen.getByRole("button", { name: /update/i });
      await user.click(updateButton);

      const cancelButton = screen.getByRole("button", { name: /cancel/i });
      await user.click(cancelButton);

      expect(screen.getByText("Discard changes?")).toBeInTheDocument();
    });

    it("should close dialog when Keep Editing is clicked", async () => {
      const user = setupUser();
      render(<NodeConfigDialog isOpen={true} onClose={mockOnClose} nodeType={NODE_TYPES.PROMPT} onSave={mockOnSave} />);

      const labelInput = screen.getByLabelText(/node label/i);
      await user.type(labelInput, " Modified");

      const cancelButton = screen.getByRole("button", { name: /cancel/i });
      await user.click(cancelButton);

      const keepEditingButton = screen.getByRole("button", { name: /keep editing/i });
      await user.click(keepEditingButton);

      expect(screen.queryByText("Discard changes?")).not.toBeInTheDocument();
      expect(mockOnClose).not.toHaveBeenCalled();
    });

    it("should call onClose when Discard is clicked", async () => {
      const user = setupUser();
      render(<NodeConfigDialog isOpen={true} onClose={mockOnClose} nodeType={NODE_TYPES.PROMPT} onSave={mockOnSave} />);

      const labelInput = screen.getByLabelText(/node label/i);
      await user.type(labelInput, " Modified");

      const cancelButton = screen.getByRole("button", { name: /cancel/i });
      await user.click(cancelButton);

      const discardButton = screen.getByRole("button", { name: /discard/i });
      await user.click(discardButton);

      expect(mockOnClose).toHaveBeenCalledTimes(1);
    });

    it("should show confirmation when closing via backdrop with changes", async () => {
      const user = setupUser();
      render(<NodeConfigDialog isOpen={true} onClose={mockOnClose} nodeType={NODE_TYPES.PROMPT} onSave={mockOnSave} />);

      const labelInput = screen.getByLabelText(/node label/i);
      await user.type(labelInput, " Modified");

      const backdrop = screen.getByTestId("dialog-backdrop");
      await user.click(backdrop);

      expect(screen.getByText("Discard changes?")).toBeInTheDocument();
      expect(mockOnClose).not.toHaveBeenCalled();
    });
  });

  describe("Escape Key Handling", () => {
    it("should close dialog when Escape is pressed without changes", async () => {
      const user = setupUser();
      render(<NodeConfigDialog isOpen={true} onClose={mockOnClose} nodeType={NODE_TYPES.PROMPT} onSave={mockOnSave} />);

      await user.keyboard("{Escape}");

      expect(mockOnClose).toHaveBeenCalledTimes(1);
    });

    it("should show confirmation when Escape is pressed with changes", async () => {
      const user = setupUser();
      render(<NodeConfigDialog isOpen={true} onClose={mockOnClose} nodeType={NODE_TYPES.PROMPT} onSave={mockOnSave} />);

      const labelInput = screen.getByLabelText(/node label/i);
      await user.type(labelInput, " Modified");

      await user.keyboard("{Escape}");

      expect(screen.getByText("Discard changes?")).toBeInTheDocument();
      expect(mockOnClose).not.toHaveBeenCalled();
    });

    it("should not respond to Escape when dialog is closed", async () => {
      const user = setupUser();
      render(
        <NodeConfigDialog isOpen={false} onClose={mockOnClose} nodeType={NODE_TYPES.PROMPT} onSave={mockOnSave} />,
      );

      await user.keyboard("{Escape}");

      expect(mockOnClose).not.toHaveBeenCalled();
    });
  });

  describe("onSave Callback", () => {
    it("should call onSave with config and label when save button is clicked", async () => {
      const user = setupUser();
      render(<NodeConfigDialog isOpen={true} onClose={mockOnClose} nodeType={NODE_TYPES.PROMPT} onSave={mockOnSave} />);

      const saveButton = screen.getByRole("button", { name: /add node/i });
      await user.click(saveButton);

      expect(mockOnSave).toHaveBeenCalledTimes(1);
      expect(mockOnSave).toHaveBeenCalledWith({}, "Prompt");
    });

    it("should call onSave with updated config", async () => {
      const user = setupUser();
      const CustomForm = ({ onChange, config }: NodeFormProps) => (
        <button onClick={() => onChange({ ...config, url: "https://api.example.com" })}>Set URL</button>
      );

      render(
        <NodeConfigDialog
          isOpen={true}
          onClose={mockOnClose}
          nodeType={NODE_TYPES.HTTP}
          onSave={mockOnSave}
          FormComponent={CustomForm}
        />,
      );

      const setUrlButton = screen.getByRole("button", { name: /set url/i });
      await user.click(setUrlButton);

      const saveButton = screen.getByRole("button", { name: /add node/i });
      await user.click(saveButton);

      expect(mockOnSave).toHaveBeenCalledWith({ url: "https://api.example.com" }, "HTTP");
    });

    it("should call onSave with custom label", async () => {
      const user = setupUser();
      render(
        <NodeConfigDialog isOpen={true} onClose={mockOnClose} nodeType={NODE_TYPES.TRANSFORM} onSave={mockOnSave} />,
      );

      const labelInput = screen.getByLabelText(/node label/i);
      await user.clear(labelInput);
      await user.type(labelInput, "Data Transformer");

      const saveButton = screen.getByRole("button", { name: /add node/i });
      await user.click(saveButton);

      expect(mockOnSave).toHaveBeenCalledWith({}, "Data Transformer");
    });

    it("should call onSave with initial config if provided", async () => {
      const user = setupUser();

      render(
        <NodeConfigDialog
          isOpen={true}
          onClose={mockOnClose}
          nodeType={NODE_TYPES.PROMPT}
          initialConfig={promptConfig}
          onSave={mockOnSave}
        />,
      );

      const saveButton = screen.getByRole("button", { name: /add node/i });
      await user.click(saveButton);

      expect(mockOnSave).toHaveBeenCalledWith(promptConfig, "Prompt");
    });

    it("should call onClose after successful save", async () => {
      const user = setupUser();
      render(<NodeConfigDialog isOpen={true} onClose={mockOnClose} nodeType={NODE_TYPES.PROMPT} onSave={mockOnSave} />);

      const saveButton = screen.getByRole("button", { name: /add node/i });
      await user.click(saveButton);

      expect(mockOnSave).toHaveBeenCalled();
      expect(mockOnClose).toHaveBeenCalled();
    });

    it("should handle complex config objects", async () => {
      const user = setupUser();
      const CustomForm = ({ onChange }: NodeFormProps) => (
        <button
          onClick={() =>
            onChange({
              method: "POST",
              url: "https://api.test.com",
              headers: { "Content-Type": "application/json" },
              body: JSON.stringify({ key: "value" }),
            })
          }
        >
          Set Complex Config
        </button>
      );

      render(
        <NodeConfigDialog
          isOpen={true}
          onClose={mockOnClose}
          nodeType={NODE_TYPES.HTTP}
          onSave={mockOnSave}
          FormComponent={CustomForm}
        />,
      );

      const setConfigButton = screen.getByRole("button", { name: /set complex config/i });
      await user.click(setConfigButton);

      const saveButton = screen.getByRole("button", { name: /add node/i });
      await user.click(saveButton);

      expect(mockOnSave).toHaveBeenCalledWith(
        {
          method: "POST",
          url: "https://api.test.com",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ key: "value" }),
        },
        "HTTP",
      );
    });
  });

  describe("State Reset on Dialog Open", () => {
    it("should reset state when dialog is opened with new node type", () => {
      const { rerender } = render(
        <NodeConfigDialog isOpen={false} onClose={mockOnClose} nodeType={NODE_TYPES.PROMPT} onSave={mockOnSave} />,
      );

      rerender(
        <NodeConfigDialog isOpen={true} onClose={mockOnClose} nodeType={NODE_TYPES.PROMPT} onSave={mockOnSave} />,
      );

      const labelInput = screen.getByLabelText(/node label/i);
      expect(labelInput).toHaveValue("Prompt");
    });

    it("should reset config when dialog is reopened", async () => {
      const user = setupUser();
      const CustomForm = ({ onChange, config }: NodeFormProps) => (
        <div>
          <button onClick={() => onChange({ ...config, field: "modified" })}>Modify</button>
          <div data-testid="config-display">{JSON.stringify(config)}</div>
        </div>
      );

      const { rerender } = render(
        <NodeConfigDialog
          isOpen={true}
          onClose={mockOnClose}
          nodeType={NODE_TYPES.PROMPT}
          onSave={mockOnSave}
          FormComponent={CustomForm}
        />,
      );

      const modifyButton = screen.getByRole("button", { name: /modify/i });
      await user.click(modifyButton);

      expect(screen.getByTestId("config-display")).toHaveTextContent("modified");

      // Close and reopen
      rerender(
        <NodeConfigDialog
          isOpen={false}
          onClose={mockOnClose}
          nodeType={NODE_TYPES.PROMPT}
          onSave={mockOnSave}
          FormComponent={CustomForm}
        />,
      );

      rerender(
        <NodeConfigDialog
          isOpen={true}
          onClose={mockOnClose}
          nodeType={NODE_TYPES.PROMPT}
          onSave={mockOnSave}
          FormComponent={CustomForm}
        />,
      );

      expect(screen.getByTestId("config-display")).not.toHaveTextContent("modified");
    });

    it("should reset errors when dialog is reopened", async () => {
      const user = setupUser();
      const CustomForm = ({ setErrors }: NodeFormProps) => (
        <button onClick={() => setErrors({ field: "Error message" })}>Add Error</button>
      );

      const { rerender } = render(
        <NodeConfigDialog
          isOpen={true}
          onClose={mockOnClose}
          nodeType={NODE_TYPES.PROMPT}
          onSave={mockOnSave}
          FormComponent={CustomForm}
        />,
      );

      const addErrorButton = screen.getByRole("button", { name: /add error/i });
      await user.click(addErrorButton);

      expect(screen.getByText("Please fix the following errors:")).toBeInTheDocument();

      // Close and reopen
      rerender(
        <NodeConfigDialog
          isOpen={false}
          onClose={mockOnClose}
          nodeType={NODE_TYPES.PROMPT}
          onSave={mockOnSave}
          FormComponent={CustomForm}
        />,
      );

      rerender(
        <NodeConfigDialog
          isOpen={true}
          onClose={mockOnClose}
          nodeType={NODE_TYPES.PROMPT}
          onSave={mockOnSave}
          FormComponent={CustomForm}
        />,
      );

      expect(screen.queryByText("Please fix the following errors:")).not.toBeInTheDocument();
    });

    it("should reset isDirty flag when dialog is reopened", async () => {
      const user = setupUser();
      const { rerender } = render(
        <NodeConfigDialog isOpen={true} onClose={mockOnClose} nodeType={NODE_TYPES.PROMPT} onSave={mockOnSave} />,
      );

      const labelInput = screen.getByLabelText(/node label/i);
      await user.type(labelInput, " Modified");

      const cancelButton = screen.getByRole("button", { name: /cancel/i });
      await user.click(cancelButton);

      // Should show confirmation
      expect(screen.getByText("Discard changes?")).toBeInTheDocument();

      // Close dialog
      const discardButton = screen.getByRole("button", { name: /discard/i });
      await user.click(discardButton);

      // Reopen
      rerender(
        <NodeConfigDialog isOpen={false} onClose={mockOnClose} nodeType={NODE_TYPES.PROMPT} onSave={mockOnSave} />,
      );

      rerender(
        <NodeConfigDialog isOpen={true} onClose={mockOnClose} nodeType={NODE_TYPES.PROMPT} onSave={mockOnSave} />,
      );

      // Should close without confirmation now
      const newCancelButton = screen.getByRole("button", { name: /cancel/i });
      await user.click(newCancelButton);

      expect(screen.queryByText("Discard changes?")).not.toBeInTheDocument();
    });
  });

  describe("Edge Cases", () => {
    it("should handle missing node type info gracefully", () => {
      // Use a node type that doesn't exist in NODE_TYPE_INFO
      const { container } = render(
        <NodeConfigDialog isOpen={true} onClose={mockOnClose} nodeType={"unknown_type" as any} onSave={mockOnSave} />,
      );

      expect(screen.getByTestId("dialog-title")).toHaveTextContent("Configure unknown_type Node");

      // Should use fallback icon and color
      const badge = container.querySelector(".bg-gray-500");
      expect(badge).toBeInTheDocument();
      expect(badge).toHaveTextContent("?");
    });

    it("should handle undefined initialConfig", () => {
      render(<NodeConfigDialog isOpen={true} onClose={mockOnClose} nodeType={NODE_TYPES.PROMPT} onSave={mockOnSave} />);

      expect(screen.getByText("Configure this node using the inspector panel after creation.")).toBeInTheDocument();
    });

    it("should handle empty initialConfig object", () => {
      render(
        <NodeConfigDialog
          isOpen={true}
          onClose={mockOnClose}
          nodeType={NODE_TYPES.PROMPT}
          initialConfig={emptyConfig}
          onSave={mockOnSave}
        />,
      );

      expect(screen.getByText("Configure this node using the inspector panel after creation.")).toBeInTheDocument();
    });

    it("should handle rapid open/close cycles", () => {
      const { rerender } = render(
        <NodeConfigDialog isOpen={true} onClose={mockOnClose} nodeType={NODE_TYPES.PROMPT} onSave={mockOnSave} />,
      );

      rerender(
        <NodeConfigDialog isOpen={false} onClose={mockOnClose} nodeType={NODE_TYPES.PROMPT} onSave={mockOnSave} />,
      );

      rerender(
        <NodeConfigDialog isOpen={true} onClose={mockOnClose} nodeType={NODE_TYPES.PROMPT} onSave={mockOnSave} />,
      );

      expect(screen.getByTestId("dialog-content")).toBeInTheDocument();
    });
  });
});
