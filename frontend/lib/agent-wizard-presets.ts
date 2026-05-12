import { NODE_TYPES, type AgentNodeConfig, type NodeConfig, type NodeType } from "./graph-types";

export type AgentMemoryMode = "none" | "session" | "persistent";

interface AgentWizardBlueprintNode {
  nodeType: NodeType;
  label: string;
  config: NodeConfig;
}

export interface AgentWizardBlueprint {
  name: string;
  nodes: AgentWizardBlueprintNode[];
}

export interface AgentWizardPresetSeed {
  agentLabel: string;
  instructions: string;
  system_prompt?: string;
  provider?: string;
  model?: string;
  temperature?: number;
  tools: string[];
  approval_required_tools?: string[];
  role?: string;
  job_description?: string;
  notes?: string;
  memoryMode?: AgentMemoryMode;
  outputKey?: string;
}

export interface AgentWizardPreset {
  id: string;
  name: string;
  description: string;
  expectedOutcome: string;
  credentialHints: string[];
  seed: AgentWizardPresetSeed;
}

export const AGENT_OUTPUT_PLACEHOLDER = "__AGENT_NODE__";
export const OBSERVATION_CONTEXT_PLACEHOLDER = "__OBSERVATION_CONTEXT_NODE__";

export const AGENT_WIZARD_PRESETS: AgentWizardPreset[] = [
  {
    id: "telegram-bot",
    name: "Telegram bot",
    description: "Reply to Telegram messages with an AI-generated response.",
    expectedOutcome:
      "Incoming Telegram text or voice transcript is handled by one agent node with Telegram tool access.",
    credentialHints: [
      "Telegram bot token from @BotFather",
      "Configure webhook secret verification before exposing the trigger publicly",
      "Install or register a telegram.send_message tool package before running this flow",
    ],
    seed: {
      agentLabel: "Telegram Support Agent",
      role: "Telegram Bot Assistant",
      job_description: "Respond to Telegram user messages with concise, actionable help.",
      instructions:
        "Read the incoming Telegram message from workflow state, decide whether a reply is needed, and use telegram.send_message when you are ready to respond.",
      system_prompt: "You are a Telegram support assistant. Keep replies concise, friendly, and operationally safe.",
      provider: "openai",
      model: "gpt-4.1-mini",
      temperature: 0.4,
      tools: ["telegram.send_message"],
      approval_required_tools: [],
      outputKey: "telegram_result",
    },
  },
  {
    id: "whatsapp-bot",
    name: "WhatsApp bot",
    description: "Reply to incoming WhatsApp messages through a verified tool.",
    expectedOutcome:
      "Incoming WhatsApp text or voice transcript is handled by one agent node with WhatsApp send access.",
    credentialHints: [
      "Twilio Auth Token credential",
      "Install or register a whatsapp.send_message tool package before running this flow",
    ],
    seed: {
      agentLabel: "WhatsApp Ops Agent",
      role: "WhatsApp Support Assistant",
      job_description: "Respond to WhatsApp users with short, practical answers.",
      instructions:
        "Read the incoming WhatsApp message from workflow state, prepare a concise answer, and call whatsapp.send_message to deliver it when appropriate.",
      system_prompt: "You are a WhatsApp assistant. Keep responses short, clear, and action-oriented.",
      provider: "openai",
      model: "gpt-4.1-mini",
      temperature: 0.4,
      tools: ["whatsapp.send_message"],
      approval_required_tools: [],
      outputKey: "whatsapp_result",
    },
  },
  {
    id: "email-responder",
    name: "Email responder",
    description: "Draft and send professional responses for incoming emails.",
    expectedOutcome: "The agent reviews unread emails, drafts a response, and can send through Gmail tools.",
    credentialHints: [
      "Gmail OAuth credential with readonly + send scopes",
      "Install or register gmail.list_unread and gmail.send_message tools before running this flow",
    ],
    seed: {
      agentLabel: "Inbox Agent",
      role: "Email Assistant",
      job_description: "Draft professional email responses and send them when they are ready.",
      instructions:
        "Use gmail.list_unread to review current inbound email context, draft a professional reply, and use gmail.send_message when you are confident the response is correct.",
      system_prompt: "You write concise, professional replies. Preserve user intent and include clear next steps.",
      provider: "openai",
      model: "gpt-4.1-mini",
      temperature: 0.3,
      tools: ["gmail.list_unread", "gmail.send_message"],
      approval_required_tools: ["gmail.send_message"],
      outputKey: "email_result",
    },
  },
  {
    id: "memory-first-assistant",
    name: "Jackie memory workflow",
    description: "Recall Jackie-specific curated memory before answering and save a new observation after.",
    expectedOutcome:
      "The workflow recalls Jackie context, answers with that context in view, saves a new observation, and returns the response.",
    credentialHints: [
      "Optional: configure a persistent memory backend before running this flow",
      "No external integration is required for the supported Jackie demo path",
    ],
    seed: {
      agentLabel: "Jackie",
      role: "Jackie Relationship Assistant",
      job_description: "Answer using recalled customer context and the latest user request.",
      instructions:
        "Review the curated observation context before answering. Use remembered customer details when they are relevant, then return a direct final answer.",
      system_prompt:
        "You are Jackie, a memory-first assistant. Prefer retrieved curated observations when they help you answer accurately, but continue normally if context is empty.",
      provider: "openai",
      model: "gpt-4.1-mini",
      temperature: 0.3,
      tools: ["knowledge.lookup"],
      approval_required_tools: [],
      memoryMode: "persistent",
      outputKey: "response",
    },
  },
];

export function getAgentWizardPreset(id: string): AgentWizardPreset | undefined {
  return AGENT_WIZARD_PRESETS.find((preset) => preset.id === id);
}

export function buildAgentWizardBlueprint(
  seed: AgentWizardPresetSeed & {
    outputKey?: string;
  },
): AgentWizardBlueprint {
  const nodes: AgentWizardBlueprintNode[] = [];

  if (seed.memoryMode === "persistent") {
    nodes.push({
      nodeType: NODE_TYPES.OBSERVATION_CONTEXT,
      label: "Recall Jackie Context",
      config: {
        query_template: "What should I remember about Jackie before answering this request?",
        limit: 5,
      },
    });
  }

  nodes.push({
    nodeType: NODE_TYPES.AGENT,
    label: seed.agentLabel,
    config: {
      role: seed.role,
      job_description: seed.job_description,
      notes: seed.notes,
      instructions: seed.instructions,
      system_prompt: seed.system_prompt,
      provider: seed.provider,
      model: seed.model,
      temperature: seed.temperature,
      tools: seed.tools,
      approval_required_tools: seed.approval_required_tools,
      ...(seed.memoryMode === "persistent"
        ? {
            observation_context_paths: [`node.${OBSERVATION_CONTEXT_PLACEHOLDER}.output`],
          }
        : {}),
      max_steps: 6,
      max_tool_calls: 4,
    } satisfies Partial<AgentNodeConfig>,
  });

  if (seed.memoryMode === "persistent") {
    nodes.push({
      nodeType: NODE_TYPES.OBSERVATION_SAVE,
      label: "Save Jackie Observation",
      config: {
        type: "customer_memory",
        scope: "graph",
        title_template: "Jackie follow-up memory",
        content_template: `Latest request: {{input.message}}. Final answer: {{node.${AGENT_OUTPUT_PLACEHOLDER}.output.final_output}}`,
        topic_key: "jackie-memory",
        dedupe: true,
        update_topic: true,
      },
    });
  }

  nodes.push({
    nodeType: NODE_TYPES.OUTPUT,
    label: "Workflow Result",
    config: {
      output_mapping: {
        [seed.outputKey || "response"]: `node.${AGENT_OUTPUT_PLACEHOLDER}.output.final_output`,
      },
    },
  });

  return {
    name: seed.agentLabel,
    nodes,
  };
}
