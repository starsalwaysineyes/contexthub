export type WorkspaceKind = "defaultWorkspace" | "agentWorkspace";

export class ApiError extends Error {
  constructor(
    readonly status: number,
    message: string,
  ) {
    super(message);
  }
}

export interface ParsedCtxUri {
  raw: string;
  userId: string;
  workspaceKind: WorkspaceKind | null;
  agentId: string;
  relativePath: string;
  isUserRoot: boolean;
  isWorkspaceRoot: boolean;
  workspaceLabel: string | null;
}

export interface WorkspaceScope {
  userId: string;
  workspaceKind: WorkspaceKind;
  agentId: string;
}

export function parseCtxUri(raw: string): ParsedCtxUri {
  const value = raw.trim();
  if (!value.startsWith("ctx://")) {
    throw new ApiError(400, `invalid ctx uri: ${raw}`);
  }

  const body = value.slice("ctx://".length);
  const segments = body.split("/").filter(Boolean);
  if (segments.length === 0) {
    throw new ApiError(400, `invalid ctx uri: ${raw}`);
  }

  const userId = validateSegment(segments[0], "user id");
  if (segments.length === 1) {
    return {
      raw: `ctx://${userId}`,
      userId,
      workspaceKind: null,
      agentId: "",
      relativePath: "",
      isUserRoot: true,
      isWorkspaceRoot: false,
      workspaceLabel: null,
    };
  }

  const workspaceHead = segments[1];
  if (workspaceHead === "defaultWorkspace") {
    const relativePath = normalizeRelativePath(segments.slice(2));
    return {
      raw: buildCtxUri(userId, "defaultWorkspace", "", relativePath),
      userId,
      workspaceKind: "defaultWorkspace",
      agentId: "",
      relativePath,
      isUserRoot: false,
      isWorkspaceRoot: relativePath === "",
      workspaceLabel: "defaultWorkspace",
    };
  }

  if (workspaceHead === "agentWorkspace") {
    if (segments.length < 3) {
      throw new ApiError(400, `invalid ctx uri: ${raw}`);
    }
    const agentId = validateSegment(segments[2], "agent id");
    const relativePath = normalizeRelativePath(segments.slice(3));
    return {
      raw: buildCtxUri(userId, "agentWorkspace", agentId, relativePath),
      userId,
      workspaceKind: "agentWorkspace",
      agentId,
      relativePath,
      isUserRoot: false,
      isWorkspaceRoot: relativePath === "",
      workspaceLabel: `agentWorkspace/${agentId}`,
    };
  }

  throw new ApiError(400, `invalid ctx uri: ${raw}`);
}

export function buildWorkspaceUri(userId: string, workspaceKind: WorkspaceKind, agentId = ""): string {
  return buildCtxUri(userId, workspaceKind, agentId, "");
}

export function buildChildUri(scope: WorkspaceScope, relativePath: string): string {
  return buildCtxUri(scope.userId, scope.workspaceKind, scope.agentId, relativePath);
}

export function toWorkspaceScope(parsed: ParsedCtxUri): WorkspaceScope {
  if (!parsed.workspaceKind) {
    throw new ApiError(400, `ctx uri is not inside a workspace: ${parsed.raw}`);
  }
  return {
    userId: parsed.userId,
    workspaceKind: parsed.workspaceKind,
    agentId: parsed.agentId,
  };
}

export function splitRelativePath(relativePath: string): string[] {
  return relativePath ? relativePath.split("/") : [];
}

export function parentPath(relativePath: string): string {
  if (!relativePath) return "";
  const segments = splitRelativePath(relativePath);
  segments.pop();
  return segments.join("/");
}

function buildCtxUri(userId: string, workspaceKind: WorkspaceKind, agentId: string, relativePath: string): string {
  const root = workspaceKind === "defaultWorkspace"
    ? `ctx://${userId}/defaultWorkspace`
    : `ctx://${userId}/agentWorkspace/${agentId}`;
  return relativePath ? `${root}/${relativePath}` : root;
}

function normalizeRelativePath(segments: string[]): string {
  if (segments.length === 0) return "";
  return segments.map((segment) => validateSegment(segment, "path segment")).join("/");
}

function validateSegment(value: string, label: string): string {
  const cleaned = value.trim();
  if (!cleaned || cleaned === "." || cleaned === ".." || cleaned.includes("/")) {
    throw new ApiError(400, `invalid ${label}: ${value}`);
  }
  return cleaned;
}
