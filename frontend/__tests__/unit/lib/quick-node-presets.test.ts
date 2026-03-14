import { getPresetById, getIntegrationPresets, searchPresets } from "@/lib/quick-node-presets";

describe("quick-node-presets", () => {
  it("includes core P2 integration presets", () => {
    const presetIds = getIntegrationPresets().map((preset) => preset.id);
    expect(presetIds).toEqual(
      expect.arrayContaining([
        "telegram-send",
        "whatsapp-send",
        "gmail-get-unread",
        "gmail-send",
        "calendar-list-events",
        "calendar-create-event",
        "tasks-list",
        "tasks-create",
        "webhook-fallback",
      ]),
    );
  });

  it("configures provider defaults for OAuth-backed nodes", () => {
    expect(getPresetById("gmail-get-unread")?.defaultConfig).toEqual(
      expect.objectContaining({ provider: "gmail", method: "GET" }),
    );
    expect(getPresetById("calendar-list-events")?.defaultConfig).toEqual(
      expect.objectContaining({ provider: "google_calendar", method: "GET" }),
    );
    expect(getPresetById("tasks-list")?.defaultConfig).toEqual(
      expect.objectContaining({ provider: "google_tasks", method: "GET" }),
    );
  });

  it("searches integration presets by provider keyword", () => {
    const whatsappResults = searchPresets("whatsapp");
    expect(whatsappResults.some((preset) => preset.id === "whatsapp-send")).toBe(true);

    const calendarResults = searchPresets("calendar");
    expect(calendarResults.some((preset) => preset.id === "calendar-list-events")).toBe(true);
  });

  it("includes setup hints and validation badges for quick-start integrations", () => {
    const telegram = getPresetById("telegram-send");
    const webhook = getPresetById("webhook-fallback");

    expect(telegram?.requiredCredentialProvider).toBe("telegram");
    expect(telegram?.validationBadge?.toLowerCase()).toContain("credential");
    expect(telegram?.setupHint?.toLowerCase()).toContain("botfather");

    expect(webhook?.validationBadge?.toLowerCase()).toContain("run test");
    expect(webhook?.setupHint?.toLowerCase()).toContain("fallback");
  });
});
