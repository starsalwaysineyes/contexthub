from __future__ import annotations

import json
from typing import Any

import httpx

from contexthub.config import AbstractionConfig, ProviderConfig


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


class LiteLLMAbstractionClient:
    def __init__(self, config: AbstractionConfig) -> None:
        self.config = config

    def status(self) -> dict[str, Any]:
        enabled = bool(self.config.base_url)
        ready = enabled and bool(self.config.model)
        return {
            "enabled": enabled,
            "ready": ready,
            "provider": self.config.provider,
            "model": self.config.model if ready else None,
            "baseUrl": self.config.base_url if enabled else None,
        }

    def derive(
        self,
        *,
        title: str,
        text: str,
        source_layer: str,
        emit_layers: list[str],
        prompt_preset: str,
        model: str | None = None,
    ) -> dict[str, Any]:
        if not self.config.base_url:
            raise RuntimeError("Abstraction base URL is not configured")

        target_model = model or self.config.model
        if not target_model:
            raise RuntimeError("Abstraction model is not configured")

        prompt = self._build_prompt(
            title=title,
            text=text,
            source_layer=source_layer,
            emit_layers=emit_layers,
            prompt_preset=prompt_preset,
        )

        headers = {"Content-Type": "application/json"}
        if self.config.api_key:
            headers["Authorization"] = f"Bearer {self.config.api_key}"

        response = httpx.post(
            f"{self.config.base_url}/chat/completions",
            headers=headers,
            json={
                "model": target_model,
                "messages": [
                    {"role": "system", "content": "You generate JSON only. No markdown fences, no commentary."},
                    {"role": "user", "content": prompt},
                ],
                "temperature": 0.2,
                "response_format": {"type": "json_object"},
            },
            timeout=self.config.timeout_seconds,
        )
        response.raise_for_status()
        payload = response.json()
        content = payload["choices"][0]["message"]["content"]
        return self._parse_json_content(content)

    def _build_prompt(
        self,
        *,
        title: str,
        text: str,
        source_layer: str,
        emit_layers: list[str],
        prompt_preset: str,
    ) -> str:
        return (
            "Return one JSON object with optional keys l1 and l0. "
            "Each key must contain an object with title, text, manualSummary, importance, tags. "
            "If a layer is not requested, omit it. "
            f"Source title: {title}\n"
            f"Source layer: {source_layer}\n"
            f"Requested layers: {', '.join(emit_layers)}\n"
            f"Preset: {prompt_preset}\n"
            f"Source text:\n{text}"
        )

    def _parse_json_content(self, content: str) -> dict[str, Any]:
        raw = content.strip()
        if raw.startswith("```"):
            raw = raw.strip("`")
            if raw.startswith("json"):
                raw = raw[4:].lstrip()
        return json.loads(raw)
