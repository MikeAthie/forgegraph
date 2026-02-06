import { AGENT_WIZARD_PRESETS, getAgentWizardPreset } from "@/lib/agent-wizard-presets";
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

  it("builds memory-first preset with memory and output nodes", () => {
    const preset = getAgentWizardPreset("memory-first-assistant");
    expect(preset).toBeDefined();

    const nodeTypes = preset!.nodes.map((node) => node.nodeType);
    expect(nodeTypes).toContain(NODE_TYPES.MEMORY);
    expect(nodeTypes).toContain(NODE_TYPES.OUTPUT);
  });
});
