import {
  buildCredentialRemediation,
  buildRunRemediation,
  getOnboardingProgress,
} from "@/lib/onboarding-guide";
import type { OnboardingMilestone } from "@/lib/api";

describe("onboarding-guide helpers", () => {
  it("computes checklist progress percentage", () => {
    const milestones: OnboardingMilestone[] = [
      { key: "select_template", label: "Select template", completed: true, completed_at: null },
      { key: "attach_credential", label: "Attach credential", completed: false, completed_at: null },
      { key: "run_template", label: "Run template", completed: false, completed_at: null },
    ];

    expect(getOnboardingProgress(milestones)).toEqual({
      total: 3,
      completed: 1,
      percentage: 33,
    });
  });

  it("builds run remediation for prompt template validation failures", () => {
    const remediation = buildRunRemediation({
      message: "Prompt node requires either 'prompt_template' or 'prompt_id'",
      hasTemplate: true,
      hasCredential: false,
      useSampleData: false,
    });

    expect(remediation.title).toBe("Run needs attention");
    expect(remediation.steps).toEqual(
      expect.arrayContaining([
        expect.stringMatching(/attach an api credential/i),
        expect.stringMatching(/missing a prompt template/i),
      ]),
    );
  });

  it("builds credential remediation for missing encryption key", () => {
    const remediation = buildCredentialRemediation({
      message: "ENCRYPTION_KEY not configured in settings",
      provider: "openai",
    });

    expect(remediation.title).toBe("Credential setup blocked");
    expect(remediation.steps[0]).toMatch(/encryption key is missing/i);
  });
});
