"use client";

import { useMemo, useState } from "react";
import {
  MessageSquare,
  FileText,
  Tags,
  Languages,
  Mail,
  Bell,
  Download,
  Upload,
  Shuffle,
  Filter,
  GitBranch,
  UserCheck,
  GitMerge,
  Database,
  Search,
  LogOut,
  Sparkles,
} from "lucide-react";
import { cn } from "@/lib/utils";
import { Input } from "@/components/ui/input";
import {
  QUICK_NODE_PRESETS,
  PRESET_CATEGORIES,
  getPopularPresets,
  searchPresets,
  type QuickNodePreset,
  type PresetCategory,
} from "@/lib/quick-node-presets";

/**
 * Icon mapping for preset icons
 */
const ICON_MAP: Record<string, React.ComponentType<{ className?: string }>> = {
  MessageSquare,
  FileText,
  Tags,
  Languages,
  Mail,
  Bell,
  Download,
  Upload,
  Shuffle,
  Filter,
  GitBranch,
  UserCheck,
  GitMerge,
  Database,
  Search,
  LogOut,
};

interface QuickNodePaletteProps {
  onSelectPreset: (preset: QuickNodePreset) => void;
  showSearch?: boolean;
  showCategories?: boolean;
  compact?: boolean;
  className?: string;
}

/**
 * Quick Node Palette - displays preset templates for quick node creation
 */
export function QuickNodePalette({
  onSelectPreset,
  showSearch = true,
  showCategories = true,
  compact = false,
  className,
}: QuickNodePaletteProps) {
  const [searchQuery, setSearchQuery] = useState("");
  const [selectedCategory, setSelectedCategory] = useState<PresetCategory | null>(null);

  const displayedPresets = useMemo(() => {
    if (searchQuery.trim()) {
      return searchPresets(searchQuery);
    }
    if (selectedCategory) {
      return QUICK_NODE_PRESETS.filter((p) => p.category === selectedCategory);
    }
    return getPopularPresets(compact ? 4 : 12);
  }, [searchQuery, selectedCategory, compact]);

  const categories = Object.entries(PRESET_CATEGORIES) as [PresetCategory, { label: string; description: string }][];

  return (
    <div className={cn("space-y-3", className)}>
      {/* Header */}
      <div className="flex items-center gap-2">
        <Sparkles className="w-4 h-4 text-violet-500" />
        <h4 className="text-sm font-medium text-foreground">Quick Nodes</h4>
      </div>

      {/* Search */}
      {showSearch && (
        <Input
          type="text"
          placeholder="Search presets..."
          value={searchQuery}
          onChange={(e) => {
            setSearchQuery(e.target.value);
            if (e.target.value) setSelectedCategory(null);
          }}
          className="text-sm"
        />
      )}

      {/* Category Pills */}
      {showCategories && !searchQuery && (
        <div className="flex flex-wrap gap-1.5">
          <button
            type="button"
            onClick={() => setSelectedCategory(null)}
            className={cn(
              "px-2 py-1 rounded-full text-xs font-medium transition-colors",
              selectedCategory === null
                ? "bg-primary text-primary-foreground"
                : "bg-muted text-muted-foreground hover:bg-muted/80"
            )}
          >
            Popular
          </button>
          {categories.map(([key, { label }]) => (
            <button
              key={key}
              type="button"
              onClick={() => setSelectedCategory(key)}
              className={cn(
                "px-2 py-1 rounded-full text-xs font-medium transition-colors",
                selectedCategory === key
                  ? "bg-primary text-primary-foreground"
                  : "bg-muted text-muted-foreground hover:bg-muted/80"
              )}
            >
              {label}
            </button>
          ))}
        </div>
      )}

      {/* Presets Grid */}
      <div className={cn("grid gap-2", compact ? "grid-cols-2" : "grid-cols-1")}>
        {displayedPresets.length === 0 ? (
          <p className="text-xs text-muted-foreground col-span-full text-center py-4">
            No presets found for &quot;{searchQuery}&quot;
          </p>
        ) : (
          displayedPresets.map((preset) => (
            <PresetCard
              key={preset.id}
              preset={preset}
              compact={compact}
              onClick={() => onSelectPreset(preset)}
            />
          ))
        )}
      </div>

      {/* Show All Link */}
      {!searchQuery && !selectedCategory && !compact && (
        <p className="text-xs text-muted-foreground text-center">
          Showing popular presets.{" "}
          <button
            type="button"
            onClick={() => setSelectedCategory("ai")}
            className="text-primary hover:underline"
          >
            Browse all categories
          </button>
        </p>
      )}
    </div>
  );
}

interface PresetCardProps {
  preset: QuickNodePreset;
  compact?: boolean;
  onClick: () => void;
}

function PresetCard({ preset, compact = false, onClick }: PresetCardProps) {
  const IconComponent = ICON_MAP[preset.icon] || Sparkles;

  return (
    <button
      type="button"
      onClick={onClick}
      className={cn(
        "flex items-start gap-3 p-3 rounded-lg border border-border bg-background/60 hover:bg-accent/50 hover:border-primary/30 transition-all text-left group",
        compact && "p-2"
      )}
    >
      <div
        className={cn(
          "flex items-center justify-center rounded-md bg-primary/10 text-primary shrink-0",
          compact ? "w-8 h-8" : "w-10 h-10"
        )}
      >
        <IconComponent className={cn(compact ? "w-4 h-4" : "w-5 h-5")} />
      </div>
      <div className="flex-1 min-w-0">
        <p
          className={cn(
            "font-medium text-foreground truncate",
            compact ? "text-xs" : "text-sm"
          )}
        >
          {preset.name}
        </p>
        {!compact && (
          <p className="text-xs text-muted-foreground line-clamp-2 mt-0.5">
            {preset.description}
          </p>
        )}
      </div>
    </button>
  );
}

export default QuickNodePalette;
