export type ConsultingGraphOptions = {
  model?: string;
  memoryWorkflow?: boolean;
};

const defaultModel =
  process.env.PLAYWRIGHT_CONSULTING_LLM_MODEL ?? process.env.OPENAI_MODEL ?? "docker.io/ai/llama3.1:latest";
const promptNodeTimeoutMs = 180_000;

const issueTreeSchema = {
  type: "object",
  properties: {
    core_question: { type: "string" },
    branches: {
      type: "array",
      items: { type: "string" },
    },
  },
  required: ["core_question", "branches"],
  additionalProperties: false,
} as const;

const hypothesisSchema = {
  type: "object",
  properties: {
    id: { type: "string", pattern: "^h[1-6]$" },
    text: { type: "string" },
  },
  required: ["id", "text"],
  additionalProperties: false,
} as const;

const recommendationSchema = {
  type: "object",
  properties: {
    selected_hypothesis: { type: "string", pattern: "^h[1-6]$" },
    selected_hypothesis_text: { type: "string" },
    rationale: { type: "string" },
  },
  required: ["selected_hypothesis", "selected_hypothesis_text", "rationale"],
  additionalProperties: false,
} as const;

const memoryRetrievalSchema = {
  type: "object",
  properties: {
    count: { type: "integer" },
    scope: { type: "string" },
    used_by_nodes: {
      type: "array",
      items: { type: "string" },
    },
    ignored_by_nodes: {
      type: "array",
      items: { type: "string" },
    },
    memory_ids: {
      type: "array",
      items: { type: "string" },
    },
  },
  required: ["count", "scope", "used_by_nodes", "ignored_by_nodes", "memory_ids"],
  additionalProperties: false,
} as const;

const reflectionSchema = {
  type: "object",
  properties: {
    weak_hypotheses: {
      type: "array",
      items: { type: "string", pattern: "^h[1-6]$" },
    },
    missing_evidence: {
      type: "array",
      items: { type: "string" },
    },
    inconsistencies: {
      type: "array",
      items: { type: "string" },
    },
  },
  required: ["weak_hypotheses", "missing_evidence", "inconsistencies"],
  additionalProperties: false,
} as const;

const executionPlanItemSchema = {
  type: "object",
  properties: {
    step: { type: "string" },
    owner: { type: "string" },
    expected_outcome: { type: "string" },
  },
  required: ["step", "owner", "expected_outcome"],
  additionalProperties: false,
} as const;

const executionStateSchema = {
  type: "object",
  properties: {
    problem_statement: { type: ["string", "null"] },
    issue_tree: {
      ...issueTreeSchema,
      type: ["object", "null"],
    },
    hypotheses: {
      type: "array",
      items: hypothesisSchema,
    },
    evidence_log: {
      type: "array",
      items: { type: "string" },
    },
    reflection: {
      ...reflectionSchema,
      type: ["object", "null"],
    },
    memory_retrieval: {
      ...memoryRetrievalSchema,
      type: ["object", "null"],
    },
    recommendation: {
      ...recommendationSchema,
      type: ["object", "null"],
    },
    execution_plan: {
      type: "array",
      items: executionPlanItemSchema,
    },
  },
  required: [
    "problem_statement",
    "issue_tree",
    "hypotheses",
    "evidence_log",
    "reflection",
    "recommendation",
    "execution_plan",
  ],
  additionalProperties: false,
} as const;

const intakePatchSchema = {
  type: "object",
  properties: {
    state_patch: executionStateSchema,
  },
  required: ["state_patch"],
  additionalProperties: false,
} as const;

const structuringPatchSchema = {
  type: "object",
  properties: {
    state_patch: {
      type: "object",
      properties: {
        problem_statement: { type: "string" },
        issue_tree: issueTreeSchema,
      },
      required: ["problem_statement", "issue_tree"],
      additionalProperties: false,
    },
  },
  required: ["state_patch"],
  additionalProperties: false,
} as const;

const hypothesisPatchSchema = {
  type: "object",
  properties: {
    state_patch: {
      type: "object",
      properties: {
        hypotheses: {
          type: "array",
          items: hypothesisSchema,
          minItems: 3,
          maxItems: 3,
        },
        memory_retrieval: memoryRetrievalSchema,
      },
      required: ["hypotheses", "memory_retrieval"],
      additionalProperties: false,
    },
  },
  required: ["state_patch"],
  additionalProperties: false,
} as const;

const analysisPatchSchema = {
  type: "object",
  properties: {
    state_patch: {
      type: "object",
      properties: {
        evidence_log: {
          type: "array",
          items: { type: "string" },
          minItems: 3,
        },
      },
      required: ["evidence_log"],
      additionalProperties: false,
    },
  },
  required: ["state_patch"],
  additionalProperties: false,
} as const;

const recommendationPatchSchema = {
  type: "object",
  properties: {
    state_patch: {
      type: "object",
      properties: {
        recommendation: recommendationSchema,
      },
      required: ["recommendation"],
      additionalProperties: false,
    },
  },
  required: ["state_patch"],
  additionalProperties: false,
} as const;

const reflectionPatchSchema = {
  type: "object",
  properties: {
    state_patch: {
      type: "object",
      properties: {
        reflection: {
          ...reflectionSchema,
          properties: {
            weak_hypotheses: {
              type: "array",
              items: { type: "string", pattern: "^h[1-6]$" },
              minItems: 1,
            },
            missing_evidence: {
              type: "array",
              items: { type: "string" },
              minItems: 1,
            },
            inconsistencies: {
              type: "array",
              items: { type: "string" },
              minItems: 1,
            },
          },
        },
        memory_retrieval: memoryRetrievalSchema,
      },
      required: ["reflection", "memory_retrieval"],
      additionalProperties: false,
    },
  },
  required: ["state_patch"],
  additionalProperties: false,
} as const;

const plannerPatchSchema = {
  type: "object",
  properties: {
    state_patch: {
      type: "object",
      properties: {
        execution_plan: {
          type: "array",
          items: executionPlanItemSchema,
          minItems: 3,
        },
      },
      required: ["execution_plan"],
      additionalProperties: false,
    },
  },
  required: ["state_patch"],
  additionalProperties: false,
} as const;

function buildStagePrompt(stage: string, instructions: string[]): string {
  return [
    `Stage: ${stage}`,
    "Return JSON only. Do not wrap the JSON in markdown fences.",
    "Follow these instructions exactly:",
    ...instructions.map((instruction) => `- ${instruction}`),
    "",
    "Problem:",
    "{{input.problem}}",
    "",
    "Context JSON:",
    "{{input.context}}",
    "",
    "Current execution state JSON:",
    "{{vars.execution_state}}",
  ].join("\n");
}

function buildPromptConfig(args: {
  stage: string;
  model: string;
  outputKey: string;
  outputSchema: Record<string, unknown>;
  systemPrompt: string;
  promptTemplate: string;
  disableMemoryContext?: boolean;
  observationContextPaths?: string[];
}): Record<string, unknown> {
  return {
    provider: "openai",
    model: args.model,
    temperature: 0,
    max_tokens: 450,
    stream: false,
    disable_memory_context: args.disableMemoryContext ?? true,
    ...(args.observationContextPaths && args.observationContextPaths.length > 0
      ? { observation_context_paths: args.observationContextPaths }
      : {}),
    output_key: args.outputKey,
    output_schema: args.outputSchema,
    schema_mode: "strict",
    simulation_role: args.stage,
    system_prompt: args.systemPrompt,
    prompt_template: args.promptTemplate,
  };
}

function buildMergeNode(id: string, name: string, expression: string): Record<string, unknown> {
  return {
    id,
    type: "transform",
    name,
    config: {
      expression_type: "state_patch",
      expression,
      output_key: "execution_state",
    },
    retry_policy: {
      max_attempts: 1,
      backoff_ms: 0,
      backoff_strategy: "fixed",
    },
  };
}

export function buildConsultingGraph(options: ConsultingGraphOptions = {}): Record<string, unknown> {
  const model = options.model ?? defaultModel;
  const memoryWorkflowEnabled = options.memoryWorkflow ?? true;

  return {
    nodes: [
      {
        id: "intake",
        type: "prompt",
        name: "Intake",
        config: buildPromptConfig({
          stage: "intake",
          model,
          outputKey: "intake_patch",
          outputSchema: intakePatchSchema,
          systemPrompt:
            "You are the intake node in a replayable ForgeGraph consulting workflow. Return only valid JSON that matches the schema.",
          promptTemplate: buildStagePrompt("intake", [
            'Return exactly one top-level key named "state_patch".',
            "Set state_patch.problem_statement to one sentence restating the problem from the input.",
            "Set state_patch.issue_tree to null.",
            "Set state_patch.hypotheses to an empty array.",
            "Set state_patch.evidence_log to an empty array.",
            "Set state_patch.reflection to null.",
            "Set state_patch.memory_retrieval to null.",
            "Set state_patch.recommendation to null.",
            "Set state_patch.execution_plan to an empty array.",
          ]),
        }),
        retry_policy: {
          max_attempts: 1,
          backoff_ms: 0,
          backoff_strategy: "fixed",
        },
        timeout_ms: promptNodeTimeoutMs,
      },
      buildMergeNode("merge_intake_state", "Merge Intake State", "node.intake.output.structured_response.state_patch"),
      {
        id: "structuring",
        type: "prompt",
        name: "Structuring",
        config: buildPromptConfig({
          stage: "structuring",
          model,
          outputKey: "structuring_patch",
          outputSchema: structuringPatchSchema,
          systemPrompt:
            "You are the structuring node in a replayable ForgeGraph consulting workflow. Return only valid JSON that matches the schema.",
          promptTemplate: buildStagePrompt("structuring", [
            'Return exactly one top-level key named "state_patch".',
            "Generate a concise problem statement for the consulting case.",
            "Generate a MECE issue tree for the business problem.",
            "You MUST consider pricing and packaging.",
            "You MUST consider product-market fit.",
            "You MUST consider onboarding and time-to-value.",
            "You MUST consider customer support and success.",
            "You MUST consider competition and alternatives.",
            "You MUST consider customer segmentation differences.",
            "Set state_patch.issue_tree.core_question to the main churn question.",
            "Set state_patch.issue_tree.branches to exactly six short branch labels, one for each required driver area.",
            "Do not add any fields beyond problem_statement and issue_tree.",
          ]),
        }),
        retry_policy: {
          max_attempts: 1,
          backoff_ms: 0,
          backoff_strategy: "fixed",
        },
        timeout_ms: promptNodeTimeoutMs,
      },
      buildMergeNode(
        "merge_structuring_state",
        "Merge Structuring State",
        "node.structuring.output.structured_response.state_patch",
      ),
      ...(memoryWorkflowEnabled
        ? [
            {
              id: "previous_similar_cases",
              type: "observation_search",
              name: "Previous Similar Cases",
              config: {
                scope: "graph",
                type: "consulting_case",
                limit: 3,
                topic_key_template:
                  "consulting_case|customer_churn_increase|{{input.context.product}}|{{input.context.customers}}",
                query_template: [
                  "case_domain: B2B SaaS {{input.context.product}} for {{input.context.customers}}",
                  "problem_type: customer_churn_increase",
                  "problem_summary: {{input.problem}}",
                  "problem_statement: {{vars.execution_state.problem_statement}}",
                  "key_drivers: {{vars.execution_state.issue_tree.branches}}",
                ].join("\n"),
              },
              retry_policy: {
                max_attempts: 1,
                backoff_ms: 0,
                backoff_strategy: "fixed",
              },
            },
            {
              id: "merge_memory_retrieval_state",
              type: "transform",
              name: "Merge Memory Retrieval State",
              config: {
                expression_type: "state_patch",
                expression: "node.previous_similar_cases.output.state_patch",
                output_key: "execution_state",
              },
              retry_policy: {
                max_attempts: 1,
                backoff_ms: 0,
                backoff_strategy: "fixed",
              },
            },
          ]
        : []),
      {
        id: "hypothesis",
        type: "prompt",
        name: "Hypothesis",
        config: buildPromptConfig({
          stage: "hypothesis",
          model,
          outputKey: "hypothesis_patch",
          outputSchema: hypothesisPatchSchema,
          systemPrompt:
            "You are the hypothesis node in a replayable ForgeGraph consulting workflow. Return only valid JSON that matches the schema.",
          disableMemoryContext: memoryWorkflowEnabled ? false : true,
          observationContextPaths: memoryWorkflowEnabled ? ["node.previous_similar_cases.output"] : undefined,
          promptTemplate: buildStagePrompt("hypothesis", [
            'Return exactly one top-level key named "state_patch".',
            "Using the issue_tree, generate exactly three hypotheses for the churn increase.",
            "Generate one hypothesis per major branch.",
            "Each hypothesis must correspond to a distinct driver from the issue_tree.",
            "Hypotheses must be mutually distinct and non-overlapping.",
            "Do NOT combine multiple drivers into one hypothesis.",
            "Prefer breadth over depth at this stage.",
            "If memory context is provided, compare each retrieved memory to the current problem before using it.",
            "Treat a memory as relevant only if it matches the same domain, a similar churn problem structure, or similar driver patterns from the current issue_tree.",
            "If no retrieved memory is clearly relevant, ignore memory completely and generate hypotheses only from the current problem and issue_tree.",
            "Do NOT mention previous similar cases, prior runs, historical examples, or memory unless at least one retrieved memory is clearly relevant.",
            "If relevant memory influences a hypothesis, use it to broaden or prioritize plausible drivers, but treat it as a weak prior signal rather than ground truth.",
            'Only when relevant memory changes a hypothesis, explicitly use the phrase "Previous similar cases suggest..." in that hypothesis text.',
            "Do not let memory override the current problem statement, issue_tree, or current-case evidence needs.",
            "Choose three different issue_tree branches and write one clear driver-specific hypothesis for each.",
            "Return state_patch.hypotheses as exactly three objects with ids h1, h2, and h3.",
            'Each hypothesis object must have the shape { "id": "h1", "text": "..." }.',
            "Also return state_patch.memory_retrieval.",
            "Copy state_patch.memory_retrieval.count, scope, and memory_ids exactly from the current execution state's memory_retrieval object.",
            'If memory was relevant and used, set state_patch.memory_retrieval.used_by_nodes to ["hypothesis"] and ignored_by_nodes to [].',
            'If memory was absent or irrelevant, set state_patch.memory_retrieval.used_by_nodes to [] and ignored_by_nodes to ["hypothesis"].',
          ]),
        }),
        retry_policy: {
          max_attempts: 1,
          backoff_ms: 0,
          backoff_strategy: "fixed",
        },
        timeout_ms: promptNodeTimeoutMs,
      },
      buildMergeNode(
        "merge_hypothesis_state",
        "Merge Hypothesis State",
        "node.hypothesis.output.structured_response.state_patch",
      ),
      {
        id: "analysis",
        type: "prompt",
        name: "Analysis",
        config: buildPromptConfig({
          stage: "analysis",
          model,
          outputKey: "analysis_patch",
          outputSchema: analysisPatchSchema,
          systemPrompt:
            "You are the analysis node in a replayable ForgeGraph consulting workflow. Return only valid JSON that matches the schema.",
          promptTemplate: buildStagePrompt("analysis", [
            'Return exactly one top-level key named "state_patch".',
            "Given the hypotheses, generate evidence for EACH hypothesis separately.",
            "Refer to hypotheses by their ids and texts from the current execution state.",
            "For each hypothesis, provide at least one supporting OR contradicting piece of evidence.",
            "Use evidence to differentiate the hypotheses and reduce uncertainty.",
            "Explicitly identify which hypotheses are weaker, contradicted, or lack support based on the evidence.",
            "Highlight contradictions or missing support when they exist.",
            "Provide evidence using realistic signals such as customer complaints, support tickets, usage patterns, qualitative feedback, and observed behavior trends.",
            "Avoid inventing precise numbers unless they are clearly justified by the prompt context.",
            'Prefer grounded qualitative phrasing such as "many customers report...", "there is a noticeable increase in...", or "users frequently struggle with...".',
            "If evidence is uncertain, say so explicitly.",
            "It is better to be vague and correct than precise and wrong.",
            "Evidence must sound realistic, grounded, and cautious rather than statistically precise.",
            "Do NOT select the best hypothesis.",
            "Do NOT conclude or recommend anything.",
            "Do NOT collapse all hypotheses into one.",
            "Do NOT avoid contradictions.",
            "Do NOT fabricate statistics.",
            "Do NOT present made-up numbers as facts.",
            "Do NOT overstate certainty.",
            "Return structured evidence covering all current hypotheses.",
            "Write exactly six evidence items.",
            "Use short prefixes such as 'Supports h1:', 'Contradicts h2:', or 'Weakens h3:' so elimination signals are explicit in the evidence_log text.",
          ]),
        }),
        retry_policy: {
          max_attempts: 1,
          backoff_ms: 0,
          backoff_strategy: "fixed",
        },
        timeout_ms: promptNodeTimeoutMs,
      },
      buildMergeNode(
        "merge_analysis_state",
        "Merge Analysis State",
        "node.analysis.output.structured_response.state_patch",
      ),
      {
        id: "reflection",
        type: "prompt",
        name: "Reflection",
        config: buildPromptConfig({
          stage: "reflection",
          model,
          outputKey: "reflection_patch",
          outputSchema: reflectionPatchSchema,
          systemPrompt:
            "You are the reflection node in a replayable ForgeGraph consulting workflow. Return only valid JSON that matches the schema.",
          disableMemoryContext: memoryWorkflowEnabled ? false : true,
          observationContextPaths: memoryWorkflowEnabled ? ["node.previous_similar_cases.output"] : undefined,
          promptTemplate: buildStagePrompt("reflection", [
            'Return exactly one top-level key named "state_patch".',
            "Given the hypotheses and evidence_log, review the current reasoning state.",
            "If memory context is provided, first decide whether the retrieved memories are relevant to the current problem based on domain, problem structure, and driver overlap.",
            "If relevant prior cases exist, use them to check whether prior similar cases revealed missing drivers, weak assumptions, or repeated mistakes.",
            "If memory is absent or not relevant, ignore it completely.",
            "Identify which hypotheses are weak, unsupported, or contradicted.",
            "Identify missing evidence that would be needed to confirm or reject the current hypotheses.",
            "Highlight inconsistencies between the hypotheses and evidence_log.",
            "Do NOT select a final hypothesis.",
            "Do NOT produce a recommendation.",
            "Do NOT rewrite previous outputs.",
            "Set state_patch.reflection.weak_hypotheses to hypothesis ids only, such as h2 or h3.",
            "Set state_patch.reflection.missing_evidence to short strings describing the missing evidence needed next.",
            "Set state_patch.reflection.inconsistencies to short strings describing reasoning conflicts or unsupported jumps.",
            "Also return state_patch.memory_retrieval.",
            "Preserve the current state_patch.memory_retrieval.count, scope, and memory_ids from the current execution state unless no memory object exists yet.",
            "Preserve any existing used_by_nodes and ignored_by_nodes from the current execution state memory_retrieval object.",
            'If relevant memory was used in reflection, ensure "reflection" is included in state_patch.memory_retrieval.used_by_nodes.',
            'If memory was absent or irrelevant for reflection, ensure "reflection" is included in state_patch.memory_retrieval.ignored_by_nodes.',
            "Do not remove existing node names from used_by_nodes or ignored_by_nodes.",
          ]),
        }),
        retry_policy: {
          max_attempts: 1,
          backoff_ms: 0,
          backoff_strategy: "fixed",
        },
        timeout_ms: promptNodeTimeoutMs,
      },
      buildMergeNode(
        "merge_reflection_state",
        "Merge Reflection State",
        "node.reflection.output.structured_response.state_patch",
      ),
      {
        id: "recommendation",
        type: "prompt",
        name: "Recommendation",
        config: buildPromptConfig({
          stage: "recommendation",
          model,
          outputKey: "recommendation_patch",
          outputSchema: recommendationPatchSchema,
          systemPrompt:
            "You are the recommendation node in a replayable ForgeGraph consulting workflow. Return only valid JSON that matches the schema.",
          promptTemplate: buildStagePrompt("recommendation", [
            'Return exactly one top-level key named "state_patch".',
            "Given the hypotheses, evidence_log, and reflection output, evaluate each hypothesis using the available evidence.",
            "Use reflection.weak_hypotheses, reflection.missing_evidence, and reflection.inconsistencies as additional decision inputs.",
            "Identify strengths and weaknesses of each hypothesis before deciding.",
            "Compare the hypotheses against each other.",
            "Select the most plausible hypothesis id based on the available evidence.",
            "Set state_patch.recommendation.selected_hypothesis_text to the exact text of the selected hypothesis.",
            "Avoid selecting a hypothesis listed in reflection.weak_hypotheses unless the rationale explicitly explains why the supporting evidence still outweighs the weakness.",
            "Explicitly acknowledge uncertainty in the evidence.",
            "Indicate if the evidence is partial, weak, indirect, or conflicting.",
            'Use qualified language such as "most plausible given current evidence", "suggests but does not confirm", "limited evidence indicates", or "appears stronger than alternatives, but remains uncertain".',
            "Clearly explain why the selected hypothesis is better supported than the alternatives, including any important inconsistencies or missing evidence.",
            "Set state_patch.recommendation.selected_hypothesis to only the chosen hypothesis id, such as h1.",
            "Do NOT select a hypothesis without comparison.",
            "Do NOT ignore competing hypotheses.",
            "Do NOT present conclusions as certain facts.",
            "Do NOT exaggerate the strength of evidence.",
            "Do NOT ignore conflicting or weak signals.",
            "Do NOT use generic reasoning.",
            "Keep the rationale concise, comparative, and explicitly qualified.",
          ]),
        }),
        retry_policy: {
          max_attempts: 1,
          backoff_ms: 0,
          backoff_strategy: "fixed",
        },
        timeout_ms: promptNodeTimeoutMs,
      },
      buildMergeNode(
        "merge_recommendation_state",
        "Merge Recommendation State",
        "node.recommendation.output.structured_response.state_patch",
      ),
      ...(memoryWorkflowEnabled
        ? [
            {
              id: "store_case_memory",
              type: "observation_save",
              name: "Store Case Memory",
              config: {
                scope: "graph",
                type: "consulting_case",
                topic_key_template:
                  "consulting_case|customer_churn_increase|{{input.context.product}}|{{input.context.customers}}",
                title_template:
                  "Consulting lesson: customer_churn_increase | {{input.context.product}} | {{input.context.customers}}",
                content_template: [
                  "{",
                  '  "case_domain": "B2B SaaS {{input.context.product}} for {{input.context.customers}}",',
                  '  "problem_type": "customer_churn_increase",',
                  '  "problem_summary": "{{vars.execution_state.problem_statement}}",',
                  '  "selected_hypothesis": "{{vars.execution_state.recommendation.selected_hypothesis}}",',
                  '  "selected_hypothesis_text": "{{vars.execution_state.recommendation.selected_hypothesis_text}}",',
                  '  "key_drivers": {{vars.execution_state.issue_tree.branches}},',
                  '  "evidence_signals": {{vars.execution_state.evidence_log}},',
                  '  "reflection_warnings": {{vars.execution_state.reflection.inconsistencies}},',
                  '  "recommended_next_actions": {{vars.execution_state.execution_plan}}',
                  "}",
                ].join("\n"),
                dedupe: true,
              },
              retry_policy: {
                max_attempts: 1,
                backoff_ms: 0,
                backoff_strategy: "fixed",
              },
            },
          ]
        : []),
      {
        id: "planner",
        type: "prompt",
        name: "Planner",
        config: buildPromptConfig({
          stage: "planner",
          model,
          outputKey: "planner_patch",
          outputSchema: plannerPatchSchema,
          systemPrompt:
            "You are the planner node in a replayable ForgeGraph consulting workflow. Return only valid JSON that matches the schema.",
          promptTemplate: buildStagePrompt("planner", [
            'Return exactly one top-level key named "state_patch".',
            "Create at least three execution steps based on the recommendation.",
          ]),
        }),
        retry_policy: {
          max_attempts: 1,
          backoff_ms: 0,
          backoff_strategy: "fixed",
        },
        timeout_ms: promptNodeTimeoutMs,
      },
      buildMergeNode(
        "merge_planner_state",
        "Merge Planner State",
        "node.planner.output.structured_response.state_patch",
      ),
      {
        id: "final_output",
        type: "output",
        name: "Final Output",
        config: {
          output_mapping: {
            problem_statement: "vars.execution_state.problem_statement",
            issue_tree: "vars.execution_state.issue_tree",
            hypotheses: "vars.execution_state.hypotheses",
            evidence_log: "vars.execution_state.evidence_log",
            reflection: "vars.execution_state.reflection",
            ...(memoryWorkflowEnabled
              ? {
                  memory_retrieval: "vars.execution_state.memory_retrieval",
                }
              : {}),
            recommendation: "vars.execution_state.recommendation",
            execution_plan: "vars.execution_state.execution_plan",
          },
        },
      },
    ],
    edges: [
      { id: "e1", from: "intake", to: "merge_intake_state" },
      { id: "e2", from: "merge_intake_state", to: "structuring" },
      { id: "e3", from: "structuring", to: "merge_structuring_state" },
      ...(memoryWorkflowEnabled
        ? [
            { id: "e4", from: "merge_structuring_state", to: "previous_similar_cases" },
            { id: "e4b", from: "previous_similar_cases", to: "merge_memory_retrieval_state" },
            { id: "e4c", from: "merge_memory_retrieval_state", to: "hypothesis" },
          ]
        : [{ id: "e4", from: "merge_structuring_state", to: "hypothesis" }]),
      { id: "e5", from: "hypothesis", to: "merge_hypothesis_state" },
      { id: "e6", from: "merge_hypothesis_state", to: "analysis" },
      { id: "e7", from: "analysis", to: "merge_analysis_state" },
      { id: "e8", from: "merge_analysis_state", to: "reflection" },
      { id: "e9", from: "reflection", to: "merge_reflection_state" },
      { id: "e10", from: "merge_reflection_state", to: "recommendation" },
      { id: "e11", from: "recommendation", to: "merge_recommendation_state" },
      ...(memoryWorkflowEnabled
        ? [
            { id: "e12", from: "merge_recommendation_state", to: "planner" },
            { id: "e13a", from: "merge_planner_state", to: "store_case_memory" },
            { id: "e13b", from: "store_case_memory", to: "final_output" },
          ]
        : [{ id: "e12", from: "merge_recommendation_state", to: "planner" }]),
      { id: "e13", from: "planner", to: "merge_planner_state" },
      ...(!memoryWorkflowEnabled ? [{ id: "e14", from: "merge_planner_state", to: "final_output" }] : []),
    ],
    metadata: {
      schema_mode: "strict",
      input_schema: {
        type: "object",
        properties: {
          problem: { type: "string" },
          context: {
            type: "object",
            properties: {
              product: { type: "string" },
              customers: { type: "string" },
            },
            required: ["product", "customers"],
            additionalProperties: true,
          },
        },
        required: ["problem", "context"],
        additionalProperties: true,
      },
      state_schema: {
        type: "object",
        properties: {
          input: {
            type: "object",
            properties: {
              problem: { type: "string" },
              context: {
                type: "object",
                additionalProperties: true,
              },
            },
            additionalProperties: true,
          },
          vars: {
            type: "object",
            properties: {
              execution_state: executionStateSchema,
            },
            additionalProperties: true,
          },
        },
        additionalProperties: true,
      },
      output_schema: executionStateSchema,
    },
  };
}
