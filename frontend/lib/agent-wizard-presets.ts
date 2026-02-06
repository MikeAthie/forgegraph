import { NODE_TYPES, type NodeType } from "./graph-types";

export interface AgentWizardPresetNode {
  nodeType: NodeType;
  label: string;
  config: Record<string, unknown>;
}

export interface AgentWizardPreset {
  id: string;
  name: string;
  description: string;
  expectedOutcome: string;
  credentialHints: string[];
  nodes: AgentWizardPresetNode[];
}

export const AGENT_WIZARD_PRESETS: AgentWizardPreset[] = [
  {
    id: "telegram-bot",
    name: "Telegram bot",
    description: "Reply to Telegram messages with an AI-generated response.",
    expectedOutcome:
      "Incoming Telegram text or voice transcript is drafted by AI and sent back to chat.",
    credentialHints: [
      "Telegram bot token from @BotFather",
      "Set webhook + X-Telegram-Bot-Api-Secret-Token for secure trigger delivery",
    ],
    nodes: [
      {
        nodeType: NODE_TYPES.PROMPT,
        label: "Telegram Assistant",
        config: {
          role: "Telegram Bot Assistant",
          job_description: "Respond to Telegram user messages with concise answers.",
          system_prompt:
            "You are a Telegram assistant. Keep replies concise, friendly, and actionable.",
          prompt_template:
            "Respond to this Telegram message (text or voice transcript):\n\n{{input.message}}",
          model: "gpt-4",
          temperature: 0.6,
        },
      },
      {
        nodeType: NODE_TYPES.HTTP,
        label: "Telegram Send",
        config: {
          provider: "telegram",
          method: "POST",
          url: "https://api.telegram.org/bot{{credentials.telegram_token}}/sendMessage",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify(
            {
              chat_id: "{{input.chat_id}}",
              text: "{{state.previousNode.output}}",
            },
            null,
            2,
          ),
          output_key: "telegram_response",
        },
      },
      {
        nodeType: NODE_TYPES.OUTPUT,
        label: "Final Output",
        config: {
          output_mapping: {
            response: "state.previousNode.output",
          },
        },
      },
    ],
  },
  {
    id: "whatsapp-bot",
    name: "WhatsApp bot",
    description: "Reply to incoming WhatsApp messages through Twilio.",
    expectedOutcome:
      "Incoming WhatsApp text or voice transcript is processed by AI and sent back to the same thread.",
    credentialHints: [
      "Twilio Auth Token credential",
      "Configure Twilio webhook URL + signature verification",
      "Provide Twilio Account SID in workflow input/config",
    ],
    nodes: [
      {
        nodeType: NODE_TYPES.PROMPT,
        label: "WhatsApp Assistant",
        config: {
          role: "WhatsApp Support Assistant",
          job_description: "Respond to WhatsApp users with concise, practical answers.",
          system_prompt:
            "You are a WhatsApp assistant. Keep responses short, clear, and actionable.",
          prompt_template:
            "Reply to this WhatsApp message:\n\n{{input.message}}\n\nInclude next action if relevant.",
          model: "gpt-4",
          temperature: 0.5,
        },
      },
      {
        nodeType: NODE_TYPES.HTTP,
        label: "WhatsApp Send",
        config: {
          provider: "twilio",
          method: "POST",
          url: "https://api.twilio.com/2010-04-01/Accounts/{{input.account_sid}}/Messages.json",
          headers: {
            "Content-Type": "application/x-www-form-urlencoded",
          },
          body: "To={{input.whatsapp.from}}&From={{input.whatsapp.to}}&Body={{state.previousNode.output}}",
          output_key: "whatsapp_response",
        },
      },
      {
        nodeType: NODE_TYPES.OUTPUT,
        label: "Final Output",
        config: {
          output_mapping: {
            response: "state.previousNode.output",
          },
        },
      },
    ],
  },
  {
    id: "email-responder",
    name: "Email responder",
    description: "Draft professional responses for incoming emails.",
    expectedOutcome: "Fetches unread Gmail items, drafts a response, and sends the email via Gmail API.",
    credentialHints: [
      "Gmail OAuth credential with readonly + send scopes",
      "Optional Google Calendar/Tasks OAuth for richer context",
    ],
    nodes: [
      {
        nodeType: NODE_TYPES.HTTP,
        label: "Get Unread Gmail",
        config: {
          provider: "gmail",
          method: "GET",
          url: "https://gmail.googleapis.com/gmail/v1/users/me/messages?q=is:unread&maxResults=5",
          headers: {},
          output_key: "gmail_unread_messages",
        },
      },
      {
        nodeType: NODE_TYPES.PROMPT,
        label: "Draft Reply",
        config: {
          role: "Email Assistant",
          job_description: "Draft professional and concise email responses.",
          system_prompt:
            "You write concise, professional replies. Preserve user intent and include clear next steps.",
          prompt_template:
            "Draft a reply for this unread email summary:\n{{state.gmail_unread_messages}}",
          model: "gpt-4",
          temperature: 0.4,
        },
      },
      {
        nodeType: NODE_TYPES.HTTP,
        label: "Send Gmail Reply",
        config: {
          provider: "gmail",
          method: "POST",
          url: "https://gmail.googleapis.com/gmail/v1/users/me/messages/send",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify(
            {
              raw: "{{input.raw_message_base64url}}",
            },
            null,
            2,
          ),
          output_key: "gmail_send_response",
        },
      },
      {
        nodeType: NODE_TYPES.OUTPUT,
        label: "Final Output",
        config: {
          output_mapping: {
            send_result: "state.previousNode.output",
          },
        },
      },
    ],
  },
  {
    id: "memory-first-assistant",
    name: "Memory-first assistant",
    description: "Recall context, answer with AI, then persist new memory.",
    expectedOutcome: "Agent retrieves prior context and stores updated conversation state.",
    credentialHints: ["Optional: persistent memory backend (Redis/Vector)"],
    nodes: [
      {
        nodeType: NODE_TYPES.MEMORY,
        label: "Recall Memory",
        config: {
          memory_type: "buffer",
          memory_key: "conversation_history",
          max_messages: 20,
        },
      },
      {
        nodeType: NODE_TYPES.PROMPT,
        label: "Memory Assistant",
        config: {
          role: "Context-Aware Assistant",
          job_description: "Answer using recalled memory and latest user input.",
          system_prompt:
            "Use available memory context when relevant. If memory is empty, continue normally.",
          prompt_template:
            "Conversation memory:\n{{state.conversation_history}}\n\nUser message:\n{{input.message}}",
          model: "gpt-4",
          temperature: 0.5,
        },
      },
      {
        nodeType: NODE_TYPES.MEMORY,
        label: "Store Memory",
        config: {
          memory_type: "buffer",
          memory_key: "conversation_history",
          max_messages: 20,
        },
      },
      {
        nodeType: NODE_TYPES.OUTPUT,
        label: "Final Output",
        config: {
          output_mapping: {
            response: "state.previousNode.output",
          },
        },
      },
    ],
  },
];

export function getAgentWizardPreset(id: string): AgentWizardPreset | undefined {
  return AGENT_WIZARD_PRESETS.find((preset) => preset.id === id);
}
