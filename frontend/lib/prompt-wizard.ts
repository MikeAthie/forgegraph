export type PromptWizardExample = {
  input: string;
  output: string;
};

export type PromptWizardOutputPreset = "none" | "bullet_list" | "json" | "custom";

export type BuildPromptTemplateInput = {
  role: string;
  task: string;
  examples: PromptWizardExample[];
  outputPreset: PromptWizardOutputPreset;
  outputInstructions: string;
};

function normalizeRole(role: string): string {
  const trimmed = role.trim();
  if (!trimmed) return "";

  if (/^you are\b/i.test(trimmed)) {
    return trimmed;
  }

  return `You are ${trimmed}`;
}

function normalizeLines(text: string): string {
  const normalized = text.replace(/\r\n/g, "\n").trim();
  return normalized;
}

export function buildPromptTemplate({
  role,
  task,
  examples,
  outputPreset,
  outputInstructions,
}: BuildPromptTemplateInput): string {
  const sections: string[] = [];

  const roleLine = normalizeRole(role);
  if (roleLine) {
    sections.push(roleLine);
  }

  const taskText = normalizeLines(task);
  if (taskText) {
    sections.push(["## Task", taskText].join("\n"));
  }

  const cleanedExamples = (examples ?? [])
    .map((example) => ({
      input: normalizeLines(example.input),
      output: normalizeLines(example.output),
    }))
    .filter((example) => example.input || example.output);

  if (cleanedExamples.length > 0) {
    const exampleLines: string[] = ["## Examples"];
    cleanedExamples.forEach((example, index) => {
      exampleLines.push(`### Example ${index + 1}`);
      if (example.input) {
        exampleLines.push("**Input**");
        exampleLines.push(example.input);
      }
      if (example.output) {
        exampleLines.push("**Output**");
        exampleLines.push(example.output);
      }
    });
    sections.push(exampleLines.join("\n"));
  }

  const outputText = normalizeLines(outputInstructions);
  const resolvedOutputPreset = outputPreset ?? "none";

  const hasPresetInstruction = resolvedOutputPreset === "bullet_list" || resolvedOutputPreset === "json";
  const shouldIncludeOutputSection = outputText.length > 0 || hasPresetInstruction;

  if (shouldIncludeOutputSection) {
    const outputLines: string[] = ["## Output Format"];

    if (resolvedOutputPreset === "bullet_list") {
      outputLines.push("Respond as a bullet list.");
    } else if (resolvedOutputPreset === "json") {
      outputLines.push("Respond with a single JSON object.");
    }

    if (outputText) {
      outputLines.push(outputText);
    }

    sections.push(outputLines.join("\n"));
  }

  return sections.filter(Boolean).join("\n\n").trim();
}

export function suggestPromptTitle({ role, task }: { role: string; task: string }): string {
  const roleText = normalizeRole(role);
  if (roleText) {
    const withoutPrefix = roleText.replace(/^you are\s+/i, "");
    const trimmed = withoutPrefix.trim();
    if (trimmed) {
      return trimmed.length > 60 ? `${trimmed.slice(0, 57)}...` : trimmed;
    }
  }

  const taskText = normalizeLines(task);
  if (!taskText) return "New Prompt";

  const firstLine = taskText.split("\n")[0]?.trim() ?? "";
  if (!firstLine) return "New Prompt";
  return firstLine.length > 60 ? `${firstLine.slice(0, 57)}...` : firstLine;
}
