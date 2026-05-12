import { expect, test, type APIRequestContext, type TestInfo } from "@playwright/test";

import { buildConsultingGraph } from "../fixtures/consulting-graph";
import { createGraphName, createTestUser, ensureUserRegistered, getAccessToken } from "../../e2e/helpers";
import { evaluateStructure, type ConsultingExecutionState } from "../utils/evaluateStructure";
import { evaluateReasoning, type ReasoningEvaluation } from "../utils/evaluateReasoning";
import { evaluateWeaknesses, type EvaluationWeaknesses } from "../utils/evaluateWeaknesses";

const API_BASE_URL = (
  process.env.PLAYWRIGHT_API_URL ??
  process.env.NEXT_PUBLIC_API_URL ??
  "http://127.0.0.1:8000"
).replace(/\/$/, "");

const consultingInput = {
  problem: "A B2B SaaS company has increased churn from 5% to 12% in 3 months",
  context: {
    product: "CRM",
    customers: "SMBs",
  },
} as const;

const unrelatedConsultingInput = {
  problem: "An e-commerce marketplace has rising seller churn after a fee increase",
  context: {
    product: "Marketplace",
    customers: "Sellers",
  },
} as const;

type ConsultingCaseInput = typeof consultingInput;

type ConsultingRunDetail = {
  id: string;
  graph_id: string;
  graph_version_id: string;
  status: string;
  status_history: string[];
  backend_attempt_id: string;
  error_message?: string | null;
  output_json?: ConsultingExecutionState | null;
  node_runs: Array<{
    node_id: string;
    node_type: string;
    status: string;
    attempt: number;
    output_json?: Record<string, unknown> | null;
  }>;
};

type MemoryConfigPatch = {
  buffer_enabled: boolean;
  auto_prepend: boolean;
  vector_enabled: boolean;
};

type SeedObservation = {
  kind: "relevant" | "unrelated";
  input: ConsultingCaseInput;
  artifact: Record<string, unknown>;
};

type VariantResult = {
  label: string;
  graph_id: string;
  graph_version_id: string;
  run_id: string;
  status: string;
  state: ConsultingExecutionState;
  structure: ReturnType<typeof evaluateStructure>;
  score: ReasoningEvaluation;
  weaknesses: EvaluationWeaknesses;
  memory_usage: {
    influenced_node_count: number;
    curated_observation_total: number;
    vector_memory_total: number;
    buffer_message_total: number;
    prompt_nodes_with_memory_context: string[];
    prompt_nodes_with_augmented_prompt: string[];
    augmented_prompt_sections: {
      recent_messages: number;
      relevant_memories: number;
      summary: number;
      curated_observations: number;
    };
  };
  seeded_memory_ids: {
    relevant: string[];
    unrelated: string[];
  };
};

async function createGraph(request: APIRequestContext, accessToken: string, label: string): Promise<string> {
  const response = await request.post(`${API_BASE_URL}/api/graphs/`, {
    headers: { Authorization: `Bearer ${accessToken}` },
    data: {
      name: createGraphName(`Consulting Memory Compare ${label}`),
      description: `Consulting workflow memory comparison (${label}).`,
    },
  });
  expect(response.ok()).toBeTruthy();
  const body = (await response.json()) as { data: { id: string } };
  return body.data.id;
}

async function patchGraphMemoryConfig(
  request: APIRequestContext,
  accessToken: string,
  graphId: string,
  patch: MemoryConfigPatch,
): Promise<void> {
  const response = await request.patch(`${API_BASE_URL}/api/graphs/${graphId}/memory-config`, {
    headers: { Authorization: `Bearer ${accessToken}` },
    data: patch,
  });
  expect(response.ok()).toBeTruthy();
}

async function createGraphVersion(
  request: APIRequestContext,
  accessToken: string,
  graphId: string,
  graphJson: Record<string, unknown>,
): Promise<string> {
  const response = await request.post(`${API_BASE_URL}/api/graph-versions`, {
    headers: { Authorization: `Bearer ${accessToken}` },
    data: {
      graph_id: graphId,
      graph_json: graphJson,
    },
  });
  expect(response.ok()).toBeTruthy();
  const body = (await response.json()) as { data: { id: string } };
  return body.data.id;
}

async function createRun(
  request: APIRequestContext,
  accessToken: string,
  graphVersionId: string,
  input: ConsultingCaseInput = consultingInput,
): Promise<string> {
  const response = await request.post(`${API_BASE_URL}/api/runs`, {
    headers: { Authorization: `Bearer ${accessToken}` },
    data: {
      graph_version_id: graphVersionId,
      input_json: input,
    },
  });
  expect(response.ok()).toBeTruthy();
  const body = (await response.json()) as { data: { id: string } };
  return body.data.id;
}

async function createMemoryObservation(
  request: APIRequestContext,
  accessToken: string,
  graphId: string,
  seed: SeedObservation,
): Promise<string> {
  const response = await request.post(`${API_BASE_URL}/api/memory/observations`, {
    headers: { Authorization: `Bearer ${accessToken}` },
    data: {
      type: "consulting_case",
      title: `Consulting lesson: customer_churn_increase | ${seed.input.context.product} | ${seed.input.context.customers}`,
      content: JSON.stringify(seed.artifact),
      scope: "graph",
      graph_id: graphId,
      session_id: crypto.randomUUID(),
      topic_key: `consulting_case|customer_churn_increase|${seed.input.context.product}|${seed.input.context.customers}`,
    },
  });
  expect(response.ok()).toBeTruthy();
  const body = (await response.json()) as { data: { id: string } };
  return body.data.id;
}

async function pollRunDetail(
  request: APIRequestContext,
  accessToken: string,
  runId: string,
): Promise<ConsultingRunDetail> {
  let latestRun: ConsultingRunDetail | null = null;

  await expect
    .poll(
      async () => {
        const response = await request.get(`${API_BASE_URL}/api/runs/${runId}`, {
          headers: { Authorization: `Bearer ${accessToken}` },
        });
        expect(response.ok()).toBeTruthy();
        const body = (await response.json()) as { data: ConsultingRunDetail };
        latestRun = body.data;
        return body.data.status;
      },
      {
        timeout: 240_000,
        message: `Timed out waiting for run ${runId} to complete.`,
      },
    )
    .toMatch(/^(succeeded|failed|canceled)$/);

  if (!latestRun) {
    throw new Error(`Run ${runId} did not produce a detail payload.`);
  }

  return latestRun;
}

function summarizeMemoryUsage(run: ConsultingRunDetail): VariantResult["memory_usage"] {
  const promptLikeNodeRuns = run.node_runs.filter((nodeRun) => {
    const nodeType = nodeRun.node_type.toLowerCase();
    return nodeType === "prompt" || nodeType === "agent";
  });

  const promptNodesWithMemoryContext: string[] = [];
  const promptNodesWithAugmentedPrompt: string[] = [];
  let curatedObservationTotal = 0;
  let vectorMemoryTotal = 0;
  let bufferMessageTotal = 0;
  let recentMessagesCount = 0;
  let relevantMemoriesCount = 0;
  let summaryCount = 0;
  let curatedObservationsCount = 0;

  for (const nodeRun of promptLikeNodeRuns) {
    const nodeRunOutput = nodeRun.output_json?.output;
    const outputPayload =
      nodeRunOutput && typeof nodeRunOutput === "object"
        ? (nodeRunOutput as Record<string, unknown>)
        : (nodeRun.output_json ?? {});
    const rawPrompt = typeof outputPayload.prompt === "string" ? outputPayload.prompt : "";
    const hasRecentMessages = rawPrompt.split("Recent messages:").length > 1;
    const hasRelevantMemories = rawPrompt.split("Relevant memories:").length > 1;
    const hasSummary = rawPrompt.split("Summary of earlier conversation:").length > 1;
    const hasCuratedObservations = rawPrompt.split("Curated observations:").length > 1;

    if (hasRecentMessages || hasRelevantMemories || hasSummary || hasCuratedObservations) {
      promptNodesWithAugmentedPrompt.push(nodeRun.node_id);
    }
    if (hasRecentMessages) {
      recentMessagesCount += 1;
    }
    if (hasRelevantMemories) {
      relevantMemoriesCount += 1;
    }
    if (hasSummary) {
      summaryCount += 1;
    }
    if (hasCuratedObservations) {
      curatedObservationsCount += 1;
    }

    const memoryContext = outputPayload.memory_context;
    if (!memoryContext || typeof memoryContext !== "object") {
      continue;
    }

    promptNodesWithMemoryContext.push(nodeRun.node_id);

    const vectorMemoryCount = (memoryContext as Record<string, unknown>).vector_memory_count;
    const bufferMessageCount = (memoryContext as Record<string, unknown>).buffer_message_count;
    const curatedObservationCount = (memoryContext as Record<string, unknown>).curated_observation_count;

    curatedObservationTotal += typeof curatedObservationCount === "number" ? curatedObservationCount : 0;
    vectorMemoryTotal += typeof vectorMemoryCount === "number" ? vectorMemoryCount : 0;
    bufferMessageTotal += typeof bufferMessageCount === "number" ? bufferMessageCount : 0;
  }

  return {
    influenced_node_count: promptNodesWithMemoryContext.length,
    curated_observation_total: curatedObservationTotal,
    vector_memory_total: vectorMemoryTotal,
    buffer_message_total: bufferMessageTotal,
    prompt_nodes_with_memory_context: promptNodesWithMemoryContext,
    prompt_nodes_with_augmented_prompt: promptNodesWithAugmentedPrompt,
    augmented_prompt_sections: {
      recent_messages: recentMessagesCount,
      relevant_memories: relevantMemoriesCount,
      summary: summaryCount,
      curated_observations: curatedObservationsCount,
    },
  };
}

function nodeOutputPayload(nodeRun: ConsultingRunDetail["node_runs"][number]): Record<string, unknown> {
  return nodeRun.output_json && typeof nodeRun.output_json.output === "object" && nodeRun.output_json.output
    ? (nodeRun.output_json.output as Record<string, unknown>)
    : (nodeRun.output_json ?? {});
}

function extractSavedMemoryId(run: ConsultingRunDetail): string | null {
  const nodeRun = run.node_runs.find((candidate) => candidate.node_id === "store_case_memory");
  if (!nodeRun) {
    return null;
  }

  const payload = nodeOutputPayload(nodeRun);
  const observation = payload.observation;
  if (!observation || typeof observation !== "object") {
    return null;
  }

  return typeof (observation as Record<string, unknown>).id === "string"
    ? ((observation as Record<string, unknown>).id as string)
    : null;
}

async function executeVariant(
  request: APIRequestContext,
  accessToken: string,
  label: string,
  memoryConfig: MemoryConfigPatch,
  graphJson: Record<string, unknown>,
  seedObservations: SeedObservation[] = [],
): Promise<VariantResult> {
  const graphId = await createGraph(request, accessToken, label);
  await patchGraphMemoryConfig(request, accessToken, graphId, memoryConfig);
  const graphVersionId = await createGraphVersion(request, accessToken, graphId, graphJson);

  const seededMemoryIds: VariantResult["seeded_memory_ids"] = {
    relevant: [],
    unrelated: [],
  };

  const createdMemories = await Promise.all(
    seedObservations.map(async (seed) => ({
      kind: seed.kind,
      id: await createMemoryObservation(request, accessToken, graphId, seed),
    })),
  );
  createdMemories.forEach((memory) => seededMemoryIds[memory.kind].push(memory.id));

  const runId = await createRun(request, accessToken, graphVersionId, consultingInput);
  const run = await pollRunDetail(request, accessToken, runId);

  const state = (run.output_json ?? {}) as ConsultingExecutionState;
  const structure = evaluateStructure(state);
  const [score, weaknesses] = await Promise.all([evaluateReasoning(state), evaluateWeaknesses(state)]);
  const memoryUsage = summarizeMemoryUsage(run);

  return {
    label,
    graph_id: graphId,
    graph_version_id: graphVersionId,
    run_id: runId,
    status: run.status,
    state,
    structure,
    score,
    weaknesses,
    memory_usage: memoryUsage,
    seeded_memory_ids: seededMemoryIds,
  };
}

test.describe("Consulting Memory Comparison", () => {
  test("compares one run with memory enabled vs disabled", async ({ request }, testInfo: TestInfo) => {
    test.setTimeout(480_000);

    const user = createTestUser(testInfo, "consulting-memory-compare");
    await ensureUserRegistered(request, user);
    const accessToken = await getAccessToken(request, user);

    const relevantSeedObservation: SeedObservation = {
      kind: "relevant",
      input: consultingInput,
      artifact: {
        case_domain: "B2B SaaS CRM for SMBs",
        problem_type: "customer_churn_increase",
        problem_summary: consultingInput.problem,
        selected_hypothesis: "h1",
        selected_hypothesis_text: "Pricing adjustments can trigger SMB churn when perceived value lags price changes.",
        key_drivers: ["Pricing and Packaging", "Product-Market Fit", "Onboarding and Time-to-Value"],
        evidence_signals: [
          "Many customers report pricing frustration after commercial changes.",
          "Support tickets mention unclear value relative to cost.",
        ],
        reflection_warnings: [
          "Do not ignore onboarding and product-fit alternatives too early.",
          "Weak evidence often overstates pricing certainty.",
        ],
        recommended_next_actions: [
          "Review pricing complaints by segment.",
          "Compare churned accounts against perceived value feedback.",
        ],
      },
    };

    const unrelatedSeedObservation: SeedObservation = {
      kind: "unrelated",
      input: unrelatedConsultingInput,
      artifact: {
        case_domain: "E-commerce Marketplace for Sellers",
        problem_type: "customer_churn_increase",
        problem_summary: unrelatedConsultingInput.problem,
        selected_hypothesis: "h3",
        selected_hypothesis_text: "Seller churn increased because fee changes hurt small sellers disproportionately.",
        key_drivers: ["Pricing and Packaging", "Competition and Alternatives", "Customer Segmentation Differences"],
        evidence_signals: [
          "Sellers complained about marketplace fees after the policy change.",
          "Some sellers considered alternative channels.",
        ],
        reflection_warnings: ["Do not assume SMB CRM churn behaves like seller marketplace churn."],
        recommended_next_actions: ["Segment fee sensitivity by seller cohort."],
      },
    };

    const [enabled, disabled] = await Promise.all([
      executeVariant(
        request,
        accessToken,
        "memory-enabled",
        {
          buffer_enabled: true,
          auto_prepend: true,
          vector_enabled: true,
        },
        buildConsultingGraph({ memoryWorkflow: true }),
        [relevantSeedObservation, unrelatedSeedObservation],
      ),
      executeVariant(
        request,
        accessToken,
        "memory-disabled",
        {
          buffer_enabled: false,
          auto_prepend: false,
          vector_enabled: false,
        },
        buildConsultingGraph({ memoryWorkflow: false }),
      ),
    ]);

    expect(enabled.status).toBe("succeeded");
    expect(disabled.status).toBe("succeeded");
    expect(enabled.memory_usage.curated_observation_total).toBeGreaterThan(0);
    expect(enabled.memory_usage.prompt_nodes_with_augmented_prompt).toContain("hypothesis");
    expect(enabled.memory_usage.prompt_nodes_with_augmented_prompt).toContain("reflection");
    expect(enabled.state.memory_retrieval?.memory_ids ?? []).toEqual(
      expect.arrayContaining(enabled.seeded_memory_ids.relevant),
    );
    expect(enabled.state.memory_retrieval?.memory_ids ?? []).not.toEqual(
      expect.arrayContaining(enabled.seeded_memory_ids.unrelated),
    );
    expect(
      (enabled.state.memory_retrieval?.used_by_nodes ?? []).includes("hypothesis") ||
        (enabled.state.memory_retrieval?.used_by_nodes ?? []).includes("reflection"),
    ).toBe(true);

    const reasoningChanged =
      enabled.state.recommendation?.selected_hypothesis !== disabled.state.recommendation?.selected_hypothesis ||
      JSON.stringify(enabled.state.hypotheses ?? []) !== JSON.stringify(disabled.state.hypotheses ?? []) ||
      JSON.stringify(enabled.state.reflection ?? null) !== JSON.stringify(disabled.state.reflection ?? null);
    expect(reasoningChanged).toBe(true);

    const comparison = {
      backend_url: API_BASE_URL,
      input: consultingInput,
      enabled: {
        run_id: enabled.run_id,
        graph_id: enabled.graph_id,
        graph_version_id: enabled.graph_version_id,
        structure: enabled.structure,
        score: enabled.score,
        weaknesses: enabled.weaknesses,
        memory_usage: enabled.memory_usage,
        seeded_memory_ids: enabled.seeded_memory_ids,
        memory_retrieval: enabled.state.memory_retrieval,
        recommendation: enabled.state.recommendation,
        hypotheses: enabled.state.hypotheses,
        reflection: enabled.state.reflection,
      },
      disabled: {
        run_id: disabled.run_id,
        graph_id: disabled.graph_id,
        graph_version_id: disabled.graph_version_id,
        structure: disabled.structure,
        score: disabled.score,
        weaknesses: disabled.weaknesses,
        memory_usage: disabled.memory_usage,
        seeded_memory_ids: disabled.seeded_memory_ids,
        memory_retrieval: disabled.state.memory_retrieval,
        recommendation: disabled.state.recommendation,
        hypotheses: disabled.state.hypotheses,
        reflection: disabled.state.reflection,
      },
      reasoning_changed: reasoningChanged,
      delta_enabled_minus_disabled: {
        structure: enabled.score.structure - disabled.score.structure,
        coverage: enabled.score.coverage - disabled.score.coverage,
        coherence: enabled.score.coherence - disabled.score.coherence,
        usefulness: enabled.score.usefulness - disabled.score.usefulness,
        evidence: enabled.score.evidence - disabled.score.evidence,
        fatal_error: Number(enabled.score.fatal_error) - Number(disabled.score.fatal_error),
      },
    };

    await testInfo.attach("consulting-memory-compare.json", {
      body: Buffer.from(JSON.stringify(comparison, null, 2), "utf8"),
      contentType: "application/json",
    });

    console.log(JSON.stringify(comparison, null, 2));
  });
});
