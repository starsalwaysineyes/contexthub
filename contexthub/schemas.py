from __future__ import annotations

from pydantic import BaseModel, Field


class RegisterWorkspaceRequest(BaseModel):
    user_id: str = Field(alias="userId")
    workspace_kind: str = Field(alias="workspaceKind")
    agent_id: str | None = Field(default=None, alias="agentId")


class MkdirRequest(BaseModel):
    uri: str
    parents: bool = True


class RemoveRequest(BaseModel):
    uri: str
    recursive: bool = False


class WriteFileRequest(BaseModel):
    uri: str
    text: str
    create_parents: bool = Field(default=True, alias="createParents")
    overwrite: bool = True


class EditFileRequest(BaseModel):
    uri: str
    match_text: str = Field(alias="matchText")
    replace_text: str = Field(alias="replaceText")
    replace_all: bool = Field(default=False, alias="replaceAll")


class ApplyPatchRequest(BaseModel):
    uri: str
    patch: str


class MoveRequest(BaseModel):
    source_uri: str = Field(alias="sourceUri")
    destination_uri: str = Field(alias="destinationUri")
    create_parents: bool = Field(default=True, alias="createParents")
    overwrite: bool = False


class CopyRequest(BaseModel):
    source_uri: str = Field(alias="sourceUri")
    destination_uri: str = Field(alias="destinationUri")
    create_parents: bool = Field(default=True, alias="createParents")
    overwrite: bool = False


class ReindexRequest(BaseModel):
    user_id: str = Field(alias="userId")
    scope_uri: str | None = Field(default=None, alias="scopeUri")


class SearchRequest(BaseModel):
    user_id: str = Field(alias="userId")
    query: str
    scope_uri: str | None = Field(default=None, alias="scopeUri")
    mode: str = "auto"
    expansions: list[str] = Field(default_factory=list)
    glob: str | None = None
    path_prefix: str | None = Field(default=None, alias="pathPrefix")
    workspace_mode: str = Field(default="default-only", alias="workspaceMode")
    doc_type_boosts: dict[str, float] | None = Field(default=None, alias="docTypeBoosts")
    rerank: bool | None = None
    explain: bool = True
    limit: int = 20


class GlobRequest(BaseModel):
    user_id: str = Field(alias="userId")
    pattern: str
    scope_uri: str | None = Field(default=None, alias="scopeUri")
    limit: int = 100


class GrepRequest(BaseModel):
    user_id: str = Field(alias="userId")
    pattern: str
    scope_uri: str | None = Field(default=None, alias="scopeUri")
    limit: int = 100
    case_sensitive: bool = Field(default=False, alias="caseSensitive")
    glob: str | None = None


class RgRequest(BaseModel):
    user_id: str = Field(alias="userId")
    pattern: str
    scope_uri: str | None = Field(default=None, alias="scopeUri")
    limit: int = 100
    case_sensitive: bool = Field(default=False, alias="caseSensitive")
    glob: str | None = None


class LsEntry(BaseModel):
    name: str
    uri: str
    kind: str


class LsResponse(BaseModel):
    uri: str
    entries: list[LsEntry]


class TreeNode(BaseModel):
    name: str
    uri: str
    kind: str
    children: list["TreeNode"] = Field(default_factory=list)


class StatResponse(BaseModel):
    uri: str
    name: str
    kind: str
    size_bytes: int | None = Field(default=None, alias="sizeBytes")
    line_count: int | None = Field(default=None, alias="lineCount")
    child_count: int | None = Field(default=None, alias="childCount")


class ReadFileResponse(BaseModel):
    uri: str
    text: str
    line_count: int = Field(alias="lineCount")


class SearchPlan(BaseModel):
    source: str
    lexical: bool
    semantic: bool
    rerank: bool
    explain: bool
    candidate_count: int = Field(alias="candidateCount")
    fallback: str | None = None


class SearchHit(BaseModel):
    uri: str
    title: str
    kind: str
    doc_type: str = Field(alias="docType")
    workspace_kind: str = Field(alias="workspaceKind")
    agent_id: str | None = Field(default=None, alias="agentId")
    score: float
    snippet: str
    line_number: int | None = Field(default=None, alias="lineNumber")
    reasons: list[str] = Field(default_factory=list)


class SearchResponse(BaseModel):
    query: str
    normalized_query: str = Field(alias="normalizedQuery")
    scope_uri: str | None = Field(alias="scopeUri")
    workspace_mode: str = Field(alias="workspaceMode")
    mode: str
    rewrites: list[str]
    plan: SearchPlan
    hits: list[SearchHit]


class ReindexResponse(BaseModel):
    user_id: str = Field(alias="userId")
    scope_uri: str = Field(alias="scopeUri")
    indexed: int
    unchanged: int
    removed: int
    skipped: int


class GlobHit(BaseModel):
    uri: str
    kind: str


class GlobResponse(BaseModel):
    pattern: str
    scope_uri: str | None = Field(alias="scopeUri")
    hits: list[GlobHit]


class GrepResponse(BaseModel):
    pattern: str
    scope_uri: str | None = Field(alias="scopeUri")
    hits: list[dict]


TreeNode.model_rebuild()
