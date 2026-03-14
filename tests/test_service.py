from __future__ import annotations

from pathlib import Path

from fastapi.testclient import TestClient

import contexthub.app as app_module
from contexthub.app import create_app
from contexthub.config import AbstractionConfig, AppConfig, AuthConfig, ProviderConfig, RetrievalConfig
from contexthub.schemas import (
    CommitSessionRequest,
    CreatePartitionRequest,
    CreateRecordRequest,
    CreateTenantRequest,
    GrepRequest,
    ImportResourceRequest,
    QueryRequest,
    RegisterAgentRequest,
    UpdateRecordRequest,
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


class FakeAbstractor:
    def status(self):
        return {
            "enabled": True,
            "ready": True,
            "provider": "litellm",
            "model": "fake-abstraction",
            "baseUrl": "https://example.com",
        }

    def derive(self, *, title, text, source_layer, emit_layers, prompt_preset, model=None):
        payload = {}
        if "l1" in emit_layers:
            payload["l1"] = {
                "title": f"{title} summary",
                "text": f"Detailed archive for: {text}",
                "manualSummary": "Detailed derived summary",
                "importance": 4,
                "tags": ["derived", "l1"],
            }
        if "l0" in emit_layers:
            payload["l0"] = {
                "title": f"{title} pointer",
                "text": "Short recall pointer",
                "manualSummary": "Short derived memory",
                "importance": 3,
                "tags": ["derived", "l0"],
            }
        return payload


class StringImportanceAbstractor(FakeAbstractor):
    def derive(self, *, title, text, source_layer, emit_layers, prompt_preset, model=None):
        payload = super().derive(
            title=title,
            text=text,
            source_layer=source_layer,
            emit_layers=emit_layers,
            prompt_preset=prompt_preset,
            model=model,
        )
        if "l1" in payload:
            payload["l1"]["importance"] = "medium"
        if "l0" in payload:
            payload["l0"]["importance"] = "4"
        return payload


def build_service(tmp_path: Path, abstractor=None) -> HubService:
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
        abstraction=AbstractionConfig(
            provider="litellm",
            base_url="https://example.com",
            api_key="demo",
            model="fake-abstraction",
            timeout_seconds=30.0,
        ),
    )
    return HubService(
        store=store,
        embedder=FakeEmbedder(),
        reranker=FakeReranker(),
        abstractor=abstractor or FakeAbstractor(),
        config=config,
    )


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


def test_read_record_lines_returns_numbered_slice(tmp_path: Path) -> None:
    service = build_service(tmp_path)
    tenant = service.create_tenant(CreateTenantRequest(slug="demo-lines", name="Demo Lines"))
    service.create_partition(CreatePartitionRequest(tenantId=tenant["id"], key="memory", name="Memory"))

    record = service.create_record(
        CreateRecordRequest(
            tenantId=tenant["id"],
            partitionKey="memory",
            type="resource",
            layer="l2",
            title="Log file",
            text="line 1\nline 2\nline 3\nline 4",
        )
    )

    page = service.read_record_lines(record["id"], line_start=2, line_limit=2)
    assert page["totalLines"] == 4
    assert page["returnedLines"] == 2
    assert page["hasMore"] is True
    assert page["items"][0]["lineNumber"] == 2
    assert page["items"][1]["text"] == "line 3"


def test_grep_records_returns_line_numbers(tmp_path: Path) -> None:
    service = build_service(tmp_path)
    tenant = service.create_tenant(CreateTenantRequest(slug="demo-grep", name="Demo Grep"))
    service.create_partition(CreatePartitionRequest(tenantId=tenant["id"], key="memory", name="Memory"))
    service.create_record(
        CreateRecordRequest(
            tenantId=tenant["id"],
            partitionKey="memory",
            type="resource",
            layer="l2",
            title="System log",
            text="alpha\nmatch here\nbeta match\ngamma",
        )
    )

    result = service.grep_records(
        GrepRequest(
            tenantId=tenant["id"],
            pattern="match",
            partitions=["memory"],
            layers=["l2"],
            limit=10,
        )
    )

    assert result["search"]["matchedRecords"] == 1
    assert result["search"]["returnedMatches"] == 2
    assert result["items"][0]["lineNumber"] == 2
    assert result["items"][1]["lineNumber"] == 3
    assert result["items"][0]["matchRanges"][0]["start"] == 0


def test_update_record_rechunks_and_changes_layer(tmp_path: Path) -> None:
    service = build_service(tmp_path)
    tenant = service.create_tenant(CreateTenantRequest(slug="demo-update", name="Demo Update"))
    service.create_partition(CreatePartitionRequest(tenantId=tenant["id"], key="memory", name="Memory"))

    record = service.create_record(
        CreateRecordRequest(
            tenantId=tenant["id"],
            partitionKey="memory",
            type="memory",
            layer="l0",
            title="Daily note",
            text="short pointer only",
        )
    )

    updated = service.update_record(
        record["id"],
        UpdateRecordRequest(
            layer="l1",
            title="Daily note expanded",
            text="expanded archive summary with richer agent memory details",
            manualSummary="expanded summary",
            importance=4,
            pinned=True,
            tags=["updated", "archive"],
        ),
    )

    assert updated["layer"] == "l1"
    assert updated["title"] == "Daily note expanded"
    assert updated["manualSummary"] == "expanded summary"
    assert updated["importance"] == 4.0
    assert updated["pinned"] is True

    result = service.query(
        QueryRequest(
            tenantId=tenant["id"],
            query="archive summary richer agent memory",
            partitions=["memory"],
            layers=["l1"],
        )
    )
    assert len(result["items"]) == 1
    assert result["items"][0]["recordId"] == record["id"]


def test_import_resource_can_derive_l1_and_l0(tmp_path: Path) -> None:
    service = build_service(tmp_path)
    tenant = service.create_tenant(CreateTenantRequest(slug="demo", name="Demo"))
    service.create_partition(CreatePartitionRequest(tenantId=tenant["id"], key="project-openclaw", name="Project OpenClaw"))

    result = service.import_resource(
        ImportResourceRequest(
            tenantId=tenant["id"],
            partitionKey="project-openclaw",
            type="resource",
            targetLayer="l2",
            title="Meeting transcript",
            content={"kind": "inline_text", "text": "We decided to keep manual curation first."},
            derive={
                "enabled": True,
                "mode": "sync",
                "emitLayers": ["l1", "l0"],
                "provider": "litellm",
                "promptPreset": "archive_and_memory",
            },
            idempotencyKey="meeting-transcript-import",
        )
    )

    assert result["record"]["layer"] == "l2"
    assert result["derivation"]["status"] == "completed"
    assert result["derivation"]["job"]["status"] == "completed"
    assert len(result["derivation"]["records"]) == 2
    assert len(result["derivation"]["links"]) == 2
    layers = {record["layer"] for record in result["derivation"]["records"]}
    assert layers == {"l1", "l0"}

    fetched_job = service.get_derivation_job(result["derivation"]["job"]["id"])
    assert fetched_job["status"] == "completed"
    fetched_links = service.list_record_links(result["record"]["id"])
    assert len(fetched_links) == 2

    replay = service.import_resource(
        ImportResourceRequest(
            tenantId=tenant["id"],
            partitionKey="project-openclaw",
            type="resource",
            targetLayer="l2",
            title="Meeting transcript",
            content={"kind": "inline_text", "text": "We decided to keep manual curation first."},
            derive={
                "enabled": True,
                "mode": "sync",
                "emitLayers": ["l1", "l0"],
                "provider": "litellm",
                "promptPreset": "archive_and_memory",
            },
            idempotencyKey="meeting-transcript-import",
        )
    )
    assert replay["record"]["id"] == result["record"]["id"]
    replay_links = service.list_record_links(result["record"]["id"])
    assert len(replay_links) == 2
    assert all(link["metadata"]["jobId"] == replay["derivation"]["job"]["id"] for link in replay_links)


def test_import_resource_accepts_string_importance_from_derive(tmp_path: Path) -> None:
    service = build_service(tmp_path, abstractor=StringImportanceAbstractor())
    tenant = service.create_tenant(CreateTenantRequest(slug="demo-importance", name="Demo Importance"))
    service.create_partition(CreatePartitionRequest(tenantId=tenant["id"], key="memory", name="Memory"))

    result = service.import_resource(
        ImportResourceRequest(
            tenantId=tenant["id"],
            partitionKey="memory",
            type="resource",
            targetLayer="l2",
            title="Importance test",
            content={"kind": "inline_text", "text": "importance coercion"},
            derive={
                "enabled": True,
                "mode": "sync",
                "emitLayers": ["l1", "l0"],
                "provider": "litellm",
            },
        )
    )

    by_layer = {record["layer"]: record for record in result["derivation"]["records"]}
    assert by_layer["l1"]["importance"] == 3.0
    assert by_layer["l0"]["importance"] == 4.0


def test_app_can_read_lines_and_grep_record_text(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setenv("CONTEXT_HUB_DATABASE_PATH", str(tmp_path / "read-api.db"))
    monkeypatch.setenv("CONTEXT_HUB_ENABLE_EMBEDDINGS", "false")
    monkeypatch.setenv("CONTEXT_HUB_ENABLE_RERANK", "false")
    monkeypatch.setenv("CONTEXT_HUB_ENABLE_AUTH", "true")
    monkeypatch.setenv("CONTEXT_HUB_ADMIN_TOKEN", "admin-secret")
    app = create_app()
    client = TestClient(app)
    admin_headers = {"Authorization": "Bearer admin-secret"}

    tenant = client.post("/v1/tenants", headers=admin_headers, json={"slug": "demo-readapi", "name": "Demo Read API"}).json()
    client.post(
        "/v1/partitions",
        headers=admin_headers,
        json={"tenantId": tenant["id"], "key": "memory", "name": "Memory"},
    ).raise_for_status()
    record = client.post(
        "/v1/records",
        headers=admin_headers,
        json={
            "tenantId": tenant["id"],
            "partitionKey": "memory",
            "type": "resource",
            "layer": "l2",
            "title": "Readme",
            "text": "alpha\nbeta hit\ngamma hit",
        },
    ).json()

    lines = client.get(f"/v1/records/{record['id']}/lines?from_line=2&limit=1", headers=admin_headers)
    assert lines.status_code == 200
    assert lines.json()["items"][0]["lineNumber"] == 2

    grep = client.post(
        "/v1/records/grep",
        headers=admin_headers,
        json={"tenantId": tenant["id"], "pattern": "hit", "partitions": ["memory"], "layers": ["l2"]},
    )
    assert grep.status_code == 200
    assert grep.json()["items"][0]["lineNumber"] == 2


def test_app_can_get_and_update_record(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setenv("CONTEXT_HUB_DATABASE_PATH", str(tmp_path / "record-api.db"))
    monkeypatch.setenv("CONTEXT_HUB_ENABLE_EMBEDDINGS", "false")
    monkeypatch.setenv("CONTEXT_HUB_ENABLE_RERANK", "false")
    monkeypatch.setenv("CONTEXT_HUB_ENABLE_AUTH", "true")
    monkeypatch.setenv("CONTEXT_HUB_ADMIN_TOKEN", "admin-secret")
    app = create_app()
    client = TestClient(app)
    admin_headers = {"Authorization": "Bearer admin-secret"}

    tenant = client.post("/v1/tenants", headers=admin_headers, json={"slug": "demo-record", "name": "Demo Record"}).json()
    client.post(
        "/v1/partitions",
        headers=admin_headers,
        json={"tenantId": tenant["id"], "key": "memory", "name": "Memory"},
    ).raise_for_status()
    created = client.post(
        "/v1/records",
        headers=admin_headers,
        json={
            "tenantId": tenant["id"],
            "partitionKey": "memory",
            "type": "memory",
            "layer": "l0",
            "title": "Original",
            "text": "original raw text",
        },
    ).json()

    fetched = client.get(f"/v1/records/{created['id']}", headers=admin_headers)
    assert fetched.status_code == 200
    assert fetched.json()["title"] == "Original"

    patched = client.patch(
        f"/v1/records/{created['id']}",
        headers=admin_headers,
        json={"title": "Updated", "text": "updated raw text", "layer": "l1"},
    )
    assert patched.status_code == 200
    assert patched.json()["title"] == "Updated"
    assert patched.json()["layer"] == "l1"


def test_app_can_run_async_derivation_job_and_fetch_links(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setenv("CONTEXT_HUB_DATABASE_PATH", str(tmp_path / "derive-api.db"))
    monkeypatch.setenv("CONTEXT_HUB_ENABLE_EMBEDDINGS", "false")
    monkeypatch.setenv("CONTEXT_HUB_ENABLE_RERANK", "false")
    monkeypatch.setenv("CONTEXT_HUB_ENABLE_AUTH", "true")
    monkeypatch.setenv("CONTEXT_HUB_ADMIN_TOKEN", "admin-secret")
    monkeypatch.setattr(app_module, "LiteLLMAbstractionClient", lambda config: FakeAbstractor())
    app = create_app()
    client = TestClient(app)
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

    response = client.post(
        "/v1/resources/import",
        headers=admin_headers,
        json={
            "tenantId": tenant["id"],
            "partitionKey": "memory",
            "targetLayer": "l2",
            "title": "Raw note",
            "content": {"kind": "inline_text", "text": "raw body"},
            "derive": {"enabled": True, "mode": "async", "emitLayers": ["l1", "l0"], "provider": "litellm"},
        },
    )
    assert response.status_code == 201
    body = response.json()
    assert body["derivation"]["status"] == "queued"
    assert body["derivation"]["effectiveMode"] == "async"

    job = client.get(f"/v1/derivation-jobs/{body['derivation']['job']['id']}", headers=admin_headers)
    assert job.status_code == 200
    assert job.json()["status"] == "completed"
    assert job.json()["effectiveMode"] == "async"
    assert job.json()["metadata"]["attemptCount"] == 1

    links = client.get(f"/v1/records/{body['record']['id']}/links", headers=admin_headers)
    assert links.status_code == 200
    assert len(links.json()["items"]) == 2


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

    import_response = client.post(
        "/v1/resources/import",
        headers=principal_headers,
        json={
            "tenantId": tenant["id"],
            "partitionKey": "memory",
            "targetLayer": "l2",
            "title": "Raw note",
            "content": {"kind": "inline_text", "text": "raw body"},
            "derive": {"enabled": False},
        },
    )
    assert import_response.status_code == 201

    query_response = client.post(
        "/v1/query",
        headers=principal_headers,
        json={"tenantId": tenant["id"], "query": "single-instance", "partitions": ["memory"]},
    )
    assert query_response.status_code == 200
    assert len(query_response.json()["items"]) >= 1

    denied_query = client.post(
        "/v1/query",
        headers=principal_headers,
        json={"tenantId": tenant["id"], "query": "secret", "partitions": ["private"]},
    )
    assert denied_query.status_code == 403
