from __future__ import annotations

from pathlib import Path

from fastapi.testclient import TestClient

from contexthub.app import create_app
from contexthub.config import AppConfig, AuthConfig, ProviderConfig, RetrievalConfig
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
        auth=AuthConfig(enabled=False, admin_token=""),
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
            layer="l0",
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
    assert result["items"][0]["layer"] == "l0"
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
                    "layer": "l1",
                    "text": "Prefer manual curation first and controlled cross-partition retrieval.",
                    "importance": 4,
                }
            ],
        )
    )

    assert len(commit["createdMemories"]) == 1
    assert commit["createdMemories"][0]["layer"] == "l1"

    result = service.query(
        QueryRequest(
            tenantId=tenant["id"],
            query="cross-partition retrieval",
            partitions=[partition["key"]],
        )
    )

    assert len(result["items"]) == 1
    assert result["items"][0]["title"] == "Architecture direction"


def test_query_can_filter_by_layer(tmp_path: Path) -> None:
    service = build_service(tmp_path)
    tenant = service.create_tenant(CreateTenantRequest(slug="demo", name="Demo"))
    service.create_partition(CreatePartitionRequest(tenantId=tenant["id"], key="memory", name="Memory"))
    service.create_record(
        CreateRecordRequest(
            tenantId=tenant["id"],
            partitionKey="memory",
            type="memory",
            layer="l0",
            title="Daily note",
            text="Short memory pointer for today.",
        )
    )
    service.create_record(
        CreateRecordRequest(
            tenantId=tenant["id"],
            partitionKey="memory",
            type="resource",
            layer="l2",
            title="Raw transcript",
            text="Full transcript with all raw details.",
        )
    )

    result = service.query(
        QueryRequest(
            tenantId=tenant["id"],
            query="raw details",
            partitions=["memory"],
            layers=["l2"],
        )
    )

    assert len(result["items"]) == 1
    assert result["items"][0]["layer"] == "l2"
    assert result["items"][0]["title"] == "Raw transcript"


def test_health_route(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setenv("CONTEXT_HUB_DATABASE_PATH", str(tmp_path / "api.db"))
    monkeypatch.setenv("CONTEXT_HUB_ENABLE_EMBEDDINGS", "false")
    monkeypatch.setenv("CONTEXT_HUB_ENABLE_RERANK", "false")
    monkeypatch.setenv("CONTEXT_HUB_ENABLE_AUTH", "false")
    app = create_app()
    client = TestClient(app)

    response = client.get("/health")

    assert response.status_code == 200
    body = response.json()
    assert body["ok"] is True
    assert body["counts"]["tenants"] == 0


def test_auth_and_partition_acl_flow(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setenv("CONTEXT_HUB_DATABASE_PATH", str(tmp_path / "auth.db"))
    monkeypatch.setenv("CONTEXT_HUB_ENABLE_EMBEDDINGS", "false")
    monkeypatch.setenv("CONTEXT_HUB_ENABLE_RERANK", "false")
    monkeypatch.setenv("CONTEXT_HUB_ENABLE_AUTH", "true")
    monkeypatch.setenv("CONTEXT_HUB_ADMIN_TOKEN", "admin-secret")
    app = create_app()
    client = TestClient(app)

    assert client.post("/v1/tenants", json={"slug": "demo", "name": "Demo"}).status_code == 401

    admin_headers = {"Authorization": "Bearer admin-secret"}
    tenant = client.post(
        "/v1/tenants",
        headers=admin_headers,
        json={"slug": "demo", "name": "Demo"},
    ).json()

    client.post(
        "/v1/partitions",
        headers=admin_headers,
        json={"tenantId": tenant["id"], "key": "memory", "name": "Memory"},
    ).raise_for_status()
    client.post(
        "/v1/partitions",
        headers=admin_headers,
        json={"tenantId": tenant["id"], "key": "private", "name": "Private"},
    ).raise_for_status()

    principal = client.post(
        "/v1/principals",
        headers=admin_headers,
        json={"tenantId": tenant["id"], "name": "OpenClaw Main", "kind": "service"},
    ).json()
    principal_headers = {"Authorization": f"Bearer {principal['token']}"}

    client.post(
        f"/v1/principals/{principal['id']}/acl",
        headers=admin_headers,
        json={
            "partitionKey": "memory",
            "canRead": True,
            "canWrite": True,
            "allowedLayers": ["l0", "l1"],
        },
    ).raise_for_status()

    me = client.get("/v1/auth/me", headers=principal_headers)
    assert me.status_code == 200
    assert me.json()["principal"]["name"] == "OpenClaw Main"

    write_response = client.post(
        "/v1/records",
        headers=principal_headers,
        json={
            "tenantId": tenant["id"],
            "partitionKey": "memory",
            "type": "memory",
            "layer": "l0",
            "title": "Decision",
            "text": "Prefer single-instance multi-tenant.",
        },
    )
    assert write_response.status_code == 201

    denied_write = client.post(
        "/v1/records",
        headers=principal_headers,
        json={
            "tenantId": tenant["id"],
            "partitionKey": "private",
            "type": "memory",
            "layer": "l0",
            "title": "Secret",
            "text": "Should not write here.",
        },
    )
    assert denied_write.status_code == 403

    query_response = client.post(
        "/v1/query",
        headers=principal_headers,
        json={"tenantId": tenant["id"], "query": "single-instance", "partitions": ["memory"]},
    )
    assert query_response.status_code == 200
    assert len(query_response.json()["items"]) == 1

    denied_query = client.post(
        "/v1/query",
        headers=principal_headers,
        json={"tenantId": tenant["id"], "query": "secret", "partitions": ["private"]},
    )
    assert denied_query.status_code == 403
