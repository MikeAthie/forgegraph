import type { Credential, GraphTemplate } from "./api";

export interface TemplateCredentialStatus {
  provider: string;
  label: string;
  connected: boolean;
  placeholder: string;
}

export interface TemplatePreview {
  expectedOutput: string;
  requiredCredentials: TemplateCredentialStatus[];
  placeholderVariables: string[];
  versionLabel: string;
  versionNote: string | null;
}

export interface TemplateQuickStart {
  id: string;
  title: string;
  description: string;
  template: GraphTemplate;
  expectedOutput: string;
  requiredProviders: string[];
  recommendedProvider: "openai" | "anthropic";
  recommendedModel: string;
}

type QuickStartDefinition = {
  id: string;
  title: string;
  description: string;
  matchers: RegExp[];
  expectedOutput: string;
  requiredProviders: string[];
  recommendedProvider: "openai" | "anthropic";
  recommendedModel: string;
};

const PROVIDER_LABELS: Record<string, string> = {
  openai: "OpenAI",
  anthropic: "Anthropic",
  google: "Google AI",
  gmail: "Gmail",
  google_calendar: "Google Calendar",
  google_tasks: "Google Tasks",
  telegram: "Telegram",
  twilio: "Twilio",
};

const PROVIDER_PLACEHOLDERS: Record<string, string> = {
  openai: "sk-proj-xxxxxxxxxxxxxxxxxxxx",
  anthropic: "sk-ant-api03-xxxxxxxxxxxxxxxxxxxx",
  google: "AIzaSyxxxxxxxxxxxxxxxxxxxx",
  gmail: "OAuth credential",
  google_calendar: "OAuth credential",
  google_tasks: "OAuth credential",
  telegram: "Bot token from @BotFather",
  twilio: "Account SID / Auth Token",
};

const QUICK_START_DEFINITIONS: QuickStartDefinition[] = [
  {
    id: "personal-assistant-telegram-gmail",
    title: "Personal Assistant (Telegram + Gmail)",
    description: "Triage inbox and generate assistant replies with calendar/task context.",
    matchers: [/personal/i, /life manager/i, /assistant/i],
    expectedOutput:
      "Produces a concise assistant response that prioritizes emails, calendar events, and follow-up tasks.",
    requiredProviders: ["openai", "gmail", "google_calendar", "google_tasks", "telegram"],
    recommendedProvider: "openai",
    recommendedModel: "gpt-4",
  },
  {
    id: "whatsapp-chatbot",
    title: "WhatsApp Chatbot",
    description: "Message-first conversational workflow for support and FAQ style replies.",
    matchers: [/whatsapp/i, /faq/i, /customer/i],
    expectedOutput:
      "Returns a ready-to-send chat reply with actionable follow-up details for the conversation.",
    requiredProviders: ["openai", "twilio"],
    recommendedProvider: "openai",
    recommendedModel: "gpt-4",
  },
];

function normalizeText(template: GraphTemplate): string {
  return [
    template.name,
    template.description,
    template.category,
    template.tags?.join(" ") ?? "",
    template.guide_steps?.join(" ") ?? "",
  ]
    .join(" ")
    .toLowerCase();
}

function uniq(values: string[]): string[] {
  const seen = new Set<string>();
  const output: string[] = [];
  for (const value of values) {
    const normalized = value.trim().toLowerCase();
    if (!normalized || seen.has(normalized)) continue;
    seen.add(normalized);
    output.push(normalized);
  }
  return output;
}

export function inferTemplateProviders(template: GraphTemplate): string[] {
  const text = normalizeText(template);
  const inferred: string[] = ["openai"];

  if (/\bgmail\b|\bemail\b/.test(text)) inferred.push("gmail");
  if (/\btelegram\b/.test(text)) inferred.push("telegram");
  if (/\bwhatsapp\b|\btwilio\b/.test(text)) inferred.push("twilio");
  if (/\bcalendar\b/.test(text)) inferred.push("google_calendar");
  if (/\btask\b|\btasks\b/.test(text)) inferred.push("google_tasks");
  if (/\bgoogle\b/.test(text)) inferred.push("google");
  if (/\banthropic\b|\bclaude\b/.test(text)) inferred.push("anthropic");

  return uniq(inferred);
}

export function getTemplatePlaceholders(template: GraphTemplate): string[] {
  const sample = template.sample_input ?? {};
  return Object.keys(sample)
    .map((key) => key.trim())
    .filter(Boolean)
    .sort((a, b) => a.localeCompare(b))
    .slice(0, 8)
    .map((key) => `{{input.${key}}}`);
}

export function getTemplateExpectedOutput(
  template: GraphTemplate,
  quickStartTitle?: string,
): string {
  const matchedQuickStart = quickStartTitle
    ? QUICK_START_DEFINITIONS.find((definition) => definition.title === quickStartTitle)
    : undefined;

  if (matchedQuickStart) {
    return matchedQuickStart.expectedOutput;
  }

  const text = normalizeText(template);
  if (/\bfaq\b/.test(text)) {
    return "Produces a structured FAQ-style answer with concise, user-friendly phrasing.";
  }
  if (/\bresearch\b/.test(text)) {
    return "Generates a research brief summarizing key findings and supporting evidence.";
  }
  if (/\bemail\b/.test(text)) {
    return "Builds a professional draft email response ready for review or delivery.";
  }

  const placeholders = getTemplatePlaceholders(template);
  if (placeholders.length > 0) {
    return `Returns a workflow output using the provided input fields (${placeholders.join(", ")}).`;
  }

  return "Returns the final workflow response defined by the template output node.";
}

export function buildTemplateQuickStarts(templates: GraphTemplate[]): TemplateQuickStart[] {
  const matchedTemplateIds = new Set<string>();
  const quickStarts: TemplateQuickStart[] = [];

  for (const definition of QUICK_START_DEFINITIONS) {
    const template = templates.find((candidate) => {
      const text = normalizeText(candidate);
      return definition.matchers.some((matcher) => matcher.test(text));
    });

    if (!template) continue;
    matchedTemplateIds.add(template.id);

    quickStarts.push({
      id: definition.id,
      title: definition.title,
      description: definition.description,
      template,
      expectedOutput: definition.expectedOutput,
      requiredProviders: definition.requiredProviders,
      recommendedProvider: definition.recommendedProvider,
      recommendedModel: definition.recommendedModel,
    });
  }

  // Fill remaining slots with top templates so quick-start UX is never empty.
  if (quickStarts.length < 3) {
    const fallbackTemplates = [...templates]
      .filter((template) => !matchedTemplateIds.has(template.id))
      .sort((a, b) => {
        const aScore = (a.usage_count ?? 0) + (a.rating_count ?? 0);
        const bScore = (b.usage_count ?? 0) + (b.rating_count ?? 0);
        if (bScore !== aScore) return bScore - aScore;
        return a.name.localeCompare(b.name);
      })
      .slice(0, 3 - quickStarts.length);

    for (const template of fallbackTemplates) {
      quickStarts.push({
        id: `recommended-${template.id}`,
        title: template.name,
        description: template.description,
        template,
        expectedOutput: getTemplateExpectedOutput(template),
        requiredProviders: inferTemplateProviders(template),
        recommendedProvider: "openai",
        recommendedModel: "gpt-4",
      });
    }
  }

  return quickStarts;
}

export function buildTemplatePreview(
  template: GraphTemplate,
  credentials: Credential[],
  quickStartTitle?: string,
): TemplatePreview {
  const quickStart = quickStartTitle
    ? QUICK_START_DEFINITIONS.find((definition) => definition.title === quickStartTitle)
    : undefined;
  const requiredProviders = uniq(quickStart?.requiredProviders ?? inferTemplateProviders(template));
  const credentialProviders = new Set(credentials.map((credential) => credential.provider.toLowerCase()));

  return {
    expectedOutput: getTemplateExpectedOutput(template, quickStartTitle),
    requiredCredentials: requiredProviders.map((provider) => ({
      provider,
      label: PROVIDER_LABELS[provider] ?? provider,
      connected: credentialProviders.has(provider),
      placeholder: PROVIDER_PLACEHOLDERS[provider] ?? "API token",
    })),
    placeholderVariables: getTemplatePlaceholders(template),
    versionLabel: `v${template.version}`,
    versionNote: template.changelog?.trim() ? template.changelog.trim() : null,
  };
}
