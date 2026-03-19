import { ApiError, buildChildUri, buildWorkspaceUri, parentPath, parseCtxUri, splitRelativePath, toWorkspaceScope, type ParsedCtxUri, type WorkspaceKind, type WorkspaceScope } from "./ctx.js";

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

  const updated = await getEntry(env, scope, parsed.relativePath);
  if (!updated) {
    throw new ApiError(500, `write succeeded but entry lookup failed: ${parsed.raw}`);
  }
  await rebuildSearchChunks(env, updated.id, text);

  return { uri: parsed.raw, written: true };
}

export async function edit(
  env: Env,
  parsed: ParsedCtxUri,
  matchText: string,
  replaceText: string,
  replaceAll: boolean,
): Promise<Record<string, unknown>> {
  const current = await read(env, parsed);
  const text = String(current.text || "");
  const matchCount = countOccurrences(text, matchText);
  if (matchCount === 0) {
    throw new ApiError(400, "matchText not found");
  }
  if (matchCount > 1 && !replaceAll) {
    throw new ApiError(400, "matchText matched multiple locations; set replaceAll=true");
  }
  const nextText = replaceAll ? text.split(matchText).join(replaceText) : text.replace(matchText, replaceText);
  await write(env, parsed, nextText, true, true);
  return {
    uri: parsed.raw,
    matched: matchCount,
    replaced: replaceAll ? matchCount : 1,
  };
}

export async function applyPatch(env: Env, parsed: ParsedCtxUri, patch: string): Promise<Record<string, unknown>> {
  const current = await read(env, parsed);
  let currentLines = String(current.text || "").split(/\r?\n/);
  const hunks = parsePatchHunks(patch);
  if (hunks.length === 0) {
    throw new ApiError(400, "no patch hunks found");
  }

  const applied: Array<Record<string, unknown>> = [];
  for (let index = 0; index < hunks.length; index += 1) {
    const hunk = hunks[index];
    const preimage = hunk.filter((line) => line.startsWith(" ") || line.startsWith("-")).map((line) => line.slice(1));
    const postimage = hunk.filter((line) => line.startsWith(" ") || line.startsWith("+")).map((line) => line.slice(1));
    if (preimage.length === 0) {
      throw new ApiError(400, "patch hunks must include context or removed lines");
    }
    const positions = findBlockPositions(currentLines, preimage);
    if (positions.length === 0) {
      throw new ApiError(400, `patch hunk ${index + 1} did not match current file`);
    }
    if (positions.length > 1) {
      throw new ApiError(400, `patch hunk ${index + 1} matched multiple locations`);
    }
    const start = positions[0];
    currentLines = currentLines.slice(0, start).concat(postimage, currentLines.slice(start + preimage.length));
    applied.push({
      index: index + 1,
      startLine: start + 1,
      removedLines: hunk.filter((line) => line.startsWith("-")).length,
      addedLines: hunk.filter((line) => line.startsWith("+")).length,
    });
  }

  await write(env, parsed, currentLines.join("\n"), true, true);
  return { uri: parsed.raw, hunks: hunks.length, applied };
}

export async function move(
  env: Env,
  sourceParsed: ParsedCtxUri,
  destinationParsed: ParsedCtxUri,
  createParents: boolean,
  overwrite: boolean,
): Promise<Record<string, unknown>> {
  assertMutableUri(sourceParsed);
  assertMutableUri(destinationParsed);
  assertNoNestedMove(sourceParsed, destinationParsed);

  const sourceScope = toWorkspaceScope(sourceParsed);
  const destinationScope = toWorkspaceScope(destinationParsed);
  await ensureWorkspaceRecord(env, destinationScope);

  const sourceEntries = await collectTransferEntries(env, sourceScope, sourceParsed.relativePath, sourceParsed.raw);
  if (createParents) {
    await ensureDirectoryPath(env, destinationScope, parentPath(destinationParsed.relativePath), true);
  } else {
    await assertDirectoryPathExists(env, destinationScope, parentPath(destinationParsed.relativePath), destinationParsed.raw);
  }

  const existingDestination = await getEntry(env, destinationScope, destinationParsed.relativePath);
  if (existingDestination && !overwrite) {
    throw new ApiError(400, `destination already exists: ${destinationParsed.raw}`);
  }
  if (existingDestination) {
    await remove(env, destinationParsed, true);
  }

  for (const row of sourceEntries) {
    const nextRelativePath = rewriteRelativePath(row.relative_path, sourceParsed.relativePath, destinationParsed.relativePath);
    await env.DB.prepare(
      `UPDATE fs_entries
       SET user_id = ?, workspace_kind = ?, agent_id = ?, relative_path = ?, updated_at = CURRENT_TIMESTAMP
       WHERE id = ?`,
    )
      .bind(destinationScope.userId, destinationScope.workspaceKind, destinationScope.agentId, nextRelativePath, row.id)
      .run();
  }

  return { sourceUri: sourceParsed.raw, destinationUri: destinationParsed.raw, moved: true };
}

export async function copy(
  env: Env,
  sourceParsed: ParsedCtxUri,
  destinationParsed: ParsedCtxUri,
  createParents: boolean,
  overwrite: boolean,
): Promise<Record<string, unknown>> {
  assertMutableUri(sourceParsed);
  assertMutableUri(destinationParsed);
  assertNoNestedMove(sourceParsed, destinationParsed);

  const sourceScope = toWorkspaceScope(sourceParsed);
  const destinationScope = toWorkspaceScope(destinationParsed);
  await ensureWorkspaceRecord(env, destinationScope);

  const sourceEntries = await collectTransferEntries(env, sourceScope, sourceParsed.relativePath, sourceParsed.raw);
  if (createParents) {
    await ensureDirectoryPath(env, destinationScope, parentPath(destinationParsed.relativePath), true);
  } else {
    await assertDirectoryPathExists(env, destinationScope, parentPath(destinationParsed.relativePath), destinationParsed.raw);
  }

  const existingDestination = await getEntry(env, destinationScope, destinationParsed.relativePath);
  if (existingDestination && !overwrite) {
    throw new ApiError(400, `destination already exists: ${destinationParsed.raw}`);
  }
  if (existingDestination) {
    await remove(env, destinationParsed, true);
  }

  for (const row of sourceEntries) {
    const nextRelativePath = rewriteRelativePath(row.relative_path, sourceParsed.relativePath, destinationParsed.relativePath);
    await env.DB.prepare(
      `INSERT INTO fs_entries (
        user_id, workspace_kind, agent_id, relative_path, kind, title, content_text, content_hash, size_bytes, created_at, updated_at
      ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, CURRENT_TIMESTAMP, CURRENT_TIMESTAMP)`,
    )
      .bind(
        destinationScope.userId,
        destinationScope.workspaceKind,
        destinationScope.agentId,
        nextRelativePath,
        row.kind,
        null,
        row.content_text,
        row.content_hash,
        row.size_bytes,
      )
      .run();

    if (row.kind === "file") {
      const inserted = await getEntry(env, destinationScope, nextRelativePath);
      if (inserted) {
        await rebuildSearchChunks(env, inserted.id, row.content_text || "");
      }
    }
  }

  return { sourceUri: sourceParsed.raw, destinationUri: destinationParsed.raw, copied: true };
}

export async function remove(env: Env, parsed: ParsedCtxUri, recursive: boolean): Promise<Record<string, unknown>> {
  assertMutableUri(parsed);
  const scope = toWorkspaceScope(parsed);
  const entry = await getEntry(env, scope, parsed.relativePath);
  if (!entry) {
    throw new ApiError(404, `path does not exist: ${parsed.raw}`);
  }
  if (entry.kind === "file") {
    await env.DB.prepare("DELETE FROM fs_entries WHERE id = ?").bind(entry.id).run();
    return { uri: parsed.raw, kind: "file", removed: true };
  }

  const rows = await collectTransferEntries(env, scope, parsed.relativePath, parsed.raw);
  if (!recursive && rows.length > 1) {
    throw new ApiError(400, `directory is not empty: ${parsed.raw}; set recursive=true`);
  }
  for (const row of [...rows].reverse()) {
    await env.DB.prepare("DELETE FROM fs_entries WHERE id = ?").bind(row.id).run();
  }
  return { uri: parsed.raw, kind: "dir", removed: true };
}

export async function search(
  env: Env,
  userId: string,
  query: string,
  scopeUri: string | null,
  workspaceMode: string,
  mode: string,
  expansions: string[],
  globPattern: string | null,
  pathPrefix: string | null,
  explain: boolean,
  limit: number,
): Promise<Record<string, unknown>> {
  const trimmedQuery = query.trim();
  const normalizedQuery = normalizeQuery(trimmedQuery);
  const effective = await resolveSearchScope(env, userId, scopeUri, workspaceMode);
  const files = await listSearchCandidates(env, effective);
  const terms = uniqueTerms([trimmedQuery, ...expansions]);
  const hits = files
    .filter((row) => matchesOptionalFilters(row.relative_path, effective.relativePrefix, globPattern, pathPrefix))
    .map((row) => scoreSearchRow(row, terms, trimmedQuery, effective.workspaceMode))
    .filter((row) => row.score > 0)
    .sort((a, b) => b.score - a.score || a.uri.localeCompare(b.uri))
    .slice(0, Math.max(1, limit))
    .map((row) => ({
      uri: row.uri,
      title: row.title,
      kind: "file",
      docType: row.docType,
      workspaceKind: row.workspaceKind,
      agentId: row.agentId || null,
      score: Number(row.score.toFixed(6)),
      snippet: row.snippet,
      lineNumber: row.lineNumber,
      reasons: explain ? row.reasons : [],
    }));

  return {
    query: trimmedQuery,
    normalizedQuery,
    scopeUri: effective.scopeUri,
    workspaceMode: effective.workspaceMode,
    mode,
    rewrites: [],
    plan: {
      source: "live-scan",
      lexical: true,
      semantic: false,
      rerank: false,
      explain,
      candidateCount: hits.length,
      fallback: mode === "lexical" ? null : "worker-live-scan-lexical-only",
    },
    hits,
  };
}

export async function reindex(env: Env, userId: string, scopeUri: string | null, workspaceMode: string): Promise<Record<string, unknown>> {
  const effective = await resolveSearchScope(env, userId, scopeUri, workspaceMode);
  const files = await listSearchCandidates(env, effective);
  let indexed = 0;
  for (const row of files) {
    await rebuildSearchChunks(env, row.id, row.content_text || "");
    indexed += 1;
  }
  return {
    userId,
    scopeUri: effective.scopeUri,
    indexed,
    unchanged: 0,
    removed: 0,
    skipped: 0,
  };
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

type SearchScope = {
  scopeUri: string;
  workspaceMode: string;
  scopes: WorkspaceScope[];
  relativePrefix: string;
};

type SearchCandidateRow = FsEntryRow & {
  uri: string;
  docType: string;
  title: string;
  workspaceKind: WorkspaceKind;
  agentId: string;
};

type ScoredSearchRow = SearchCandidateRow & {
  score: number;
  snippet: string;
  lineNumber: number | null;
  reasons: string[];
};

function countLines(text: string): number {
  return text ? text.split(/\r?\n/).length : 0;
}

function byteLength(text: string): number {
  return new TextEncoder().encode(text).byteLength;
}

function countOccurrences(text: string, needle: string): number {
  if (!needle) return 0;
  let index = 0;
  let count = 0;
  while (true) {
    const next = text.indexOf(needle, index);
    if (next < 0) return count;
    count += 1;
    index = next + needle.length;
  }
}

function normalizeQuery(value: string): string {
  return value.trim().toLowerCase();
}

function uniqueTerms(values: string[]): string[] {
  const terms = new Set<string>();
  for (const value of values) {
    for (const match of value.toLowerCase().match(/[\p{L}\p{N}_-]+/gu) || []) {
      if (match) terms.add(match);
    }
  }
  return [...terms];
}

function matchesOptionalFilters(relativePath: string, scopePrefix: string, globPattern: string | null, pathPrefix: string | null): boolean {
  const target = relativePath;
  if (scopePrefix && !target.startsWith(scopePrefix)) return false;
  if (pathPrefix && !target.startsWith(pathPrefix.replace(/^\/+/, ""))) return false;
  if (globPattern && !globToRegExp(globPattern).test(target)) return false;
  return true;
}

function globToRegExp(pattern: string): RegExp {
  const escaped = pattern
    .replace(/[.+^${}()|[\]\\]/g, "\\$&")
    .replace(/\*\*/g, "::DOUBLE_STAR::")
    .replace(/\*/g, "[^/]*")
    .replace(/::DOUBLE_STAR::/g, ".*")
    .replace(/\?/g, ".");
  return new RegExp(`^${escaped}$`);
}

function docTypeForPath(relativePath: string): string {
  const head = splitRelativePath(relativePath)[0] || "root";
  if (["docs", "memory", "archive", "tasks"].includes(head)) return head;
  const segments = splitRelativePath(relativePath);
  const tail = segments[segments.length - 1] || "";
  if (tail.endsWith(".md")) return "markdown";
  return "file";
}

function titleForRow(row: FsEntryRow): string {
  const text = row.content_text || "";
  const heading = text.split(/\r?\n/).find((line) => line.trim().startsWith("# "));
  if (heading) return heading.trim().replace(/^#\s+/, "");
  return basename(row.relative_path);
}

function findSnippet(text: string, query: string, terms: string[]): { snippet: string; lineNumber: number | null } {
  const lines = text.split(/\r?\n/);
  const lowerQuery = query.toLowerCase();
  for (let index = 0; index < lines.length; index += 1) {
    const lower = lines[index].toLowerCase();
    if ((lowerQuery && lower.includes(lowerQuery)) || terms.some((term) => lower.includes(term))) {
      return { snippet: lines[index].slice(0, 240), lineNumber: index + 1 };
    }
  }
  const snippet = text.replace(/\s+/g, " ").slice(0, 240);
  return { snippet, lineNumber: text ? 1 : null };
}

function scoreSearchRow(row: SearchCandidateRow, terms: string[], rawQuery: string, workspaceMode: string): ScoredSearchRow {
  const pathText = row.relative_path.toLowerCase();
  const titleText = row.title.toLowerCase();
  const bodyText = (row.content_text || "").toLowerCase();
  const normalizedQuery = rawQuery.toLowerCase();
  let score = 0;
  const reasons: string[] = [];

  if (normalizedQuery && titleText.includes(normalizedQuery)) {
    score += 6;
    reasons.push(`title match: ${rawQuery}`);
  }
  if (normalizedQuery && pathText.includes(normalizedQuery)) {
    score += 5;
    reasons.push(`path match: ${rawQuery}`);
  }
  if (normalizedQuery && bodyText.includes(normalizedQuery)) {
    score += 4;
    reasons.push(`body match: ${rawQuery}`);
  }

  for (const term of terms) {
    if (titleText.includes(term)) {
      score += 2.5;
      reasons.push(`title token: ${term}`);
    }
    if (pathText.includes(term)) {
      score += 2;
      reasons.push(`path token: ${term}`);
    }
    if (bodyText.includes(term)) {
      score += 1;
      reasons.push(`body token: ${term}`);
    }
  }

  if (workspaceMode === "default-first" && row.workspaceKind === "defaultWorkspace") {
    score += 0.75;
    reasons.push("workspace boost: defaultWorkspace");
  }

  const snippet = findSnippet(row.content_text || "", rawQuery, terms);
  return {
    ...row,
    score,
    snippet: snippet.snippet,
    lineNumber: snippet.lineNumber,
    reasons: reasons.slice(0, 6),
  };
}

async function resolveSearchScope(env: Env, userId: string, scopeUri: string | null, workspaceMode: string): Promise<SearchScope> {
  if (scopeUri) {
    const parsed = parseCtxUri(scopeUri);
    if (parsed.userId !== userId) {
      throw new ApiError(400, `scope user mismatch: ${scopeUri}`);
    }
    if (parsed.isUserRoot) {
      const scopes = await listWorkspaceScopes(env, userId);
      return {
        scopeUri: parsed.raw,
        workspaceMode,
        scopes,
        relativePrefix: "",
      };
    }
    const scope = toWorkspaceScope(parsed);
    await assertWorkspaceExists(env, scope, parsed.raw);
    return {
      scopeUri: parsed.raw,
      workspaceMode,
      scopes: [scope],
      relativePrefix: parsed.relativePath ? `${parsed.relativePath}/` : "",
    };
  }

  if (workspaceMode === "user" || workspaceMode === "default-first") {
    return {
      scopeUri: `ctx://${userId}`,
      workspaceMode,
      scopes: await listWorkspaceScopes(env, userId),
      relativePrefix: "",
    };
  }

  const defaultScope: WorkspaceScope = { userId, workspaceKind: "defaultWorkspace", agentId: "" };
  return {
    scopeUri: buildWorkspaceUri(userId, "defaultWorkspace", ""),
    workspaceMode: "default-only",
    scopes: [defaultScope],
    relativePrefix: "",
  };
}

async function listWorkspaceScopes(env: Env, userId: string): Promise<WorkspaceScope[]> {
  const rows = await listWorkspaces(env, userId);
  return rows.map((row) => ({
    userId: row.user_id,
    workspaceKind: row.workspace_kind,
    agentId: row.agent_id,
  }));
}

async function collectTransferEntries(env: Env, scope: WorkspaceScope, rootRelativePath: string, rawUri: string): Promise<FsEntryRow[]> {
  const target = await getEntry(env, scope, rootRelativePath);
  if (!target) {
    throw new ApiError(404, `path does not exist: ${rawUri}`);
  }
  if (target.kind === "file") {
    return [target];
  }
  const prefix = `${rootRelativePath}/`;
  const result = await env.DB.prepare(
    `SELECT id, user_id, workspace_kind, agent_id, relative_path, kind, content_text, content_hash, size_bytes, created_at, updated_at
     FROM fs_entries
     WHERE user_id = ? AND workspace_kind = ? AND agent_id = ? AND (relative_path = ? OR relative_path LIKE ?)
     ORDER BY LENGTH(relative_path) ASC, relative_path ASC`,
  )
    .bind(scope.userId, scope.workspaceKind, scope.agentId, rootRelativePath, `${prefix}%`)
    .all<FsEntryRow>();
  return result.results || [];
}

function rewriteRelativePath(currentPath: string, sourceRoot: string, destinationRoot: string): string {
  if (currentPath === sourceRoot) return destinationRoot;
  const suffix = currentPath.slice(sourceRoot.length + 1);
  return `${destinationRoot}/${suffix}`;
}

function assertMutableUri(parsed: ParsedCtxUri): void {
  if (parsed.isUserRoot || parsed.isWorkspaceRoot) {
    throw new ApiError(400, "cannot mutate a user root or workspace root directly");
  }
}

function assertNoNestedMove(source: ParsedCtxUri, destination: ParsedCtxUri): void {
  if (
    source.userId === destination.userId &&
    source.workspaceKind === destination.workspaceKind &&
    source.agentId === destination.agentId &&
    destination.relativePath &&
    (destination.relativePath === source.relativePath || destination.relativePath.startsWith(`${source.relativePath}/`))
  ) {
    throw new ApiError(400, `destination cannot be the same as or nested under source: ${destination.raw}`);
  }
}

function parsePatchHunks(patchText: string): string[][] {
  const hunks: string[][] = [];
  let current: string[] = [];
  let sawPatchMarker = false;

  for (const rawLine of patchText.split(/\r?\n/)) {
    if (rawLine.startsWith("*** Begin Patch")) {
      sawPatchMarker = true;
      continue;
    }
    if (rawLine.startsWith("*** End Patch")) {
      break;
    }
    if (rawLine.startsWith("*** Update File:") || rawLine.startsWith("*** Delete File:") || rawLine.startsWith("*** Add File:") || rawLine.startsWith("--- ") || rawLine.startsWith("+++ ")) {
      sawPatchMarker = true;
      continue;
    }
    if (rawLine.startsWith("@@")) {
      sawPatchMarker = true;
      if (current.length > 0) {
        hunks.push(current);
        current = [];
      }
      continue;
    }
    if (rawLine.startsWith("\\")) {
      continue;
    }
    if (rawLine.startsWith(" ") || rawLine.startsWith("+") || rawLine.startsWith("-")) {
      sawPatchMarker = true;
      current.push(rawLine);
      continue;
    }
    if (rawLine.trim() === "") {
      if (current.length > 0) {
        throw new ApiError(400, "blank lines inside hunks must keep a diff prefix");
      }
      continue;
    }
    if (sawPatchMarker) {
      throw new ApiError(400, `invalid patch line: ${rawLine}`);
    }
  }

  if (current.length > 0) {
    hunks.push(current);
  }
  return hunks;
}

function findBlockPositions(lines: string[], needle: string[]): number[] {
  const positions: number[] = [];
  if (needle.length === 0) return positions;
  const maxStart = lines.length - needle.length;
  for (let start = 0; start <= maxStart; start += 1) {
    const candidate = lines.slice(start, start + needle.length);
    if (candidate.length === needle.length && candidate.every((line, index) => line === needle[index])) {
      positions.push(start);
    }
  }
  return positions;
}

async function listSearchCandidates(env: Env, searchScope: SearchScope): Promise<SearchCandidateRow[]> {
  const results: SearchCandidateRow[] = [];
  for (const scope of searchScope.scopes) {
    const rows = await env.DB.prepare(
      `SELECT id, user_id, workspace_kind, agent_id, relative_path, kind, content_text, content_hash, size_bytes, created_at, updated_at
       FROM fs_entries
       WHERE user_id = ? AND workspace_kind = ? AND agent_id = ? AND kind = 'file'`,
    )
      .bind(scope.userId, scope.workspaceKind, scope.agentId)
      .all<FsEntryRow>();
    for (const row of rows.results || []) {
      results.push({
        ...row,
        uri: buildChildUri(scope, row.relative_path),
        docType: docTypeForPath(row.relative_path),
        title: titleForRow(row),
        workspaceKind: scope.workspaceKind,
        agentId: scope.agentId,
      });
    }
  }
  return results;
}

async function rebuildSearchChunks(env: Env, entryId: number, text: string): Promise<void> {
  await env.DB.prepare("DELETE FROM search_chunks WHERE entry_id = ?").bind(entryId).run();
  const chunks = chunkText(text);
  for (let index = 0; index < chunks.length; index += 1) {
    await env.DB.prepare(
      `INSERT INTO search_chunks (entry_id, chunk_index, chunk_text, created_at)
       VALUES (?, ?, ?, CURRENT_TIMESTAMP)`,
    )
      .bind(entryId, index, chunks[index])
      .run();
  }
}

function chunkText(text: string): string[] {
  const normalized = text.replace(/\r\n/g, "\n");
  if (!normalized) return [];
  const paragraphs = normalized.split(/\n{2,}/).map((value) => value.trim()).filter(Boolean);
  if (paragraphs.length > 0) return paragraphs.slice(0, 64);
  return [normalized.slice(0, 4000)];
}

async function sha256(text: string): Promise<string> {
  const bytes = new TextEncoder().encode(text);
  const digest = await crypto.subtle.digest("SHA-256", bytes);
  return [...new Uint8Array(digest)].map((byte) => byte.toString(16).padStart(2, "0")).join("");
}
