export type ConsultingHypothesis = {
  id?: string | null;
  text?: string | null;
};

export type ConsultingExecutionState = {
  problem_statement?: string | null;
  issue_tree?: {
    core_question?: string | null;
    branches?: string[] | null;
  } | null;
  hypotheses?: ConsultingHypothesis[] | null;
  evidence_log?: string[] | null;
  reflection?: {
    weak_hypotheses?: string[] | null;
    missing_evidence?: string[] | null;
    inconsistencies?: string[] | null;
  } | null;
  memory_retrieval?: {
    scope?: string | null;
    count?: number | null;
    used_by_nodes?: string[] | null;
    ignored_by_nodes?: string[] | null;
    memory_ids?: string[] | null;
  } | null;
  recommendation?: {
    selected_hypothesis?: string | null;
    selected_hypothesis_text?: string | null;
    rationale?: string | null;
  } | null;
  execution_plan?: Array<{
    step?: string | null;
    owner?: string | null;
    expected_outcome?: string | null;
  }> | null;
};

export type StructureEvaluation = {
  structure_valid: boolean;
  artifact_complete: boolean;
  state_consistent: boolean;
};

function isNonEmptyString(value: unknown): value is string {
  return typeof value === "string" && value.trim().length > 0;
}

function isNonEmptyStringArray(value: unknown): value is string[] {
  return Array.isArray(value) && value.length > 0 && value.every((item) => isNonEmptyString(item));
}

function hasValidHypotheses(value: ConsultingExecutionState["hypotheses"]): value is ConsultingHypothesis[] {
  return Boolean(
    Array.isArray(value) &&
    value.length > 0 &&
    value.every((item) => item && typeof item === "object" && isNonEmptyString(item.id) && isNonEmptyString(item.text)),
  );
}

function hasValidIssueTree(
  value: ConsultingExecutionState["issue_tree"],
): value is NonNullable<ConsultingExecutionState["issue_tree"]> {
  return Boolean(value && isNonEmptyString(value.core_question) && isNonEmptyStringArray(value.branches));
}

function hasValidRecommendation(
  value: ConsultingExecutionState["recommendation"],
): value is NonNullable<ConsultingExecutionState["recommendation"]> {
  return Boolean(value && isNonEmptyString(value.selected_hypothesis) && isNonEmptyString(value.rationale));
}

function hasValidExecutionPlan(
  value: ConsultingExecutionState["execution_plan"],
): value is NonNullable<ConsultingExecutionState["execution_plan"]> {
  return Boolean(
    Array.isArray(value) &&
    value.length > 0 &&
    value.every(
      (item) =>
        item &&
        typeof item === "object" &&
        isNonEmptyString(item.step) &&
        isNonEmptyString(item.owner) &&
        isNonEmptyString(item.expected_outcome),
    ),
  );
}

export function evaluateStructure(state: ConsultingExecutionState): StructureEvaluation {
  const structureValid =
    isNonEmptyString(state.problem_statement) &&
    hasValidIssueTree(state.issue_tree) &&
    hasValidHypotheses(state.hypotheses) &&
    Array.isArray(state.evidence_log) &&
    hasValidRecommendation(state.recommendation) &&
    Array.isArray(state.execution_plan);

  const artifactComplete =
    structureValid &&
    hasValidHypotheses(state.hypotheses) &&
    isNonEmptyStringArray(state.evidence_log) &&
    hasValidExecutionPlan(state.execution_plan);

  const selectedHypothesis = state.recommendation?.selected_hypothesis?.trim();
  const hypotheses = state.hypotheses ?? [];
  const stateConsistent =
    artifactComplete &&
    Boolean(
      selectedHypothesis &&
      hypotheses.some((hypothesis) => hypothesis.id?.trim() === selectedHypothesis) &&
      state.issue_tree?.branches?.every((branch) => isNonEmptyString(branch)) &&
      state.execution_plan?.every(
        (item) =>
          isNonEmptyString(item.step) && isNonEmptyString(item.owner) && isNonEmptyString(item.expected_outcome),
      ),
    );

  return {
    structure_valid: structureValid,
    artifact_complete: artifactComplete,
    state_consistent: stateConsistent,
  };
}
