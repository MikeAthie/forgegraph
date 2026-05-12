/**
 * Graph JSON Types
 *
 * These types define the structure of graph data as specified in the root SPECS.md.
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
  AGENT: "agent",
  PROMPT: "prompt",
  HTTP: "http",
  TRANSFORM: "transform",
  BRANCH: "branch",
  MERGE: "merge",
  HUMAN_GATE: "human_gate",
  MEMORY: "memory",
  OBSERVATION_SAVE: "observation_save",
  OBSERVATION_SEARCH: "observation_search",
  OBSERVATION_CONTEXT: "observation_context",
  OBSERVATION_TIMELINE: "observation_timeline",
  TOOL: "tool",
  SUBGRAPH: "subgraph",
  OUTPUT: "output",
} as const;

export type NodeType = (typeof NODE_TYPES)[keyof typeof NODE_TYPES];

/**
 * LangGraph-style sentinel endpoints for entry/exit edges.
 *
 * These are not real nodes; they are represented as special edge endpoints:
 * - START -> node_id (entry points)
 * - node_id -> END (exit points)
 */
export const START_NODE_ID = "START" as const;
export const END_NODE_ID = "END" as const;

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
interface BaseNodeConfig {
  [key: string]: unknown;
}

/**
 * Agent node configuration.
 */
export interface AgentNodeConfig extends BaseNodeConfig {
  instructions?: string;
  system_prompt?: string;
  provider?: string;
  credential_id?: string;
  model?: string;
  tools?: string[];
  max_steps?: number;
  max_tool_calls?: number;
  max_tokens?: number;
  temperature?: number;
  approval_required_tools?: string[];
  stop_condition?: "final_answer";
}

/**
 * Prompt node configuration.
 */
interface PromptNodeConfig extends BaseNodeConfig {
  prompt_id?: string;
  template_id?: string;
  prompt_template?: string;
  system_prompt?: string;
  provider?: string;
  credential_id?: string;
  model?: string;
  temperature?: number;
  max_tokens?: number;
  variables?: Record<string, string>;
}

/**
 * HTTP node configuration.
 */
interface HttpNodeConfig extends BaseNodeConfig {
  method: "GET" | "POST" | "PUT" | "PATCH" | "DELETE";
  url: string;
  headers?: Record<string, string>;
  provider?: string;
  credential_id?: string;
  body?: string;
  output_key?: string;
}

/**
 * Transform node configuration.
 */
interface TransformNodeConfig extends BaseNodeConfig {
  expression: string;
  output_key?: string;
}

/**
 * Branch node configuration.
 */
interface BranchNodeConfig extends BaseNodeConfig {
  condition?: string;
}

/**
 * Merge node configuration.
 */
interface MergeNodeConfig extends BaseNodeConfig {
  merge_strategy?: "last_write_wins" | "namespaced";
}

/**
 * Memory node configuration.
 */
interface MemoryNodeConfig extends BaseNodeConfig {
  action?: "get" | "set" | "delete";
  key?: string;
  namespace?: string;
  namespace_path?: string;
  value?: unknown;
  value_path?: string;
  value_template?: string;
  ttl_seconds?: number;
}

interface ObservationSaveNodeConfig extends BaseNodeConfig {
  observation_id?: string;
  type?: string;
  scope?: "graph" | "run" | "session";
  title?: string;
  title_path?: string;
  title_template?: string;
  content?: string;
  content_path?: string;
  content_template?: string;
  topic_key?: string;
  topic_key_path?: string;
  tool_name?: string;
  tool_name_path?: string;
  agent_id?: string;
  agent_id_path?: string;
  dedupe?: boolean;
  update_topic?: boolean;
}

interface ObservationSearchNodeConfig extends BaseNodeConfig {
  scope?: "graph" | "run" | "session";
  query?: string;
  query_path?: string;
  query_template?: string;
  type?: string;
  topic_key?: string;
  topic_key_path?: string;
  agent_id?: string;
  agent_id_path?: string;
  limit?: number;
  include_deleted?: boolean;
}

interface ObservationContextNodeConfig extends BaseNodeConfig {
  query?: string;
  query_path?: string;
  query_template?: string;
  agent_id?: string;
  agent_id_path?: string;
  limit?: number;
}

interface ObservationTimelineNodeConfig extends BaseNodeConfig {
  scope?: "graph" | "run" | "session";
  agent_id?: string;
  agent_id_path?: string;
  limit?: number;
  include_deleted?: boolean;
}

/**
 * Tool node configuration.
 */
interface ToolNodeConfig extends BaseNodeConfig {
  tool?: string;
  version?: string;
  provider?: string;
  credential_id?: string;
  input?: unknown;
  input_path?: string;
  input_template?: string;
  config?: Record<string, unknown>;
}

/**
 * Subgraph node configuration.
 */
interface SubgraphNodeConfig extends BaseNodeConfig {
  graph_json?: GraphJson | string;
  graph_id?: string;
  graph_version_id?: string;
  graph_version?: number;
  input?: Record<string, unknown>;
  input_path?: string;
  input_mapping?: Record<string, string>;
  output_mapping?: Record<string, string>;
  output_key?: string;
}

/**
 * Human gate node configuration.
 */
interface HumanGateNodeConfig extends BaseNodeConfig {
  prompt_message?: string;
  required_fields?: string[];
}

/**
 * Output node configuration.
 */
interface OutputNodeConfig extends BaseNodeConfig {
  output_mapping?: Record<string, string>;
}

/**
 * Node configuration type - allows any key-value pairs.
 * Specific interfaces above are for documentation and type hints only.
 */
export type NodeConfig = Record<string, unknown>;

/**
 * A node in the graph JSON structure.
 * @see ../../SPECS.md
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
 * @see ../../SPECS.md
 */
export interface GraphEdge {
  /** Unique identifier for the edge */
  id: string;
  /** Source node ID (or START for entry edges) */
  from: string;
  /** Target node ID (or END for exit edges) */
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
interface EditorState {
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
 * @see ../../SPECS.md
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
    type: NODE_TYPES.AGENT,
    label: "AI Worker",
    description: "Run a model-to-tool loop inside one operating-model step",
    enabled: true,
  },
  {
    type: NODE_TYPES.PROMPT,
    label: "Prompted Worker",
    description: "Call an intelligence provider with a prompt template",
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
    label: "Data Transform",
    description: "Transform data with an expression",
    enabled: true,
  },
  {
    type: NODE_TYPES.OUTPUT,
    label: "Final Deliverable",
    description: "Define the final deliverable of the operating model",
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
    label: "Approval Gate",
    description: "Pause for human approval",
    enabled: true,
  },
  {
    type: NODE_TYPES.MEMORY,
    label: "Memory",
    description: "Store or retrieve shared memory values",
    enabled: true,
  },
  {
    type: NODE_TYPES.OBSERVATION_SAVE,
    label: "Observation Save",
    description: "Persist a curated observation for later runs",
    enabled: true,
  },
  {
    type: NODE_TYPES.OBSERVATION_SEARCH,
    label: "Observation Search",
    description: "Search curated observations by query or topic",
    enabled: true,
  },
  {
    type: NODE_TYPES.OBSERVATION_CONTEXT,
    label: "Observation Context",
    description: "Assemble the best curated context for a prompt or agent",
    enabled: true,
  },
  {
    type: NODE_TYPES.OBSERVATION_TIMELINE,
    label: "Observation Timeline",
    description: "Browse recent curated observations in scope order",
    enabled: true,
  },
  {
    type: NODE_TYPES.TOOL,
    label: "Tool Action",
    description: "Call a tool from the tool registry",
    enabled: true,
  },
  {
    type: NODE_TYPES.SUBGRAPH,
    label: "Reusable Model",
    description: "Run another operating model inline",
    enabled: true,
  },
];
