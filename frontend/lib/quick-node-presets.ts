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
type PresetCategory = "ai" | "communication" | "data" | "logic" | "utility" | "integrations";

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
  requiredCredentialProvider?: string;
  setupHint?: string;
  validationBadge?: string;
}

/**
 * Category metadata for display
 */
const PRESET_CATEGORIES: Record<PresetCategory, { label: string; description: string }> = {
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
  integrations: {
    label: "Integrations",
    description: "Popular third-party API integrations",
  },
};

/**
 * All available Quick Node presets
 */
const QUICK_NODE_PRESETS: QuickNodePreset[] = [
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
      system_prompt: "You are a helpful AI assistant. Respond naturally and helpfully to user messages.",
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
      prompt_template: "Please summarize the following text:\n\n{{input.text}}\n\nProvide 3-5 key bullet points.",
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
      system_prompt: "You are an intent classifier. Analyze the user message and respond with ONLY the category name.",
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
      prompt_template: "Translate the following text to {{input.target_language}}:\n\n{{input.text}}",
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
      system_prompt: "You are a professional email writer. Draft clear, concise, and appropriate email responses.",
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
      key: "stored_data",
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
      key: "stored_data",
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

  // Integration Presets
  {
    id: "telegram-send",
    name: "Telegram",
    description: "Send or reply to messages via Telegram Bot API",
    icon: "Send",
    category: "integrations",
    nodeType: NODE_TYPES.HTTP,
    defaultConfig: {
      provider: "telegram",
      method: "POST",
      url: "https://api.telegram.org/bot{{credentials.telegram_token}}/sendMessage",
      headers: {
        "Content-Type": "application/json",
      },
      body: JSON.stringify(
        {
          chat_id: "{{input.chat_id}}",
          text: "{{input.message}}",
        },
        null,
        2,
      ),
      output_key: "telegram_response",
    },
    tags: ["telegram", "messaging", "bot", "chat"],
    requiredCredentialProvider: "telegram",
    setupHint: "Connect a Telegram bot token from @BotFather, then set chat_id + text payload fields.",
    validationBadge: "Credential required",
  },
  {
    id: "whatsapp-send",
    name: "WhatsApp",
    description: "Send WhatsApp replies via Twilio API",
    icon: "MessageCircle",
    category: "integrations",
    nodeType: NODE_TYPES.HTTP,
    defaultConfig: {
      provider: "twilio",
      method: "POST",
      url: "https://api.twilio.com/2010-04-01/Accounts/{{input.account_sid}}/Messages.json",
      headers: {
        "Content-Type": "application/x-www-form-urlencoded",
      },
      body: "To={{input.to}}&From={{input.from}}&Body={{input.message}}",
      output_key: "whatsapp_response",
    },
    tags: ["whatsapp", "twilio", "messaging", "chatbot"],
    requiredCredentialProvider: "twilio",
    setupHint: "Provide Twilio credential and Account SID, then map To/From/Body placeholders.",
    validationBadge: "Credential required",
  },
  {
    id: "gmail-get-unread",
    name: "Gmail Unread",
    description: "Fetch unread emails from Gmail inbox",
    icon: "Mail",
    category: "integrations",
    nodeType: NODE_TYPES.HTTP,
    defaultConfig: {
      provider: "gmail",
      method: "GET",
      url: "https://gmail.googleapis.com/gmail/v1/users/me/messages?q=is:unread&maxResults=5",
      headers: {},
      output_key: "gmail_unread_messages",
    },
    tags: ["gmail", "email", "inbox", "unread"],
    requiredCredentialProvider: "gmail",
    setupHint: "Use Gmail OAuth credential with readonly scope and adjust query/maxResults as needed.",
    validationBadge: "OAuth required",
  },
  {
    id: "gmail-send",
    name: "Gmail Send",
    description: "Send email using Gmail API",
    icon: "Send",
    category: "integrations",
    nodeType: NODE_TYPES.HTTP,
    defaultConfig: {
      provider: "gmail",
      method: "POST",
      url: "https://gmail.googleapis.com/gmail/v1/users/me/messages/send",
      headers: {
        "Content-Type": "application/json",
      },
      body: JSON.stringify(
        {
          raw: "{{input.raw_message_base64url}}",
        },
        null,
        2,
      ),
      output_key: "gmail_send_response",
    },
    tags: ["gmail", "email", "send", "reply"],
    requiredCredentialProvider: "gmail",
    setupHint: "Use Gmail OAuth credential and provide RFC2822 message encoded as base64url raw payload.",
    validationBadge: "OAuth required",
  },
  {
    id: "calendar-list-events",
    name: "Calendar Events",
    description: "List Google Calendar events for a date range",
    icon: "CalendarDays",
    category: "integrations",
    nodeType: NODE_TYPES.HTTP,
    defaultConfig: {
      provider: "google_calendar",
      method: "GET",
      url: "https://www.googleapis.com/calendar/v3/calendars/primary/events?singleEvents=true&orderBy=startTime&timeMin={{input.time_min}}&timeMax={{input.time_max}}",
      headers: {},
      output_key: "calendar_events",
    },
    tags: ["google", "calendar", "events", "schedule"],
    requiredCredentialProvider: "google_calendar",
    setupHint: "Set ISO8601 time_min/time_max input values and connect Google Calendar OAuth credential.",
    validationBadge: "OAuth required",
  },
  {
    id: "calendar-create-event",
    name: "Calendar Create",
    description: "Create a Google Calendar event",
    icon: "CalendarPlus",
    category: "integrations",
    nodeType: NODE_TYPES.HTTP,
    defaultConfig: {
      provider: "google_calendar",
      method: "POST",
      url: "https://www.googleapis.com/calendar/v3/calendars/primary/events",
      headers: {
        "Content-Type": "application/json",
      },
      body: "{{input.event_json}}",
      output_key: "calendar_event_created",
    },
    tags: ["google", "calendar", "create", "event"],
    requiredCredentialProvider: "google_calendar",
    setupHint: "Pass event_json with summary/start/end fields and a Google Calendar OAuth credential.",
    validationBadge: "OAuth required",
  },
  {
    id: "tasks-list",
    name: "Tasks List",
    description: "List tasks from Google Tasks",
    icon: "ListTodo",
    category: "integrations",
    nodeType: NODE_TYPES.HTTP,
    defaultConfig: {
      provider: "google_tasks",
      method: "GET",
      url: "https://tasks.googleapis.com/tasks/v1/lists/{{input.task_list_id}}/tasks",
      headers: {},
      output_key: "tasks_list",
    },
    tags: ["google", "tasks", "todo", "list"],
    requiredCredentialProvider: "google_tasks",
    setupHint: "Provide task_list_id input and connect Google Tasks OAuth credential.",
    validationBadge: "OAuth required",
  },
  {
    id: "tasks-create",
    name: "Tasks Create",
    description: "Create a task in Google Tasks",
    icon: "CheckSquare",
    category: "integrations",
    nodeType: NODE_TYPES.HTTP,
    defaultConfig: {
      provider: "google_tasks",
      method: "POST",
      url: "https://tasks.googleapis.com/tasks/v1/lists/{{input.task_list_id}}/tasks",
      headers: {
        "Content-Type": "application/json",
      },
      body: "{{input.task_json}}",
      output_key: "task_created",
    },
    tags: ["google", "tasks", "create", "todo"],
    requiredCredentialProvider: "google_tasks",
    setupHint: "Provide task_list_id + task_json and connect Google Tasks OAuth credential.",
    validationBadge: "OAuth required",
  },
  {
    id: "webhook-fallback",
    name: "Webhook",
    description: "Generic webhook/REST fallback node",
    icon: "Webhook",
    category: "integrations",
    nodeType: NODE_TYPES.HTTP,
    defaultConfig: {
      method: "POST",
      url: "{{input.webhook_url}}",
      headers: {
        "Content-Type": "application/json",
      },
      body: JSON.stringify(
        {
          event: "{{input.event}}",
          payload: "{{input.payload}}",
        },
        null,
        2,
      ),
      output_key: "webhook_response",
    },
    tags: ["webhook", "http", "integration", "fallback"],
    setupHint: "Use this fallback when no native connector exists and validate endpoint/auth with Run test.",
    validationBadge: "Run test recommended",
  },
  {
    id: "notion-create",
    name: "Notion",
    description: "Create pages in Notion workspace",
    icon: "BookOpen",
    category: "integrations",
    nodeType: NODE_TYPES.HTTP,
    defaultConfig: {
      method: "POST",
      url: "https://api.notion.com/v1/pages",
      headers: {
        "Content-Type": "application/json",
        Authorization: "Bearer {{credentials.notion_token}}",
        "Notion-Version": "2022-06-28",
      },
      body: JSON.stringify(
        {
          parent: { database_id: "{{input.database_id}}" },
          properties: {
            title: {
              title: [{ text: { content: "{{input.title}}" } }],
            },
          },
        },
        null,
        2,
      ),
      output_key: "notion_response",
    },
    tags: ["notion", "pages", "database", "productivity"],
  },
  {
    id: "slack-message",
    name: "Slack",
    description: "Send messages to Slack channels",
    icon: "Hash",
    category: "integrations",
    nodeType: NODE_TYPES.HTTP,
    defaultConfig: {
      method: "POST",
      url: "{{input.webhook_url}}",
      headers: {
        "Content-Type": "application/json",
      },
      body: JSON.stringify(
        {
          text: "{{input.message}}",
          channel: "{{input.channel}}",
        },
        null,
        2,
      ),
      output_key: "slack_response",
    },
    tags: ["slack", "messaging", "webhook", "team"],
  },
  {
    id: "discord-webhook",
    name: "Discord",
    description: "Send messages to Discord channels",
    icon: "MessageCircle",
    category: "integrations",
    nodeType: NODE_TYPES.HTTP,
    defaultConfig: {
      method: "POST",
      url: "{{input.webhook_url}}",
      headers: {
        "Content-Type": "application/json",
      },
      body: JSON.stringify(
        {
          content: "{{input.message}}",
          username: "{{input.username}}",
        },
        null,
        2,
      ),
      output_key: "discord_response",
    },
    tags: ["discord", "messaging", "webhook", "gaming"],
  },
  {
    id: "openai-chat",
    name: "OpenAI",
    description: "Call OpenAI Chat Completions API",
    icon: "Sparkles",
    category: "integrations",
    nodeType: NODE_TYPES.HTTP,
    defaultConfig: {
      method: "POST",
      url: "https://api.openai.com/v1/chat/completions",
      headers: {
        "Content-Type": "application/json",
        Authorization: "Bearer {{credentials.openai_api_key}}",
      },
      body: JSON.stringify(
        {
          model: "gpt-4",
          messages: [
            { role: "system", content: "{{input.system_prompt}}" },
            { role: "user", content: "{{input.user_message}}" },
          ],
        },
        null,
        2,
      ),
      output_key: "openai_response",
    },
    tags: ["openai", "ai", "gpt", "chat", "llm"],
  },
  {
    id: "github-issue",
    name: "GitHub",
    description: "Create issues on GitHub repositories",
    icon: "Github",
    category: "integrations",
    nodeType: NODE_TYPES.HTTP,
    defaultConfig: {
      method: "POST",
      url: "https://api.github.com/repos/{{input.owner}}/{{input.repo}}/issues",
      headers: {
        "Content-Type": "application/json",
        Authorization: "Bearer {{credentials.github_token}}",
        Accept: "application/vnd.github+json",
      },
      body: JSON.stringify(
        {
          title: "{{input.title}}",
          body: "{{input.body}}",
          labels: ["{{input.labels}}"],
        },
        null,
        2,
      ),
      output_key: "github_response",
    },
    tags: ["github", "issues", "repository", "devops"],
  },
  {
    id: "google-sheets-append",
    name: "Google Sheets",
    description: "Append rows to Google Sheets",
    icon: "Table",
    category: "integrations",
    nodeType: NODE_TYPES.HTTP,
    defaultConfig: {
      method: "POST",
      url: "https://sheets.googleapis.com/v4/spreadsheets/{{input.spreadsheet_id}}/values/{{input.range}}:append?valueInputOption=USER_ENTERED",
      headers: {
        "Content-Type": "application/json",
        Authorization: "Bearer {{credentials.google_token}}",
      },
      body: JSON.stringify(
        {
          values: [["{{input.col1}}", "{{input.col2}}", "{{input.col3}}"]],
        },
        null,
        2,
      ),
      output_key: "sheets_response",
    },
    tags: ["google", "sheets", "spreadsheet", "data"],
  },
];

/**
 * Get presets by category
 */
function getPresetsByCategory(category: PresetCategory): QuickNodePreset[] {
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
      preset.tags.some((tag) => tag.toLowerCase().includes(lowerQuery)),
  );
}

/**
 * Get popular/featured presets
 */
function getPopularPresets(limit = 6): QuickNodePreset[] {
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
    .flatMap((id) => {
      const preset = getPresetById(id);
      return preset ? [preset] : [];
    })
    .slice(0, limit);
}

/**
 * Get integration presets for quick tool bar
 */
export function getIntegrationPresets(): QuickNodePreset[] {
  return QUICK_NODE_PRESETS.filter((preset) => preset.category === "integrations");
}
