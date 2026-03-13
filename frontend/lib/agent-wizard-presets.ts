import { NODE_TYPES, type AgentNodeConfig, type NodeConfig, type NodeType } from "./graph-types";

export type AgentMemoryMode = "none" | "session" | "persistent";

export interface AgentWizardBlueprintNode {
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
      system_prompt:
        "You are a Telegram support assistant. Keep replies concise, friendly, and operationally safe.",
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
      system_prompt:
        "You are a WhatsApp assistant. Keep responses short, clear, and action-oriented.",
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
    expectedOutcome:
      "The agent reviews unread emails, drafts a response, and can send through Gmail tools.",
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
      system_prompt:
        "You write concise, professional replies. Preserve user intent and include clear next steps.",
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
    name: "Memory-first assistant",
    description: "Use persistent memory before answering and store the final answer after.",
    expectedOutcome:
      "The workflow loads memory, runs the agent, stores the final answer back to memory, and returns the response.",
    credentialHints: ["Optional: configure a persistent memory backend before running this flow"],
    seed: {
      agentLabel: "Context Agent",
      role: "Context-Aware Assistant",
      job_description: "Answer using recalled context and the latest user request.",
      instructions:
        "Review available workflow state, use the conversation history if present, and return a final answer once the task is complete.",
      system_prompt:
        "Use available memory context when relevant. If memory is empty, continue normally.",
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

export function buildAgentWizardBlueprint(seed: AgentWizardPresetSeed & {
  outputKey?: string;
}): AgentWizardBlueprint {
  const nodes: AgentWizardBlueprintNode[] = [];

  if (seed.memoryMode === "persistent") {
    nodes.push({
      nodeType: NODE_TYPES.MEMORY,
      label: "Load Memory",
      config: {
        action: "get",
        key: "conversation_history",
        namespace_path: "input.thread_id",
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
      max_steps: 6,
      max_tool_calls: 4,
    } satisfies Partial<AgentNodeConfig>,
  });

  if (seed.memoryMode === "persistent") {
    nodes.push({
      nodeType: NODE_TYPES.MEMORY,
      label: "Store Memory",
      config: {
        action: "set",
        key: "conversation_history",
        namespace_path: "input.thread_id",
        value_path: `node.${AGENT_OUTPUT_PLACEHOLDER}.output.final_output`,
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
