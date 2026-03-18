import { ApiError, buildChildUri, buildWorkspaceUri, parentPath, splitRelativePath, toWorkspaceScope, type ParsedCtxUri, type WorkspaceKind, type WorkspaceScope } from "./ctx.js";

export interface Env {
  DB: D1Database;
  CONTEXT_HUB_ADMIN_TOKEN?: string;
  CONTEXT_HUB_BIND_MODE?: string;
}

interface FsEntryRow {
  id: number;
  user_id: string;
  workspace_kind: WorkspaceKind;
  agent_id: string;
  relative_path: string;
  kind: "file" | "dir";
  content_text: string | null;
  content_hash: string | null;
  size_bytes: number | null;
  created_at: string;
  updated_at: string;
}

interface WorkspaceRow {
  user_id: string;
  workspace_kind: WorkspaceKind;
  agent_id: string;
  root_uri: string;
}

export async function registerWorkspace(env: Env, userId: string, workspaceKind: WorkspaceKind, agentId: string): Promise<Record<string, unknown>> {
  await ensureWorkspaceRecord(env, { userId, workspaceKind, agentId });
  return {
    uri: buildWorkspaceUri(userId, workspaceKind, agentId),
    workspaceKind,
    agentId: agentId || null,
  };
}

export async function mkdir(env: Env, parsed: ParsedCtxUri, parents: boolean): Promise<Record<string, unknown>> {
  if (parsed.isUserRoot) {
    return { uri: parsed.raw, created: true };
  }

  const scope = toWorkspaceScope(parsed);
  await ensureWorkspaceRecord(env, scope);
  if (parsed.isWorkspaceRoot) {
    return { uri: parsed.raw, created: true };
  }

  await ensureDirectoryPath(env, scope, parsed.relativePath, parents);
  return { uri: parsed.raw, created: true };
}

export async function ls(env: Env, parsed: ParsedCtxUri): Promise<Record<string, unknown>> {
  if (parsed.isUserRoot) {
    const workspaces = await listWorkspaces(env, parsed.userId);
    if (workspaces.length === 0) {
      throw new ApiError(404, `path does not exist: ${parsed.raw}`);
    }
    const entries = workspaces.map((workspace) => ({
      name: workspace.workspace_kind === "defaultWorkspace" ? "defaultWorkspace" : `agentWorkspace/${workspace.agent_id}`,
      uri: workspace.root_uri,
      kind: "dir",
    }));
    return { uri: parsed.raw, entries };
  }

  const scope = toWorkspaceScope(parsed);
  await assertDirectoryExists(env, parsed);
  const entries = await listImmediateChildren(env, scope, parsed.relativePath);
  return { uri: parsed.raw, entries };
}

export async function stat(env: Env, parsed: ParsedCtxUri): Promise<Record<string, unknown>> {
  if (parsed.isUserRoot) {
    const listing = await ls(env, parsed);
    return {
      uri: parsed.raw,
      name: parsed.userId,
      kind: "dir",
      sizeBytes: null,
      lineCount: null,
      childCount: Array.isArray(listing.entries) ? listing.entries.length : 0,
    };
  }

  const scope = toWorkspaceScope(parsed);
  if (parsed.isWorkspaceRoot) {
    await assertWorkspaceExists(env, scope, parsed.raw);
    const children = await listImmediateChildren(env, scope, "");
    return {
      uri: parsed.raw,
      name: parsed.workspaceLabel,
      kind: "dir",
      sizeBytes: null,
      lineCount: null,
      childCount: children.length,
    };
  }

  const entry = await getEntry(env, scope, parsed.relativePath);
  if (!entry) {
    throw new ApiError(404, `path does not exist: ${parsed.raw}`);
  }
  if (entry.kind === "dir") {
    const children = await listImmediateChildren(env, scope, parsed.relativePath);
    return {
      uri: parsed.raw,
      name: basename(parsed.relativePath),
      kind: "dir",
      sizeBytes: null,
      lineCount: null,
      childCount: children.length,
    };
  }
  const text = entry.content_text || "";
  return {
    uri: parsed.raw,
    name: basename(parsed.relativePath),
    kind: "file",
    sizeBytes: entry.size_bytes ?? text.length,
    lineCount: countLines(text),
    childCount: null,
  };
}

export async function tree(env: Env, parsed: ParsedCtxUri, depth: number): Promise<Record<string, unknown>> {
  const remaining = Math.max(depth, 0);
  if (parsed.isUserRoot) {
    const workspaces = await listWorkspaces(env, parsed.userId);
    if (workspaces.length === 0) {
      throw new ApiError(404, `path does not exist: ${parsed.raw}`);
    }
    return {
      name: parsed.userId,
      uri: parsed.raw,
      kind: "dir",
      children: remaining > 0
        ? await Promise.all(
            workspaces.map((workspace) =>
              buildTreeNode(
                env,
                {
                  raw: workspace.root_uri,
                  userId: workspace.user_id,
                  workspaceKind: workspace.workspace_kind,
                  agentId: workspace.agent_id,
                  relativePath: "",
                  isUserRoot: false,
                  isWorkspaceRoot: true,
                  workspaceLabel: workspace.workspace_kind === "defaultWorkspace"
                    ? "defaultWorkspace"
                    : `agentWorkspace/${workspace.agent_id}`,
                },
                remaining - 1,
              ),
            ),
          )
        : [],
    };
  }
  return buildTreeNode(env, parsed, remaining);
}

export async function read(env: Env, parsed: ParsedCtxUri): Promise<Record<string, unknown>> {
  if (parsed.isUserRoot || parsed.isWorkspaceRoot) {
    throw new ApiError(400, `path is not a file: ${parsed.raw}`);
  }
  const scope = toWorkspaceScope(parsed);
  const entry = await getEntry(env, scope, parsed.relativePath);
  if (!entry) {
    throw new ApiError(404, `path does not exist: ${parsed.raw}`);
  }
  if (entry.kind !== "file") {
    throw new ApiError(400, `path is not a file: ${parsed.raw}`);
  }
  const text = entry.content_text || "";
  return {
    uri: parsed.raw,
    text,
    lineCount: countLines(text),
  };
}

export async function write(
  env: Env,
  parsed: ParsedCtxUri,
  text: string,
  createParents: boolean,
  overwrite: boolean,
): Promise<Record<string, unknown>> {
  if (parsed.isUserRoot || parsed.isWorkspaceRoot) {
    throw new ApiError(400, "cannot write to a workspace root");
  }

  const scope = toWorkspaceScope(parsed);
  await ensureWorkspaceRecord(env, scope);
  const parent = parentPath(parsed.relativePath);
  if (createParents) {
    await ensureDirectoryPath(env, scope, parent, true);
  } else {
    await assertDirectoryPathExists(env, scope, parent, parsed.raw);
  }

  const existing = await getEntry(env, scope, parsed.relativePath);
  if (existing?.kind === "dir") {
    throw new ApiError(400, `path is a directory: ${parsed.raw}`);
  }
  if (existing && !overwrite) {
    throw new ApiError(400, `file already exists: ${parsed.raw}`);
  }

  const sizeBytes = byteLength(text);
  const contentHash = await sha256(text);
  await env.DB.prepare(
    `INSERT INTO fs_entries (
      user_id, workspace_kind, agent_id, relative_path, kind, content_text, content_hash, size_bytes, created_at, updated_at
    ) VALUES (?, ?, ?, ?, 'file', ?, ?, ?, CURRENT_TIMESTAMP, CURRENT_TIMESTAMP)
    ON CONFLICT(user_id, workspace_kind, agent_id, relative_path)
    DO UPDATE SET
      kind='file',
      content_text=excluded.content_text,
      content_hash=excluded.content_hash,
      size_bytes=excluded.size_bytes,
      updated_at=CURRENT_TIMESTAMP`,
  )
    .bind(scope.userId, scope.workspaceKind, scope.agentId, parsed.relativePath, text, contentHash, sizeBytes)
    .run();

  return { uri: parsed.raw, written: true };
}

export async function assertAuthorized(request: Request, env: Env): Promise<void> {
  const expected = (env.CONTEXT_HUB_ADMIN_TOKEN || "").trim();
  if (!expected) return;
  const actual = request.headers.get("authorization") || "";
  if (actual !== `Bearer ${expected}`) {
    throw new ApiError(401, "Missing or invalid bearer token");
  }
}

async function buildTreeNode(env: Env, parsed: ParsedCtxUri, depth: number): Promise<Record<string, unknown>> {
  const statResult = await stat(env, parsed);
  const node: Record<string, unknown> = {
    name: statResult.name,
    uri: parsed.raw,
    kind: statResult.kind,
    children: [],
  };
  if (statResult.kind === "dir" && depth > 0) {
    const listing = await ls(env, parsed);
    const children = Array.isArray(listing.entries) ? listing.entries as Array<Record<string, unknown>> : [];
    node.children = await Promise.all(
      children.map(async (child) => {
        const childParsed = parseChildFromListing(parsed, String(child.uri));
        return buildTreeNode(env, childParsed, depth - 1);
      }),
    );
  }
  return node;
}

function parseChildFromListing(parent: ParsedCtxUri, childUri: string): ParsedCtxUri {
  return parent.isUserRoot ? parseChildUserRoot(childUri) : parseChildWorkspaceRoot(childUri);
}

function parseChildUserRoot(childUri: string): ParsedCtxUri {
  const segments = childUri.replace(/^ctx:\/\//, "").split("/").filter(Boolean);
  const userId = segments[0];
  if (segments[1] === "defaultWorkspace") {
    return {
      raw: childUri,
      userId,
      workspaceKind: "defaultWorkspace",
      agentId: "",
      relativePath: segments.slice(2).join("/"),
      isUserRoot: false,
      isWorkspaceRoot: segments.length === 2,
      workspaceLabel: "defaultWorkspace",
    };
  }
  const agentId = segments[2] || "";
  return {
    raw: childUri,
    userId,
    workspaceKind: "agentWorkspace",
    agentId,
    relativePath: segments.slice(3).join("/"),
    isUserRoot: false,
    isWorkspaceRoot: segments.length === 3,
    workspaceLabel: `agentWorkspace/${agentId}`,
  };
}

function parseChildWorkspaceRoot(childUri: string): ParsedCtxUri {
  const match = childUri.match(/^ctx:\/\/([^/]+)\/(defaultWorkspace|agentWorkspace)(?:\/([^/]+))?(?:\/(.*))?$/);
  if (!match) {
    throw new ApiError(400, `invalid ctx uri: ${childUri}`);
  }
  const [, userId, workspaceKindRaw, agentIdRaw, relativeRaw] = match;
  const workspaceKind = workspaceKindRaw as WorkspaceKind;
  const agentId = workspaceKind === "agentWorkspace" ? (agentIdRaw || "") : "";
  const relativePath = relativeRaw || "";
  return {
    raw: childUri,
    userId,
    workspaceKind,
    agentId,
    relativePath,
    isUserRoot: false,
    isWorkspaceRoot: relativePath === "",
    workspaceLabel: workspaceKind === "defaultWorkspace" ? "defaultWorkspace" : `agentWorkspace/${agentId}`,
  };
}

async function ensureWorkspaceRecord(env: Env, scope: WorkspaceScope): Promise<void> {
  const rootUri = buildWorkspaceUri(scope.userId, scope.workspaceKind, scope.agentId);
  await env.DB.prepare(
    `INSERT INTO workspaces (user_id, workspace_kind, agent_id, root_uri, created_at, updated_at)
     VALUES (?, ?, ?, ?, CURRENT_TIMESTAMP, CURRENT_TIMESTAMP)
     ON CONFLICT(user_id, workspace_kind, agent_id)
     DO UPDATE SET updated_at=CURRENT_TIMESTAMP`,
  )
    .bind(scope.userId, scope.workspaceKind, scope.agentId, rootUri)
    .run();
}

async function assertWorkspaceExists(env: Env, scope: WorkspaceScope, rawUri: string): Promise<void> {
  const row = await env.DB.prepare(
    "SELECT root_uri FROM workspaces WHERE user_id = ? AND workspace_kind = ? AND agent_id = ? LIMIT 1",
  )
    .bind(scope.userId, scope.workspaceKind, scope.agentId)
    .first<WorkspaceRow>();
  if (!row) {
    throw new ApiError(404, `path does not exist: ${rawUri}`);
  }
}

async function listWorkspaces(env: Env, userId: string): Promise<WorkspaceRow[]> {
  const result = await env.DB.prepare(
    "SELECT user_id, workspace_kind, agent_id, root_uri FROM workspaces WHERE user_id = ? ORDER BY workspace_kind ASC, agent_id ASC",
  )
    .bind(userId)
    .all<WorkspaceRow>();
  const rows = result.results || [];
  return rows.sort((a, b) => {
    const aKey = a.workspace_kind === "defaultWorkspace" ? `0:${a.workspace_kind}` : `1:${a.agent_id}`;
    const bKey = b.workspace_kind === "defaultWorkspace" ? `0:${b.workspace_kind}` : `1:${b.agent_id}`;
    return aKey.localeCompare(bKey);
  });
}

async function assertDirectoryExists(env: Env, parsed: ParsedCtxUri): Promise<void> {
  if (parsed.isWorkspaceRoot) {
    await assertWorkspaceExists(env, toWorkspaceScope(parsed), parsed.raw);
    return;
  }
  const scope = toWorkspaceScope(parsed);
  const entry = await getEntry(env, scope, parsed.relativePath);
  if (!entry) {
    throw new ApiError(404, `path does not exist: ${parsed.raw}`);
  }
  if (entry.kind !== "dir") {
    throw new ApiError(400, `path is not a directory: ${parsed.raw}`);
  }
}

async function assertDirectoryPathExists(env: Env, scope: WorkspaceScope, relativePath: string, rawUri: string): Promise<void> {
  if (!relativePath) {
    await assertWorkspaceExists(env, scope, buildWorkspaceUri(scope.userId, scope.workspaceKind, scope.agentId));
    return;
  }
  const entry = await getEntry(env, scope, relativePath);
  if (!entry || entry.kind !== "dir") {
    throw new ApiError(400, `parent directory does not exist: ${rawUri}`);
  }
}

async function ensureDirectoryPath(env: Env, scope: WorkspaceScope, relativePath: string, parents: boolean): Promise<void> {
  await ensureWorkspaceRecord(env, scope);
  if (!relativePath) return;
  const segments = splitRelativePath(relativePath);
  if (!parents && segments.length > 1) {
    const directParent = segments.slice(0, -1).join("/");
    await assertDirectoryPathExists(env, scope, directParent, buildChildUri(scope, relativePath));
  }
  let current = "";
  for (const segment of segments) {
    current = current ? `${current}/${segment}` : segment;
    const existing = await getEntry(env, scope, current);
    if (existing?.kind === "file") {
      throw new ApiError(400, `path is a file: ${buildChildUri(scope, current)}`);
    }
    if (!existing) {
      await env.DB.prepare(
        `INSERT INTO fs_entries (
          user_id, workspace_kind, agent_id, relative_path, kind, created_at, updated_at
        ) VALUES (?, ?, ?, ?, 'dir', CURRENT_TIMESTAMP, CURRENT_TIMESTAMP)`,
      )
        .bind(scope.userId, scope.workspaceKind, scope.agentId, current)
        .run();
    }
  }
}

async function getEntry(env: Env, scope: WorkspaceScope, relativePath: string): Promise<FsEntryRow | null> {
  return env.DB.prepare(
    `SELECT id, user_id, workspace_kind, agent_id, relative_path, kind, content_text, content_hash, size_bytes, created_at, updated_at
     FROM fs_entries
     WHERE user_id = ? AND workspace_kind = ? AND agent_id = ? AND relative_path = ?
     LIMIT 1`,
  )
    .bind(scope.userId, scope.workspaceKind, scope.agentId, relativePath)
    .first<FsEntryRow>();
}

async function listImmediateChildren(env: Env, scope: WorkspaceScope, relativePath: string): Promise<Array<Record<string, unknown>>> {
  const prefix = relativePath ? `${relativePath}/` : "";
  const result = await env.DB.prepare(
    `SELECT relative_path, kind FROM fs_entries WHERE user_id = ? AND workspace_kind = ? AND agent_id = ?`,
  )
    .bind(scope.userId, scope.workspaceKind, scope.agentId)
    .all<{ relative_path: string; kind: "file" | "dir" }>();
  const rows = result.results || [];
  const children = new Map<string, { kind: "file" | "dir" }>();

  for (const row of rows) {
    if (prefix) {
      if (!row.relative_path.startsWith(prefix)) continue;
    }
    const remainder = prefix ? row.relative_path.slice(prefix.length) : row.relative_path;
    if (!remainder) continue;
    const name = remainder.split("/")[0];
    const kind = remainder.includes("/") ? "dir" : row.kind;
    const existing = children.get(name);
    if (!existing || existing.kind !== "dir") {
      children.set(name, { kind });
    }
  }

  return [...children.entries()]
    .sort((a, b) => {
      const kindOrder = a[1].kind === b[1].kind ? 0 : a[1].kind === "dir" ? -1 : 1;
      return kindOrder || a[0].localeCompare(b[0]);
    })
    .map(([name, value]) => {
      const childRelativePath = relativePath ? `${relativePath}/${name}` : name;
      return {
        name,
        uri: buildChildUri(scope, childRelativePath),
        kind: value.kind === "dir" ? "dir" : "file",
      };
    });
}

function basename(relativePath: string): string {
  const segments = splitRelativePath(relativePath);
  return segments[segments.length - 1] || relativePath;
}

function countLines(text: string): number {
  return text ? text.split(/\r?\n/).length : 0;
}

function byteLength(text: string): number {
  return new TextEncoder().encode(text).byteLength;
}

async function sha256(text: string): Promise<string> {
  const bytes = new TextEncoder().encode(text);
  const digest = await crypto.subtle.digest("SHA-256", bytes);
  return [...new Uint8Array(digest)].map((byte) => byte.toString(16).padStart(2, "0")).join("");
}
