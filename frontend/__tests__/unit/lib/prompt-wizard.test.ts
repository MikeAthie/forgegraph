import { buildPromptTemplate, suggestPromptTitle } from "@/lib/prompt-wizard";

describe("prompt-wizard", () => {
  describe("buildPromptTemplate", () => {
    it("should build a minimal template with a task", () => {
      const result = buildPromptTemplate({
        role: "",
        task: "Summarize the following text.",
        examples: [],
        outputPreset: "none",
        outputInstructions: "",
      });

      expect(result).toContain("## Task");
      expect(result).toContain("Summarize the following text.");
      expect(result).not.toContain("## Output Format");
    });

    it("should normalize role to start with 'You are'", () => {
      const result = buildPromptTemplate({
        role: "a software developer",
        task: "Write a function.",
        examples: [],
        outputPreset: "none",
        outputInstructions: "",
      });

      expect(result.split("\n")[0]).toBe("You are a software developer");
    });

    it("should include examples that have input or output", () => {
      const result = buildPromptTemplate({
        role: "",
        task: "Do the thing.",
        examples: [
          { input: "Hello", output: "Hi!" },
          { input: "", output: "" },
          { input: "Ping", output: "" },
        ],
        outputPreset: "none",
        outputInstructions: "",
      });

      expect(result).toContain("## Examples");
      expect(result).toContain("### Example 1");
      expect(result).toContain("**Input**");
      expect(result).toContain("**Output**");
      expect(result).toContain("Hello");
      expect(result).toContain("Hi!");
      expect(result).toContain("### Example 2");
      expect(result).toContain("Ping");
    });

    it("should include a preset output instruction for bullet list", () => {
      const result = buildPromptTemplate({
        role: "",
        task: "List items.",
        examples: [],
        outputPreset: "bullet_list",
        outputInstructions: "",
      });

      expect(result).toContain("## Output Format");
      expect(result).toContain("Respond as a bullet list.");
    });

    it("should not include output section for custom preset without instructions", () => {
      const result = buildPromptTemplate({
        role: "",
        task: "Do the thing.",
        examples: [],
        outputPreset: "custom",
        outputInstructions: "",
      });

      expect(result).not.toContain("## Output Format");
    });
  });

  describe("suggestPromptTitle", () => {
    it("should derive a title from role when provided", () => {
      expect(suggestPromptTitle({ role: "You are a financial analyst", task: "" })).toBe("a financial analyst");
    });

    it("should fall back to the first line of task", () => {
      expect(suggestPromptTitle({ role: "", task: "Draft an email.\nInclude a subject." })).toBe("Draft an email.");
    });
  });
});

