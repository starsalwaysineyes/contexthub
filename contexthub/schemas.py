from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, Field

RecordLayer = Literal["l0", "l1", "l2"]


class CreateTenantRequest(BaseModel):
    slug: str
    name: str
    description: str = ""


class CreatePartitionRequest(BaseModel):
    tenant_id: str = Field(alias="tenantId")
    key: str
    name: str
    kind: str = "context"
    description: str = ""
    allow_cross_query_from: list[str] = Field(default_factory=list, alias="allowCrossQueryFrom")


class RegisterAgentRequest(BaseModel):
    tenant_id: str = Field(alias="tenantId")
    name: str
    kind: str = "generic"
    metadata: dict[str, Any] = Field(default_factory=dict)


class CreatePrincipalRequest(BaseModel):
    tenant_id: str = Field(alias="tenantId")
    name: str
    kind: str = "service"
    metadata: dict[str, Any] = Field(default_factory=dict)


class UpsertPrincipalAclRequest(BaseModel):
    partition_key: str = Field(alias="partitionKey")
    can_read: bool = Field(default=True, alias="canRead")
    can_write: bool = Field(default=False, alias="canWrite")
    allowed_layers: list[RecordLayer] = Field(default_factory=lambda: ["l0", "l1", "l2"], alias="allowedLayers")


class CreateRecordRequest(BaseModel):
    tenant_id: str = Field(alias="tenantId")
    partition_key: str = Field(alias="partitionKey")
    type: str
    layer: RecordLayer = "l1"
    title: str
    text: str
    source: dict[str, Any] | None = None
    tags: list[str] = Field(default_factory=list)
    metadata: dict[str, Any] = Field(default_factory=dict)
    manual_summary: str = Field(default="", alias="manualSummary")
    importance: float = 0.0
    pinned: bool = False
    idempotency_key: str | None = Field(default=None, alias="idempotencyKey")


class QueryRequest(BaseModel):
    tenant_id: str = Field(alias="tenantId")
    query: str
    partitions: list[str] = Field(default_factory=list)
    types: list[str] = Field(default_factory=list)
    layers: list[RecordLayer] = Field(default_factory=list)
    limit: int | None = None
    rerank: bool | None = None


class MemoryEntry(BaseModel):
    type: str = "memory"
    layer: RecordLayer = "l0"
    title: str
    text: str
    manual_summary: str = Field(default="", alias="manualSummary")
    tags: list[str] = Field(default_factory=list)
    metadata: dict[str, Any] = Field(default_factory=dict)
    importance: float = 3.0
    pinned: bool = False
    idempotency_key: str | None = Field(default=None, alias="idempotencyKey")


class SessionMessage(BaseModel):
    role: str
    content: str


class CommitSessionRequest(BaseModel):
    tenant_id: str = Field(alias="tenantId")
    partition_key: str = Field(alias="partitionKey")
    agent_id: str | None = Field(default=None, alias="agentId")
    session_id: str | None = Field(default=None, alias="sessionId")
    summary: str = ""
    metadata: dict[str, Any] = Field(default_factory=dict)
    messages: list[SessionMessage] = Field(default_factory=list)
    memory_entries: list[MemoryEntry] = Field(default_factory=list, alias="memoryEntries")


class HealthResponse(BaseModel):
    ok: bool
    counts: dict[str, int]
    providers: dict[str, dict[str, Any]]
