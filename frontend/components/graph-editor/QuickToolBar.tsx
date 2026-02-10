"use client";

import { useMemo, useState, type ComponentType } from "react";
import {
  AlertCircle,
  BookOpen,
  Brain,
  Briefcase,
  CheckCircle2,
  Cloud,
  Database,
  FileText,
  Folder,
  Github,
  Globe,
  Hash,
  Layers,
  Link2,
  Mail,
  MessageCircle,
  Plus,
  Search,
  Send,
  Sheet,
  Sparkles,
  Table,
  Zap,
} from "lucide-react";
import { cn } from "@/lib/utils";
import type { MarketplacePackage } from "@/lib/api";
import {
  Badge,
  Dialog,
  DialogContent,
  DialogDescription,
  DialogHeader,
  DialogTitle,
  Input,
} from "@/components/ui";

const INTEGRATION_ICONS: Record<
  string,
  { icon: ComponentType<{ className?: string }>; color: string }
> = {
  Send: { icon: Send, color: "bg-blue-500" },
  BookOpen: { icon: BookOpen, color: "bg-stone-700" },
  Hash: { icon: Hash, color: "bg-violet-500" },
  MessageCircle: { icon: MessageCircle, color: "bg-indigo-500" },
  Sparkles: { icon: Sparkles, color: "bg-emerald-600" },
  Github: { icon: Github, color: "bg-zinc-700" },
  Table: { icon: Table, color: "bg-green-600" },
  Folder: { icon: Folder, color: "bg-amber-500" },
  FileText: { icon: FileText, color: "bg-cyan-600" },
  Briefcase: { icon: Briefcase, color: "bg-orange-600" },
  Database: { icon: Database, color: "bg-pink-600" },
  Brain: { icon: Brain, color: "bg-violet-600" },
  Globe: { icon: Globe, color: "bg-blue-600" },
  Mail: { icon: Mail, color: "bg-red-500" },
  Sheet: { icon: Sheet, color: "bg-green-500" },
  Cloud: { icon: Cloud, color: "bg-sky-500" },
  Layers: { icon: Layers, color: "bg-fuchsia-500" },
  Zap: { icon: Zap, color: "bg-yellow-500" },
};

/** Default integration tiles shown when no marketplace packages are installed */
const DEFAULT_TILES: Array<{ label: string; iconKey: string }> = [
  { label: "LLM", iconKey: "Brain" },
  { label: "OpenAI", iconKey: "Sparkles" },
  { label: "Notion", iconKey: "BookOpen" },
  { label: "Slack", iconKey: "Hash" },
  { label: "Linear", iconKey: "Zap" },
  { label: "Sheets", iconKey: "Sheet" },
  { label: "GitHub", iconKey: "Github" },
  { label: "Stripe", iconKey: "Briefcase" },
  { label: "Drive", iconKey: "Folder" },
  { label: "Dropbox", iconKey: "Cloud" },
  { label: "Email", iconKey: "Mail" },
  { label: "HTTP", iconKey: "Globe" },
  { label: "DB", iconKey: "Database" },
  { label: "Layers", iconKey: "Layers" },
];

interface QuickToolBarProps {
  marketplaceNodes: MarketplacePackage[];
  onSelectPackage: (pkg: MarketplacePackage) => void;
  hasSelectedNode?: boolean;
  className?: string;
}

const FEATURED_PACKAGE_ORDER = [
  "whatsapp-send-message",
  "gmail-list-unread",
  "google-calendar-list-events",
  "google-tasks-list",
  "slack-alerts",
  "notion-page-upsert",
  "gmail-send-email",
  "telegram-send-message",
];

const ICON_BY_KEY: Record<string, string> = {
  slack: "Hash",
  notion: "BookOpen",
  gmail: "Send",
  jira: "MessageCircle",
  linear: "Zap",
  hubspot: "Briefcase",
  "google-drive": "Folder",
  telegram: "Send",
  whatsapp: "MessageCircle",
  twilio: "MessageCircle",
  calendar: "BookOpen",
  tasks: "Table",
  github: "Github",
  salesforce: "Database",
  stripe: "Briefcase",
  openai: "Sparkles",
  anthropic: "Brain",
};

const pickIconKey = (pkg: MarketplacePackage): string => {
  const icon = String(pkg.icon || "").toLowerCase().trim();
  const slug = pkg.slug.toLowerCase();
  for (const [needle, key] of Object.entries(ICON_BY_KEY)) {
    if (icon.includes(needle) || slug.includes(needle)) {
      return key;
    }
  }
  return "Sparkles";
};

const packageRank = (pkg: MarketplacePackage): number => {
  const index = FEATURED_PACKAGE_ORDER.indexOf(pkg.slug);
  return index === -1 ? FEATURED_PACKAGE_ORDER.length + 1 : index;
};

export function QuickToolBar({
  marketplaceNodes,
  onSelectPackage,
  hasSelectedNode = false,
  className,
}: QuickToolBarProps) {
  const [isBrowseOpen, setIsBrowseOpen] = useState(false);
  const [searchQuery, setSearchQuery] = useState("");

  const integrations = useMemo(() => {
    return [...marketplaceNodes].sort((a, b) => {
      const rankDiff = packageRank(a) - packageRank(b);
      if (rankDiff !== 0) return rankDiff;
      return a.name.localeCompare(b.name);
    });
  }, [marketplaceNodes]);

  const filtered = useMemo(() => {
    const query = searchQuery.trim().toLowerCase();
    if (!query) return integrations;
    return integrations.filter((pkg) => {
      return (
        pkg.name.toLowerCase().includes(query) ||
        pkg.slug.toLowerCase().includes(query) ||
        pkg.summary.toLowerCase().includes(query)
      );
    });
  }, [integrations, searchQuery]);

  const handleSelectPackage = (pkg: MarketplacePackage) => {
    onSelectPackage(pkg);
    setIsBrowseOpen(false);
    setSearchQuery("");
  };

  // Build the tile list from marketplace packages or defaults
  const tiles = useMemo(() => {
    if (integrations.length > 0) {
      return integrations.slice(0, 14).map((pkg) => {
        const iconKey = pickIconKey(pkg);
        const config = INTEGRATION_ICONS[iconKey] ?? INTEGRATION_ICONS.Sparkles;
        return {
          key: pkg.slug,
          label: pkg.name,
          icon: config.icon,
          color: config.color,
          onClick: () => handleSelectPackage(pkg),
        };
      });
    }
    return DEFAULT_TILES.map((tile) => {
      const config = INTEGRATION_ICONS[tile.iconKey] ?? INTEGRATION_ICONS.Sparkles;
      return {
        key: tile.label,
        label: tile.label,
        icon: config.icon,
        color: config.color,
        onClick: undefined as (() => void) | undefined,
      };
    });
  }, [integrations]);

  return (
    <>
      <div
        className={cn(
          "flex items-center gap-1 px-3 py-2 border-b border-border bg-card/50 backdrop-blur-sm overflow-x-auto",
          className,
        )}
      >
        {tiles.map((tile) => {
          const Icon = tile.icon;
          return (
            <button
              key={tile.key}
              type="button"
              onClick={tile.onClick}
              disabled={!tile.onClick}
              title={tile.label}
              className={cn(
                "flex flex-col items-center gap-1 px-2 py-1.5 rounded-lg shrink-0 transition-all",
                tile.onClick
                  ? "hover:bg-accent/40 cursor-pointer"
                  : "opacity-50 cursor-default",
              )}
            >
              <div className={cn("w-9 h-9 rounded-lg flex items-center justify-center text-white shadow-sm", tile.color)}>
                <Icon className="w-4.5 h-4.5" />
              </div>
              <span className="text-[10px] text-muted-foreground font-medium truncate max-w-[56px]">
                {tile.label}
              </span>
            </button>
          );
        })}

        {/* Browse / + button */}
        <button
          type="button"
          onClick={() => setIsBrowseOpen(true)}
          aria-label="Browse integration tools"
          className="flex flex-col items-center gap-1 px-2 py-1.5 rounded-lg shrink-0 transition-all hover:bg-accent/40"
        >
          <div className="w-9 h-9 rounded-lg flex items-center justify-center border-2 border-dashed border-border text-muted-foreground">
            <Plus className="w-4 h-4" />
          </div>
          <span className="text-[10px] text-muted-foreground font-medium">More</span>
        </button>
      </div>

      {/* Browse dialog */}
      <Dialog open={isBrowseOpen} onOpenChange={setIsBrowseOpen}>
        <DialogContent className="max-w-3xl overscroll-contain">
          <DialogHeader>
            <DialogTitle>Integration Tools</DialogTitle>
            <DialogDescription>
              Add installed marketplace integrations to your graph with one click.
            </DialogDescription>
          </DialogHeader>
          <div className="space-y-3">
            <div className="relative">
              <Search className="pointer-events-none absolute left-2.5 top-2.5 h-4 w-4 text-muted-foreground" />
              <Input
                type="text"
                name="integration-search"
                autoComplete="off"
                aria-label="Search integration tools"
                placeholder="Search integrations..."
                value={searchQuery}
                onChange={(event) => setSearchQuery(event.target.value)}
                className="pl-9"
              />
            </div>
            <div className="max-h-[65vh] space-y-2 overflow-y-auto pr-1">
              {filtered.length === 0 ? (
                <div className="rounded-lg border border-dashed border-border p-5 text-sm text-muted-foreground">
                  <div className="flex items-center gap-2">
                    <AlertCircle className="h-4 w-4" aria-hidden="true" />
                    {integrations.length === 0
                      ? "No integration packages are installed yet."
                      : "No matching integration found."}
                  </div>
                </div>
              ) : (
                filtered.map((pkg) => {
                  const iconKey = pickIconKey(pkg);
                  const config = INTEGRATION_ICONS[iconKey] ?? INTEGRATION_ICONS.Sparkles;
                  const IconComponent = config.icon;
                  return (
                    <button
                      key={pkg.slug}
                      type="button"
                      onClick={() => handleSelectPackage(pkg)}
                      className="flex w-full items-start gap-3 rounded-lg border border-border bg-background/70 p-3 text-left transition-colors hover:border-primary/40 hover:bg-accent/40"
                    >
                      <span className={cn("flex h-8 w-8 items-center justify-center rounded-md text-white", config.color)}>
                        <IconComponent className="h-4 w-4" aria-hidden="true" />
                      </span>
                      <div className="min-w-0 flex-1">
                        <div className="flex items-center gap-2">
                          <p className="truncate text-sm font-medium text-foreground">{pkg.name}</p>
                          <Badge variant="outline" className="text-[10px] uppercase tracking-wide">
                            {pkg.category}
                          </Badge>
                        </div>
                        <p className="line-clamp-2 text-xs text-muted-foreground">{pkg.summary || "Installed integration package"}</p>
                      </div>
                      <CheckCircle2 className="mt-1 h-4 w-4 text-emerald-500" aria-hidden="true" />
                    </button>
                  );
                })
              )}
            </div>
          </div>
        </DialogContent>
      </Dialog>
    </>
  );
}

export default QuickToolBar;
