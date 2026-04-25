import { type ConsultingExecutionState } from "./evaluateStructure";
import { analyzeArtifact, type EvaluationWeaknesses } from "./evaluationSignals";
import { callLocalLlmJson } from "./localLlm";

export type { EvaluationWeaknesses } from "./evaluationSignals";

function assertStringArray(name: string, value: unknown): asserts value is string[] {
  if (!Array.isArray(value) || value.some((item) => typeof item !== "string")) {
    throw new Error(`${name} must be an array of strings. Received: ${JSON.stringify(value)}`);
  }
}

function dedupe(values: string[]): string[] {
  const seen = new Set<string>();
  return values.filter((value) => {
    const normalized = value.trim().toLowerCase();
    if (!normalized || seen.has(normalized)) {
      return false;
    }
    seen.add(normalized);
    return true;
  });
}

function mergeWeaknesses(
  judgeWeaknesses: EvaluationWeaknesses,
  localWeaknesses: EvaluationWeaknesses,
): EvaluationWeaknesses {
  return {
    missing_drivers: dedupe([...judgeWeaknesses.missing_drivers, ...localWeaknesses.missing_drivers]).slice(0, 5),
    weak_assumptions: dedupe([...judgeWeaknesses.weak_assumptions, ...localWeaknesses.weak_assumptions]).slice(0, 5),
    unsupported_claims: dedupe([...judgeWeaknesses.unsupported_claims, ...localWeaknesses.unsupported_claims]).slice(
      0,
      5,
    ),
    better_alternatives: dedupe([...judgeWeaknesses.better_alternatives, ...localWeaknesses.better_alternatives]).slice(
      0,
      5,
    ),
  };
}

export async function evaluateWeaknesses(state: ConsultingExecutionState): Promise<EvaluationWeaknesses> {
  const judgeWeaknesses = await callLocalLlmJson<EvaluationWeaknesses>({
    systemPrompt: [
      "You are an adversarial consulting evaluator for ForgeGraph.",
      "Search for flaws only. Do not summarize the artifact. Do not mention positives. Do not explain strengths.",
      "Return JSON only with the required keys and arrays of critique strings.",
    ].join(" "),
    userPrompt: [
      "Critique the consulting artifact below.",
      "Your job is to find weaknesses aggressively.",
      "Rules:",
      "- missing_drivers: identify important churn drivers or problem dimensions the artifact ignored.",
      "- weak_assumptions: identify leaps of logic, generic assumptions, or causal claims made without proof.",
      "- unsupported_claims: identify statements where recommendation, evidence, or plan are not properly linked.",
      "- better_alternatives: propose tighter analyses or tests that would produce a more defensible answer.",
      "- Do not summarize the artifact.",
      "- Do not praise the artifact.",
      "- Do not leave arrays empty unless the artifact is exceptionally rigorous.",
      'Return exactly this JSON shape: {"missing_drivers":[],"weak_assumptions":[],"unsupported_claims":[],"better_alternatives":[]}',
      "",
      "Consulting artifact JSON:",
      JSON.stringify(state, null, 2),
    ].join("\n"),
    maxTokens: 400,
  });

  assertStringArray("missing_drivers", judgeWeaknesses.missing_drivers);
  assertStringArray("weak_assumptions", judgeWeaknesses.weak_assumptions);
  assertStringArray("unsupported_claims", judgeWeaknesses.unsupported_claims);
  assertStringArray("better_alternatives", judgeWeaknesses.better_alternatives);

  return mergeWeaknesses(judgeWeaknesses, analyzeArtifact(state).localWeaknesses);
}
