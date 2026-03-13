function sendJson(response, statusCode, payload) {
  response.writeHead(statusCode, { "Content-Type": "application/json; charset=utf-8" });
  response.end(`${JSON.stringify(payload, null, 2)}\n`);
}

async function readJson(request) {
  const chunks = [];

  for await (const chunk of request) {
    chunks.push(chunk);
  }

  if (chunks.length === 0) {
    return {};
  }

  return JSON.parse(Buffer.concat(chunks).toString("utf8"));
}

export async function routeRequest(request, response, service) {
  const url = new URL(request.url, "http://localhost");
  const method = request.method ?? "GET";

  try {
    if (method === "GET" && url.pathname === "/health") {
      sendJson(response, 200, service.health());
      return;
    }

    if (method === "POST" && url.pathname === "/v1/tenants") {
      sendJson(response, 201, await service.createTenant(await readJson(request)));
      return;
    }

    if (method === "POST" && url.pathname === "/v1/partitions") {
      sendJson(response, 201, await service.createPartition(await readJson(request)));
      return;
    }

    if (method === "POST" && url.pathname === "/v1/agents") {
      sendJson(response, 201, await service.registerAgent(await readJson(request)));
      return;
    }

    if (method === "POST" && url.pathname === "/v1/records") {
      sendJson(response, 201, await service.createRecord(await readJson(request)));
      return;
    }

    if (method === "POST" && url.pathname === "/v1/query") {
      sendJson(response, 200, await service.query(await readJson(request)));
      return;
    }

    if (method === "POST" && url.pathname === "/v1/sessions/commit") {
      sendJson(response, 201, await service.commitSession(await readJson(request)));
      return;
    }

    sendJson(response, 404, { error: `Not found: ${method} ${url.pathname}` });
  } catch (error) {
    sendJson(response, 400, {
      error: error instanceof Error ? error.message : String(error)
    });
  }
}
