import type { ComponentType } from "react";
import type { NodeFormProps } from "../NodeConfigDialog";

import { AgentNodeForm } from "./AgentNodeForm";
import { PromptNodeForm } from "./PromptNodeForm";
import { HttpNodeForm } from "./HttpNodeForm";
import { TransformNodeForm } from "./TransformNodeForm";
import { OutputNodeForm } from "./OutputNodeForm";
import { BranchNodeForm } from "./BranchNodeForm";
import { MergeNodeForm } from "./MergeNodeForm";
import { MemoryNodeForm } from "./MemoryNodeForm";
import { ObservationSaveNodeForm } from "./ObservationSaveNodeForm";
import { ObservationSearchNodeForm } from "./ObservationSearchNodeForm";
import { ObservationContextNodeForm } from "./ObservationContextNodeForm";
import { ObservationTimelineNodeForm } from "./ObservationTimelineNodeForm";
import { ToolNodeForm } from "./ToolNodeForm";
import { SubgraphNodeForm } from "./SubgraphNodeForm";
import { HumanGateNodeForm } from "./HumanGateNodeForm";

/**
 * Node type display configuration
 */
export interface NodeTypeInfo {
  /** Display label for the node type */
  label: string;
  /** Short description of what the node does */
  description: string;
  /** Icon name from lucide-react */
  icon: string;
  /** Category for grouping in palette */
  category: "input" | "processing" | "output" | "control" | "integration";
  /** Color for node styling */
  color: string;
}

/**
 * Registry entry for a node type
 */
interface NodeFormEntry {
  /** The form component to render */
  component: ComponentType<NodeFormProps>;
  /** Display information */
  info: NodeTypeInfo;
}

/**
 * Registry mapping node types to their form components and metadata
 */
export const nodeFormRegistry: Record<string, NodeFormEntry> = {
  agent: {
    component: AgentNodeForm,
    info: {
      label: "Agent",
      description: "Run a bounded model-to-tool loop inside one node",
      icon: "Bot",
      category: "processing",
      color: "#0ea5e9",
    },
  },
  prompt: {
    component: PromptNodeForm,
    info: {
      label: "Prompt",
      description: "Send prompts to LLM models and process responses",
      icon: "MessageSquare",
      category: "processing",
      color: "#8b5cf6", // purple
    },
  },
  http: {
    component: HttpNodeForm,
    info: {
      label: "HTTP Request",
      description: "Make HTTP requests to external APIs",
      icon: "Globe",
      category: "integration",
      color: "#3b82f6", // blue
    },
  },
  transform: {
    component: TransformNodeForm,
    info: {
      label: "Transform",
      description: "Transform data using JavaScript expressions",
      icon: "Shuffle",
      category: "processing",
      color: "#f59e0b", // amber
    },
  },
  output: {
    component: OutputNodeForm,
    info: {
      label: "Output",
      description: "Define the final output of the workflow",
      icon: "LogOut",
      category: "output",
      color: "#10b981", // green
    },
  },
  branch: {
    component: BranchNodeForm,
    info: {
      label: "Branch",
      description: "Route data to different paths based on conditions",
      icon: "GitBranch",
      category: "control",
      color: "#ec4899", // pink
    },
  },
  merge: {
    component: MergeNodeForm,
    info: {
      label: "Merge",
      description: "Combine data from multiple branches",
      icon: "GitMerge",
      category: "control",
      color: "#ec4899", // pink
    },
  },
  memory: {
    component: MemoryNodeForm,
    info: {
      label: "Memory",
      description: "Store and retrieve information across interactions",
      icon: "Database",
      category: "processing",
      color: "#6366f1", // indigo
    },
  },
  observation_save: {
    component: ObservationSaveNodeForm,
    info: {
      label: "Observation Save",
      description: "Persist curated observations for later runs",
      icon: "BookmarkPlus",
      category: "processing",
      color: "#0f766e",
    },
  },
  observation_search: {
    component: ObservationSearchNodeForm,
    info: {
      label: "Observation Search",
      description: "Search curated observations by query, type, or topic",
      icon: "SearchCheck",
      category: "processing",
      color: "#0369a1",
    },
  },
  observation_context: {
    component: ObservationContextNodeForm,
    info: {
      label: "Observation Context",
      description: "Assemble a curated context pack for prompts and agents",
      icon: "BrainCircuit",
      category: "processing",
      color: "#2563eb",
    },
  },
  observation_timeline: {
    component: ObservationTimelineNodeForm,
    info: {
      label: "Observation Timeline",
      description: "Load recent curated observations as an ordered timeline",
      icon: "History",
      category: "processing",
      color: "#7c3aed",
    },
  },
  tool: {
    component: ToolNodeForm,
    info: {
      label: "Tool",
      description: "Execute tools and external functions",
      icon: "Wrench",
      category: "integration",
      color: "#64748b", // slate
    },
  },
  subgraph: {
    component: SubgraphNodeForm,
    info: {
      label: "Subgraph",
      description: "Execute another graph as a nested workflow",
      icon: "Workflow",
      category: "integration",
      color: "#0ea5e9", // sky
    },
  },
  human_gate: {
    component: HumanGateNodeForm,
    info: {
      label: "Human Gate",
      description: "Pause for human review and approval",
      icon: "UserCheck",
      category: "control",
      color: "#f97316", // orange
    },
  },
};

/**
 * Get the form component for a node type
 */
export function getNodeFormComponent(
  nodeType: string
): ComponentType<NodeFormProps> | null {
  return nodeFormRegistry[nodeType]?.component || null;
}

/**
 * Get the display info for a node type
 */
export function getNodeTypeInfo(nodeType: string): NodeTypeInfo | null {
  return nodeFormRegistry[nodeType]?.info || null;
}

/**
 * Get all registered node types
 */
export function getAllNodeTypes(): string[] {
  return Object.keys(nodeFormRegistry);
}

/**
 * Get node types by category
 */
export function getNodeTypesByCategory(
  category: NodeTypeInfo["category"]
): string[] {
  return Object.entries(nodeFormRegistry)
    .filter(([, entry]) => entry.info.category === category)
    .map(([type]) => type);
}

/**
 * Check if a node type is registered
 */
export function isNodeTypeRegistered(nodeType: string): boolean {
  return nodeType in nodeFormRegistry;
}
