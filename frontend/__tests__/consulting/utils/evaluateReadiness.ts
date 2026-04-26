import { type ConsultingCaseDefinition, type ConsultingDriver } from "../fixtures/case-pack-v2";
import { analyzeArtifact } from "./evaluationSignals";
import { evaluateStructure, type ConsultingExecutionState } from "./evaluateStructure";

export type DriverMatch = "correct_primary" | "correct_secondary" | "acceptable" | "wrong" | "unclear";
export type Actionability = "high" | "medium" | "low";
export type Consistency = "consistent" | "partial" | "inconsistent";

export type ReadinessEvaluation = {
  driver_match: DriverMatch;
  actionability: Actionability;
  consistency: Consistency;
};

const DRIVER_KEYWORDS: Array<{ driver: ConsultingDriver; keywords: string[] }> = [
  {
    driver: "user_mix_quality",
    keywords: [
      "user mix",
      "acquisition channel",
      "channel mix",
      "low-intent",
      "high-intent",
      "cohort quality",
      "traffic quality",
      "referral cohort",
      "creator cohort",
      "top-of-funnel quality",
      "signup quality",
    ],
  },
  {
    driver: "usability_regression",
    keywords: [
      "usability",
      "more clicks",
      "harder to use",
      "task completion time",
      "error correction",
      "workflow friction",
      "hidden defaults",
      "exception handling",
      "interface regression",
      "confusing console",
    ],
  },
  {
    driver: "pricing_segmentation_shift",
    keywords: [
      "packaging shift",
      "segment pricing",
      "price realization",
      "contract value",
      "bundle",
      "tier mix",
      "lower tier",
      "enterprise packaging",
      "average contract value",
      "revenue per account",
    ],
  },
  {
    driver: "billing_complexity",
    keywords: [
      "billing",
      "invoice",
      "proration",
      "credit",
      "overage",
      "charge confusion",
      "billing portal",
      "line items",
      "usage tier",
      "plan change",
    ],
  },
  {
    driver: "external_competition",
    keywords: [
      "competitor",
      "competing bundle",
      "switch vendors",
      "alternative platform",
      "market displacement",
      "broader suite",
      "vendor switch",
      "win-loss",
      "bundle comparison",
    ],
  },
  {
    driver: "activation_friction",
    keywords: [
      "activation",
      "time-to-value",
      "onboarding",
      "setup friction",
      "first use",
      "first-value",
      "trial conversion",
    ],
  },
  {
    driver: "workflow_misalignment",
    keywords: [
      "workflow mismatch",
      "workflow misalignment",
      "frontline workflow",
      "day-to-day workflow",
      "operational workflow",
      "process fit",
    ],
  },
  {
    driver: "discount_policy_drift",
    keywords: [
      "discount",
      "price concession",
      "discounting",
      "commercial guardrails",
      "deal desk",
      "discount policy",
      "pricing exception",
    ],
  },
  {
    driver: "support_capacity",
    keywords: ["support queue", "response time", "sla", "staffing", "agent capacity", "support backlog", "headcount"],
  },
  {
    driver: "feature_positioning_gap",
    keywords: [
      "positioning",
      "value narrative",
      "message-market fit",
      "feature promise",
      "expectation gap",
      "market narrative",
      "differentiation",
    ],
  },
];

type PrimaryBenchmarkDriver =
  | "user_mix_quality"
  | "usability_regression"
  | "pricing_segmentation_shift"
  | "billing_complexity"
  | "external_competition";

const SECONDARY_DRIVER_BY_PRIMARY: Record<PrimaryBenchmarkDriver, ConsultingDriver[]> = {
  user_mix_quality: ["activation_friction"],
  usability_regression: ["workflow_misalignment"],
  pricing_segmentation_shift: ["discount_policy_drift"],
  billing_complexity: ["support_capacity"],
  external_competition: ["feature_positioning_gap"],
};

const STOP_WORDS = new Set([
  "the",
  "and",
  "for",
  "with",
  "that",
  "this",
  "from",
  "into",
  "their",
  "they",
  "them",
  "have",
  "has",
  "had",
  "are",
  "was",
  "were",
  "been",
  "being",
  "after",
  "before",
  "about",
  "against",
  "across",
  "through",
  "because",
  "without",
  "within",
  "than",
  "what",
  "which",
  "when",
  "where",
  "while",
  "company",
  "customers",
  "customer",
  "accounts",
  "account",
  "teams",
  "team",
  "users",
  "user",
  "feature",
  "problem",
]);

function normalizeText(value: string | null | undefined): string {
  return (value ?? "").trim().toLowerCase();
}

function tokenize(value: string): string[] {
  return normalizeText(value)
    .replace(/[^a-z0-9\s-]/g, " ")
    .split(/\s+/)
    .filter((token) => token.length > 2 && !STOP_WORDS.has(token));
}

function countSharedTokens(left: string, right: string): number {
  const leftTokens = new Set(tokenize(left));
  return tokenize(right).filter((token) => leftTokens.has(token)).length;
}

function selectedHypothesisText(state: ConsultingExecutionState): string {
  if (state.recommendation?.selected_hypothesis_text) {
    return state.recommendation.selected_hypothesis_text;
  }

  const selectedHypothesis = normalizeText(state.recommendation?.selected_hypothesis);
  if (!selectedHypothesis) {
    return "";
  }

  return (
    state.hypotheses?.find((hypothesis) => normalizeText(hypothesis.id) === selectedHypothesis)?.text?.trim() ?? ""
  );
}

function inferDriverScores(state: ConsultingExecutionState): Map<ConsultingDriver, number> {
  const weightedTexts = [
    { text: state.problem_statement ?? "", weight: 1 },
    { text: state.recommendation?.selected_hypothesis ?? "", weight: 1 },
    { text: selectedHypothesisText(state), weight: 5 },
    { text: state.recommendation?.rationale ?? "", weight: 5 },
    ...((state.issue_tree?.branches ?? []).map((branch) => ({ text: branch, weight: 1 })) ?? []),
    ...((state.evidence_log ?? []).map((evidence) => ({ text: evidence, weight: 2 })) ?? []),
    ...((state.execution_plan ?? []).flatMap((item) => [
      { text: item.step ?? "", weight: 3 },
      { text: item.expected_outcome ?? "", weight: 1 },
    ]) ?? []),
  ].filter((entry) => normalizeText(entry.text).length > 0);

  const scores = new Map<ConsultingDriver, number>();
  for (const { driver } of DRIVER_KEYWORDS) {
    scores.set(driver, 0);
  }

  for (const entry of weightedTexts) {
    const normalizedText = normalizeText(entry.text);
    for (const rule of DRIVER_KEYWORDS) {
      if (rule.keywords.some((keyword) => normalizedText.includes(keyword))) {
        scores.set(rule.driver, (scores.get(rule.driver) ?? 0) + entry.weight);
      }
    }
  }

  return scores;
}

function inferPrimaryCandidate(state: ConsultingExecutionState): ConsultingDriver | null {
  const scores = inferDriverScores(state);
  const ordered = [...scores.entries()].sort((left, right) => right[1] - left[1]);
  const [winner, winnerScore] = ordered[0] ?? [null, 0];
  const secondScore = ordered[1]?.[1] ?? 0;

  if (!winner || winnerScore <= 0 || winnerScore === secondScore) {
    return null;
  }

  return winnerScore - secondScore <= 1 ? null : winner;
}

function evaluateDriverMatch(
  inferredDriver: ConsultingDriver | null,
  benchmark: ConsultingCaseDefinition["hidden_benchmark"],
): DriverMatch {
  if (!inferredDriver) {
    return "unclear";
  }
  if (inferredDriver === benchmark.primary_driver) {
    return "correct_primary";
  }
  if (SECONDARY_DRIVER_BY_PRIMARY[benchmark.primary_driver].includes(inferredDriver)) {
    return "correct_secondary";
  }
  if (benchmark.acceptable_drivers.includes(inferredDriver)) {
    return "acceptable";
  }
  if (benchmark.wrong_paths.includes(inferredDriver)) {
    return "wrong";
  }
  return "unclear";
}

function matchedExpectedActionCount(
  state: ConsultingExecutionState,
  benchmark: ConsultingCaseDefinition["hidden_benchmark"],
): number {
  const planEntries = state.execution_plan ?? [];
  if (planEntries.length === 0) {
    return 0;
  }

  let matches = 0;
  for (const expectedAction of benchmark.expected_actions) {
    const hasMatch = planEntries.some((item) => {
      const planText = `${item.step ?? ""} ${item.expected_outcome ?? ""}`.trim();
      return countSharedTokens(expectedAction, planText) >= 2;
    });
    if (hasMatch) {
      matches += 1;
    }
  }

  return matches;
}

function evaluateActionability(
  state: ConsultingExecutionState,
  benchmark: ConsultingCaseDefinition["hidden_benchmark"],
): Actionability {
  const structure = evaluateStructure(state);
  const analysis = analyzeArtifact(state);
  const expectedActionMatches = matchedExpectedActionCount(state, benchmark);

  if (
    structure.artifact_complete &&
    analysis.actionableStepCount >= 2 &&
    analysis.distinctOwnerCount >= 2 &&
    expectedActionMatches >= 2
  ) {
    return "high";
  }

  if (structure.structure_valid && analysis.actionableStepCount >= 1 && expectedActionMatches >= 1) {
    return "medium";
  }

  return "low";
}

function evaluateConsistency(state: ConsultingExecutionState): Consistency {
  const structure = evaluateStructure(state);
  const analysis = analyzeArtifact(state);

  const alignedChecks = [
    structure.state_consistent,
    analysis.recommendationMatchesHypothesis,
    analysis.recommendationEvidenceLinked,
    analysis.recommendationPlanLinked,
  ].filter(Boolean).length;

  if (structure.state_consistent && alignedChecks >= 4) {
    return "consistent";
  }

  if (structure.structure_valid && alignedChecks >= 2) {
    return "partial";
  }

  return "inconsistent";
}

export function evaluateReadiness(
  state: ConsultingExecutionState,
  benchmark: ConsultingCaseDefinition["hidden_benchmark"],
): ReadinessEvaluation {
  const inferredDriver = inferPrimaryCandidate(state);

  return {
    driver_match: evaluateDriverMatch(inferredDriver, benchmark),
    actionability: evaluateActionability(state, benchmark),
    consistency: evaluateConsistency(state),
  };
}

export function hasCorrectDirection(evaluation: ReadinessEvaluation): boolean {
  return ["correct_primary", "correct_secondary", "acceptable"].includes(evaluation.driver_match);
}
