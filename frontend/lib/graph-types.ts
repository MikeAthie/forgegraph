/**
 * Graph JSON Types
 *
 * These types define the structure of graph data as specified in SPECS.md section 8.
 * They are used for:
 * - Persisting graphs to the backend (GraphVersion.graph_json)
 * - Converting between React Flow format and our canonical format
 * - Type safety in the graph editor
 */

/**
 * Supported node types matching backend NodeType enum.
 * @see backend/domain/value_objects/node_types.py
 */
export const NODE_TYPES = {
  PROMPT: "prompt",
  HTTP: "http",
  TRANSFORM: "transform",
  BRANCH: "branch",
  MERGE: "merge",
  HUMAN_GATE: "human_gate",
  OUTPUT: "output",
} as const;

export type NodeType = (typeof NODE_TYPES)[keyof typeof NODE_TYPES];

/**
 * Retry policy for node execution.
 */
export interface RetryPolicy {
  max_attempts: number;
  backoff_ms: number;
  backoff_strategy?: "fixed" | "exponential";
}

/**
 * Named output definition for nodes with multiple outputs.
 */
export interface NodeOutput {
  name: string;
  description?: string;
}

/**
 * Base node configuration - common fields for all node types.
 */
export interface BaseNodeConfig {
  [key: string]: unknown;
}

/**
 * Prompt node configuration.
 */
export interface PromptNodeConfig extends BaseNodeConfig {
  prompt_id?: string;
  template_id?: string;
  variables?: Record<string, string>;
}

/**
 * HTTP node configuration.
 */
export interface HttpNodeConfig extends BaseNodeConfig {
  method: "GET" | "POST" | "PUT" | "PATCH" | "DELETE";
  url: string;
  headers?: Record<string, string>;
  body?: string;
  output_key?: string;
}

/**
 * Transform node configuration.
 */
export interface TransformNodeConfig extends BaseNodeConfig {
  expression: string;
  output_key?: string;
}

/**
 * Branch node configuration.
 */
export interface BranchNodeConfig extends BaseNodeConfig {
  condition?: string;
}

/**
 * Merge node configuration.
 */
export interface MergeNodeConfig extends BaseNodeConfig {
  merge_strategy?: "last_write_wins" | "namespaced";
}

/**
 * Human gate node configuration.
 */
export interface HumanGateNodeConfig extends BaseNodeConfig {
  prompt_message?: string;
  required_fields?: string[];
}

/**
 * Output node configuration.
 */
export interface OutputNodeConfig extends BaseNodeConfig {
  output_mapping?: Record<string, string>;
}

/**
 * Node configuration type - allows any key-value pairs.
 * Specific interfaces above are for documentation and type hints only.
 */
export type NodeConfig = Record<string, unknown>;

/**
 * A node in the graph JSON structure.
 * @see SPECS.md section 8.2
 */
export interface GraphNode {
  /** Unique identifier for the node */
  id: string;
  /** Node type from NODE_TYPES */
  type: NodeType;
  /** Display name for the node */
  name: string;
  /** If true, node is skipped during execution. */
  disabled?: boolean;
  /** Node-specific configuration */
  config: NodeConfig;
  /** Optional retry policy */
  retry_policy?: RetryPolicy;
  /** Optional timeout in milliseconds */
  timeout_ms?: number;
  /** Optional named outputs for branch/merge */
  outputs?: NodeOutput[];
}

/**
 * An edge connecting two nodes.
 * @see SPECS.md section 8.3
 */
export interface GraphEdge {
  /** Unique identifier for the edge */
  id: string;
  /** Source node ID */
  from: string;
  /** Target node ID */
  to: string;
  /** Optional condition expression (for branch nodes) */
  condition?: string;
  /** Optional label for display */
  label?: string;
}

/**
 * Graph metadata stored alongside the graph structure.
 */
export interface GraphMetadata {
  name?: string;
  description?: string;
  [key: string]: unknown;
}

export interface NoteEditorNode {
  id: string;
  label?: string;
  text: string;
}

/**
 * Editor-specific UI state that should be preserved but ignored by the engine.
 * Stored in a dedicated location to keep engine-relevant data clean.
 */
export interface EditorState {
  /** Node positions for React Flow */
  nodePositions?: Record<string, { x: number; y: number }>;
  /** Viewport state */
  viewport?: {
    x: number;
    y: number;
    zoom: number;
  };
  /** Sticky notes/annotations (editor-only). */
  notes?: NoteEditorNode[];
  /** Additional UI flags */
  [key: string]: unknown;
}

/**
 * Complete graph JSON structure.
 * @see SPECS.md section 8.1
 */
export interface GraphJson {
  /** Graph ID (optional when creating new) */
  graph_id?: string;
  /** Version ID (optional, set by backend) */
  version_id?: string;
  /** Array of nodes */
  nodes: GraphNode[];
  /** Array of edges */
  edges: GraphEdge[];
  /** Graph metadata */
  metadata?: GraphMetadata;
  /** Editor-only UI state (ignored by engine) */
  editor_state?: EditorState;
}

/**
 * Graph version as returned by the API.
 */
export interface GraphVersion {
  id: string;
  version: number;
  graph_json: GraphJson;
  checksum: string;
  created_at: string;
}

/**
 * Input for creating a new graph version.
 */
export interface CreateGraphVersionInput {
  graph_json: GraphJson;
}

/**
 * Helper to check if a string is a valid node type.
 */
export function isValidNodeType(type: string): type is NodeType {
  return Object.values(NODE_TYPES).includes(type as NodeType);
}

/**
 * Helper to create an empty graph JSON structure.
 */
export function createEmptyGraphJson(metadata?: GraphMetadata): GraphJson {
  return {
    nodes: [],
    edges: [],
    metadata: metadata ?? {},
    editor_state: {
      viewport: { x: 0, y: 0, zoom: 1 },
      nodePositions: {},
    },
  };
}

/**
 * Node type display information for the palette.
 */
export interface NodeTypeInfo {
  type: NodeType;
  label: string;
  description: string;
  icon?: string;
  enabled: boolean;
}

/**
 * Node types available in Phase 2 (MVP).
 */
export const PHASE2_NODE_TYPES: NodeTypeInfo[] = [
  {
    type: NODE_TYPES.PROMPT,
    label: "Prompt",
    description: "Call an LLM with a prompt template",
    enabled: true,
  },
  {
    type: NODE_TYPES.HTTP,
    label: "HTTP",
    description: "Make an HTTP request to an external API",
    enabled: true,
  },
  {
    type: NODE_TYPES.TRANSFORM,
    label: "Transform",
    description: "Transform data with an expression",
    enabled: true,
  },
  {
    type: NODE_TYPES.OUTPUT,
    label: "Output",
    description: "Define the final output of the workflow",
    enabled: true,
  },
  {
    type: NODE_TYPES.BRANCH,
    label: "Branch",
    description: "Conditional routing based on state",
    enabled: true, // Phase 5
  },
  {
    type: NODE_TYPES.MERGE,
    label: "Merge",
    description: "Join parallel branches",
    enabled: true, // Phase 5
  },
  {
    type: NODE_TYPES.HUMAN_GATE,
    label: "Human Gate",
    description: "Pause for human approval",
    enabled: false, // Coming in Phase 6
  },
];
