from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path


@dataclass(slots=True)
class RetrievalConfig:
    default_limit: int = 8
    candidate_limit: int = 40
    rerank_top_n: int = 8
    lexical_weight: float = 0.45
    vector_weight: float = 0.35
    manual_weight: float = 0.15
    recency_weight: float = 0.05


@dataclass(slots=True)
class ProviderConfig:
    enabled: bool
    base_url: str
    api_key: str
    model: str


@dataclass(slots=True)
class AuthConfig:
    enabled: bool
    admin_token: str


@dataclass(slots=True)
class AbstractionConfig:
    provider: str
    base_url: str
    api_key: str
    model: str
    timeout_seconds: float


@dataclass(slots=True)
class AppConfig:
    port: int
    data_dir: Path
    database_path: Path
    retrieval: RetrievalConfig
    embedding: ProviderConfig
    rerank: ProviderConfig
    auth: AuthConfig
    abstraction: AbstractionConfig


def _get_bool(name: str, default: bool) -> bool:
    value = os.environ.get(name)
    if value is None or value == "":
        return default
    return value.strip().lower() in {"1", "true", "yes", "on"}


def _get_int(name: str, default: int) -> int:
    value = os.environ.get(name)
    return int(value) if value not in (None, "") else default


def _get_float(name: str, default: float) -> float:
    value = os.environ.get(name)
    return float(value) if value not in (None, "") else default


def load_config() -> AppConfig:
    root = Path.cwd()
    data_dir = Path(os.environ.get("CONTEXT_HUB_DATA_DIR", root / "var" / "data")).expanduser().resolve()
    database_path = Path(
        os.environ.get("CONTEXT_HUB_DATABASE_PATH", data_dir / "contexthub.db")
    ).expanduser().resolve()

    return AppConfig(
        port=_get_int("CONTEXT_HUB_PORT", _get_int("PORT", 4040)),
        data_dir=data_dir,
        database_path=database_path,
        retrieval=RetrievalConfig(
            default_limit=_get_int("CONTEXT_HUB_DEFAULT_LIMIT", 8),
            candidate_limit=_get_int("CONTEXT_HUB_CANDIDATE_LIMIT", 40),
            rerank_top_n=_get_int("CONTEXT_HUB_RERANK_TOP_N", 8),
            lexical_weight=_get_float("CONTEXT_HUB_LEXICAL_WEIGHT", 0.45),
            vector_weight=_get_float("CONTEXT_HUB_VECTOR_WEIGHT", 0.35),
            manual_weight=_get_float("CONTEXT_HUB_MANUAL_WEIGHT", 0.15),
            recency_weight=_get_float("CONTEXT_HUB_RECENCY_WEIGHT", 0.05),
        ),
        embedding=ProviderConfig(
            enabled=_get_bool("CONTEXT_HUB_ENABLE_EMBEDDINGS", True),
            base_url=os.environ.get("CONTEXT_HUB_EMBEDDING_BASE_URL", "https://cloud.infini-ai.com/maas/v1").rstrip("/"),
            api_key=os.environ.get("CONTEXT_HUB_EMBEDDING_API_KEY", ""),
            model=os.environ.get("CONTEXT_HUB_EMBEDDING_MODEL", "bge-m3"),
        ),
        rerank=ProviderConfig(
            enabled=_get_bool("CONTEXT_HUB_ENABLE_RERANK", False),
            base_url=os.environ.get("CONTEXT_HUB_RERANK_BASE_URL", "https://cloud.infini-ai.com/maas/v1").rstrip("/"),
            api_key=os.environ.get("CONTEXT_HUB_RERANK_API_KEY", ""),
            model=os.environ.get("CONTEXT_HUB_RERANK_MODEL", "bge-reranker-v2-m3"),
        ),
        auth=AuthConfig(
            enabled=_get_bool("CONTEXT_HUB_ENABLE_AUTH", False),
            admin_token=os.environ.get("CONTEXT_HUB_ADMIN_TOKEN", ""),
        ),
        abstraction=AbstractionConfig(
            provider=os.environ.get("CONTEXT_HUB_ABSTRACTION_PROVIDER", "litellm"),
            base_url=os.environ.get("CONTEXT_HUB_ABSTRACTION_BASE_URL", "").rstrip("/"),
            api_key=os.environ.get("CONTEXT_HUB_ABSTRACTION_API_KEY", ""),
            model=os.environ.get("CONTEXT_HUB_ABSTRACTION_MODEL", "gpt-5.4"),
            timeout_seconds=_get_float("CONTEXT_HUB_ABSTRACTION_TIMEOUT_SECONDS", 60.0),
        ),
    )
