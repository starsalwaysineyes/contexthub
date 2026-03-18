import { ApiError, parseCtxUri, type WorkspaceKind } from "./ctx.js";
import { assertAuthorized, ls, mkdir, read, registerWorkspace, stat, tree, write, type Env } from "./filesystem.js";

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
    try {
      const url = new URL(request.url);

      if (request.method === "GET" && url.pathname === "/") {
        return json({
          ok: true,
          mode: "phase1-cloud-filesystem-worker-mvp",
          freePlanTarget: true,
          hint: "see /health and /v1/fs/* routes",
        });
      }

      if (request.method === "GET" && url.pathname === "/health") {
        const dbCheck = await env.DB.prepare("select 1 as ok").first<{ ok: number }>();
        return json({
          ok: true,
          mode: "phase1-cloud-filesystem-worker-mvp",
          storage: "d1",
          freePlanTarget: true,
          d1: dbCheck?.ok === 1 ? "ok" : "unexpected",
        });
      }

      await assertAuthorized(request, env);

      if (request.method === "POST" && url.pathname === "/v1/workspaces/register") {
        const payload = await request.json<Record<string, unknown>>();
        const userId = String(payload.userId || "").trim();
        const workspaceKind = String(payload.workspaceKind || "").trim() as WorkspaceKind;
        const agentId = String(payload.agentId || "").trim();
        if (!userId || (workspaceKind !== "defaultWorkspace" && workspaceKind !== "agentWorkspace")) {
          throw new ApiError(400, "invalid register workspace payload");
        }
        if (workspaceKind === "agentWorkspace" && !agentId) {
          throw new ApiError(400, "agentId is required for agentWorkspace");
        }
        return json(await registerWorkspace(env, userId, workspaceKind, agentId));
      }

      if (request.method === "POST" && url.pathname === "/v1/fs/mkdir") {
        const payload = await request.json<Record<string, unknown>>();
        const uri = String(payload.uri || "").trim();
        const parents = payload.parents === undefined ? true : Boolean(payload.parents);
        return json(await mkdir(env, parseCtxUri(uri), parents));
      }

      if (request.method === "GET" && url.pathname === "/v1/fs/ls") {
        const uri = url.searchParams.get("uri") || "";
        return json(await ls(env, parseCtxUri(uri)));
      }

      if (request.method === "GET" && url.pathname === "/v1/fs/stat") {
        const uri = url.searchParams.get("uri") || "";
        return json(await stat(env, parseCtxUri(uri)));
      }

      if (request.method === "GET" && url.pathname === "/v1/fs/tree") {
        const uri = url.searchParams.get("uri") || "";
        const depth = Number(url.searchParams.get("depth") || "3");
        return json(await tree(env, parseCtxUri(uri), Number.isFinite(depth) ? depth : 3));
      }

      if (request.method === "GET" && url.pathname === "/v1/fs/read") {
        const uri = url.searchParams.get("uri") || "";
        return json(await read(env, parseCtxUri(uri)));
      }

      if (request.method === "POST" && url.pathname === "/v1/fs/write") {
        const payload = await request.json<Record<string, unknown>>();
        const uri = String(payload.uri || "").trim();
        const text = String(payload.text || "");
        const createParents = payload.createParents === undefined ? true : Boolean(payload.createParents);
        const overwrite = payload.overwrite === undefined ? true : Boolean(payload.overwrite);
        return json(await write(env, parseCtxUri(uri), text, createParents, overwrite));
      }

      if (url.pathname.startsWith("/v1/fs/")) {
        return json(
          {
            detail: "not implemented in Worker MVP yet",
            path: url.pathname,
            implementedNow: [
              "GET /health",
              "POST /v1/workspaces/register",
              "POST /v1/fs/mkdir",
              "GET /v1/fs/ls",
              "GET /v1/fs/stat",
              "GET /v1/fs/tree",
              "GET /v1/fs/read",
              "POST /v1/fs/write",
            ],
            nextSlice: [
              "POST /v1/fs/edit",
              "POST /v1/fs/search",
              "POST /v1/fs/reindex",
            ],
          },
          501,
        );
      }

      return json({ detail: "Not Found" }, 404);
    } catch (error) {
      if (error instanceof ApiError) {
        return json({ detail: error.message }, error.status);
      }
      return json({ detail: error instanceof Error ? error.message : String(error) }, 500);
    }
  },
};
