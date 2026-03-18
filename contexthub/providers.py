from __future__ import annotations

from typing import Any

import httpx

from contexthub.config import ProviderSettings


class EmbeddingClient:
    def __init__(self, settings: ProviderSettings) -> None:
        self.settings = settings

    def status(self) -> dict[str, Any]:
        ready = self.settings.enabled and bool(self.settings.api_key) and bool(self.settings.model)
        return {
            "enabled": self.settings.enabled,
            "ready": ready,
            "baseUrl": self.settings.base_url if self.settings.enabled else None,
            "model": self.settings.model if self.settings.enabled else None,
        }

    def embed(self, inputs: list[str]) -> list[list[float]] | None:
        if not inputs or not self.status()["ready"]:
            return None
        response = httpx.post(
            f"{self.settings.base_url}/embeddings",
            headers={
                "Content-Type": "application/json",
                "Authorization": f"Bearer {self.settings.api_key}",
            },
            json={"model": self.settings.model, "input": inputs},
            timeout=30.0,
        )
        response.raise_for_status()
        payload = response.json()
        return [item.get("embedding", []) for item in payload.get("data", [])]


class RerankClient:
    def __init__(self, settings: ProviderSettings) -> None:
        self.settings = settings

    def status(self) -> dict[str, Any]:
        ready = self.settings.enabled and bool(self.settings.api_key) and bool(self.settings.model)
        return {
            "enabled": self.settings.enabled,
            "ready": ready,
            "baseUrl": self.settings.base_url if self.settings.enabled else None,
            "model": self.settings.model if self.settings.enabled else None,
        }

    def rank(self, query: str, documents: list[str]) -> list[dict[str, float]] | None:
        if not query or not documents or not self.status()["ready"]:
            return None
        response = httpx.post(
            f"{self.settings.base_url}/rerank",
            headers={
                "Content-Type": "application/json",
                "Authorization": f"Bearer {self.settings.api_key}",
            },
            json={"model": self.settings.model, "query": query, "documents": documents},
            timeout=30.0,
        )
        response.raise_for_status()
        payload = response.json()
        return [
            {
                "index": int(item["index"]),
                "score": float(item.get("relevance_score", item.get("score", 0.0))),
            }
            for item in payload.get("results", [])
        ]
