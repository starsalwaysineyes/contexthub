from __future__ import annotations

from pathlib import Path
from typing import Any


def parse_csv_list(value: str | None) -> list[str]:
    if not value:
        return []
    return [item.strip() for item in value.split(",") if item.strip()]


def read_optional_text(*, text: str | None = None, file_path: str | None = None) -> str | None:
    if text is not None:
        return text
    if file_path is None:
        return None
    return Path(file_path).expanduser().read_text(encoding="utf-8")


def build_query_payload(
    *,
    tenant_id: str,
    query: str,
    partitions: list[str] | None = None,
    layers: list[str] | None = None,
    limit: int = 5,
    rerank: bool = False,
) -> dict[str, Any]:
    return {
        "tenantId": tenant_id,
        "query": query,
        "partitions": partitions or [],
        "layers": layers or ["l0", "l1"],
        "limit": limit,
        "rerank": rerank,
    }


def build_memory_entry(
    *,
    title: str,
    text: str,
    layer: str = "l0",
    importance: float = 3.0,
    tags: list[str] | None = None,
) -> dict[str, Any]:
    return {
        "title": title,
        "text": text,
        "layer": layer,
        "importance": importance,
        "tags": tags or [],
    }


def build_commit_payload(
    *,
    tenant_id: str,
    partition_key: str,
    summary: str,
    agent_id: str | None = None,
    messages: list[dict[str, str]] | None = None,
    memory_entries: list[dict[str, Any]] | None = None,
    metadata: dict[str, Any] | None = None,
) -> dict[str, Any]:
    payload = {
        "tenantId": tenant_id,
        "partitionKey": partition_key,
        "summary": summary,
        "messages": messages or [],
        "memoryEntries": memory_entries or [],
        "metadata": metadata or {},
    }
    if agent_id:
        payload["agentId"] = agent_id
    return payload
