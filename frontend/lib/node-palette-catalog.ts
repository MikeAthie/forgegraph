import { PHASE2_NODE_TYPES, type NodeType } from "./graph-types";
import type { MarketplacePackage } from "./api";
import {
  canAddMarketplacePackageToEditor,
  getMarketplacePackageBadges,
  getMarketplacePackageDescription,
} from "./marketplace-runtime";

export type PaletteCatalogItem =
  | {
      kind: "node";
      id: string;
      type: NodeType;
      label: string;
      description: string;
      enabled: boolean;
      category: string;
      tags: string[];
      badges: string[];
      requiresCredential: boolean;
    }
  | {
      kind: "note";
      id: "note";
      type: "note";
      label: "Note";
      description: string;
      enabled: true;
      category: string;
      tags: string[];
      badges: string[];
      requiresCredential: false;
    }
  | {
      kind: "marketplace";
      id: string;
      type: `marketplace:${string}`;
      label: string;
      description: string;
      enabled: boolean;
      category: "Marketplace";
      tags: string[];
      badges: string[];
      requiresCredential: true;
      package: MarketplacePackage;
    };

export const CATEGORY_ORDER = [
  "Recommended",
  "Recently used",
  "AI",
  "Logic",
  "Extensibility",
  "Marketplace",
  "Memory",
  "I/O",
  "Annotations",
] as const;

const NODE_CATEGORIES: Record<NodeType | "note", string> = {
  agent: "AI",
  prompt: "AI",
  http: "I/O",
  transform: "Logic",
  output: "I/O",
  branch: "Logic",
  merge: "Logic",
  human_gate: "Logic",
  memory: "Memory",
  observation_save: "Memory",
  observation_search: "Memory",
  observation_context: "Memory",
  observation_timeline: "Memory",
  tool: "Extensibility",
  subgraph: "Extensibility",
  note: "Annotations",
};

const NODE_TAGS: Record<NodeType | "note", string[]> = {
  agent: ["agent", "tools", "reasoning", "loop", "llm"],
  prompt: ["llm", "model", "template", "gpt", "chat"],
  http: ["api", "webhook", "rest", "request", "integration"],
  transform: ["map", "filter", "json", "expression", "data"],
  output: ["result", "return", "response", "final"],
  branch: ["if", "else", "condition", "route"],
  merge: ["join", "combine", "aggregate", "paths"],
  human_gate: ["approval", "review", "manual", "human"],
  memory: ["state", "context", "history", "recall"],
  observation_save: ["memory", "observation", "save", "persist", "curated"],
  observation_search: ["memory", "observation", "search", "query", "retrieve"],
  observation_context: ["memory", "context", "observation", "prompt", "agent"],
  observation_timeline: ["memory", "timeline", "history", "observation", "recent"],
  tool: ["function", "action", "external", "registry"],
  subgraph: ["reuse", "nested", "workflow", "compose"],
  note: ["annotation", "comment", "documentation"],
};

const NODE_BADGES: Record<NodeType | "note", string[]> = {
  agent: ["Agent", "LLM", "Credential"],
  prompt: ["LLM", "Credential"],
  http: ["API", "Credential"],
  transform: ["Data"],
  output: ["Terminal"],
  branch: ["Control"],
  merge: ["Control"],
  human_gate: ["Human"],
  memory: ["State"],
  observation_save: ["Curated Memory", "Write"],
  observation_search: ["Curated Memory", "Search"],
  observation_context: ["Curated Memory", "Context"],
  observation_timeline: ["Curated Memory", "Timeline"],
  tool: ["Action", "Credential"],
  subgraph: ["Composable"],
  note: ["Annotation"],
};

const RECOMMENDED_ITEM_IDS = ["agent", "prompt", "http", "transform", "output"];
const RECENT_STORAGE_KEY = "forgegraph.node_palette.recent";

function tokenize(value: string): string[] {
  return value
    .toLowerCase()
    .split(/[^a-z0-9]+/)
    .map((part) => part.trim())
    .filter(Boolean);
}

function scoreItemForQuery(item: PaletteCatalogItem, query: string): number {
  const trimmed = query.trim().toLowerCase();
  if (!trimmed) return 0;

  const tokens = tokenize(trimmed);
  const label = item.label.toLowerCase();
  const type = item.type.toLowerCase();
  const description = item.description.toLowerCase();
  const category = item.category.toLowerCase();
  const tags = item.tags.map((tag) => tag.toLowerCase());

  let score = 0;

  for (const token of tokens) {
    if (label === token) score += 100;
    else if (label.startsWith(token)) score += 70;
    else if (label.includes(token)) score += 45;

    if (type === token) score += 80;
    else if (type.includes(token)) score += 35;

    if (category.includes(token)) score += 18;
    if (description.includes(token)) score += 12;
    if (tags.some((tag) => tag === token)) score += 40;
    else if (tags.some((tag) => tag.includes(token))) score += 24;
  }

  if (item.enabled) score += 6;
  return score;
}

export function buildNodePaletteCatalog(marketplaceNodes: MarketplacePackage[] = []): PaletteCatalogItem[] {
  const baseItems: PaletteCatalogItem[] = PHASE2_NODE_TYPES.map((nodeType) => ({
    kind: "node",
    id: nodeType.type,
    type: nodeType.type,
    label: nodeType.label,
    description: nodeType.description,
    enabled: nodeType.type === "human_gate" ? true : nodeType.enabled,
    category: NODE_CATEGORIES[nodeType.type],
    tags: NODE_TAGS[nodeType.type],
    badges: NODE_BADGES[nodeType.type],
    requiresCredential: nodeType.type === "prompt" || nodeType.type === "http" || nodeType.type === "tool",
  }));

  const marketplaceItems: PaletteCatalogItem[] = marketplaceNodes.map((pkg) => ({
    kind: "marketplace",
    id: `marketplace:${pkg.slug}`,
    type: `marketplace:${pkg.slug}`,
    label: String(pkg.latest_release?.ui_schema?.label || pkg.name),
    description: getMarketplacePackageDescription(pkg),
    enabled: canAddMarketplacePackageToEditor(pkg),
    category: "Marketplace",
    tags: tokenize(`${pkg.slug} ${pkg.name} ${pkg.summary ?? ""}`),
    badges: getMarketplacePackageBadges(pkg),
    requiresCredential: true,
    package: pkg,
  }));

  const noteItem: PaletteCatalogItem = {
    kind: "note",
    id: "note",
    type: "note",
    label: "Note",
    description: "Add a sticky note to annotate the workflow",
    enabled: true,
    category: NODE_CATEGORIES.note,
    tags: NODE_TAGS.note,
    badges: NODE_BADGES.note,
    requiresCredential: false,
  };

  return [...baseItems, ...marketplaceItems, noteItem];
}

export function searchNodePaletteCatalog(items: PaletteCatalogItem[], query: string): PaletteCatalogItem[] {
  const trimmed = query.trim();
  if (!trimmed) {
    return items;
  }

  return items
    .map((item) => ({
      item,
      score: scoreItemForQuery(item, trimmed),
    }))
    .filter((entry) => entry.score > 0)
    .sort((a, b) => {
      if (b.score !== a.score) return b.score - a.score;
      return a.item.label.localeCompare(b.item.label);
    })
    .map((entry) => entry.item);
}

export function groupPaletteItems(items: PaletteCatalogItem[]): Array<[string, PaletteCatalogItem[]]> {
  const groups = new Map<string, PaletteCatalogItem[]>();
  for (const item of items) {
    const existing = groups.get(item.category) ?? [];
    existing.push(item);
    groups.set(item.category, existing);
  }

  return Array.from(groups.entries())
    .map(([category, groupedItems]) => [
      category,
      [...groupedItems].sort((a, b) => a.label.localeCompare(b.label)),
    ] as [string, PaletteCatalogItem[]])
    .sort(([a], [b]) => {
      const aIndex = CATEGORY_ORDER.indexOf(a as (typeof CATEGORY_ORDER)[number]);
      const bIndex = CATEGORY_ORDER.indexOf(b as (typeof CATEGORY_ORDER)[number]);
      if (aIndex === -1 && bIndex === -1) return a.localeCompare(b);
      if (aIndex === -1) return 1;
      if (bIndex === -1) return -1;
      return aIndex - bIndex;
    });
}

export function getRecommendedPaletteItems(items: PaletteCatalogItem[], limit = 6): PaletteCatalogItem[] {
  return RECOMMENDED_ITEM_IDS.map((id) => items.find((item) => item.id === id))
    .filter((item): item is PaletteCatalogItem => Boolean(item && item.enabled))
    .slice(0, limit);
}

export function getRecentPaletteItems(
  items: PaletteCatalogItem[],
  recentIds: string[],
  limit = 6,
): PaletteCatalogItem[] {
  const itemById = new Map(items.map((item) => [item.id, item]));
  return recentIds
    .map((id) => itemById.get(id))
    .filter((item): item is PaletteCatalogItem => Boolean(item && item.enabled))
    .slice(0, limit);
}

export function updateRecentPaletteIds(currentIds: string[], selectedId: string, limit = 8): string[] {
  const withoutSelected = currentIds.filter((id) => id !== selectedId);
  return [selectedId, ...withoutSelected].slice(0, limit);
}

export function loadRecentPaletteIds(): string[] {
  if (typeof window === "undefined") return [];
  try {
    const raw = window.localStorage.getItem(RECENT_STORAGE_KEY);
    if (!raw) return [];
    const parsed = JSON.parse(raw);
    if (!Array.isArray(parsed)) return [];
    return parsed.filter((value): value is string => typeof value === "string");
  } catch {
    return [];
  }
}

export function saveRecentPaletteIds(ids: string[]): void {
  if (typeof window === "undefined") return;
  try {
    window.localStorage.setItem(RECENT_STORAGE_KEY, JSON.stringify(ids));
  } catch {
    // Non-blocking: ignore storage errors.
  }
}
