import type { OnboardingMilestone } from "./api";

export interface OnboardingProgress {
  total: number;
  completed: number;
  percentage: number;
}

export interface OnboardingRemediation {
  title: string;
  summary: string;
  steps: string[];
  docsUrl: string;
}

const ONBOARDING_DOC_LINKS = {
  templates: "https://github.com/GreyCrossX/forgegraph/blob/main/docs/user-guide/template-library.md",
  credentials:
    "https://github.com/GreyCrossX/forgegraph/blob/main/docs/user-guide/v2-launch-quickstart.md#3-credentials-and-provider-setup",
  troubleshooting: "https://github.com/GreyCrossX/forgegraph/blob/main/docs/user-guide/agent-wizard.md",
} as const;

function withFallbackSteps(steps: string[]): string[] {
  if (steps.length > 0) return steps;
  return [
    "Retry the run after re-checking template selection and input payload.",
    "Open the template preview to confirm required credentials are connected.",
  ];
}

export function getOnboardingProgress(items: OnboardingMilestone[]): OnboardingProgress {
  const total = items.length;
  if (total === 0) {
    return { total: 0, completed: 0, percentage: 0 };
  }

  const completed = items.filter((item) => item.completed).length;
  return {
    total,
    completed,
    percentage: Math.round((completed / total) * 100),
  };
}

export function buildRunRemediation(input: {
  message: string;
  hasTemplate: boolean;
  hasCredential: boolean;
  useSampleData: boolean;
}): OnboardingRemediation {
  const normalized = input.message.toLowerCase();
  const steps: string[] = [];

  if (!input.hasTemplate) {
    steps.push("Select a quick-start template before launching the first run.");
  }
  if (!input.hasCredential) {
    steps.push("Attach an API credential or confirm the selected template can run without one.");
  }
  if (normalized.includes("prompt_template") || normalized.includes("prompt node")) {
    steps.push("Open the cloned graph and configure any prompt nodes missing a prompt template.");
  }
  if (normalized.includes("output")) {
    steps.push("Ensure the workflow has a valid output node and mapping before running.");
  }
  if (!input.useSampleData && normalized.includes("json")) {
    steps.push("Fix custom JSON input to a valid object format, then retry.");
  }
  if (normalized.includes("credential") || normalized.includes("oauth")) {
    steps.push("Reconnect the required credential and verify token health.");
  }
  if (normalized.includes("encryption_key")) {
    steps.push("Backend encryption is not configured. Set ENCRYPTION_KEY before creating credentials.");
  }

  return {
    title: "Run needs attention",
    summary: input.message,
    steps: withFallbackSteps(steps),
    docsUrl: ONBOARDING_DOC_LINKS.troubleshooting,
  };
}

export function buildCredentialRemediation(input: { message: string; provider: string }): OnboardingRemediation {
  const normalized = input.message.toLowerCase();
  const steps: string[] = [`Verify the ${input.provider} key format and try saving again.`];

  if (normalized.includes("encryption_key")) {
    steps.unshift("Backend encryption key is missing. Configure ENCRYPTION_KEY and retry.");
  }
  if (normalized.includes("unique") || normalized.includes("already exists")) {
    steps.unshift("Use a different credential label for this provider.");
  }

  return {
    title: "Credential setup blocked",
    summary: input.message,
    steps: withFallbackSteps(steps),
    docsUrl: ONBOARDING_DOC_LINKS.credentials,
  };
}
