import { useCallback, useEffect, useMemo, useState, type KeyboardEvent, type Ref } from "react";
import { Link } from "lucide-react";

import { type NodeType } from "../../lib/graph-types";
import type { MarketplacePackage } from "../../lib/api";
import { Input } from "@/components/ui/input";
import {
  buildNodePaletteCatalog,
  getRecentPaletteItems,
  getRecommendedPaletteItems,
  groupPaletteItems,
  loadRecentPaletteIds,
  saveRecentPaletteIds,
  searchNodePaletteCatalog,
  updateRecentPaletteIds,
  type PaletteCatalogItem,
} from "@/lib/node-palette-catalog";

interface NodePaletteProps {
  onAddNode: (nodeType: NodeType, connectToSelected?: boolean) => void;
  onAddNote?: () => void;
  onAddMarketplaceNode?: (pkg: MarketplacePackage, connectToSelected?: boolean) => void;
  marketplaceNodes?: MarketplacePackage[];
  hasSelectedNode?: boolean;
  searchInputRef?: Ref<HTMLInputElement>;
}

const nodeTypeIcons: Record<string, string> = {
  agent: "A",
  prompt: "M",
  http: "H",
  transform: "T",
  output: "O",
  branch: "B",
  merge: "M",
  human_gate: "G",
  memory: "S",
  observation_save: "OS",
  observation_search: "SQ",
  observation_context: "CX",
  observation_timeline: "TL",
  tool: "TL",
  subgraph: "SG",
  note: "N",
};

const nodeTypeColors: Record<string, string> = {
  agent: "bg-sky-500",
  prompt: "bg-violet-500",
  http: "bg-amber-500",
  transform: "bg-blue-500",
  output: "bg-sky-500",
  branch: "bg-rose-500",
  merge: "bg-emerald-500",
  human_gate: "bg-orange-500",
  memory: "bg-teal-500",
  observation_save: "bg-teal-700",
  observation_search: "bg-sky-700",
  observation_context: "bg-blue-700",
  observation_timeline: "bg-violet-700",
  tool: "bg-cyan-500",
  subgraph: "bg-fuchsia-500",
  note: "bg-amber-500",
};

const RECENT_ITEM_LIMIT = 6;
const RECOMMENDED_ITEM_LIMIT = 6;
const EMPTY_MARKETPLACE_NODES: MarketplacePackage[] = [];

function PaletteKeyboardShortcuts() {
  return (
    <div className="mt-6 pt-4 border-t border-border">
      <h4 className="text-xs font-medium text-muted-foreground uppercase tracking-wider mb-2">Keyboard Shortcuts</h4>
      <div className="space-y-1 text-xs text-muted-foreground">
        {[
          ["Open wizard", "Ctrl+W"],
          ["Search steps", "Ctrl+Shift+F"],
          ["Save", "Ctrl+S"],
          ["Select all", "Ctrl+A"],
          ["Undo", "Ctrl+Z"],
          ["Redo", "Ctrl+Y"],
          ["Copy", "Ctrl+C"],
          ["Paste", "Ctrl+V"],
          ["Duplicate", "Ctrl+D"],
          ["Delete step", "Delete"],
          ["Close dialog/wizard", "Esc"],
        ].map(([label, shortcut]) => (
          <div key={label} className="flex justify-between">
            <span>{label}</span>
            <kbd className="px-1.5 py-0.5 rounded border border-border/60 bg-muted font-mono text-foreground">
              {shortcut}
            </kbd>
          </div>
        ))}
      </div>
    </div>
  );
}

export function NodePalette({
  onAddNode,
  onAddNote,
  onAddMarketplaceNode,
  marketplaceNodes = EMPTY_MARKETPLACE_NODES,
  hasSelectedNode = false,
  searchInputRef,
}: NodePaletteProps) {
  const [searchQuery, setSearchQuery] = useState("");
  const [recentItemIds, setRecentItemIds] = useState<string[]>(() => loadRecentPaletteIds());
  const [activeSearchIndex, setActiveSearchIndex] = useState(0);

  useEffect(() => {
    saveRecentPaletteIds(recentItemIds);
  }, [recentItemIds]);

  const paletteItems = useMemo(() => {
    return buildNodePaletteCatalog(marketplaceNodes);
  }, [marketplaceNodes]);

  const filteredItems = useMemo(() => {
    return searchNodePaletteCatalog(paletteItems, searchQuery);
  }, [paletteItems, searchQuery]);

  const recommendedItems = useMemo(() => {
    return getRecommendedPaletteItems(paletteItems, RECOMMENDED_ITEM_LIMIT);
  }, [paletteItems]);

  const recentItems = useMemo(() => {
    return getRecentPaletteItems(paletteItems, recentItemIds, RECENT_ITEM_LIMIT);
  }, [paletteItems, recentItemIds]);

  const searchNavigableItems = useMemo(() => filteredItems.filter((item) => item.enabled), [filteredItems]);

  const groupedItems = useMemo(() => {
    if (searchQuery.trim()) {
      return [["Search results", filteredItems] as [string, PaletteCatalogItem[]]];
    }
    return groupPaletteItems(paletteItems);
  }, [paletteItems, filteredItems, searchQuery]);

  const resolvedActiveSearchIndex =
    searchNavigableItems.length === 0 ? 0 : Math.min(activeSearchIndex, searchNavigableItems.length - 1);
  const activeSearchItemId = searchNavigableItems[resolvedActiveSearchIndex]?.id ?? null;

  const addPaletteItem = useCallback(
    (item: PaletteCatalogItem) => {
      if (!item.enabled) return;

      setRecentItemIds((current) => updateRecentPaletteIds(current, item.id));

      if (item.kind === "note") {
        onAddNote?.();
        return;
      }

      if (item.kind === "marketplace") {
        onAddMarketplaceNode?.(item.package, hasSelectedNode);
        return;
      }

      onAddNode(item.type, hasSelectedNode);
    },
    [hasSelectedNode, onAddMarketplaceNode, onAddNode, onAddNote],
  );

  const handleSearchKeyDown = (event: KeyboardEvent<HTMLInputElement>) => {
    if (!searchQuery.trim() || searchNavigableItems.length === 0) return;

    if (event.key === "ArrowDown") {
      event.preventDefault();
      setActiveSearchIndex((current) => (current + 1) % searchNavigableItems.length);
      return;
    }

    if (event.key === "ArrowUp") {
      event.preventDefault();
      setActiveSearchIndex((current) => (current - 1 + searchNavigableItems.length) % searchNavigableItems.length);
      return;
    }

    if (event.key === "Enter") {
      event.preventDefault();
      const activeItem = searchNavigableItems[resolvedActiveSearchIndex];
      if (!activeItem) return;
      addPaletteItem(activeItem);
      setSearchQuery("");
      setActiveSearchIndex(0);
    }
  };

  return (
    <div className="p-4">
      <h3 className="text-sm font-semibold text-foreground mb-3">Add Steps</h3>

      <div className="mb-4">
        <Input
          ref={searchInputRef}
          type="text"
          placeholder="Search steps"
          value={searchQuery}
          onChange={(e) => {
            setSearchQuery(e.target.value);
            setActiveSearchIndex(0);
          }}
          onKeyDown={handleSearchKeyDown}
          aria-label="Search steps"
          data-testid="palette-query-input"
        />
        {searchQuery.trim() && searchNavigableItems.length > 0 && (
          <p className="mt-2 text-[11px] text-muted-foreground">
            Press{" "}
            <kbd className="px-1 py-0.5 rounded border border-border/60 bg-muted font-mono text-foreground">Enter</kbd>{" "}
            to add{" "}
            <span className="font-medium text-foreground">
              {searchNavigableItems[resolvedActiveSearchIndex]?.label}
            </span>
          </p>
        )}
      </div>

      <p className="text-xs text-muted-foreground mb-4">
        {hasSelectedNode ? "Click to add connected to the selected step" : "Click to add a step to the operating model"}
      </p>

      <div className="space-y-4">
        {filteredItems.length === 0 ? (
          <p className="text-sm text-muted-foreground text-center py-4">No steps match &quot;{searchQuery}&quot;</p>
        ) : null}

        {!searchQuery.trim() && (
          <>
            {recentItems.length > 0 && (
              <div>
                <h4 className="text-[11px] font-semibold text-muted-foreground uppercase tracking-wider mb-2">
                  Recently used
                </h4>
                <div className="flex flex-wrap gap-2">
                  {recentItems.map((item) => (
                    <button
                      key={`recent-${item.id}`}
                      type="button"
                      aria-label={`Recent ${item.label}`}
                      data-testid={`palette-recent-${item.id}`}
                      onClick={() => addPaletteItem(item)}
                      className="rounded-full border border-border bg-background px-2.5 py-1 text-xs font-medium text-foreground hover:border-primary/40 hover:bg-accent/40"
                    >
                      {item.label}
                    </button>
                  ))}
                </div>
              </div>
            )}

            {recommendedItems.length > 0 && (
              <div>
                <h4 className="text-[11px] font-semibold text-muted-foreground uppercase tracking-wider mb-2">
                  Recommended
                </h4>
                <div className="flex flex-wrap gap-2">
                  {recommendedItems.map((item) => (
                    <button
                      key={`recommended-${item.id}`}
                      type="button"
                      aria-label={`Recommended ${item.label}`}
                      data-testid={`palette-recommended-${item.id}`}
                      onClick={() => addPaletteItem(item)}
                      className="rounded-full border border-primary/30 bg-primary/5 px-2.5 py-1 text-xs font-medium text-foreground hover:bg-primary/10"
                    >
                      {item.label}
                    </button>
                  ))}
                </div>
              </div>
            )}
          </>
        )}

        {groupedItems.map(([category, items]) => (
          <div key={category}>
            <h4 className="text-[11px] font-semibold text-muted-foreground uppercase tracking-wider mb-2">
              {category}
            </h4>
            <div className="space-y-2">
              {items.map((item) => (
                <button
                  key={item.id}
                  type="button"
                  aria-label={item.label}
                  data-testid={`palette-item-${item.id}`}
                  onClick={() => addPaletteItem(item)}
                  disabled={!item.enabled}
                  className={`w-full flex min-h-11 items-center gap-3 rounded-lg border p-3 transition-[color,background-color,border-color,box-shadow] motion-reduce:transition-none ${
                    activeSearchItemId === item.id && searchQuery.trim()
                      ? "border-primary ring-1 ring-primary/40 bg-accent/50"
                      : ""
                  } ${
                    item.enabled
                      ? "border-border bg-background/40 hover:border-primary/30 hover:bg-accent/40 cursor-pointer"
                      : "border-border/50 bg-muted/30 cursor-not-allowed opacity-60"
                  }`}
                >
                  <div
                    aria-hidden="true"
                    className={`size-8 rounded-md flex items-center justify-center text-white text-sm font-bold shadow-xs ${
                      item.kind === "marketplace" ? "bg-cyan-500" : (nodeTypeColors[item.type] ?? "bg-neutral-500")
                    }`}
                  >
                    {item.kind === "marketplace"
                      ? item.label.slice(0, 2).toUpperCase()
                      : (nodeTypeIcons[item.type] ?? "?")}
                  </div>
                  <div className="flex-1 text-left">
                    <div className="text-sm font-medium text-foreground flex items-center gap-1">
                      {item.label}
                      {!item.enabled && (
                        <span className="ml-2 text-xs text-muted-foreground">
                          {item.kind === "marketplace" ? "(Unavailable)" : "(Coming soon)"}
                        </span>
                      )}
                      {item.kind !== "note" && hasSelectedNode && item.enabled && (
                        <Link className="size-3 text-primary ml-1" />
                      )}
                    </div>
                    <div className="text-xs text-muted-foreground line-clamp-1">{item.description}</div>
                    <div className="mt-1 flex flex-wrap gap-1">
                      {(item.requiresCredential ? ["Credential", ...item.badges] : item.badges)
                        .filter((badge, index, all) => all.indexOf(badge) === index)
                        .slice(0, 3)
                        .map((badge) => (
                          <span
                            key={`${item.id}-${badge}`}
                            className="rounded-full border border-border/70 bg-muted px-1.5 py-0.5 text-[10px] font-medium text-muted-foreground"
                          >
                            {badge}
                          </span>
                        ))}
                    </div>
                  </div>
                </button>
              ))}
            </div>
          </div>
        ))}
      </div>

      <PaletteKeyboardShortcuts />
    </div>
  );
}
