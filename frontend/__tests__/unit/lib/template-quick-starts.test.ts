import type { Credential, GraphTemplate } from "@/lib/api";
import {
  buildTemplatePreview,
  buildTemplateQuickStarts,
  inferTemplateProviders,
  getTemplatePlaceholders,
} from "@/lib/template-quick-starts";

function makeTemplate(overrides: Partial<GraphTemplate>): GraphTemplate {
  return {
    id: "template-1",
    group_id: "group-1",
    name: "Template",
    description: "Template description",
    category: "assistant",
    tags: [],
    estimated_minutes: 5,
    sample_input: {},
    guide_steps: [],
    version: 1,
    changelog: "",
    is_latest: true,
    visibility: "public",
    owner_organization_id: null,
    rating_average: null,
    rating_count: 0,
    usage_count: 0,
    ...overrides,
  };
}

describe("template-quick-starts", () => {
  it("infers credential providers from template metadata", () => {
    const template = makeTemplate({
      name: "Personal Assistant",
      description: "Reads Gmail and sends Telegram updates.",
      tags: ["email", "telegram"],
    });

    expect(inferTemplateProviders(template)).toEqual(expect.arrayContaining(["openai", "gmail", "telegram"]));
  });

  it("extracts sample input placeholders", () => {
    const template = makeTemplate({
      sample_input: {
        message: "hello",
        user_name: "alex",
      },
    });

    expect(getTemplatePlaceholders(template)).toEqual(["{{input.message}}", "{{input.user_name}}"]);
  });

  it("builds quick-start aliases for known templates", () => {
    const templates = [
      makeTemplate({
        id: "life-manager",
        name: "Personal Life Manager",
        description: "Assistant that checks emails and tasks.",
      }),
      makeTemplate({
        id: "faq",
        name: "Customer FAQ Generator",
      }),
    ];

    const quickStarts = buildTemplateQuickStarts(templates);
    const titles = quickStarts.map((quickStart) => quickStart.title);

    expect(titles).toEqual(expect.arrayContaining(["Personal Assistant (Telegram + Gmail)", "WhatsApp Chatbot"]));
  });

  it("builds preview with credential coverage and version metadata", () => {
    const template = makeTemplate({
      id: "life-manager",
      name: "Personal Life Manager",
      version: 3,
      changelog: "Added calendar context.",
      sample_input: { message: "hello" },
    });
    const credentials: Credential[] = [
      {
        id: "cred-1",
        provider: "openai",
        name: "OpenAI Key",
        key_hint: "1234",
        is_oauth_connection: false,
        token_expires_at: null,
        health_status: "healthy",
        requires_reauth: false,
        health_message: null,
        created_at: new Date().toISOString(),
      },
    ];

    const preview = buildTemplatePreview(template, credentials, "Personal Assistant (Telegram + Gmail)");

    expect(preview.versionLabel).toBe("v3");
    expect(preview.versionNote).toBe("Added calendar context.");
    expect(preview.placeholderVariables).toContain("{{input.message}}");
    expect(preview.requiredCredentials).toEqual(
      expect.arrayContaining([
        expect.objectContaining({ provider: "openai", connected: true }),
        expect.objectContaining({ provider: "gmail", connected: false }),
      ]),
    );
  });

  it("only marks OAuth providers connected when OAuth credential is healthy", () => {
    const template = makeTemplate({
      id: "life-manager",
      name: "Personal Life Manager",
      description: "Uses gmail and calendar context",
    });
    const credentials: Credential[] = [
      {
        id: "gmail-api-key",
        provider: "gmail",
        name: "Gmail API Key",
        key_hint: "1234",
        is_oauth_connection: false,
        token_expires_at: null,
        health_status: "healthy",
        requires_reauth: false,
        health_message: null,
        created_at: new Date().toISOString(),
      },
      {
        id: "gmail-oauth-expired",
        provider: "gmail",
        name: "Gmail OAuth Expired",
        key_hint: "5678",
        is_oauth_connection: true,
        token_expires_at: new Date().toISOString(),
        health_status: "expired",
        requires_reauth: true,
        health_message: "OAuth access token expired",
        created_at: new Date().toISOString(),
      },
    ];

    const preview = buildTemplatePreview(template, credentials);
    const gmailStatus = preview.requiredCredentials.find((item) => item.provider === "gmail");
    expect(gmailStatus?.connected).toBe(false);
  });
});
