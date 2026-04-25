import { type ConsultingExecutionInput } from "../fixtures/case-pack-v2";
import { type ConsultingExecutionState } from "./evaluateStructure";
import { callLocalLlmJson } from "./localLlm";

function isExecutionState(value: unknown): value is ConsultingExecutionState {
  return Boolean(value && typeof value === "object");
}

export async function runBaseline(input: ConsultingExecutionInput): Promise<ConsultingExecutionState> {
  const result = await callLocalLlmJson<ConsultingExecutionState>({
    systemPrompt:
      [
        "You are producing a single-response consulting artifact for ForgeGraph evaluation.",
        "Use only the provided case input.",
        "Do not use memory, external context, or multi-step reasoning.",
        "Return JSON only. Do not include markdown, explanation, or extra keys.",
      ].join(" "),
    userPrompt: [
      "Solve this business problem in one response.",
      "Return exactly this JSON shape with all fields present:",
      "{",
      '  "problem_statement": "string",',
      '  "issue_tree": { "core_question": "string", "branches": ["string"] },',
      '  "hypotheses": [',
      '    { "id": "h1", "text": "string" }',
      "  ],",
      '  "evidence_log": ["string"],',
      '  "reflection": { "weak_hypotheses": ["h2"], "missing_evidence": ["string"], "inconsistencies": ["string"] },',
      '  "memory_retrieval": null,',
      '  "recommendation": { "selected_hypothesis": "h1", "selected_hypothesis_text": "string", "rationale": "string" },',
      '  "execution_plan": [',
      '    { "step": "string", "owner": "string", "expected_outcome": "string" }',
      "  ]",
      "}",
      "Use exactly three hypotheses with ids h1, h2, and h3.",
      "Use 1-3 weak_hypotheses ids based on the evidence you generated.",
      "Do not return null values.",
      "Except memory_retrieval, which must be null because the baseline has no memory.",
      "Do not omit any keys.",
      "Use the evidence pack and ignore distractors unless they materially support the chosen direction.",
      "",
      "Input JSON:",
      JSON.stringify(input, null, 2),
    ].join("\n"),
    maxTokens: 700,
  });

  if (!isExecutionState(result)) {
    throw new Error(`Baseline output was not a consulting execution state: ${JSON.stringify(result)}`);
  }

  return result;
}
