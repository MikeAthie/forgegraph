import { act, fireEvent, render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { type ComponentType, useState } from "react";

import { ObservationContextNodeForm } from "@/components/graph-editor/forms/ObservationContextNodeForm";
import { ObservationSaveNodeForm } from "@/components/graph-editor/forms/ObservationSaveNodeForm";
import { ObservationSearchNodeForm } from "@/components/graph-editor/forms/ObservationSearchNodeForm";
import { ObservationTimelineNodeForm } from "@/components/graph-editor/forms/ObservationTimelineNodeForm";
import type { NodeFormProps } from "@/components/graph-editor/NodeConfigDialog";

describe("Observation node forms", () => {
  const mockSetErrors = jest.fn();

  const setupUser = () => {
    const user = userEvent.setup();
    return {
      click: (element: HTMLElement) => act(async () => user.click(element)),
      type: (element: HTMLElement, text: string) => act(async () => user.type(element, text)),
      clear: (element: HTMLElement) => act(async () => user.clear(element)),
      select: (element: HTMLElement, value: string) => act(async () => user.selectOptions(element, value)),
    };
  };

  beforeEach(() => {
    jest.clearAllMocks();
  });

  function renderWithState(Component: ComponentType<NodeFormProps>, initialConfig: NodeFormProps["config"] = {}) {
    const onChange = jest.fn();

    const Wrapper = () => {
      const [config, setConfig] = useState(initialConfig);
      const recordConfigChange = (nextConfig: NodeFormProps["config"]) => {
        setConfig(nextConfig);
        onChange(nextConfig);
      };

      return <Component config={config} onChange={recordConfigChange} errors={{}} setErrors={mockSetErrors} />;
    };

    const result = render(<Wrapper />);
    return { ...result, onChange };
  }

  it("validates required save fields", async () => {
    const user = setupUser();
    renderWithState(ObservationSaveNodeForm, { type: "preference" });

    await user.clear(screen.getByLabelText(/observation type/i));

    await waitFor(() => {
      expect(mockSetErrors).toHaveBeenCalledWith(
        expect.objectContaining({
          type: "Observation type is required.",
          content: "content requires one configured source.",
        }),
      );
    });
  });

  it("updates save content_path when path mode is already configured", async () => {
    const user = setupUser();
    const { onChange } = renderWithState(ObservationSaveNodeForm, {
      type: "preference",
      scope: "graph",
      content_path: "node.old.output",
    });

    const input = screen.getByDisplayValue("node.old.output");
    await user.clear(input);
    await user.type(input, "node.prompt_1.output");

    await waitFor(() => {
      const lastCall = onChange.mock.calls[onChange.mock.calls.length - 1][0];
      expect(lastCall.content_path).toContain("node.prompt_1.output");
    });
  });

  it("validates required search query source", async () => {
    const user = setupUser();
    renderWithState(ObservationSearchNodeForm, { query: "customer preferences" });

    await user.clear(screen.getByLabelText(/^query/i));

    await waitFor(() => {
      expect(mockSetErrors).toHaveBeenCalledWith(
        expect.objectContaining({
          query: "query requires one configured source.",
        }),
      );
    });
  });

  it("updates context query_template when template mode is already configured", async () => {
    const { onChange } = renderWithState(ObservationContextNodeForm, {
      query_template: "Initial {{input.customer_name}}",
    });

    const input = screen.getByDisplayValue("Initial {{input.customer_name}}");
    fireEvent.change(input, {
      target: { value: "Prepare context for {{input.customer_name}}" },
    });

    await waitFor(() => {
      const lastCall = onChange.mock.calls[onChange.mock.calls.length - 1][0];
      expect(lastCall.query_template).toContain("{{input.customer_name}}");
    });
  });

  it("updates timeline scope and deleted toggle", async () => {
    const user = setupUser();
    const { onChange } = renderWithState(ObservationTimelineNodeForm, {
      scope: "graph",
    });

    await user.select(screen.getAllByRole("combobox")[0] as HTMLElement, "session");
    await user.click(screen.getByRole("checkbox", { name: /include deleted observations/i }));

    await waitFor(() => {
      expect(onChange).toHaveBeenCalledWith(
        expect.objectContaining({
          scope: "session",
          include_deleted: true,
        }),
      );
    });
  });
});
