import http from "node:http";

const port = Number(process.env.PLAYWRIGHT_LLM_MOCK_PORT ?? "8011");

function json(response, statusCode, payload, extraHeaders = {}) {
  response.writeHead(statusCode, {
    "Content-Type": "application/json",
    ...extraHeaders,
  });
  response.end(JSON.stringify(payload));
}

function extractPrompt(messages) {
  if (!Array.isArray(messages) || messages.length === 0) return "";
  const lastMessage = messages[messages.length - 1];
  return typeof lastMessage?.content === "string" ? lastMessage.content : "";
}

function extractStage(prompt) {
  const match = prompt.match(/Stage:\s*([A-Za-z0-9_:-]+)/);
  return match ? match[1] : "";
}

function extractExecutionState(prompt) {
  const match = prompt.match(/BEGIN_EXECUTION_STATE_JSON\s*([\s\S]*?)\s*END_EXECUTION_STATE_JSON/);
  if (!match) return null;
  try {
    return JSON.parse(match[1]);
  } catch {
    return null;
  }
}

function cloneState(state) {
  return JSON.parse(JSON.stringify(state));
}

function buildMarketingPatch(stage, currentState) {
  const next = cloneState(currentState ?? {
    goal: "Launch a replayable AI digital marketing campaign for ForgeGraph.",
    strategy: null,
    content_assets: [],
    distribution_plan: null,
    analytics: null,
    iteration: 0,
  });
  const pass = Number(next.iteration ?? 0) + 1;

  switch (stage) {
    case "strategy_agent":
      return {
        strategy: {
          company: "ForgeGraph Digital Marketing Co",
          objective: next.goal,
          primary_channel: "linkedin",
          audience: "B2B operators evaluating AI workflow tooling",
          positioning: `Iteration ${pass} message focused on replayable execution and observability.`,
          content_pillars: ["reliability", "traceability", "measurable campaign loops"],
        },
      };
    case "content_copywriter_specialist":
      return {
        asset: {
          asset_id: `copy-${pass}`,
          specialist: "copywriter_specialist",
          channel: "linkedin",
          format: "post",
          headline: `Replayable growth loop v${pass}`,
          body: `Launch ForgeGraph's replayable workflow story with observable execution, resilient retries, and clear operator trust signals in pass ${pass}.`,
          iteration: pass,
          reviewed: false,
          department: "content",
          state_field: "content_assets",
        },
      };
    case "content_editor_specialist":
      return {
        asset: {
          asset_id: `editorial-${pass}`,
          specialist: "editor_specialist",
          channel: "email",
          format: "brief",
          headline: `Editorial QA pass v${pass}`,
          body: "Reviewed copy for clarity, CTA alignment, and observable execution language.",
          iteration: pass,
          reviewed: true,
          department: "content",
          state_field: "content_assets",
        },
      };
    case "distribution_agent":
      return {
        distribution_plan: {
          owner: "distribution_agent",
          channels: next.content_assets.map((asset) => asset.channel),
          asset_ids: next.content_assets.map((asset) => asset.asset_id),
          cadence: `day-${pass} morning publish window`,
        },
      };
    default:
      return next;
  }
}

function extractAllowedTools(prompt) {
  const marker = "Allowed tools:\n";
  const nextMarker = "\n\nCurrent workflow state:";
  const start = prompt.indexOf(marker);
  if (start === -1) return [];
  const end = prompt.indexOf(nextMarker, start);
  const block = prompt.slice(start + marker.length, end === -1 ? undefined : end);
  return block
    .split("\n")
    .map((line) => line.trim())
    .filter((line) => line.startsWith("- "))
    .map((line) => line.slice(2).trim())
    .filter(Boolean);
}

function buildChatCompletion(content, model) {
  return {
    id: "chatcmpl-playwright-mock",
    object: "chat.completion",
    created: Math.floor(Date.now() / 1000),
    model,
    choices: [
      {
        index: 0,
        message: {
          role: "assistant",
          content,
        },
        finish_reason: "stop",
      },
    ],
    usage: {
      prompt_tokens: 42,
      completion_tokens: 18,
      total_tokens: 60,
    },
  };
}

function handleAgentPrompt(prompt, model) {
  const allowedTools = extractAllowedTools(prompt);
  const primaryTool = allowedTools[0] ?? "playwright_runtime_health_check";
  const hasToolOutput = prompt.includes('"tool_output"');

  if (!hasToolOutput) {
    return buildChatCompletion(
      JSON.stringify({
        action: "tool_call",
        tool: primaryTool,
        tool_input: {
          channel: "telegram",
          mode: "status_check",
        },
      }),
      model,
    );
  }

  return buildChatCompletion(
    JSON.stringify({
      action: "final_answer",
      final_answer: "Jackie checked your workspace health and everything looks good. No urgent issues found.",
    }),
    model,
  );
}

function handleMarketingPrompt(prompt, model) {
  const stage = extractStage(prompt);
  const currentState = extractExecutionState(prompt);
  const patch = buildMarketingPatch(stage, currentState);
  return buildChatCompletion(JSON.stringify(patch, null, 2), model);
}

const server = http.createServer(async (request, response) => {
  if (!request.url) {
    json(response, 404, { error: "missing URL" });
    return;
  }

  if (request.method === "GET" && request.url === "/health") {
    json(response, 200, { status: "ok" });
    return;
  }

  if (request.method === "POST" && request.url === "/v1/chat/completions") {
    let body = "";
    request.setEncoding("utf8");
    for await (const chunk of request) {
      body += chunk;
    }

    const payload = body ? JSON.parse(body) : {};
    const prompt = extractPrompt(payload.messages);
    const model = typeof payload.model === "string" && payload.model ? payload.model : "gpt-4.1-mini";

    if (prompt.includes("You are executing inside a ForgeGraph agent node.")) {
      json(response, 200, handleAgentPrompt(prompt, model));
      return;
    }

    if (prompt.includes("BEGIN_EXECUTION_STATE_JSON") && prompt.includes("END_EXECUTION_STATE_JSON")) {
      json(response, 200, handleMarketingPrompt(prompt, model));
      return;
    }

    json(response, 200, buildChatCompletion("Mock response from the Playwright OpenAI server.", model));
    return;
  }

  json(response, 404, { error: "not found", path: request.url });
});

server.listen(port, "127.0.0.1", () => {
  // eslint-disable-next-line no-console
  console.log(`Playwright OpenAI mock listening on http://127.0.0.1:${port}`);
});
