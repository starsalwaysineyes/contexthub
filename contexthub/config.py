from __future__ import annotations

import os
from dataclasses import dataclass, field
from pathlib import Path


@dataclass(frozen=True)
class RetrievalSettings:
    default_limit: int = 10
    candidate_limit: int = 40
    rerank_top_n: int = 8
    lexical_weight: float = 0.68
    semantic_weight: float = 0.32
    default_workspace_boost: float = 1.12
    semantic_max_chars: int = 3500
    snippet_chars: int = 220


@dataclass(frozen=True)
class ProviderSettings:
    enabled: bool = True
    base_url: str = "https://cloud.infini-ai.com/maas/v1"
    api_key: str = ""
    model: str = ""


@dataclass(frozen=True)
class Settings:
    data_dir: Path
    database_path: Path
    admin_token: str | None
    retrieval: RetrievalSettings = field(default_factory=RetrievalSettings)
    embedding: ProviderSettings = field(
        default_factory=lambda: ProviderSettings(model="bge-m3")
    )
    rerank: ProviderSettings = field(
        default_factory=lambda: ProviderSettings(model="bge-reranker-v2-m3")
    )


def _get_bool(name: str, default: bool) -> bool:
    value = os.getenv(name)
    if value is None or value == "":
        return default
    return value.strip().lower() in {"1", "true", "yes", "on"}


def _get_int(name: str, default: int) -> int:
    value = os.getenv(name)
    return int(value) if value not in (None, "") else default


def _get_float(name: str, default: float) -> float:
    value = os.getenv(name)
    return float(value) if value not in (None, "") else default


def load_settings() -> Settings:
    raw_data_dir = os.getenv("CONTEXT_HUB_DATA_DIR", "var/data")
    data_dir = Path(raw_data_dir).expanduser().resolve()
    database_path = Path(os.getenv("CONTEXT_HUB_DATABASE_PATH", data_dir / "contexthub.db")).expanduser().resolve()
    admin_token = os.getenv("CONTEXT_HUB_ADMIN_TOKEN") or None
    embedding_base_url = os.getenv("CONTEXT_HUB_EMBEDDING_BASE_URL", "https://cloud.infini-ai.com/maas/v1").rstrip("/")
    rerank_base_url = os.getenv("CONTEXT_HUB_RERANK_BASE_URL", embedding_base_url).rstrip("/")
    embedding_api_key = os.getenv("CONTEXT_HUB_EMBEDDING_API_KEY", "")
    rerank_api_key = os.getenv("CONTEXT_HUB_RERANK_API_KEY", embedding_api_key)
    return Settings(
        data_dir=data_dir,
        database_path=database_path,
        admin_token=admin_token,
        retrieval=RetrievalSettings(
            default_limit=_get_int("CONTEXT_HUB_DEFAULT_LIMIT", 10),
            candidate_limit=_get_int("CONTEXT_HUB_SEARCH_CANDIDATE_LIMIT", 40),
            rerank_top_n=_get_int("CONTEXT_HUB_RERANK_TOP_N", 8),
            lexical_weight=_get_float("CONTEXT_HUB_LEXICAL_WEIGHT", 0.68),
            semantic_weight=_get_float("CONTEXT_HUB_SEMANTIC_WEIGHT", 0.32),
            default_workspace_boost=_get_float("CONTEXT_HUB_DEFAULT_WORKSPACE_BOOST", 1.12),
            semantic_max_chars=_get_int("CONTEXT_HUB_SEARCH_SEMANTIC_MAX_CHARS", 3500),
            snippet_chars=_get_int("CONTEXT_HUB_SEARCH_SNIPPET_CHARS", 220),
        ),
        embedding=ProviderSettings(
            enabled=_get_bool("CONTEXT_HUB_ENABLE_EMBEDDINGS", True),
            base_url=embedding_base_url,
            api_key=embedding_api_key,
            model=os.getenv("CONTEXT_HUB_EMBEDDING_MODEL", "bge-m3"),
        ),
        rerank=ProviderSettings(
            enabled=_get_bool("CONTEXT_HUB_ENABLE_RERANK", True),
            base_url=rerank_base_url,
            api_key=rerank_api_key,
            model=os.getenv("CONTEXT_HUB_RERANK_MODEL", "bge-reranker-v2-m3"),
        ),
    )
