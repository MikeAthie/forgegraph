/**
 * Component tests for GraphEditor.
 *
 * Focuses on editor behaviors that require GraphEditor state:
 * - Quick-add edge creation
 * - Delete selected node/edge
 */

import { render, screen, within, fireEvent, act, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { useRouter } from "next/router";

let lastOnConnect: ((connection: any) => void) | undefined;

jest.mock("@xyflow/react", () => {
  const React = require("react");

  return {
    __esModule: true,
    ReactFlow: ({
      nodes = [],
      edges = [],
      onConnect,
      onNodeClick,
      onEdgeClick,
      onPaneClick,
      children,
    }: any) => (
      <div
        data-testid="reactflow"
        onClick={() => {
          lastOnConnect = onConnect;
          onPaneClick?.();
        }}
      >
        <div data-testid="reactflow-nodes">
          {nodes.map((node: any) => (
            <button
              key={node.id}
              type="button"
              data-testid={`node-${node.id}`}
              onClick={(event) => {
                event.stopPropagation();
                onNodeClick?.(event, node);
              }}
            >
              {node.data?.label ?? node.id}
            </button>
          ))}
        </div>
        <div data-testid="reactflow-edges">
          {edges.map((edge: any) => (
            <button
              key={edge.id}
              type="button"
              data-testid={`edge-${edge.id}`}
              onClick={(event) => {
                event.stopPropagation();
                onEdgeClick?.(event, edge);
              }}
            >
              {edge.source}-{">"}
              {edge.target}
              {edge.label ? ` (${edge.label})` : ""}
            </button>
          ))}
        </div>
        {children}
      </div>
    ),
    Controls: () => null,
    Background: () => null,
    MiniMap: () => null,
    Panel: ({ children }: any) => <div>{children}</div>,
    useNodesState: (initialNodes: any[]) => {
      const [nodes, setNodes] = React.useState(initialNodes);
      return [nodes, setNodes, jest.fn()];
    },
    useEdgesState: (initialEdges: any[]) => {
      const [edges, setEdges] = React.useState(initialEdges);
      return [edges, setEdges, jest.fn()];
    },
    addEdge: (edge: any, edges: any[]) => [...edges, edge],
    SelectionMode: { Partial: "partial" },
    BackgroundVariant: { Dots: "dots" },
  };
});

jest.mock("next/router", () => ({
  useRouter: jest.fn(),
}));

jest.mock("@/components/graph-editor/PromptNodeWizardDialog", () => ({
  PromptNodeWizardDialog: ({ open, onOpenChange, onComplete }: any) =>
    open ? (
      <div role="dialog">
        <button
          type="button"
          onClick={() => {
            onComplete({});
            onOpenChange?.(false);
          }}
        >
          Finish
        </button>
      </div>
    ) : null,
}));

import { GraphEditor } from "@/components/graph-editor/GraphEditor";

const mockUseRouter = useRouter as jest.MockedFunction<typeof useRouter>;

const actClick = (user: ReturnType<typeof userEvent.setup>, element: HTMLElement) =>
  act(async () => user.click(element));

function renderGraphEditor() {
  return render(
    <GraphEditor
      graphId="graph-1"
      graphName="Test Graph"
      graphDescription="Test Description"
      initialGraphJson={null}
      currentVersion={null}
      currentVersionId={null}
      availableVersions={[]}
      onSelectVersion={jest.fn().mockResolvedValue(undefined)}
      onSave={jest.fn().mockResolvedValue(undefined)}
      onUpdateMetadata={jest.fn().mockResolvedValue(undefined)}
      saving={false}
    />
  );
}

async function addPromptNodeViaWizard(
  user: ReturnType<typeof userEvent.setup>,
  task = "Write a short response."
) {
  await actClick(user, screen.getByRole("button", { name: /^prompt$/i }));

  const dialog = await screen.findByRole("dialog");
  const dialogScope = within(dialog);

  await actClick(user, dialogScope.getByRole("button", { name: /^finish$/i }));

  await waitFor(() => {
    expect(screen.queryByRole("dialog")).not.toBeInTheDocument();
  });
}

async function addNodeViaConfigDialog(
  user: ReturnType<typeof userEvent.setup>,
  label: RegExp
) {
  await actClick(user, screen.getByRole("button", { name: label }));

  const dialog = await screen.findByRole("dialog");
  const dialogScope = within(dialog);

  await actClick(user, dialogScope.getByRole("button", { name: /add node/i }));

  await waitFor(() => {
    expect(screen.queryByRole("dialog")).not.toBeInTheDocument();
  });
}

describe("GraphEditor", () => {
  beforeEach(() => {
    jest.clearAllMocks();
    lastOnConnect = undefined;
    mockUseRouter.mockReturnValue({
      push: jest.fn(),
      replace: jest.fn(),
      prefetch: jest.fn(),
      pathname: "/graphs/graph-1",
      query: { graphId: "graph-1" },
      asPath: "/graphs/graph-1",
    } as any);
  });

  it("should quick-add an edge when adding a node with a selection", async () => {
    const user = userEvent.setup();
    renderGraphEditor();

    await addPromptNodeViaWizard(user);
    await addNodeViaConfigDialog(user, /^http$/i);

    const flow = screen.getByTestId("reactflow");
    expect(within(flow).getAllByTestId(/node-/)).toHaveLength(2);
    expect(within(flow).getAllByTestId(/edge-/)).toHaveLength(1);
  });

  it("should delete the selected edge with Delete key", async () => {
    const user = userEvent.setup();
    renderGraphEditor();

    await addPromptNodeViaWizard(user);
    await addNodeViaConfigDialog(user, /^http$/i);

    const flow = screen.getByTestId("reactflow");
    expect(within(flow).getAllByTestId(/edge-/)).toHaveLength(1);

    await actClick(user, within(flow).getAllByTestId(/edge-/)[0] as HTMLElement);
    fireEvent.keyDown(window, { key: "Delete" });

    expect(within(flow).queryAllByTestId(/edge-/)).toHaveLength(0);
    expect(within(flow).getAllByTestId(/node-/)).toHaveLength(2);
  });

  it("should delete the selected node and its connected edges", async () => {
    const user = userEvent.setup();
    renderGraphEditor();

    await addPromptNodeViaWizard(user);
    await addNodeViaConfigDialog(user, /^http$/i);

    const flow = screen.getByTestId("reactflow");
    expect(within(flow).getAllByTestId(/node-/)).toHaveLength(2);
    expect(within(flow).getAllByTestId(/edge-/)).toHaveLength(1);

    await actClick(user, within(flow).getByRole("button", { name: /prompt node/i }));
    fireEvent.keyDown(window, { key: "Delete" });

    expect(within(flow).queryAllByTestId(/edge-/)).toHaveLength(0);
    expect(within(flow).getAllByTestId(/node-/)).toHaveLength(1);
  });

  it("should label edges from a Branch node based on the source handle", async () => {
    const user = userEvent.setup();
    renderGraphEditor();

    await addNodeViaConfigDialog(user, /^branch$/i);

    const nodesContainer = screen.getByTestId("reactflow-nodes");
    const branchNodeButton = within(nodesContainer).getByRole("button", { name: /^branch$/i });
    const branchTestId = branchNodeButton.getAttribute("data-testid") ?? "";
    const branchId = branchTestId.replace(/^node-/, "");

    // Clear selection so the next node doesn't auto-connect.
    await actClick(user, screen.getByTestId("reactflow"));

    await addNodeViaConfigDialog(user, /^output$/i);

    const outputNodeButton = within(nodesContainer).getByRole("button", { name: /^output$/i });
    const outputTestId = outputNodeButton.getAttribute("data-testid") ?? "";
    const outputId = outputTestId.replace(/^node-/, "");

    expect(typeof lastOnConnect).toBe("function");
    await act(async () => {
      lastOnConnect?.({
        source: branchId,
        target: outputId,
        sourceHandle: "true",
      });
    });

    const flow = screen.getByTestId("reactflow");
    const edgeButtons = await within(flow).findAllByTestId(/edge-/);
    expect(edgeButtons).toHaveLength(1);
    expect(edgeButtons[0]).toHaveTextContent(/\(true\)/i);
  });
});
