import { type ReadinessEvaluation } from "./evaluateReadiness";

export type PairwiseJudgement = {
  winner: "forgegraph" | "baseline" | "tie";
  reason: string;
};

const DRIVER_MATCH_RANK: Record<ReadinessEvaluation["driver_match"], number> = {
  correct_primary: 4,
  correct_secondary: 3,
  acceptable: 2,
  unclear: 1,
  wrong: 0,
};

const ACTIONABILITY_RANK: Record<ReadinessEvaluation["actionability"], number> = {
  high: 2,
  medium: 1,
  low: 0,
};

const CONSISTENCY_RANK: Record<ReadinessEvaluation["consistency"], number> = {
  consistent: 2,
  partial: 1,
  inconsistent: 0,
};

function compareRank<T extends keyof ReadinessEvaluation>(
  forgegraph: ReadinessEvaluation,
  baseline: ReadinessEvaluation,
  key: T,
  ranks: Record<ReadinessEvaluation[T], number>,
): number {
  return ranks[forgegraph[key]] - ranks[baseline[key]];
}

export function judgePairwise(
  forgegraph: ReadinessEvaluation,
  baseline: ReadinessEvaluation,
): PairwiseJudgement {
  const driverDelta = compareRank(forgegraph, baseline, "driver_match", DRIVER_MATCH_RANK);
  if (driverDelta > 0) {
    return {
      winner: "forgegraph",
      reason: `ForgeGraph had the stronger directional call (${forgegraph.driver_match} vs ${baseline.driver_match}).`,
    };
  }
  if (driverDelta < 0) {
    return {
      winner: "baseline",
      reason: `Baseline had the stronger directional call (${baseline.driver_match} vs ${forgegraph.driver_match}).`,
    };
  }

  const actionabilityDelta = compareRank(forgegraph, baseline, "actionability", ACTIONABILITY_RANK);
  if (actionabilityDelta > 0) {
    return {
      winner: "forgegraph",
      reason: `Direction was tied, but ForgeGraph produced the more actionable plan (${forgegraph.actionability} vs ${baseline.actionability}).`,
    };
  }
  if (actionabilityDelta < 0) {
    return {
      winner: "baseline",
      reason: `Direction was tied, but baseline produced the more actionable plan (${baseline.actionability} vs ${forgegraph.actionability}).`,
    };
  }

  const consistencyDelta = compareRank(forgegraph, baseline, "consistency", CONSISTENCY_RANK);
  if (consistencyDelta > 0) {
    return {
      winner: "forgegraph",
      reason: `Direction and actionability were tied, and ForgeGraph was more internally consistent (${forgegraph.consistency} vs ${baseline.consistency}).`,
    };
  }
  if (consistencyDelta < 0) {
    return {
      winner: "baseline",
      reason: `Direction and actionability were tied, and baseline was more internally consistent (${baseline.consistency} vs ${forgegraph.consistency}).`,
    };
  }

  return {
    winner: "tie",
    reason: "Both systems landed on the same directional quality, plan quality, and internal consistency.",
  };
}
