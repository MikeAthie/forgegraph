export type MarketingSimulationGraphOptions = {
  defaultGoal?: string;
  model?: string;
};

const defaultGoal = "Launch a replayable AI digital marketing campaign for ForgeGraph.";
const defaultModel =
  process.env.PLAYWRIGHT_MARKETING_LLM_MODEL ??
  process.env.OPENAI_MODEL ??
  "docker.io/ai/llama3.1:latest";
const promptNodeTimeoutMs = 180_000;

const strategySchema = {
  type: "object",
  properties: {
    company: { type: "string" },
    objective: { type: "string" },
    primary_channel: { type: "string" },
    audience: { type: "string" },
    positioning: { type: "string" },
    content_pillars: {
      type: "array",
      items: { type: "string" },
    },
  },
  required: [
    "company",
    "objective",
    "primary_channel",
    "audience",
    "positioning",
    "content_pillars",
  ],
  additionalProperties: false,
} as const;

const contentAssetSchema = {
  type: "object",
  properties: {
    asset_id: { type: "string" },
    specialist: { type: "string" },
    channel: { type: "string" },
    format: { type: "string" },
    headline: { type: "string" },
    body: { type: "string" },
    iteration: { type: "integer" },
    reviewed: { type: "boolean" },
    department: { type: "string" },
    state_field: { type: "string" },
  },
  required: [
    "asset_id",
    "specialist",
    "channel",
    "format",
    "headline",
    "body",
    "iteration",
    "reviewed",
    "department",
    "state_field",
  ],
  additionalProperties: false,
} as const;

const distributionPlanSchema = {
  type: "object",
  properties: {
    asset_ids: {
      type: "array",
      items: { type: "string" },
    },
    channels: {
      type: "array",
      items: { type: "string" },
    },
    cadence: { type: "string" },
    owner: { type: "string" },
  },
  required: ["asset_ids", "channels", "cadence", "owner"],
  additionalProperties: false,
} as const;

const analyticsSchema = {
  type: ["object", "null"],
  properties: {
    iteration: { type: "integer" },
    impressions: { type: "integer" },
    clicks: { type: "integer" },
    conversions: { type: "integer" },
    ctr: { type: "number" },
    summary: { type: "string" },
  },
  required: ["iteration", "impressions", "clicks", "conversions", "ctr", "summary"],
  additionalProperties: false,
} as const;

const executionStateSchema = {
  type: "object",
  properties: {
    goal: { type: "string" },
    strategy: {
      ...strategySchema,
      type: ["object", "null"],
    },
    content_assets: {
      type: "array",
      items: contentAssetSchema,
    },
    distribution_plan: {
      ...distributionPlanSchema,
      type: ["object", "null"],
    },
    analytics: analyticsSchema,
    iteration: { type: "integer" },
  },
  required: [
    "goal",
    "strategy",
    "content_assets",
    "distribution_plan",
    "analytics",
    "iteration",
  ],
  additionalProperties: false,
} as const;

const strategyPatchSchema = {
  type: "object",
  properties: {
    strategy: strategySchema,
  },
  required: ["strategy"],
  additionalProperties: false,
} as const;

const contentAssetPatchSchema = {
  type: "object",
  properties: {
    asset: contentAssetSchema,
  },
  required: ["asset"],
  additionalProperties: false,
} as const;

const distributionPatchSchema = {
  type: "object",
  properties: {
    distribution_plan: distributionPlanSchema,
  },
  required: ["distribution_plan"],
  additionalProperties: false,
} as const;

function buildPromptConfig(args: {
  stage: string;
  systemPrompt: string;
  promptTemplate: string;
  model: string;
  outputKey: string;
  outputSchema: Record<string, unknown>;
  simulateFailureOnIteration?: number;
}): Record<string, unknown> {
  const config: Record<string, unknown> = {
    provider: "openai",
    model: args.model,
    temperature: 0,
    max_tokens: 450,
    stream: false,
    disable_memory_context: true,
    output_key: args.outputKey,
    output_schema: args.outputSchema,
    schema_mode: "strict",
    simulation_role: args.stage,
    system_prompt: args.systemPrompt,
    prompt_template: args.promptTemplate,
  };
  if (args.simulateFailureOnIteration) {
    config.simulate_failure_input_key = "force_content_failure";
    config.simulate_failure_on_iteration = args.simulateFailureOnIteration;
  }
  return config;
}

function buildStatePatchTransform(args: {
  id: string;
  name: string;
  expression: string;
  targetPath?: string;
  patchMode?: "deep_merge" | "append_array" | "replace";
}): Record<string, unknown> {
  const config: Record<string, unknown> = {
    expression_type: "state_patch",
    expression: args.expression,
    output_key: "execution_state",
  };
  if (args.targetPath) {
    config.target_path = args.targetPath;
  }
  if (args.patchMode) {
    config.patch_mode = args.patchMode;
  }
  return {
    id: args.id,
    type: "transform",
    name: args.name,
    config,
    retry_policy: {
      max_attempts: 1,
      backoff_ms: 0,
      backoff_strategy: "fixed",
    },
  };
}

function buildStagePrompt(stage: string, instructions: string[]): string {
  return [
    `Stage: ${stage}`,
    "Return JSON only. Do not wrap the JSON in markdown fences.",
    "Follow these instructions exactly:",
    ...instructions.map((instruction) => `- ${instruction}`),
    "",
    "Current execution state JSON:",
    "BEGIN_EXECUTION_STATE_JSON",
    "{{vars.execution_state}}",
    "END_EXECUTION_STATE_JSON",
  ].join("\n");
}

export function buildMarketingSimulationGraph(
  options: MarketingSimulationGraphOptions = {},
): Record<string, unknown> {
  const goal = options.defaultGoal ?? defaultGoal;
  const model = options.model ?? defaultModel;

  return {
    nodes: [
      {
        id: "strategy_agent",
        type: "prompt",
        name: "Strategy Agent",
        config: buildPromptConfig({
          stage: "strategy_agent",
          model,
          outputKey: "strategy_patch",
          outputSchema: strategyPatchSchema,
          systemPrompt:
            "You are the strategy department inside a replayable ForgeGraph marketing simulation. Return only the requested JSON object and never invent keys outside the schema.",
          promptTemplate: buildStagePrompt("strategy_agent", [
            `Preserve the campaign goal exactly as "${goal}" when present, otherwise keep the existing goal.`,
            'Return exactly one top-level key named "strategy".',
            'Set strategy.company to "ForgeGraph Digital Marketing Co".',
            "Set strategy.objective to the current goal.",
            'Set strategy.primary_channel to "linkedin".',
            'Set strategy.audience to "B2B operators evaluating AI workflow tooling".',
            "Set strategy.positioning to one sentence about replayable execution, observability, and the current campaign pass.",
            'Set strategy.content_pillars to exactly ["reliability","traceability","measurable campaign loops"].',
          ]),
        }),
        retry_policy: {
          max_attempts: 1,
          backoff_ms: 0,
          backoff_strategy: "fixed",
        },
        timeout_ms: promptNodeTimeoutMs,
      },
      buildStatePatchTransform({
        id: "merge_strategy_state",
        name: "Merge Strategy State",
        expression: "node.strategy_agent.output.structured_response",
      }),
      {
        id: "content_copywriter_specialist",
        type: "prompt",
        name: "Content Copywriter Specialist",
        config: buildPromptConfig({
          stage: "content_copywriter_specialist",
          model,
          outputKey: "content_copywriter_patch",
          outputSchema: contentAssetPatchSchema,
          simulateFailureOnIteration: 1,
          systemPrompt:
            "You are the copywriter specialist inside a replayable ForgeGraph marketing simulation. Return only the requested JSON object and keep copy short, explicit, and production-safe.",
          promptTemplate: buildStagePrompt("content_copywriter_specialist", [
            'Return exactly one top-level key named "asset".',
            "Create one new LinkedIn post asset for the next campaign pass.",
            'Set asset.specialist to "copywriter_specialist".',
            'Set asset.channel to "linkedin".',
            'Set asset.format to "post".',
            "Set asset.asset_id to a stable value in the form copy-<next iteration number>.",
            "Set asset.iteration to the next iteration number.",
            "Set asset.reviewed to false.",
            'Set asset.department to "content".',
            'Set asset.state_field to "content_assets".',
            "Use the current goal and strategy to write a concise headline and body about replayable execution and observable marketing loops.",
          ]),
        }),
        retry_policy: {
          max_attempts: 1,
          backoff_ms: 0,
          backoff_strategy: "fixed",
        },
        timeout_ms: promptNodeTimeoutMs,
      },
      buildStatePatchTransform({
        id: "merge_copywriter_asset",
        name: "Merge Copywriter Asset",
        expression: "node.content_copywriter_specialist.output.structured_response.asset",
        targetPath: "content_assets",
        patchMode: "append_array",
      }),
      {
        id: "content_editor_specialist",
        type: "prompt",
        name: "Content Editor Specialist",
        config: buildPromptConfig({
          stage: "content_editor_specialist",
          model,
          outputKey: "content_editor_patch",
          outputSchema: contentAssetPatchSchema,
          systemPrompt:
            "You are the editor specialist inside a replayable ForgeGraph marketing simulation. Return only the requested JSON object and keep the language explicit and audit-friendly.",
          promptTemplate: buildStagePrompt("content_editor_specialist", [
            'Return exactly one top-level key named "asset".',
            "Create one editorial review asset for the same campaign pass as the newest content asset already in state.",
            'Set asset.specialist to "editor_specialist".',
            'Set asset.channel to "email".',
            'Set asset.format to "brief".',
            "Set asset.asset_id to a stable value in the form editorial-<next iteration number>.",
            "Set asset.iteration to the next iteration number.",
            "Set asset.reviewed to true.",
            'Set asset.department to "content".',
            'Set asset.state_field to "content_assets".',
            "Use the strategy plus the newest copy asset to produce a brief QA-oriented review headline and body.",
          ]),
        }),
        retry_policy: {
          max_attempts: 1,
          backoff_ms: 0,
          backoff_strategy: "fixed",
        },
        timeout_ms: promptNodeTimeoutMs,
      },
      buildStatePatchTransform({
        id: "merge_editor_asset",
        name: "Merge Editor Asset",
        expression: "node.content_editor_specialist.output.structured_response.asset",
        targetPath: "content_assets",
        patchMode: "append_array",
      }),
      {
        id: "content_agent",
        type: "transform",
        name: "Content Agent",
        config: {
          expression_type: "simulation_step",
          simulation_role: "content_agent",
          output_key: "execution_state",
          department: "content",
        },
        retry_policy: {
          max_attempts: 1,
          backoff_ms: 0,
          backoff_strategy: "fixed",
        },
      },
      {
        id: "distribution_agent",
        type: "prompt",
        name: "Distribution Agent",
        config: buildPromptConfig({
          stage: "distribution_agent",
          model,
          outputKey: "distribution_patch",
          outputSchema: distributionPatchSchema,
          systemPrompt:
            "You are the distribution department inside a replayable ForgeGraph marketing simulation. Return only the requested JSON object and keep the plan explicit and deterministic.",
          promptTemplate: buildStagePrompt("distribution_agent", [
            'Return exactly one top-level key named "distribution_plan".',
            "Read the current content_assets array and include every asset_id in order.",
            "Read the current content_assets array and include every channel in order.",
            "Set distribution_plan.owner to distribution_agent.",
            "Set cadence to a concise phrase for the next publish window.",
          ]),
        }),
        retry_policy: {
          max_attempts: 1,
          backoff_ms: 0,
          backoff_strategy: "fixed",
        },
        timeout_ms: promptNodeTimeoutMs,
      },
      buildStatePatchTransform({
        id: "merge_distribution_state",
        name: "Merge Distribution State",
        expression: "node.distribution_agent.output.structured_response",
      }),
      {
        id: "analytics_agent",
        type: "transform",
        name: "Analytics Agent",
        config: {
          expression_type: "simulation_step",
          simulation_role: "analytics_agent",
          output_key: "execution_state",
          department: "analytics",
        },
        retry_policy: {
          max_attempts: 1,
          backoff_ms: 0,
          backoff_strategy: "fixed",
        },
      },
      {
        id: "decision_node",
        type: "branch",
        name: "Decision Node",
        config: {
          condition: "vars.execution_state.iteration < 2",
        },
      },
      {
        id: "final_output",
        type: "output",
        name: "Final Output",
        config: {
          output_mapping: {
            goal: "vars.execution_state.goal",
            strategy: "vars.execution_state.strategy",
            content_assets: "vars.execution_state.content_assets",
            distribution_plan: "vars.execution_state.distribution_plan",
            analytics: "vars.execution_state.analytics",
            iteration: "vars.execution_state.iteration",
          },
        },
      },
    ],
    edges: [
      { id: "e1", from: "strategy_agent", to: "merge_strategy_state" },
      { id: "e2", from: "merge_strategy_state", to: "content_copywriter_specialist" },
      { id: "e3", from: "content_copywriter_specialist", to: "merge_copywriter_asset" },
      { id: "e4", from: "merge_copywriter_asset", to: "content_editor_specialist" },
      { id: "e5", from: "content_editor_specialist", to: "merge_editor_asset" },
      { id: "e6", from: "merge_editor_asset", to: "content_agent" },
      { id: "e7", from: "content_agent", to: "distribution_agent" },
      { id: "e8", from: "distribution_agent", to: "merge_distribution_state" },
      { id: "e9", from: "merge_distribution_state", to: "analytics_agent" },
      { id: "e10", from: "analytics_agent", to: "decision_node" },
      { id: "e11", from: "decision_node", to: "strategy_agent", label: "true" },
      { id: "e12", from: "decision_node", to: "final_output", label: "false" },
    ],
    metadata: {
      allow_cycles: true,
      default_max_visits: 30,
      schema_mode: "strict",
      state_schema: {
        type: "object",
        properties: {
          input: {
            type: "object",
            properties: {
              goal: { type: "string" },
              force_content_failure: { type: "boolean" },
            },
            additionalProperties: true,
          },
          vars: {
            type: "object",
            properties: {
              execution_state: executionStateSchema,
            },
            required: ["execution_state"],
            additionalProperties: true,
          },
        },
        required: ["vars"],
        additionalProperties: true,
      },
      output_schema: {
        type: "object",
        properties: {
          goal: { type: "string" },
          strategy: { type: "object" },
          content_assets: { type: "array", minItems: 4 },
          distribution_plan: { type: "object" },
          analytics: { type: "object" },
          iteration: { type: "integer", minimum: 2 },
        },
        required: [
          "goal",
          "strategy",
          "content_assets",
          "distribution_plan",
          "analytics",
          "iteration",
        ],
        additionalProperties: false,
      },
    },
  };
}
