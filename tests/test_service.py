from __future__ import annotations

from pathlib import Path

from fastapi.testclient import TestClient

from contexthub.app import create_app
from contexthub.config import AppConfig, ProviderConfig, RetrievalConfig
from contexthub.schemas import (
    CommitSessionRequest,
    CreatePartitionRequest,
    CreateRecordRequest,
    CreateTenantRequest,
    QueryRequest,
    RegisterAgentRequest,
)
from contexthub.service import HubService
from contexthub.store import SQLiteStore


class FakeEmbedder:
    def status(self):
        return {"enabled": True, "ready": True, "model": "fake"}

    def embed(self, inputs):
        vectors = []
        for item in inputs:
            lowered = item.lower()
            vectors.append([1.0 if "memory" in lowered else 0.0, 1.0 if "agent" in lowered else 0.0])
        return vectors


class FakeReranker:
    def status(self):
        return {"enabled": True, "ready": True, "model": "fake-rerank"}

    def rank(self, query, documents):
        lowered_query = query.lower()
        return [
            {"index": index, "score": 1.0 if lowered_query in document.lower() else 0.2}
            for index, document in enumerate(documents)
        ]


def build_service(tmp_path: Path) -> HubService:
    database_path = tmp_path / "contexthub.db"
    store = SQLiteStore(database_path)
    store.init()
    config = AppConfig(
        port=4040,
        data_dir=tmp_path,
        database_path=database_path,
        retrieval=RetrievalConfig(),
        embedding=ProviderConfig(enabled=True, base_url="https://example.com", api_key="demo", model="fake"),
        rerank=ProviderConfig(enabled=True, base_url="https://example.com", api_key="demo", model="fake"),
    )
    return HubService(store=store, embedder=FakeEmbedder(), reranker=FakeReranker(), config=config)


def test_query_returns_relevant_record(tmp_path: Path) -> None:
    service = build_service(tmp_path)
    tenant = service.create_tenant(CreateTenantRequest(slug="demo", name="Demo"))
    service.create_partition(CreatePartitionRequest(tenantId=tenant["id"], key="memory", name="Memory"))
    service.create_record(
        CreateRecordRequest(
            tenantId=tenant["id"],
            partitionKey="memory",
            type="memory",
            title="Memory retrieval",
            text="ContextHub should help every agent reuse memory safely.",
            importance=5,
            pinned=True,
        )
    )

    result = service.query(
        QueryRequest(
            tenantId=tenant["id"],
            query="memory for agent",
            partitions=["memory"],
            rerank=True,
        )
    )

    assert len(result["items"]) == 1
    assert result["items"][0]["title"] == "Memory retrieval"
    assert result["retrieval"]["usedEmbeddings"] is True


def test_commit_session_materializes_memory(tmp_path: Path) -> None:
    service = build_service(tmp_path)
    tenant = service.create_tenant(CreateTenantRequest(slug="demo", name="Demo"))
    partition = service.create_partition(
        CreatePartitionRequest(tenantId=tenant["id"], key="project-openclaw", name="Project OpenClaw")
    )
    agent = service.register_agent(RegisterAgentRequest(tenantId=tenant["id"], name="OpenClaw"))

    commit = service.commit_session(
        CommitSessionRequest(
            tenantId=tenant["id"],
            partitionKey=partition["key"],
            agentId=agent["id"],
            summary="Agreed on multi-agent context backend.",
            messages=[{"role": "user", "content": "Build a context backend."}],
            memoryEntries=[
                {
                    "title": "Architecture direction",
                    "text": "Prefer manual curation first and controlled cross-partition retrieval.",
                    "importance": 4,
                }
            ],
        )
    )

    assert len(commit["createdMemories"]) == 1

    result = service.query(
        QueryRequest(
            tenantId=tenant["id"],
            query="cross-partition retrieval",
            partitions=[partition["key"]],
        )
    )

    assert len(result["items"]) == 1
    assert result["items"][0]["title"] == "Architecture direction"


def test_health_route(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setenv("CONTEXT_HUB_DATABASE_PATH", str(tmp_path / "api.db"))
    monkeypatch.setenv("CONTEXT_HUB_ENABLE_EMBEDDINGS", "false")
    monkeypatch.setenv("CONTEXT_HUB_ENABLE_RERANK", "false")
    app = create_app()
    client = TestClient(app)

    response = client.get("/health")

    assert response.status_code == 200
    body = response.json()
    assert body["ok"] is True
    assert body["counts"]["tenants"] == 0
