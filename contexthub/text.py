from __future__ import annotations

import math
import re
from datetime import datetime, timezone

TOKEN_SPLIT = re.compile(r"[^\w\-]+", re.UNICODE)
SENTENCE_SPLIT = re.compile(r"(?<=[.!?。！？])\s+")


def tokenize(text: str) -> list[str]:
    return [token for token in TOKEN_SPLIT.split(text.lower()) if token]


def split_into_chunks(text: str, max_length: int = 900) -> list[str]:
    source = (text or "").strip()
    if not source:
        return []

    paragraphs = [part.strip() for part in re.split(r"\n\s*\n", source) if part.strip()]
    chunks: list[str] = []
    current = ""

    for paragraph in paragraphs:
        candidate = f"{current}\n\n{paragraph}" if current else paragraph
        if len(candidate) <= max_length:
            current = candidate
            continue

        if current:
            chunks.append(current)
            current = ""

        if len(paragraph) <= max_length:
            current = paragraph
            continue

        sentence_chunk = ""
        for sentence in SENTENCE_SPLIT.split(paragraph):
            candidate = f"{sentence_chunk} {sentence}" if sentence_chunk else sentence
            if len(candidate) <= max_length:
                sentence_chunk = candidate
                continue

            if sentence_chunk:
                chunks.append(sentence_chunk)
            sentence_chunk = sentence

        if sentence_chunk:
            current = sentence_chunk

    if current:
        chunks.append(current)

    return chunks


def clamp(value: float, minimum: float = 0.0, maximum: float = 1.0) -> float:
    return max(minimum, min(maximum, value))


def lexical_score(query: str, text: str) -> float:
    query_tokens = set(tokenize(query))
    text_tokens = set(tokenize(text))
    if not query_tokens or not text_tokens:
        return 0.0
    overlap = sum(1 for token in query_tokens if token in text_tokens)
    return overlap / len(query_tokens)


def cosine_similarity(left: list[float] | None, right: list[float] | None) -> float:
    if not left or not right or len(left) != len(right):
        return 0.0

    dot = sum(a * b for a, b in zip(left, right, strict=True))
    left_magnitude = math.sqrt(sum(a * a for a in left))
    right_magnitude = math.sqrt(sum(b * b for b in right))
    if left_magnitude == 0 or right_magnitude == 0:
        return 0.0
    return clamp(dot / (left_magnitude * right_magnitude))


def recency_score(timestamp: str | None, *, now: datetime | None = None) -> float:
    if not timestamp:
        return 0.0
    now = now or datetime.now(timezone.utc)

    normalized = timestamp.replace("Z", "+00:00")
    try:
        created_at = datetime.fromisoformat(normalized)
    except ValueError:
        return 0.0

    if created_at.tzinfo is None:
        created_at = created_at.replace(tzinfo=timezone.utc)

    age_days = max(0.0, (now - created_at).total_seconds() / 86400)
    return 1.0 / (1.0 + age_days / 14.0)


def manual_score(*, importance: float, pinned: bool, manual_summary: str | None) -> float:
    importance_score = clamp((importance or 0.0) / 5.0)
    pinned_boost = 1.0 if pinned else 0.0
    curated_boost = 0.5 if manual_summary else 0.0
    return clamp(importance_score * 0.6 + pinned_boost * 0.3 + curated_boost * 0.1)
