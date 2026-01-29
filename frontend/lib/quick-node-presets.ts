/**
 * Quick Node Presets
 *
 * Pre-configured node templates for common agent patterns.
 * Users can quickly add these to their workflows without manual configuration.
 */

import { NODE_TYPES, type NodeType } from "./graph-types";

/**
 * Categories for organizing presets
 */
export type PresetCategory = "ai" | "communication" | "data" | "logic" | "utility";

/**
 * Quick Node Preset definition
 */
export interface QuickNodePreset {
  id: string;
  name: string;
  description: string;
  icon: string;
  category: PresetCategory;
  nodeType: NodeType;
  defaultConfig: Record<string, unknown>;
  tags: string[];
}

/**
 * Category metadata for display
 */
export const PRESET_CATEGORIES: Record<
  PresetCategory,
  { label: string; description: string }
> = {
  ai: {
    label: "AI & LLM",
    description: "Language model prompts and AI processing",
  },
  communication: {
    label: "Communication",
    description: "Messaging and notification integrations",
  },
  data: {
    label: "Data",
    description: "Data fetching and transformation",
  },
  logic: {
    label: "Logic",
    description: "Control flow and decision making",
  },
  utility: {
    label: "Utility",
    description: "Helper nodes and common patterns",
  },
};

/**
 * All available Quick Node presets
 */
export const QUICK_NODE_PRESETS: QuickNodePreset[] = [
  // AI & LLM Presets
  {
    id: "chat-assistant",
    name: "Chat Assistant",
    description: "Conversational AI assistant with memory",
    icon: "MessageSquare",
    category: "ai",
    nodeType: NODE_TYPES.PROMPT,
    defaultConfig: {
      role: "Helpful AI Assistant",
      job_description: "Engage in helpful, natural conversation with the user",
      system_prompt:
        "You are a helpful AI assistant. Respond naturally and helpfully to user messages.",
      model: "gpt-4",
      temperature: 0.7,
    },
    tags: ["chat", "assistant", "conversation"],
  },
  {
    id: "summarizer",
    name: "Text Summarizer",
    description: "Summarize long text into key points",
    icon: "FileText",
    category: "ai",
    nodeType: NODE_TYPES.PROMPT,
    defaultConfig: {
      role: "Content Summarizer",
      job_description: "Summarize text into concise, clear bullet points",
      system_prompt:
        "You are an expert at summarizing content. Extract the key points and present them as a bulleted list.",
      prompt_template:
        "Please summarize the following text:\n\n{{input.text}}\n\nProvide 3-5 key bullet points.",
      model: "gpt-4",
      temperature: 0.3,
    },
    tags: ["summarize", "text", "extract"],
  },
  {
    id: "classifier",
    name: "Intent Classifier",
    description: "Classify user input into categories",
    icon: "Tags",
    category: "ai",
    nodeType: NODE_TYPES.PROMPT,
    defaultConfig: {
      role: "Intent Classifier",
      job_description: "Classify user messages into predefined categories",
      system_prompt:
        'You are an intent classifier. Analyze the user message and respond with ONLY the category name.',
      prompt_template:
        'Classify the following message into one of these categories: [question, request, complaint, feedback, other]\n\nMessage: "{{input.message}}"\n\nCategory:',
      model: "gpt-4",
      temperature: 0,
    },
    tags: ["classify", "intent", "category"],
  },
  {
    id: "translator",
    name: "Translator",
    description: "Translate text between languages",
    icon: "Languages",
    category: "ai",
    nodeType: NODE_TYPES.PROMPT,
    defaultConfig: {
      role: "Translator",
      job_description: "Accurately translate text while preserving meaning",
      system_prompt:
        "You are a professional translator. Translate the provided text accurately while maintaining the original tone and meaning.",
      prompt_template:
        "Translate the following text to {{input.target_language}}:\n\n{{input.text}}",
      model: "gpt-4",
      temperature: 0.3,
    },
    tags: ["translate", "language", "i18n"],
  },

  // Communication Presets
  {
    id: "email-responder",
    name: "Email Responder",
    description: "Generate professional email responses",
    icon: "Mail",
    category: "communication",
    nodeType: NODE_TYPES.PROMPT,
    defaultConfig: {
      role: "Email Assistant",
      job_description: "Draft professional email responses",
      system_prompt:
        "You are a professional email writer. Draft clear, concise, and appropriate email responses.",
      prompt_template:
        "Draft a response to the following email:\n\nFrom: {{input.sender}}\nSubject: {{input.subject}}\n\n{{input.body}}\n\nTone: {{input.tone || 'professional'}}",
      model: "gpt-4",
      temperature: 0.5,
    },
    tags: ["email", "response", "professional"],
  },
  {
    id: "notification-sender",
    name: "Notification",
    description: "Send notifications via webhook",
    icon: "Bell",
    category: "communication",
    nodeType: NODE_TYPES.HTTP,
    defaultConfig: {
      method: "POST",
      url: "",
      headers: {
        "Content-Type": "application/json",
      },
      body: '{"message": "{{input.message}}"}',
    },
    tags: ["notify", "webhook", "alert"],
  },

  // Data Presets
  {
    id: "api-fetcher",
    name: "API Fetcher",
    description: "Fetch data from an external API",
    icon: "Download",
    category: "data",
    nodeType: NODE_TYPES.HTTP,
    defaultConfig: {
      method: "GET",
      url: "",
      headers: {},
      output_key: "api_response",
    },
    tags: ["api", "fetch", "get"],
  },
  {
    id: "api-poster",
    name: "API Poster",
    description: "Send data to an external API",
    icon: "Upload",
    category: "data",
    nodeType: NODE_TYPES.HTTP,
    defaultConfig: {
      method: "POST",
      url: "",
      headers: {
        "Content-Type": "application/json",
      },
      body: "{}",
      output_key: "api_response",
    },
    tags: ["api", "post", "send"],
  },
  {
    id: "json-transformer",
    name: "JSON Transformer",
    description: "Transform and reshape JSON data",
    icon: "Shuffle",
    category: "data",
    nodeType: NODE_TYPES.TRANSFORM,
    defaultConfig: {
      expression: `// Transform input data
const data = state.previousNode.output;
return {
  transformed: data
};`,
      output_key: "transformed",
    },
    tags: ["transform", "json", "map"],
  },
  {
    id: "data-extractor",
    name: "Data Extractor",
    description: "Extract specific fields from data",
    icon: "Filter",
    category: "data",
    nodeType: NODE_TYPES.TRANSFORM,
    defaultConfig: {
      expression: `// Extract specific fields
const data = state.previousNode.output;
return {
  extracted: data.fieldName
};`,
      output_key: "extracted",
    },
    tags: ["extract", "filter", "pick"],
  },

  // Logic Presets
  {
    id: "conditional-router",
    name: "Conditional Router",
    description: "Route based on conditions",
    icon: "GitBranch",
    category: "logic",
    nodeType: NODE_TYPES.BRANCH,
    defaultConfig: {
      conditions: [
        {
          id: "condition_1",
          name: "Condition 1",
          expression: "state.value > 0",
        },
      ],
      default_branch: "default",
    },
    tags: ["condition", "if", "route"],
  },
  {
    id: "approval-gate",
    name: "Approval Gate",
    description: "Require human approval before proceeding",
    icon: "UserCheck",
    category: "logic",
    nodeType: NODE_TYPES.HUMAN_GATE,
    defaultConfig: {
      approval_message: "Please review and approve this action.",
      instructions: "Verify the data is correct before approving.",
      timeout_hours: 24,
      require_comment: false,
      show_context: true,
    },
    tags: ["approve", "human", "review"],
  },
  {
    id: "merge-paths",
    name: "Merge Paths",
    description: "Combine results from multiple branches",
    icon: "GitMerge",
    category: "logic",
    nodeType: NODE_TYPES.MERGE,
    defaultConfig: {
      merge_strategy: "all",
      output_key: "merged",
    },
    tags: ["merge", "combine", "join"],
  },

  // Utility Presets
  {
    id: "memory-store",
    name: "Save to Memory",
    description: "Store data in memory for later use",
    icon: "Database",
    category: "utility",
    nodeType: NODE_TYPES.MEMORY,
    defaultConfig: {
      memory_type: "conversation",
      memory_key: "stored_data",
    },
    tags: ["memory", "store", "save"],
  },
  {
    id: "memory-recall",
    name: "Recall Memory",
    description: "Retrieve previously stored data",
    icon: "Search",
    category: "utility",
    nodeType: NODE_TYPES.MEMORY,
    defaultConfig: {
      memory_type: "conversation",
      memory_key: "stored_data",
    },
    tags: ["memory", "recall", "get"],
  },
  {
    id: "final-output",
    name: "Final Output",
    description: "Define the workflow output",
    icon: "LogOut",
    category: "utility",
    nodeType: NODE_TYPES.OUTPUT,
    defaultConfig: {
      output_mapping: {
        result: "node.previousNode.output",
      },
    },
    tags: ["output", "result", "end"],
  },
];

/**
 * Get presets by category
 */
export function getPresetsByCategory(
  category: PresetCategory
): QuickNodePreset[] {
  return QUICK_NODE_PRESETS.filter((preset) => preset.category === category);
}

/**
 * Get a preset by ID
 */
export function getPresetById(id: string): QuickNodePreset | undefined {
  return QUICK_NODE_PRESETS.find((preset) => preset.id === id);
}

/**
 * Search presets by name, description, or tags
 */
export function searchPresets(query: string): QuickNodePreset[] {
  const lowerQuery = query.toLowerCase();
  return QUICK_NODE_PRESETS.filter(
    (preset) =>
      preset.name.toLowerCase().includes(lowerQuery) ||
      preset.description.toLowerCase().includes(lowerQuery) ||
      preset.tags.some((tag) => tag.toLowerCase().includes(lowerQuery))
  );
}

/**
 * Get popular/featured presets
 */
export function getPopularPresets(limit = 6): QuickNodePreset[] {
  // Return a curated list of popular presets
  const popularIds = [
    "chat-assistant",
    "api-fetcher",
    "json-transformer",
    "conditional-router",
    "approval-gate",
    "final-output",
  ];
  return popularIds
    .map((id) => getPresetById(id))
    .filter((p): p is QuickNodePreset => p !== undefined)
    .slice(0, limit);
}
