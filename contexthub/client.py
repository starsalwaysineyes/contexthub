from __future__ import annotations

from typing import Any

import httpx


class ContextHubClient:
    def __init__(self, base_url: str, token: str | None = None, headers: dict[str, str] | None = None) -> None:
        self.base_url = base_url.rstrip("/")
        self.token = token
        self.headers = headers or {}

    def health(self) -> dict[str, Any]:
        return self._request("GET", "/health")

    def auth_me(self) -> dict[str, Any]:
        return self._request("GET", "/v1/auth/me")

    def create_tenant(self, payload: dict[str, Any]) -> dict[str, Any]:
        return self._request("POST", "/v1/tenants", payload)

    def create_partition(self, payload: dict[str, Any]) -> dict[str, Any]:
        return self._request("POST", "/v1/partitions", payload)

    def register_agent(self, payload: dict[str, Any]) -> dict[str, Any]:
        return self._request("POST", "/v1/agents", payload)

    def create_principal(self, payload: dict[str, Any]) -> dict[str, Any]:
        return self._request("POST", "/v1/principals", payload)

    def upsert_principal_acl(self, principal_id: str, payload: dict[str, Any]) -> dict[str, Any]:
        return self._request("POST", f"/v1/principals/{principal_id}/acl", payload)

    def create_record(self, payload: dict[str, Any]) -> dict[str, Any]:
        return self._request("POST", "/v1/records", payload)

    def import_resource(self, payload: dict[str, Any]) -> dict[str, Any]:
        return self._request("POST", "/v1/resources/import", payload)

    def query(self, payload: dict[str, Any]) -> dict[str, Any]:
        return self._request("POST", "/v1/query", payload)

    def commit_session(self, payload: dict[str, Any]) -> dict[str, Any]:
        return self._request("POST", "/v1/sessions/commit", payload)

    def _request(self, method: str, path: str, payload: dict[str, Any] | None = None) -> dict[str, Any]:
        headers = {"Accept": "application/json", **self.headers}
        if self.token:
            headers["Authorization"] = f"Bearer {self.token}"

        response = httpx.request(
            method,
            f"{self.base_url}{path}",
            headers=headers,
            json=payload,
            timeout=30.0,
        )
        response.raise_for_status()
        return response.json()
