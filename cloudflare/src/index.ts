export interface Env {
  DB: D1Database;
  CONTEXT_HUB_BIND_MODE?: string;
}

function json(data: unknown, status = 200): Response {
  return new Response(JSON.stringify(data, null, 2), {
    status,
    headers: {
      "content-type": "application/json; charset=utf-8",
      "cache-control": "no-store",
    },
  });
}

export default {
  async fetch(request: Request, env: Env): Promise<Response> {
    const url = new URL(request.url);

    if (request.method === "GET" && url.pathname === "/") {
      return json({
        ok: true,
        mode: "phase1-cloud-filesystem-worker-mvp",
        hint: "see /health or implement /v1/fs/* routes next",
      });
    }

    if (request.method === "GET" && url.pathname === "/health") {
      const dbCheck = await env.DB.prepare("select 1 as ok").first<{ ok: number }>();
      return json({
        ok: true,
        mode: "phase1-cloud-filesystem-worker-mvp",
        storage: "d1",
        d1: dbCheck?.ok === 1 ? "ok" : "unexpected",
      });
    }

    if (url.pathname.startsWith("/v1/fs/")) {
      return json(
        {
          detail: "not implemented in Worker MVP yet",
          path: url.pathname,
          recommendedFirstSlice: [
            "GET /health",
            "GET /v1/fs/read",
            "POST /v1/fs/write",
            "GET /v1/fs/stat",
            "GET /v1/fs/ls",
            "GET /v1/fs/tree",
            "POST /v1/fs/search",
          ],
        },
        501,
      );
    }

    return json({ detail: "Not Found" }, 404);
  },
};
