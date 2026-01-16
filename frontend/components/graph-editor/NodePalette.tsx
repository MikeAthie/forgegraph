import { useState, useMemo } from "react";
import { Link } from "lucide-react";
import { PHASE2_NODE_TYPES, type NodeType } from "../../lib/graph-types";

interface NodePaletteProps {
  onAddNode: (nodeType: NodeType, connectToSelected?: boolean) => void;
  hasSelectedNode?: boolean;
}

const nodeTypeIcons: Record<string, string> = {
  prompt: "M",
  http: "H",
  transform: "T",
  output: "O",
  branch: "B",
  merge: "M",
  human_gate: "G",
};

const nodeTypeColors: Record<string, string> = {
  prompt: "bg-purple-500",
  http: "bg-blue-500",
  transform: "bg-green-500",
  output: "bg-orange-500",
  branch: "bg-yellow-500",
  merge: "bg-teal-500",
  human_gate: "bg-pink-500",
};

export function NodePalette({ onAddNode, hasSelectedNode = false }: NodePaletteProps) {
  const [searchQuery, setSearchQuery] = useState("");

  const filteredNodeTypes = useMemo(() => {
    if (!searchQuery.trim()) {
      return PHASE2_NODE_TYPES;
    }
    const query = searchQuery.toLowerCase();
    return PHASE2_NODE_TYPES.filter(
      (nodeType) =>
        nodeType.label.toLowerCase().includes(query) ||
        nodeType.description.toLowerCase().includes(query) ||
        nodeType.type.toLowerCase().includes(query)
    );
  }, [searchQuery]);

  return (
    <div className="p-4">
      <h3 className="text-sm font-semibold text-gray-900 mb-3">Add Nodes</h3>

      <div className="mb-4">
        <input
          type="text"
          placeholder="Search nodes..."
          value={searchQuery}
          onChange={(e) => setSearchQuery(e.target.value)}
          className="w-full px-3 py-2 text-sm border border-gray-200 rounded-lg focus:outline-none focus:ring-2 focus:ring-primary focus:border-transparent"
          aria-label="Search nodes"
        />
      </div>

      <p className="text-xs text-gray-500 mb-4">
        {hasSelectedNode
          ? "Click to add connected to selected node"
          : "Click to add a node to the canvas"}
      </p>

      <div className="space-y-2">
        {filteredNodeTypes.length === 0 ? (
          <p className="text-sm text-gray-400 text-center py-4">
            No nodes match "{searchQuery}"
          </p>
        ) : null}
        {filteredNodeTypes.map((nodeType) => (
          <button
            key={nodeType.type}
            type="button"
            aria-label={nodeType.label}
            onClick={() => onAddNode(nodeType.type, hasSelectedNode)}
            disabled={!nodeType.enabled}
            className={`w-full flex items-center gap-3 p-3 rounded-lg border transition-all ${
              nodeType.enabled
                ? "border-gray-200 hover:border-primary hover:bg-gray-50 cursor-pointer"
                : "border-gray-100 bg-gray-50 cursor-not-allowed opacity-60"
            }`}
          >
            <div
              aria-hidden="true"
              className={`w-8 h-8 rounded-md flex items-center justify-center text-white text-sm font-bold ${
                nodeTypeColors[nodeType.type] ?? "bg-gray-500"
              }`}
            >
              {nodeTypeIcons[nodeType.type] ?? "?"}
            </div>
            <div className="flex-1 text-left">
              <div className="text-sm font-medium text-gray-900 flex items-center gap-1">
                {nodeType.label}
                {!nodeType.enabled && (
                  <span className="ml-2 text-xs text-gray-400">(Coming soon)</span>
                )}
                {hasSelectedNode && nodeType.enabled && (
                  <Link className="w-3 h-3 text-primary ml-1" />
                )}
              </div>
              <div className="text-xs text-gray-500 line-clamp-1">
                {nodeType.description}
              </div>
            </div>
          </button>
        ))}
      </div>

      <div className="mt-6 pt-4 border-t border-gray-200">
        <h4 className="text-xs font-medium text-gray-500 uppercase tracking-wider mb-2">
          Keyboard Shortcuts
        </h4>
        <div className="space-y-1 text-xs text-gray-600">
          <div className="flex justify-between">
            <span>Save</span>
            <kbd className="px-1.5 py-0.5 bg-gray-100 rounded text-gray-700">
              Ctrl+S
            </kbd>
          </div>
          <div className="flex justify-between">
            <span>Select all</span>
            <kbd className="px-1.5 py-0.5 bg-gray-100 rounded text-gray-700">
              Ctrl+A
            </kbd>
          </div>
          <div className="flex justify-between">
            <span>Delete node</span>
            <kbd className="px-1.5 py-0.5 bg-gray-100 rounded text-gray-700">
              Delete
            </kbd>
          </div>
        </div>
      </div>
    </div>
  );
}
