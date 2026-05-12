import http from "node:http";

const port = Number(process.env.PLAYWRIGHT_LLM_MOCK_PORT ?? 8011);

const state = {
  errorMode: "off",
  responseDelayMs: 0,
};

function json(response, status, body) {
  response.writeHead(status, {
    "access-control-allow-origin": "*",
    "access-control-allow-methods": "GET,POST,OPTIONS",
    "access-control-allow-headers": "content-type,authorization",
    "content-type": "application/json",
  });
  response.end(JSON.stringify(body));
}

function readBody(request) {
  return new Promise((resolve) => {
    let body = "";
    request.setEncoding("utf8");
    request.on("data", (chunk) => {
      body += chunk;
    });
    request.on("end", () => {
      resolve(body);
    });
  });
}

function chatCompletionBody(requestBody) {
  const model = typeof requestBody?.model === "string" ? requestBody.model : "playwright-mock-model";
  const content =
    "Deterministic Playwright LLM mock response. The backend remains the durable source of truth for test state.";
  return {
    id: `chatcmpl-playwright-${Date.now()}`,
    object: "chat.completion",
    created: Math.floor(Date.now() / 1000),
    model,
    choices: [
      {
        index: 0,
        finish_reason: "stop",
        message: {
          role: "assistant",
          content,
        },
      },
    ],
    usage: {
      prompt_tokens: 12,
      completion_tokens: 16,
      total_tokens: 28,
    },
  };
}

const server = http.createServer(async (request, response) => {
  if (request.method === "OPTIONS") {
    json(response, 204, {});
    return;
  }

  const url = new URL(request.url ?? "/", `http://${request.headers.host ?? `127.0.0.1:${port}`}`);

  if (request.method === "GET" && url.pathname === "/health") {
    json(response, 200, { ok: true, errorMode: state.errorMode });
    return;
  }

  if (request.method === "GET" && url.pathname === "/v1/models") {
    json(response, 200, {
      object: "list",
      data: [{ id: "playwright-mock-model", object: "model", owned_by: "forgegraph" }],
    });
    return;
  }

  if (request.method === "POST" && url.pathname === "/control") {
    const rawBody = await readBody(request);
    const body = rawBody ? JSON.parse(rawBody) : {};
    state.errorMode = body.errorMode ?? "off";
    state.responseDelayMs = Number(body.responseDelayMs ?? 0);
    json(response, 200, { ok: true, ...state });
    return;
  }

  if (request.method === "POST" && url.pathname === "/v1/chat/completions") {
    if (state.responseDelayMs > 0) {
      await new Promise((resolve) => setTimeout(resolve, state.responseDelayMs));
    }
    if (state.errorMode === "rate_limit") {
      json(response, 429, { error: { message: "Deterministic rate limit from Playwright mock." } });
      return;
    }
    const rawBody = await readBody(request);
    const body = rawBody ? JSON.parse(rawBody) : {};
    json(response, 200, chatCompletionBody(body));
    return;
  }

  json(response, 404, { error: { message: `No mock route for ${request.method} ${url.pathname}` } });
});

server.listen(port, "127.0.0.1", () => {
  console.log(`Playwright OpenAI mock listening on http://127.0.0.1:${port}`);
});

process.on("SIGTERM", () => {
  server.close(() => process.exit(0));
});
