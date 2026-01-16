/**
 * Component tests for GraphEditor.
 *
 * Focuses on editor behaviors that require GraphEditor state:
 * - Quick-add edge creation
 * - Delete selected node/edge
 */

import { render, screen, within, fireEvent } from "@testing-library/react";
import userEvent from "@testing-library/user-event";

jest.mock("@xyflow/react", () => {
  const React = require("react");

  return {
    __esModule: true,
    ReactFlow: ({
      nodes = [],
      edges = [],
      onNodeClick,
      onEdgeClick,
      onPaneClick,
      children,
    }: any) => (
      <div data-testid="reactflow" onClick={() => onPaneClick?.()}>
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

import { GraphEditor } from "@/components/graph-editor/GraphEditor";

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

describe("GraphEditor", () => {
  it("should quick-add an edge when adding a node with a selection", async () => {
    const user = userEvent.setup();
    renderGraphEditor();

    await user.click(screen.getByRole("button", { name: /^prompt$/i }));
    await user.click(screen.getByRole("button", { name: /^http$/i }));

    const flow = screen.getByTestId("reactflow");
    expect(within(flow).getAllByTestId(/node-/)).toHaveLength(2);
    expect(within(flow).getAllByTestId(/edge-/)).toHaveLength(1);
  });

  it("should delete the selected edge with Delete key", async () => {
    const user = userEvent.setup();
    renderGraphEditor();

    await user.click(screen.getByRole("button", { name: /^prompt$/i }));
    await user.click(screen.getByRole("button", { name: /^http$/i }));

    const flow = screen.getByTestId("reactflow");
    expect(within(flow).getAllByTestId(/edge-/)).toHaveLength(1);

    await user.click(within(flow).getAllByTestId(/edge-/)[0]);
    fireEvent.keyDown(window, { key: "Delete" });

    expect(within(flow).queryAllByTestId(/edge-/)).toHaveLength(0);
    expect(within(flow).getAllByTestId(/node-/)).toHaveLength(2);
  });

  it("should delete the selected node and its connected edges", async () => {
    const user = userEvent.setup();
    renderGraphEditor();

    await user.click(screen.getByRole("button", { name: /^prompt$/i }));
    await user.click(screen.getByRole("button", { name: /^http$/i }));

    const flow = screen.getByTestId("reactflow");
    expect(within(flow).getAllByTestId(/node-/)).toHaveLength(2);
    expect(within(flow).getAllByTestId(/edge-/)).toHaveLength(1);

    await user.click(within(flow).getByRole("button", { name: /prompt node/i }));
    fireEvent.keyDown(window, { key: "Delete" });

    expect(within(flow).queryAllByTestId(/edge-/)).toHaveLength(0);
    expect(within(flow).getAllByTestId(/node-/)).toHaveLength(1);
  });
});

