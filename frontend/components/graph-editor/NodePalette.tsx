import { useMemo, useState, type RefObject } from "react";
import { Link } from "lucide-react";
import { PHASE2_NODE_TYPES, type NodeType } from "../../lib/graph-types";
import { Input } from "@/components/ui/input";

interface NodePaletteProps {
  onAddNode: (nodeType: NodeType, connectToSelected?: boolean) => void;
  onAddNote: () => void;
  hasSelectedNode?: boolean;
  searchInputRef?: RefObject<HTMLInputElement | null>;
}

const nodeTypeIcons: Record<string, string> = {
  prompt: "M",
  http: "H",
  transform: "T",
  output: "O",
  branch: "B",
  merge: "M",
  human_gate: "G",
  note: "N",
};

const nodeTypeColors: Record<string, string> = {
  prompt: "bg-violet-500",
  http: "bg-amber-500",
  transform: "bg-blue-500",
  output: "bg-indigo-500",
  branch: "bg-rose-500",
  merge: "bg-emerald-500",
  human_gate: "bg-orange-500",
  note: "bg-amber-500",
};

type PaletteItem =
  | {
      kind: "node";
      type: NodeType;
      label: string;
      description: string;
      enabled: boolean;
      category: string;
    }
  | {
      kind: "note";
      type: "note";
      label: string;
      description: string;
      enabled: true;
      category: string;
    };

const NODE_CATEGORIES: Record<string, string> = {
  prompt: "AI",
  http: "I/O",
  transform: "Logic",
  output: "I/O",
  branch: "Logic",
  merge: "Logic",
  human_gate: "Logic",
  note: "Annotations",
};

const CATEGORY_ORDER = ["AI", "Logic", "I/O", "Annotations"];

export function NodePalette({
  onAddNode,
  onAddNote,
  hasSelectedNode = false,
  searchInputRef,
}: NodePaletteProps) {
  const [searchQuery, setSearchQuery] = useState("");

  const paletteItems: PaletteItem[] = useMemo(() => {
    const baseItems: PaletteItem[] = PHASE2_NODE_TYPES.map((nodeType) => ({
      kind: "node",
      type: nodeType.type,
      label: nodeType.label,
      description: nodeType.description,
      enabled: nodeType.enabled,
      category: NODE_CATEGORIES[nodeType.type] ?? "Other",
    }));

    return [
      ...baseItems,
      {
        kind: "note",
        type: "note",
        label: "Note",
        description: "Add a sticky note to annotate the workflow",
        enabled: true,
        category: NODE_CATEGORIES.note,
      },
    ];
  }, []);

  const filteredItems = useMemo(() => {
    if (!searchQuery.trim()) {
      return paletteItems;
    }
    const query = searchQuery.toLowerCase();
    return paletteItems.filter(
      (item) =>
        item.label.toLowerCase().includes(query) ||
        item.description.toLowerCase().includes(query) ||
        item.type.toLowerCase().includes(query) ||
        item.category.toLowerCase().includes(query)
    );
  }, [paletteItems, searchQuery]);

  const groupedItems = useMemo(() => {
    const groups = new Map<string, PaletteItem[]>();
    for (const item of filteredItems) {
      const existing = groups.get(item.category) ?? [];
      existing.push(item);
      groups.set(item.category, existing);
    }

    const sortedEntries = Array.from(groups.entries()).sort(([a], [b]) => {
      const aIndex = CATEGORY_ORDER.indexOf(a);
      const bIndex = CATEGORY_ORDER.indexOf(b);
      if (aIndex === -1 && bIndex === -1) return a.localeCompare(b);
      if (aIndex === -1) return 1;
      if (bIndex === -1) return -1;
      return aIndex - bIndex;
    });

    return sortedEntries;
  }, [filteredItems]);

  return (
    <div className="p-4">
      <h3 className="text-sm font-semibold text-foreground mb-3">Add Nodes</h3>

      <div className="mb-4">
        <Input
          ref={searchInputRef}
          type="text"
          placeholder="Search nodes..."
          value={searchQuery}
          onChange={(e) => setSearchQuery(e.target.value)}
          aria-label="Search nodes"
        />
      </div>

      <p className="text-xs text-muted-foreground mb-4">
        {hasSelectedNode
          ? "Click to add connected to selected node"
          : "Click to add a node to the canvas"}
      </p>

      <div className="space-y-4">
        {filteredItems.length === 0 ? (
          <p className="text-sm text-muted-foreground text-center py-4">
            No nodes match &quot;{searchQuery}&quot;
          </p>
        ) : null}
        {groupedItems.map(([category, items]) => (
          <div key={category}>
            <h4 className="text-[11px] font-semibold text-muted-foreground uppercase tracking-wider mb-2">
              {category}
            </h4>
            <div className="space-y-2">
              {items.map((item) => (
                <button
                  key={item.type}
                  type="button"
                  aria-label={item.label}
                  onClick={() => {
                    if (item.kind === "note") {
                      onAddNote();
                      return;
                    }
                    onAddNode(item.type, hasSelectedNode);
                  }}
                  disabled={!item.enabled}
                  className={`w-full flex items-center gap-3 p-3 rounded-lg border transition-all ${
                    item.enabled
                      ? "border-border bg-background/40 hover:border-primary/30 hover:bg-accent/40 cursor-pointer"
                      : "border-border/50 bg-muted/30 cursor-not-allowed opacity-60"
                  }`}
                >
                  <div
                    aria-hidden="true"
                    className={`w-8 h-8 rounded-md flex items-center justify-center text-white text-sm font-bold shadow-xs ${
                      nodeTypeColors[item.type] ?? "bg-gray-500"
                    }`}
                  >
                    {nodeTypeIcons[item.type] ?? "?"}
                  </div>
                  <div className="flex-1 text-left">
                    <div className="text-sm font-medium text-foreground flex items-center gap-1">
                      {item.label}
                      {!item.enabled && (
                        <span className="ml-2 text-xs text-muted-foreground">(Coming soon)</span>
                      )}
                      {item.kind !== "note" && hasSelectedNode && item.enabled && (
                        <Link className="w-3 h-3 text-primary ml-1" />
                      )}
                    </div>
                    <div className="text-xs text-muted-foreground line-clamp-1">
                      {item.description}
                    </div>
                  </div>
                </button>
              ))}
            </div>
          </div>
        ))}
      </div>

      <div className="mt-6 pt-4 border-t border-border">
        <h4 className="text-xs font-medium text-muted-foreground uppercase tracking-wider mb-2">
          Keyboard Shortcuts
        </h4>
        <div className="space-y-1 text-xs text-muted-foreground">
          <div className="flex justify-between">
            <span>Search nodes</span>
            <kbd className="px-1.5 py-0.5 rounded border border-border/60 bg-muted font-mono text-foreground">
              Ctrl+Shift+F
            </kbd>
          </div>
          <div className="flex justify-between">
            <span>Save</span>
            <kbd className="px-1.5 py-0.5 rounded border border-border/60 bg-muted font-mono text-foreground">
              Ctrl+S
            </kbd>
          </div>
          <div className="flex justify-between">
            <span>Select all</span>
            <kbd className="px-1.5 py-0.5 rounded border border-border/60 bg-muted font-mono text-foreground">
              Ctrl+A
            </kbd>
          </div>
          <div className="flex justify-between">
            <span>Undo</span>
            <kbd className="px-1.5 py-0.5 rounded border border-border/60 bg-muted font-mono text-foreground">
              Ctrl+Z
            </kbd>
          </div>
          <div className="flex justify-between">
            <span>Redo</span>
            <kbd className="px-1.5 py-0.5 rounded border border-border/60 bg-muted font-mono text-foreground">
              Ctrl+Y
            </kbd>
          </div>
          <div className="flex justify-between">
            <span>Copy</span>
            <kbd className="px-1.5 py-0.5 rounded border border-border/60 bg-muted font-mono text-foreground">
              Ctrl+C
            </kbd>
          </div>
          <div className="flex justify-between">
            <span>Paste</span>
            <kbd className="px-1.5 py-0.5 rounded border border-border/60 bg-muted font-mono text-foreground">
              Ctrl+V
            </kbd>
          </div>
          <div className="flex justify-between">
            <span>Duplicate</span>
            <kbd className="px-1.5 py-0.5 rounded border border-border/60 bg-muted font-mono text-foreground">
              Ctrl+D
            </kbd>
          </div>
          <div className="flex justify-between">
            <span>Delete node</span>
            <kbd className="px-1.5 py-0.5 rounded border border-border/60 bg-muted font-mono text-foreground">
              Delete
            </kbd>
          </div>
        </div>
      </div>
    </div>
  );
}
