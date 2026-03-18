from pathlib import Path

from fastapi.testclient import TestClient

from contexthub.app import create_app


def test_health_and_panel_stay_open_without_token(monkeypatch, tmp_path: Path) -> None:
    monkeypatch.setenv("CONTEXT_HUB_DATA_DIR", str(tmp_path / "data"))
    monkeypatch.setenv("CONTEXT_HUB_ADMIN_TOKEN", "secret-token")
    client = TestClient(create_app())

    health = client.get("/health")
    assert health.status_code == 200
    assert health.json()["ok"] is True

    panel = client.get("/panel")
    assert panel.status_code == 200
    assert "ctx panel" in panel.text
    assert "Run search" in panel.text

    root = client.get("/", follow_redirects=False)
    assert root.status_code == 307
    assert root.headers["location"] == "/panel"


def test_fs_endpoints_require_bearer_when_configured(monkeypatch, tmp_path: Path) -> None:
    monkeypatch.setenv("CONTEXT_HUB_DATA_DIR", str(tmp_path / "data"))
    monkeypatch.setenv("CONTEXT_HUB_ADMIN_TOKEN", "secret-token")
    client = TestClient(create_app())

    unauthorized = client.post(
        "/v1/workspaces/register",
        json={"userId": "alice", "workspaceKind": "defaultWorkspace", "agentId": None},
    )
    assert unauthorized.status_code == 401

    authorized = client.post(
        "/v1/workspaces/register",
        headers={"Authorization": "Bearer secret-token"},
        json={"userId": "alice", "workspaceKind": "defaultWorkspace", "agentId": None},
    )
    assert authorized.status_code == 200
    assert authorized.json()["uri"] == "ctx://alice/defaultWorkspace"

    reindex = client.post(
        "/v1/fs/reindex",
        headers={"Authorization": "Bearer secret-token"},
        json={"userId": "alice", "scopeUri": "ctx://alice/defaultWorkspace"},
    )
    assert reindex.status_code == 200
    assert reindex.json()["scopeUri"] == "ctx://alice/defaultWorkspace"
