import {
  MessageSquare,
  Globe,
  Shuffle,
  LogOut,
  GitBranch,
  GitMerge,
  UserCheck,
  Database,
  Wrench,
  Layers,
  Play,
  Square,
  type LucideIcon,
} from "lucide-react";

import { NODE_TYPES } from "../../../lib/graph-types";

export type NodeShape = "pill" | "rectangle" | "diamond";

export interface NodeVisualConfig {
  shape: NodeShape;
  icon: LucideIcon;
  accentColor: string;     // Tailwind color stem e.g. "violet-500"
  bgClass: string;         // Full bg class e.g. "bg-violet-500"
  textClass: string;       // Text color for labels e.g. "text-violet-300"
}

export const NODE_VISUALS: Record<string, NodeVisualConfig> = {
  [NODE_TYPES.PROMPT]: {
    shape: "rectangle",
    icon: MessageSquare,
    accentColor: "violet-500",
    bgClass: "bg-violet-500",
    textClass: "text-violet-300",
  },
  [NODE_TYPES.HTTP]: {
    shape: "rectangle",
    icon: Globe,
    accentColor: "amber-500",
    bgClass: "bg-amber-500",
    textClass: "text-amber-300",
  },
  [NODE_TYPES.TRANSFORM]: {
    shape: "rectangle",
    icon: Shuffle,
    accentColor: "blue-500",
    bgClass: "bg-blue-500",
    textClass: "text-blue-300",
  },
  [NODE_TYPES.OUTPUT]: {
    shape: "rectangle",
    icon: LogOut,
    accentColor: "indigo-500",
    bgClass: "bg-indigo-500",
    textClass: "text-indigo-300",
  },
  [NODE_TYPES.BRANCH]: {
    shape: "diamond",
    icon: GitBranch,
    accentColor: "orange-500",
    bgClass: "bg-orange-500",
    textClass: "text-orange-300",
  },
  [NODE_TYPES.MERGE]: {
    shape: "rectangle",
    icon: GitMerge,
    accentColor: "emerald-500",
    bgClass: "bg-emerald-500",
    textClass: "text-emerald-300",
  },
  [NODE_TYPES.HUMAN_GATE]: {
    shape: "rectangle",
    icon: UserCheck,
    accentColor: "orange-500",
    bgClass: "bg-orange-500",
    textClass: "text-orange-300",
  },
  [NODE_TYPES.MEMORY]: {
    shape: "rectangle",
    icon: Database,
    accentColor: "teal-500",
    bgClass: "bg-teal-500",
    textClass: "text-teal-300",
  },
  [NODE_TYPES.TOOL]: {
    shape: "rectangle",
    icon: Wrench,
    accentColor: "cyan-500",
    bgClass: "bg-cyan-500",
    textClass: "text-cyan-300",
  },
  [NODE_TYPES.SUBGRAPH]: {
    shape: "rectangle",
    icon: Layers,
    accentColor: "fuchsia-500",
    bgClass: "bg-fuchsia-500",
    textClass: "text-fuchsia-300",
  },
};

/** Start Trigger visual overrides */
export const TRIGGER_VISUAL: NodeVisualConfig = {
  shape: "pill",
  icon: Play,
  accentColor: "emerald-500",
  bgClass: "bg-emerald-500",
  textClass: "text-emerald-300",
};

/** End node visual overrides */
export const END_VISUAL: NodeVisualConfig = {
  shape: "pill",
  icon: Square,
  accentColor: "rose-500",
  bgClass: "bg-rose-500",
  textClass: "text-rose-300",
};

/**
 * Resolve the visual config for a node based on its type and flags.
 * Trigger/End flags take priority over the type's default shape.
 */
export function getNodeVisual(
  nodeType: string,
  isTrigger?: boolean,
  isEnd?: boolean,
): NodeVisualConfig {
  if (isTrigger) return TRIGGER_VISUAL;
  if (isEnd) return END_VISUAL;
  return NODE_VISUALS[nodeType] ?? NODE_VISUALS[NODE_TYPES.PROMPT];
}
