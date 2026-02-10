import { useCallback, useEffect, useMemo, useState, type KeyboardEvent, type RefObject } from "react";
import { Search } from "lucide-react";

import { type NodeType } from "../../lib/graph-types";
import type { MarketplacePackage } from "../../lib/api";
import { cn } from "@/lib/utils";
import { NODE_VISUALS } from "./nodes/nodeShapes";
import {
  buildNodePaletteCatalog,
  getRecentPaletteItems,
  loadRecentPaletteIds,
  saveRecentPaletteIds,
  searchNodePaletteCatalog,
  updateRecentPaletteIds,
  groupPaletteItems,
  type PaletteCatalogItem,
} from "@/lib/node-palette-catalog";

interface NodePaletteProps {
  onAddNode: (nodeType: NodeType, connectToSelected?: boolean) => void;
  onAddNote?: () => void;
  onAddMarketplaceNode?: (pkg: MarketplacePackage, connectToSelected?: boolean) => void;
  marketplaceNodes?: MarketplacePackage[];
  hasSelectedNode?: boolean;
  searchInputRef?: RefObject<HTMLInputElement | null>;
}

const RECENT_ITEM_LIMIT = 6;

export function NodePalette({
  onAddNode,
  onAddNote,
  onAddMarketplaceNode,
  marketplaceNodes = [],
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
    searchNavigableItems.length === 0
      ? 0
      : Math.min(activeSearchIndex, searchNavigableItems.length - 1);
  const activeSearchItemId = searchNavigableItems[resolvedActiveSearchIndex]?.id ?? null;

  const addPaletteItem = useCallback((item: PaletteCatalogItem) => {
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
  }, [hasSelectedNode, onAddMarketplaceNode, onAddNode, onAddNote]);

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
      <h3 className="text-sm font-semibold text-foreground mb-3">Nodes</h3>

      {/* Search */}
      <div className="relative mb-4">
        <Search className="absolute left-3 top-1/2 -translate-y-1/2 h-4 w-4 text-muted-foreground pointer-events-none" />
        <input
          ref={searchInputRef}
          type="text"
          placeholder="Search tools..."
          value={searchQuery}
          onChange={(e) => {
            setSearchQuery(e.target.value);
            setActiveSearchIndex(0);
          }}
          onKeyDown={handleSearchKeyDown}
          aria-label="Search nodes"
          className="w-full rounded-lg border border-border bg-background/60 pl-9 pr-3 py-2 text-sm text-foreground placeholder:text-muted-foreground outline-none focus:border-primary/50 focus:ring-1 focus:ring-primary/30 transition-colors"
        />
        {searchQuery.trim() && searchNavigableItems.length > 0 && (
          <p className="mt-2 text-[11px] text-muted-foreground">
            Press <kbd className="px-1 py-0.5 rounded border border-border/60 bg-muted font-mono text-foreground">Enter</kbd> to add{" "}
            <span className="font-medium text-foreground">{searchNavigableItems[resolvedActiveSearchIndex]?.label}</span>
          </p>
        )}
      </div>

      {/* Recently used */}
      {!searchQuery.trim() && recentItems.length > 0 && (
        <div className="mb-4">
          <h4 className="text-[11px] font-semibold text-muted-foreground uppercase tracking-wider mb-2">
            Recently used
          </h4>
          <div className="flex flex-wrap gap-1.5">
            {recentItems.map((item) => (
              <button
                key={`recent-${item.id}`}
                type="button"
                aria-label={`Recent ${item.label}`}
                onClick={() => addPaletteItem(item)}
                className="rounded-full border border-border bg-background/50 px-2.5 py-1 text-xs font-medium text-foreground hover:border-primary/40 hover:bg-accent/40 transition-colors"
              >
                {item.label}
              </button>
            ))}
          </div>
        </div>
      )}

      {/* Node list */}
      <div className="space-y-3">
        {filteredItems.length === 0 && (
          <p className="text-sm text-muted-foreground text-center py-4">
            No nodes match &quot;{searchQuery}&quot;
          </p>
        )}

        {groupedItems.map(([category, items]) => (
          <div key={category}>
            <h4 className="text-[11px] font-semibold text-muted-foreground uppercase tracking-wider mb-1.5">
              {category}
            </h4>
            <div className="space-y-0.5">
              {items.map((item) => {
                const visual = NODE_VISUALS[item.type];
                const Icon = visual?.icon;
                const isActive = activeSearchItemId === item.id && searchQuery.trim();

                return (
                  <button
                    key={item.id}
                    type="button"
                    aria-label={item.label}
                    onClick={() => addPaletteItem(item)}
                    disabled={!item.enabled}
                    className={cn(
                      "w-full flex items-center gap-3 px-3 py-2.5 rounded-lg transition-all",
                      isActive && "ring-1 ring-primary/40 bg-accent/50",
                      item.enabled
                        ? "hover:bg-accent/40 cursor-pointer"
                        : "cursor-not-allowed opacity-50",
                    )}
                  >
                    <div
                      aria-hidden="true"
                      className={cn(
                        "w-8 h-8 rounded-lg flex items-center justify-center text-white shadow-sm shrink-0",
                        visual?.bgClass ?? "bg-gray-500",
                      )}
                    >
                      {Icon ? (
                        <Icon className="w-4 h-4" />
                      ) : (
                        <span className="text-xs font-bold">
                          {item.label.slice(0, 2).toUpperCase()}
                        </span>
                      )}
                    </div>
                    <span className="text-sm font-medium text-foreground truncate">
                      {item.label}
                    </span>
                    {!item.enabled && (
                      <span className="ml-auto text-[10px] text-muted-foreground">Soon</span>
                    )}
                  </button>
                );
              })}
            </div>
          </div>
        ))}
      </div>
    </div>
  );
}
