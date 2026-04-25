import { type ConsultingExecutionState } from "./evaluateStructure";
import { analyzeArtifact } from "./evaluationSignals";
import { callLocalLlmJson } from "./localLlm";

export type ReasoningEvaluation = {
  structure: number;
  coverage: number;
  coherence: number;
  usefulness: number;
  evidence: number;
  fatal_error: boolean;
  usable_first_draft: boolean;
};

function assertScoreRange(name: string, value: unknown): asserts value is number {
  if (typeof value !== "number" || !Number.isInteger(value) || value < 1 || value > 5) {
    throw new Error(`${name} must be an integer between 1 and 5. Received: ${String(value)}`);
  }
}

function clampScore(value: number): number {
  return Math.max(1, Math.min(5, Math.round(value)));
}

function buildHeuristicScores(state: ConsultingExecutionState): ReasoningEvaluation {
  const analysis = analyzeArtifact(state);
  const weaknessCount =
    analysis.localWeaknesses.missing_drivers.length +
    analysis.localWeaknesses.weak_assumptions.length +
    analysis.localWeaknesses.unsupported_claims.length;

  let structure = analysis.structure.structure_valid ? 3 : 1;
  if (analysis.structure.artifact_complete) {
    structure += 1;
  }
  if (analysis.structure.state_consistent) {
    structure += 1;
  }

  let coverage = 2;
  if (analysis.structure.structure_valid) {
    coverage += 1;
  }
  if (analysis.driverCoverageCount >= 3) {
    coverage += 1;
  }
  if (analysis.driverCoverageCount >= 4) {
    coverage += 1;
  }
  coverage -= Math.min(2, analysis.localWeaknesses.missing_drivers.length);

  let coherence = analysis.recommendationMatchesHypothesis ? 3 : 1;
  if (analysis.recommendationEvidenceLinked) {
    coherence += 1;
  }
  if (analysis.recommendationPlanLinked) {
    coherence += 1;
  }
  if (analysis.rationaleDuplicatesHypothesis) {
    coherence -= 1;
  }
  coherence -= Math.min(1, analysis.localWeaknesses.unsupported_claims.length);

  let usefulness = analysis.structure.artifact_complete ? 3 : 1;
  if (analysis.actionableStepCount >= 3) {
    usefulness += 1;
  }
  if (analysis.distinctOwnerCount >= 2) {
    usefulness += 1;
  }
  usefulness -= Math.min(2, Math.floor(weaknessCount / 3));

  let evidence = 1;
  if ((state.evidence_log ?? []).length > 0) {
    evidence += 1;
  }
  if (analysis.specificEvidenceCount >= 1) {
    evidence += 1;
  }
  if (analysis.recommendationEvidenceLinked) {
    evidence += 1;
  }
  if (analysis.specificEvidenceCount >= 2 && analysis.hedgedEvidenceCount === 0) {
    evidence += 1;
  }
  evidence -= Math.min(2, analysis.localWeaknesses.unsupported_claims.length);
  evidence -= Math.min(1, analysis.hedgedEvidenceCount);

  const fatalError =
    !analysis.structure.structure_valid ||
    !analysis.recommendationMatchesHypothesis ||
    (state.evidence_log ?? []).length === 0;
  const usableFirstDraft =
    !fatalError &&
    clampScore(usefulness) >= 3 &&
    clampScore(evidence) >= 3 &&
    analysis.localWeaknesses.unsupported_claims.length <= 1;

  return {
    structure: clampScore(structure),
    coverage: clampScore(coverage),
    coherence: clampScore(coherence),
    usefulness: clampScore(usefulness),
    evidence: clampScore(evidence),
    fatal_error: fatalError,
    usable_first_draft: usableFirstDraft,
  };
}

function validateJudgeResult(result: ReasoningEvaluation): void {
  assertScoreRange("structure", result.structure);
  assertScoreRange("coverage", result.coverage);
  assertScoreRange("coherence", result.coherence);
  assertScoreRange("usefulness", result.usefulness);
  assertScoreRange("evidence", result.evidence);
  if (typeof result.fatal_error !== "boolean") {
    throw new Error(`fatal_error must be boolean. Received: ${String(result.fatal_error)}`);
  }
  if (typeof result.usable_first_draft !== "boolean") {
    throw new Error(`usable_first_draft must be boolean. Received: ${String(result.usable_first_draft)}`);
  }
}

function combineScores(judge: ReasoningEvaluation, heuristic: ReasoningEvaluation): ReasoningEvaluation {
  return {
    structure: Math.min(judge.structure, heuristic.structure),
    coverage: Math.min(judge.coverage, heuristic.coverage),
    coherence: Math.min(judge.coherence, heuristic.coherence),
    usefulness: Math.min(judge.usefulness, heuristic.usefulness),
    evidence: Math.min(judge.evidence, heuristic.evidence),
    fatal_error: judge.fatal_error || heuristic.fatal_error,
    usable_first_draft: judge.usable_first_draft && heuristic.usable_first_draft,
  };
}

export async function evaluateReasoning(state: ConsultingExecutionState): Promise<ReasoningEvaluation> {
  const heuristic = buildHeuristicScores(state);
  const judge = await callLocalLlmJson<ReasoningEvaluation>({
    systemPrompt: [
      "You are a strict consulting-evaluation judge for ForgeGraph.",
      "Your job is to penalize generic answers, unsupported claims, weak causal reasoning, and weak evidence linkage.",
      "Do not be lenient. Do not reward fluency. A polished but generic answer must not receive a high score.",
      "Only assign a 5 when the artifact is unusually strong and clearly earns it.",
      "Return JSON only with no commentary and no extra keys.",
    ].join(" "),
    userPrompt: [
      "Evaluate the consulting artifact below.",
      "Use this strict rubric for each 1-5 score:",
      "- 1 = poor or broken: major gaps, generic filler, unsupported recommendation, or missing causal logic.",
      "- 3 = acceptable but limited: structurally present, somewhat relevant, but still generic, shallow, weakly evidenced, or partially linked.",
      "- 5 = exceptional: specific, well-supported, causally coherent, clearly linked across sections, and difficult to improve without new data.",
      "Additional instructions:",
      "- Penalize generic business language.",
      "- Penalize missing churn drivers such as onboarding, competition, segmentation, or value realization when the artifact ignores them.",
      "- Penalize unsupported claims and recommendations that are not directly tied to the evidence log.",
      "- Penalize execution plans that do not clearly flow from the chosen recommendation.",
      "- Do not default to 4 or 5. If you are uncertain, choose the lower score.",
      "- Use score 5 rarely and only when clearly justified by the artifact itself.",
      "Dimension definitions:",
      "- structure: is the expected consulting artifact present and internally well-formed?",
      "- coverage: does it cover the important churn drivers and problem dimensions rather than a narrow slice?",
      "- coherence: do hypotheses, evidence, recommendation, and plan logically connect?",
      "- usefulness: could an operator use this as a serious first draft without rewriting the core argument?",
      "- evidence: does the evidence log materially support the recommendation instead of hand-waving toward it?",
      'Return exactly this JSON shape: {"structure":1,"coverage":1,"coherence":1,"usefulness":1,"evidence":1,"fatal_error":false,"usable_first_draft":false}',
      "",
      "Consulting artifact JSON:",
      JSON.stringify(state, null, 2),
    ].join("\n"),
    maxTokens: 350,
  });

  validateJudgeResult(judge);
  const combined = combineScores(judge, heuristic);
  validateJudgeResult(combined);
  return combined;
}
