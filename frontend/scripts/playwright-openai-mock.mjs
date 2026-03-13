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

function extractAllowedTools(prompt) {
  const marker = "Allowed tools:\n";
  const nextMarker = "\n\nCurrent workflow state:";
  const start = prompt.indexOf(marker);
  if (start === -1) return [];
  const end = prompt.indexOf(nextMarker, start);
  const block = prompt.slice(
    start + marker.length,
    end === -1 ? undefined : end,
  );
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
      final_answer:
        "Jackie checked your workspace health and everything looks good. No urgent issues found.",
    }),
    model,
  );
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
    const model =
      typeof payload.model === "string" && payload.model
        ? payload.model
        : "gpt-4.1-mini";

    if (prompt.includes("You are executing inside a ForgeGraph agent node.")) {
      json(response, 200, handleAgentPrompt(prompt, model));
      return;
    }

    json(
      response,
      200,
      buildChatCompletion(
        "Mock response from the Playwright OpenAI server.",
        model,
      ),
    );
    return;
  }

  json(response, 404, { error: "not found", path: request.url });
});

server.listen(port, "127.0.0.1", () => {
  // eslint-disable-next-line no-console
  console.log(`Playwright OpenAI mock listening on http://127.0.0.1:${port}`);
});
