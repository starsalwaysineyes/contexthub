from __future__ import annotations

from typing import Any

import httpx

from contexthub.config import ProviderConfig


class EmbeddingClient:
    def __init__(self, config: ProviderConfig) -> None:
        self.config = config

    def status(self) -> dict[str, Any]:
        return {
            "enabled": self.config.enabled,
            "ready": self.config.enabled and bool(self.config.api_key),
            "model": self.config.model if self.config.enabled else None,
            "baseUrl": self.config.base_url if self.config.enabled else None,
        }

    def embed(self, inputs: list[str]) -> list[list[float]] | None:
        if not self.config.enabled or not self.config.api_key or not inputs:
            return None

        response = httpx.post(
            f"{self.config.base_url}/embeddings",
            headers={
                "Content-Type": "application/json",
                "Authorization": f"Bearer {self.config.api_key}",
            },
            json={"model": self.config.model, "input": inputs},
            timeout=30.0,
        )
        response.raise_for_status()
        payload = response.json()
        data = payload.get("data", [])
        return [item.get("embedding") for item in data]


class RerankClient:
    def __init__(self, config: ProviderConfig) -> None:
        self.config = config

    def status(self) -> dict[str, Any]:
        return {
            "enabled": self.config.enabled,
            "ready": self.config.enabled and bool(self.config.api_key),
            "model": self.config.model if self.config.enabled else None,
            "baseUrl": self.config.base_url if self.config.enabled else None,
        }

    def rank(self, query: str, documents: list[str]) -> list[dict[str, float]] | None:
        if not self.config.enabled or not self.config.api_key or not query or not documents:
            return None

        response = httpx.post(
            f"{self.config.base_url}/rerank",
            headers={
                "Content-Type": "application/json",
                "Authorization": f"Bearer {self.config.api_key}",
            },
            json={"model": self.config.model, "query": query, "documents": documents},
            timeout=30.0,
        )
        response.raise_for_status()
        payload = response.json()
        results = payload.get("results", [])
        return [
            {
                "index": int(item["index"]),
                "score": float(item.get("relevance_score", item.get("score", 0.0))),
            }
            for item in results
        ]
