import { type ConsultingExecutionState } from "./evaluateStructure";
import { callLocalLlmJson } from "./localLlm";

type ConsultingCaseInput = {
  problem: string;
  context: {
    product: string;
    customers: string;
  };
};

function isExecutionState(value: unknown): value is ConsultingExecutionState {
  return Boolean(value && typeof value === "object");
}

export async function runBaseline(input: ConsultingCaseInput): Promise<ConsultingExecutionState> {
  const result = await callLocalLlmJson<ConsultingExecutionState>({
    systemPrompt:
      "You are producing a single-response consulting artifact for ForgeGraph evaluation. Return JSON only. Do not include markdown, explanation, or extra keys.",
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
      '  "recommendation": { "selected_hypothesis": "h1", "rationale": "string" },',
      '  "execution_plan": [',
      '    { "step": "string", "owner": "string", "expected_outcome": "string" }',
      "  ]",
      "}",
      "Use exactly three hypotheses with ids h1, h2, and h3.",
      "Do not return null values.",
      "Do not omit any keys.",
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
