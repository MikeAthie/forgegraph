import {
  AGENT_WIZARD_PRESETS,
  AGENT_OUTPUT_PLACEHOLDER,
  OBSERVATION_CONTEXT_PLACEHOLDER,
  buildAgentWizardBlueprint,
  getAgentWizardPreset,
} from "@/lib/agent-wizard-presets";
import { NODE_TYPES } from "@/lib/graph-types";

describe("agent-wizard-presets", () => {
  it("includes required launch presets", () => {
    const presetIds = AGENT_WIZARD_PRESETS.map((preset) => preset.id);

    expect(presetIds).toEqual(
      expect.arrayContaining([
        "telegram-bot",
        "whatsapp-bot",
        "email-responder",
        "memory-first-assistant",
      ]),
    );
  });

  it("includes credential hints for integration-heavy presets", () => {
    const telegram = getAgentWizardPreset("telegram-bot");
    const whatsapp = getAgentWizardPreset("whatsapp-bot");
    const email = getAgentWizardPreset("email-responder");

    expect(telegram?.credentialHints.length).toBeGreaterThan(0);
    expect(telegram?.credentialHints.join(" ").toLowerCase()).toContain("botfather");
    expect(telegram?.credentialHints.join(" ").toLowerCase()).toContain("secret");
    expect(whatsapp?.credentialHints.length).toBeGreaterThan(0);
    expect(whatsapp?.credentialHints.join(" ").toLowerCase()).toContain("twilio");
    expect(email?.credentialHints.length).toBeGreaterThan(0);
  });

  it("builds the Jackie memory preset with curated observation nodes", () => {
    const preset = getAgentWizardPreset("memory-first-assistant");
    expect(preset).toBeDefined();

    const blueprint = buildAgentWizardBlueprint(preset!.seed);
    const nodeTypes = blueprint.nodes.map((node) => node.nodeType);

    expect(nodeTypes).toEqual([
      NODE_TYPES.OBSERVATION_CONTEXT,
      NODE_TYPES.AGENT,
      NODE_TYPES.OBSERVATION_SAVE,
      NODE_TYPES.OUTPUT,
    ]);
    expect(nodeTypes).toContain(NODE_TYPES.AGENT);
    expect(nodeTypes).toContain(NODE_TYPES.OUTPUT);

    expect(blueprint.nodes[1]?.config).toEqual(
      expect.objectContaining({
        observation_context_paths: [
          `node.${OBSERVATION_CONTEXT_PLACEHOLDER}.output`,
        ],
      }),
    );
    expect(blueprint.nodes[2]?.config).toEqual(
      expect.objectContaining({
        content_template: expect.stringContaining(AGENT_OUTPUT_PLACEHOLDER),
        topic_key: "jackie-memory",
      }),
    );
  });

  it("stores tool-first agent seeds for integration presets", () => {
    const email = getAgentWizardPreset("email-responder");
    expect(email?.seed.tools).toEqual(
      expect.arrayContaining(["gmail.list_unread", "gmail.send_message"]),
    );
    expect(email?.seed.approval_required_tools).toEqual(["gmail.send_message"]);
  });
});
