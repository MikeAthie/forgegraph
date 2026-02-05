"use client";

import { useMemo, useState, type ComponentType } from "react";
import {
  AlertCircle,
  BookOpen,
  Briefcase,
  CheckCircle2,
  Database,
  FileText,
  Folder,
  Github,
  Hash,
  Link2,
  MessageCircle,
  Plus,
  Search,
  Send,
  Sparkles,
  Table,
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

/**
 * Icon mapping for integration tools
 */
const INTEGRATION_ICONS: Record<
  string,
  { icon: ComponentType<{ className?: string }>; color: string; dot: string }
> = {
  Send: { icon: Send, color: "bg-blue-500", dot: "text-blue-500" },
  BookOpen: { icon: BookOpen, color: "bg-stone-700", dot: "text-stone-600" },
  Hash: { icon: Hash, color: "bg-violet-500", dot: "text-violet-500" },
  MessageCircle: { icon: MessageCircle, color: "bg-indigo-500", dot: "text-indigo-500" },
  Sparkles: { icon: Sparkles, color: "bg-emerald-600", dot: "text-emerald-500" },
  Github: { icon: Github, color: "bg-zinc-700", dot: "text-zinc-500" },
  Table: { icon: Table, color: "bg-green-600", dot: "text-green-500" },
  Folder: { icon: Folder, color: "bg-amber-500", dot: "text-amber-500" },
  FileText: { icon: FileText, color: "bg-cyan-600", dot: "text-cyan-500" },
  Briefcase: { icon: Briefcase, color: "bg-orange-600", dot: "text-orange-500" },
  Database: { icon: Database, color: "bg-pink-600", dot: "text-pink-500" },
};

interface QuickToolBarProps {
  marketplaceNodes: MarketplacePackage[];
  onSelectPackage: (pkg: MarketplacePackage) => void;
  hasSelectedNode?: boolean;
  className?: string;
}

const FEATURED_TOOL_COUNT = 6;
const FEATURED_PACKAGE_ORDER = [
  "slack-alerts",
  "notion-page-upsert",
  "gmail-send-email",
  "jira-issue-create",
  "linear-issue-create",
  "hubspot-contact-upsert",
];

const ICON_BY_KEY: Record<string, keyof typeof INTEGRATION_ICONS> = {
  slack: "Hash",
  notion: "BookOpen",
  gmail: "Send",
  jira: "MessageCircle",
  linear: "Sparkles",
  hubspot: "Briefcase",
  "google-drive": "Folder",
  telegram: "Send",
  github: "Github",
  salesforce: "Database",
};

const pickIconKey = (pkg: MarketplacePackage): keyof typeof INTEGRATION_ICONS => {
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

/**
 * Quick Tool Bar - horizontal bar of popular API integrations for fast node creation
 */
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
  const featured = useMemo(
    () => integrations.slice(0, FEATURED_TOOL_COUNT),
    [integrations],
  );
  const filtered = useMemo(() => {
    const query = searchQuery.trim().toLowerCase();
    if (!query) return integrations;
    return integrations.filter((pkg) => {
      return (
        pkg.name.toLowerCase().includes(query) ||
        pkg.slug.toLowerCase().includes(query) ||
        pkg.summary.toLowerCase().includes(query) ||
        String(pkg.icon || "").toLowerCase().includes(query)
      );
    });
  }, [integrations, searchQuery]);
  const extraCount = Math.max(integrations.length - featured.length, 0);

  const handleSelectPackage = (pkg: MarketplacePackage) => {
    onSelectPackage(pkg);
    setIsBrowseOpen(false);
    setSearchQuery("");
  };

  return (
    <>
      <div
        className={cn(
          "flex max-w-[calc(100vw-2rem)] items-center gap-2 rounded-xl border border-border/80 bg-background/75 px-2 py-1.5 shadow-sm backdrop-blur-md",
          className,
        )}
      >
        <div className="hidden md:flex items-center gap-2 pr-2">
          <div className="flex h-7 w-7 items-center justify-center rounded-lg bg-muted/70 text-foreground">
            <Sparkles className="h-4 w-4" aria-hidden="true" />
          </div>
          <div className="leading-none">
            <p className="text-xs font-semibold text-foreground">Quick Tools</p>
            <p className="text-[10px] text-muted-foreground">{hasSelectedNode ? "Adds and links from selected node" : "Adds standalone node"}</p>
          </div>
        </div>

        <div className="h-6 w-px bg-border/70 hidden md:block" />

        <div className="flex min-w-0 items-center gap-1 overflow-x-auto pr-1">
          {integrations.length === 0 && (
            <p className="hidden sm:block text-xs text-muted-foreground px-2">
              Install integrations in Marketplace to enable quick add.
            </p>
          )}
          {featured.map((pkg) => {
            const iconConfig = INTEGRATION_ICONS[pickIconKey(pkg)] || {
              icon: Sparkles,
              color: "bg-primary",
              dot: "text-primary",
            };
            const IconComponent = iconConfig.icon;
            return (
              <button
                key={pkg.slug}
                type="button"
                onClick={() => handleSelectPackage(pkg)}
                title={`Add ${pkg.name}`}
                aria-label={`Add ${pkg.name} integration node`}
                className="group flex shrink-0 touch-manipulation items-center gap-1.5 rounded-lg border border-transparent bg-background/70 px-2 py-1.5 text-xs font-medium text-foreground transition-colors transition-transform transition-shadow hover:-translate-y-0.5 hover:border-primary/40 hover:bg-background hover:shadow-sm focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-primary/70 focus-visible:ring-offset-1 motion-reduce:transform-none motion-reduce:transition-none"
              >
                <span className={cn("flex h-5 w-5 items-center justify-center rounded-md text-white", iconConfig.color)}>
                  <IconComponent className="h-3.5 w-3.5" aria-hidden="true" />
                </span>
                <span className="hidden sm:inline">{pkg.name}</span>
                {hasSelectedNode && (
                  <Link2 className={cn("h-3 w-3", iconConfig.dot)} aria-hidden="true" />
                )}
              </button>
            );
          })}
        </div>

        <button
          type="button"
          onClick={() => setIsBrowseOpen(true)}
          aria-label="Browse integration tools"
          className="flex shrink-0 touch-manipulation items-center gap-1 rounded-lg border border-border bg-muted/40 px-2 py-1.5 text-xs font-medium text-foreground transition-colors hover:bg-muted/70 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-primary/70 focus-visible:ring-offset-1"
        >
          <Plus className="h-3.5 w-3.5" aria-hidden="true" />
          <span className="hidden sm:inline">Browse</span>
          {extraCount > 0 && (
            <span className="rounded-full bg-background px-1.5 py-0.5 text-[10px] text-muted-foreground">
              +{extraCount}
            </span>
          )}
        </button>
      </div>

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
                placeholder="Search integrations…"
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
                  const iconConfig = INTEGRATION_ICONS[pickIconKey(pkg)] || {
                    icon: Sparkles,
                    color: "bg-primary",
                    dot: "text-primary",
                  };
                  const IconComponent = iconConfig.icon;
                  return (
                    <button
                      key={pkg.slug}
                      type="button"
                      onClick={() => handleSelectPackage(pkg)}
                      className="flex w-full touch-manipulation items-start gap-3 rounded-lg border border-border bg-background/70 p-3 text-left transition-colors hover:border-primary/40 hover:bg-accent/40 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-primary/70 focus-visible:ring-offset-1"
                    >
                      <span className={cn("flex h-8 w-8 items-center justify-center rounded-md text-white", iconConfig.color)}>
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
