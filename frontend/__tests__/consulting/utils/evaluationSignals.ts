import { evaluateStructure, type ConsultingExecutionState } from "./evaluateStructure";

export type EvaluationWeaknesses = {
  missing_drivers: string[];
  weak_assumptions: string[];
  unsupported_claims: string[];
  better_alternatives: string[];
};

export type ArtifactSignals = {
  structure: ReturnType<typeof evaluateStructure>;
  driverCoverageCount: number;
  recommendationMatchesHypothesis: boolean;
  recommendationEvidenceLinked: boolean;
  recommendationPlanLinked: boolean;
  rationaleDuplicatesHypothesis: boolean;
  specificEvidenceCount: number;
  hedgedEvidenceCount: number;
  genericEvidenceCount: number;
  actionableStepCount: number;
  distinctOwnerCount: number;
  localWeaknesses: EvaluationWeaknesses;
};

const DRIVER_RULES = [
  {
    key: "pricing",
    keywords: ["price", "pricing", "cost", "budget", "discount", "contract"],
  },
  {
    key: "product_fit",
    keywords: ["product", "feature", "fit", "needs", "workflow", "use case", "value"],
  },
  {
    key: "support",
    keywords: ["support", "ticket", "help desk", "service", "csm", "customer success"],
  },
  {
    key: "onboarding",
    keywords: ["onboarding", "activation", "adoption", "implementation", "setup", "training"],
  },
  {
    key: "competition",
    keywords: ["competitor", "alternative", "competition", "switch", "vendor"],
  },
  {
    key: "segmentation",
    keywords: ["smb", "segment", "persona", "cohort", "industry", "customer type"],
  },
];

const STOP_WORDS = new Set([
  "the",
  "and",
  "for",
  "with",
  "that",
  "this",
  "from",
  "have",
  "has",
  "into",
  "their",
  "they",
  "them",
  "will",
  "been",
  "being",
  "over",
  "than",
  "your",
  "were",
  "what",
  "when",
  "where",
  "which",
  "why",
  "how",
  "does",
  "doesn",
  "because",
  "could",
  "would",
  "should",
  "about",
  "there",
  "these",
  "those",
  "into",
  "each",
  "across",
  "through",
  "while",
  "within",
  "without",
  "after",
  "before",
  "under",
  "between",
  "company",
  "customers",
  "customer",
]);

const HEDGING_PATTERN =
  /\b(may|might|could|suggests?|suggesting|indicates?|indicating|potentially|possibly|appears?)\b/i;
const SPECIFIC_EVIDENCE_PATTERN =
  /\b(\d+%|\d+|month|months|quarter|quarters|crm|smb|survey|ticket|tickets|cohort|retention|churn)\b/i;
const ACTIONABLE_STEP_PATTERN =
  /^(analyze|review|segment|interview|audit|instrument|measure|launch|build|develop|improve|update|test|compare|prioritize|map|quantify)\b/i;

function normalizeText(value: string | null | undefined): string {
  return (value ?? "").trim().toLowerCase();
}

function uniqueStrings(values: string[]): string[] {
  const seen = new Set<string>();
  return values.filter((value) => {
    const normalized = normalizeText(value);
    if (!normalized || seen.has(normalized)) {
      return false;
    }
    seen.add(normalized);
    return true;
  });
}

function tokenize(value: string): string[] {
  return uniqueStrings(
    normalizeText(value)
      .replace(/[^a-z0-9\s]/g, " ")
      .split(/\s+/)
      .filter((token) => token.length > 2 && !STOP_WORDS.has(token)),
  );
}

function overlaps(left: string, right: string, minimumSharedTokens = 2): boolean {
  const leftTokens = new Set(tokenize(left));
  const sharedCount = tokenize(right).filter((token) => leftTokens.has(token)).length;
  return sharedCount >= minimumSharedTokens;
}

function textIncludesAny(text: string, keywords: string[]): boolean {
  const normalized = normalizeText(text);
  return keywords.some((keyword) => normalized.includes(keyword));
}

function hypothesisLabel(hypothesis: NonNullable<ConsultingExecutionState["hypotheses"]>[number]): string {
  return `${hypothesis.id ?? ""} ${hypothesis.text ?? ""}`.trim();
}

function selectedHypothesisText(state: ConsultingExecutionState): string {
  const selectedId = normalizeText(state.recommendation?.selected_hypothesis);
  if (!selectedId) {
    return "";
  }

  const match = (state.hypotheses ?? []).find((hypothesis) => normalizeText(hypothesis.id) === selectedId);
  return match?.text?.trim() ?? "";
}

function collectArtifactText(state: ConsultingExecutionState): string {
  return [
    state.problem_statement ?? "",
    state.issue_tree?.core_question ?? "",
    ...(state.issue_tree?.branches ?? []),
    ...(state.hypotheses ?? []).map((hypothesis) => hypothesisLabel(hypothesis)),
    ...(state.evidence_log ?? []),
    state.recommendation?.selected_hypothesis ?? "",
    selectedHypothesisText(state),
    state.recommendation?.rationale ?? "",
    ...(state.execution_plan ?? []).flatMap((item) => [item.step ?? "", item.expected_outcome ?? "", item.owner ?? ""]),
  ]
    .filter(Boolean)
    .join("\n");
}

function inferMissingDrivers(state: ConsultingExecutionState): string[] {
  const artifactText = collectArtifactText(state);
  const coveredDrivers = DRIVER_RULES.filter((rule) => textIncludesAny(artifactText, rule.keywords)).map(
    (rule) => rule.key,
  );
  const missingDrivers: string[] = [];

  if (!coveredDrivers.includes("onboarding")) {
    missingDrivers.push("Customer onboarding or time-to-value is not evaluated as a churn driver.");
  }
  if (!coveredDrivers.includes("competition")) {
    missingDrivers.push("Competitive alternatives are not evaluated as a reason customers may churn.");
  }
  if (!coveredDrivers.includes("segmentation")) {
    missingDrivers.push("The artifact does not test whether different SMB segments churn for different reasons.");
  }

  return uniqueStrings(missingDrivers);
}

function inferWeakAssumptions(state: ConsultingExecutionState): string[] {
  const weakAssumptions: string[] = [];
  const selectedHypothesis = normalizeText(state.recommendation?.selected_hypothesis);
  const rationale = normalizeText(state.recommendation?.rationale);
  const selectedText = normalizeText(selectedHypothesisText(state));

  if (
    (selectedHypothesis && rationale && selectedHypothesis === rationale) ||
    (selectedText && rationale && selectedText === rationale)
  ) {
    weakAssumptions.push("The recommendation rationale repeats the chosen hypothesis instead of proving it.");
  }

  for (const evidence of state.evidence_log ?? []) {
    if (HEDGING_PATTERN.test(evidence)) {
      weakAssumptions.push(`Evidence relies on hedging instead of direct proof: "${evidence}"`);
    }
  }

  if ((state.evidence_log ?? []).every((evidence) => !SPECIFIC_EVIDENCE_PATTERN.test(evidence))) {
    weakAssumptions.push(
      "Evidence is not grounded in concrete numbers, time windows, cohorts, or observed support volume.",
    );
  }

  return uniqueStrings(weakAssumptions).slice(0, 4);
}

function inferUnsupportedClaims(state: ConsultingExecutionState): string[] {
  const unsupportedClaims: string[] = [];
  const selectedHypothesisId = state.recommendation?.selected_hypothesis ?? "";
  const selectedHypothesis = selectedHypothesisText(state);
  const recommendationRationale = state.recommendation?.rationale ?? "";
  const combinedRecommendation = `${selectedHypothesisId} ${selectedHypothesis} ${recommendationRationale}`.trim();
  const evidenceLog = state.evidence_log ?? [];
  const executionPlan = state.execution_plan ?? [];

  if (
    combinedRecommendation &&
    evidenceLog.length > 0 &&
    !evidenceLog.some((evidence) => overlaps(combinedRecommendation, evidence, 2))
  ) {
    unsupportedClaims.push("The chosen recommendation is not directly supported by the evidence log.");
  }

  if (
    combinedRecommendation &&
    executionPlan.length > 0 &&
    !executionPlan.some((item) =>
      overlaps(combinedRecommendation, `${item.step ?? ""} ${item.expected_outcome ?? ""}`, 1),
    )
  ) {
    unsupportedClaims.push("The execution plan does not clearly follow from the chosen recommendation.");
  }

  if ((state.evidence_log ?? []).filter((evidence) => !SPECIFIC_EVIDENCE_PATTERN.test(evidence)).length >= 2) {
    unsupportedClaims.push("Multiple evidence items are generic claims without concrete support.");
  }

  return uniqueStrings(unsupportedClaims).slice(0, 4);
}

function inferBetterAlternatives(missingDrivers: string[], unsupportedClaims: string[]): string[] {
  const betterAlternatives: string[] = [];

  if (missingDrivers.some((item) => item.includes("onboarding"))) {
    betterAlternatives.push("Segment churn by onboarding cohort and time-to-value before selecting a root cause.");
  }
  if (missingDrivers.some((item) => item.includes("Competitive alternatives"))) {
    betterAlternatives.push(
      "Interview lost accounts and code churn reasons against specific competitive alternatives.",
    );
  }
  if (missingDrivers.some((item) => item.includes("SMB segments"))) {
    betterAlternatives.push(
      "Break SMB churn by size, tenure, and use case instead of treating the segment as uniform.",
    );
  }
  if (unsupportedClaims.some((item) => item.includes("evidence log"))) {
    betterAlternatives.push("Rank hypotheses by observed evidence strength before naming a winning recommendation.");
  }
  if (unsupportedClaims.some((item) => item.includes("execution plan"))) {
    betterAlternatives.push("Rewrite plan steps so each action explicitly tests or addresses the selected hypothesis.");
  }

  return uniqueStrings(betterAlternatives).slice(0, 4);
}

export function analyzeArtifact(state: ConsultingExecutionState): ArtifactSignals {
  const structure = evaluateStructure(state);
  const artifactText = collectArtifactText(state);
  const driverCoverageCount = DRIVER_RULES.filter((rule) => textIncludesAny(artifactText, rule.keywords)).length;
  const selectedHypothesis = state.recommendation?.selected_hypothesis ?? "";
  const selectedHypothesisTextValue = selectedHypothesisText(state);
  const evidenceLog = state.evidence_log ?? [];
  const executionPlan = state.execution_plan ?? [];
  const recommendationMatchesHypothesis = Boolean(
    selectedHypothesis &&
    (state.hypotheses ?? []).some((hypothesis) => normalizeText(hypothesis.id) === normalizeText(selectedHypothesis)),
  );
  const recommendationEvidenceLinked = Boolean(
    selectedHypothesisTextValue && evidenceLog.some((evidence) => overlaps(selectedHypothesisTextValue, evidence, 2)),
  );
  const recommendationPlanLinked = Boolean(
    selectedHypothesisTextValue &&
    executionPlan.some((item) =>
      overlaps(selectedHypothesisTextValue, `${item.step ?? ""} ${item.expected_outcome ?? ""}`, 1),
    ),
  );
  const rationaleDuplicatesHypothesis =
    Boolean(state.recommendation?.rationale) &&
    (normalizeText(state.recommendation?.rationale) === normalizeText(state.recommendation?.selected_hypothesis) ||
      normalizeText(state.recommendation?.rationale) === normalizeText(selectedHypothesisTextValue));
  const specificEvidenceCount = evidenceLog.filter((evidence) => SPECIFIC_EVIDENCE_PATTERN.test(evidence)).length;
  const hedgedEvidenceCount = evidenceLog.filter((evidence) => HEDGING_PATTERN.test(evidence)).length;
  const genericEvidenceCount = evidenceLog.filter((evidence) => !SPECIFIC_EVIDENCE_PATTERN.test(evidence)).length;
  const actionableStepCount = executionPlan.filter((item) => ACTIONABLE_STEP_PATTERN.test(item.step ?? "")).length;
  const distinctOwnerCount = new Set(executionPlan.map((item) => normalizeText(item.owner)).filter(Boolean)).size;
  const missingDrivers = inferMissingDrivers(state);
  const weakAssumptions = inferWeakAssumptions(state);
  const unsupportedClaims = inferUnsupportedClaims(state);
  const betterAlternatives = inferBetterAlternatives(missingDrivers, unsupportedClaims);

  return {
    structure,
    driverCoverageCount,
    recommendationMatchesHypothesis,
    recommendationEvidenceLinked,
    recommendationPlanLinked,
    rationaleDuplicatesHypothesis,
    specificEvidenceCount,
    hedgedEvidenceCount,
    genericEvidenceCount,
    actionableStepCount,
    distinctOwnerCount,
    localWeaknesses: {
      missing_drivers: missingDrivers,
      weak_assumptions: weakAssumptions,
      unsupported_claims: unsupportedClaims,
      better_alternatives: betterAlternatives,
    },
  };
}
