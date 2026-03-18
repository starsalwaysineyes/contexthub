from __future__ import annotations

from dataclasses import dataclass
import hashlib
import json
import math
from pathlib import PurePosixPath
import re
import sqlite3
import time
from typing import Any

from contexthub.config import Settings
from contexthub.uri import parse_ctx_uri


@dataclass(frozen=True)
class IndexedDocument:
    uri: str
    user_id: str
    workspace_kind: str
    agent_id: str | None
    relative_path: str
    doc_type: str
    title: str
    body: str


class SearchIndex:
    def __init__(self, settings: Settings, *, embedder: Any | None = None, reranker: Any | None = None) -> None:
        self.settings = settings
        self.embedder = embedder
        self.reranker = reranker
        self.settings.database_path.parent.mkdir(parents=True, exist_ok=True)
        self._init_db()

    def _connect(self) -> sqlite3.Connection:
        connection = sqlite3.connect(self.settings.database_path)
        connection.row_factory = sqlite3.Row
        connection.execute("PRAGMA journal_mode=WAL")
        connection.execute("PRAGMA foreign_keys=ON")
        return connection

    def _init_db(self) -> None:
        with self._connect() as connection:
            connection.executescript(
                """
                CREATE TABLE IF NOT EXISTS fs_search_documents (
                    uri TEXT PRIMARY KEY,
                    user_id TEXT NOT NULL,
                    workspace_kind TEXT NOT NULL,
                    agent_id TEXT,
                    relative_path TEXT NOT NULL,
                    doc_type TEXT NOT NULL,
                    title TEXT NOT NULL,
                    body TEXT NOT NULL,
                    content_hash TEXT NOT NULL,
                    updated_at REAL NOT NULL
                );

                CREATE INDEX IF NOT EXISTS idx_fs_search_documents_user ON fs_search_documents (user_id);
                CREATE INDEX IF NOT EXISTS idx_fs_search_documents_workspace ON fs_search_documents (user_id, workspace_kind, agent_id);
                CREATE INDEX IF NOT EXISTS idx_fs_search_documents_path ON fs_search_documents (user_id, relative_path);

                CREATE TABLE IF NOT EXISTS fs_search_chunks (
                    chunk_id TEXT PRIMARY KEY,
                    uri TEXT NOT NULL,
                    chunk_index INTEGER NOT NULL,
                    chunk_text TEXT NOT NULL,
                    embedding_json TEXT,
                    FOREIGN KEY(uri) REFERENCES fs_search_documents(uri) ON DELETE CASCADE
                );

                CREATE INDEX IF NOT EXISTS idx_fs_search_chunks_uri ON fs_search_chunks (uri);

                CREATE VIRTUAL TABLE IF NOT EXISTS fs_search_fts USING fts5(
                    uri UNINDEXED,
                    title,
                    body,
                    relative_path,
                    doc_type,
                    tokenize='unicode61 remove_diacritics 2'
                );
                """
            )

    def upsert_document(self, document: IndexedDocument) -> dict[str, Any]:
        content_hash = hashlib.sha256(document.body.encode("utf-8")).hexdigest()
        timestamp = time.time()

        with self._connect() as connection:
            previous = connection.execute(
                "SELECT content_hash FROM fs_search_documents WHERE uri = ?",
                (document.uri,),
            ).fetchone()
            if previous and previous["content_hash"] == content_hash:
                connection.execute(
                    "UPDATE fs_search_documents SET updated_at = ? WHERE uri = ?",
                    (timestamp, document.uri),
                )
                return {"indexed": False, "reason": "unchanged", "chunks": 0}

            chunks = _chunk_text(document.body)
            embeddings = self._safe_embed(chunks)
            self._replace_document(
                connection,
                document=document,
                content_hash=content_hash,
                timestamp=timestamp,
                chunks=chunks,
                embeddings=embeddings,
            )
        return {"indexed": True, "reason": "updated", "chunks": len(chunks)}

    def delete_uri(self, uri: str) -> int:
        with self._connect() as connection:
            return self._delete_uri(connection, uri)

    def delete_prefix(self, prefix: str) -> int:
        with self._connect() as connection:
            rows = connection.execute(
                "SELECT uri FROM fs_search_documents WHERE uri = ? OR uri LIKE ?",
                (prefix, f"{prefix.rstrip('/')}/%"),
            ).fetchall()
            removed = 0
            for row in rows:
                removed += self._delete_uri(connection, row["uri"])
            return removed

    def has_documents(self, *, user_id: str, scope_uri: str | None) -> bool:
        where_sql, params = self._scope_clause(user_id=user_id, scope_uri=scope_uri)
        with self._connect() as connection:
            row = connection.execute(
                f"SELECT COUNT(*) AS total FROM fs_search_documents WHERE {where_sql}",
                params,
            ).fetchone()
        return bool(row and row["total"] > 0)

    def search(
        self,
        *,
        user_id: str,
        scope_uri: str,
        query: str,
        rewrites: list[str],
        search_terms: list[str],
        mode: str,
        workspace_mode: str,
        doc_type_boosts: dict[str, float],
        glob_pattern: str | None,
        path_prefix: str | None,
        rerank_requested: bool,
        explain: bool,
    ) -> dict[str, Any] | None:
        if not self.has_documents(user_id=user_id, scope_uri=scope_uri):
            return None

        lexical_rows = self._lexical_candidates(
            user_id=user_id,
            scope_uri=scope_uri,
            rewrites=rewrites,
            search_terms=search_terms,
            limit=max(50, self.settings.retrieval.candidate_limit),
        ) if mode in {"lexical", "hybrid"} else {}

        semantic_rows = self._semantic_candidates(
            user_id=user_id,
            scope_uri=scope_uri,
            query=query,
            limit=max(50, self.settings.retrieval.candidate_limit),
        ) if mode in {"semantic", "hybrid"} else {}

        if mode == "semantic" and not semantic_rows:
            return self._empty_result(semantic=False, rerank=False, candidate_count=0)
        if mode == "hybrid" and not lexical_rows and not semantic_rows:
            return self._empty_result(semantic=False, rerank=False, candidate_count=0)
        if mode == "lexical" and not lexical_rows:
            return self._empty_result(semantic=False, rerank=False, candidate_count=0)

        reasons_map: dict[str, list[str]] = {}
        candidates: dict[str, dict[str, Any]] = {}
        if lexical_rows:
            for uri, row in lexical_rows.items():
                candidates[uri] = row
                reasons_map[uri] = list(row.get("reasons", []))
        if semantic_rows:
            for uri, row in semantic_rows.items():
                if uri not in candidates:
                    candidates[uri] = row
                    reasons_map[uri] = []
                else:
                    candidates[uri]["semantic"] = max(candidates[uri].get("semantic", 0.0), row.get("semantic", 0.0))
                    if not candidates[uri].get("snippet") and row.get("snippet"):
                        candidates[uri]["snippet"] = row["snippet"]
                        candidates[uri]["lineNumber"] = row.get("lineNumber")
                if row.get("semantic", 0.0) > 0.0:
                    reasons_map[uri].append(f"semantic similarity: {row['semantic']:.2f}")

        rows = list(candidates.values())
        filtered_rows = [
            row for row in rows if _matches_optional_filters(row["relative_path"], glob_pattern=glob_pattern, path_prefix=path_prefix)
        ]
        if not filtered_rows:
            return self._empty_result(semantic=bool(semantic_rows), rerank=False, candidate_count=0)

        for row in filtered_rows:
            lexical_score = max(0.0, row.get("lexical", 0.0))
            semantic_score = max(0.0, row.get("semantic", 0.0))
            if mode == "lexical":
                base_score = lexical_score
            elif mode == "semantic":
                base_score = semantic_score
            else:
                base_score = (
                    lexical_score * self.settings.retrieval.lexical_weight
                    + semantic_score * self.settings.retrieval.semantic_weight
                )
            workspace_boost = self.settings.retrieval.default_workspace_boost if workspace_mode == "default-first" and row["workspaceKind"] == "defaultWorkspace" else 1.0
            doc_boost = doc_type_boosts.get(row["docType"], 1.0)
            recency = _recency_boost(row.get("updatedAt", 0.0))
            row["score"] = base_score * workspace_boost * doc_boost + recency
            if workspace_boost > 1.0:
                reasons_map[row["uri"]].append("workspace boost: defaultWorkspace")
            if doc_boost != 1.0:
                reasons_map[row["uri"]].append(f"doc type boost: {row['docType']}")

        filtered_rows = [row for row in filtered_rows if row.get("score", 0.0) > 0]
        filtered_rows.sort(key=lambda item: item["score"], reverse=True)
        filtered_rows = filtered_rows[: self.settings.retrieval.candidate_limit]

        rerank_used = False
        if rerank_requested and self.reranker and filtered_rows:
            rerank_results = self._safe_rerank(
                query,
                [f"{row['title']}\n{row['relative_path']}\n{row['snippet']}" for row in filtered_rows[: self.settings.retrieval.rerank_top_n]],
            )
            if rerank_results:
                rerank_used = True
                score_map = {item["index"]: item["score"] for item in rerank_results}
                for index, row in enumerate(filtered_rows[: self.settings.retrieval.rerank_top_n]):
                    rerank_score = max(0.0, score_map.get(index, 0.0))
                    row["score"] = row["score"] * 0.65 + rerank_score * 0.35
                    reasons_map[row["uri"]].append(f"rerank score: {rerank_score:.2f}")

        filtered_rows.sort(key=lambda item: item["score"], reverse=True)
        hits = []
        for row in filtered_rows[: self.settings.retrieval.default_limit]:
            hits.append(
                {
                    "uri": row["uri"],
                    "title": row["title"],
                    "kind": "file",
                    "docType": row["docType"],
                    "workspaceKind": row["workspaceKind"],
                    "agentId": row.get("agentId"),
                    "score": round(row["score"], 6),
                    "snippet": row.get("snippet", ""),
                    "lineNumber": row.get("lineNumber"),
                    "reasons": reasons_map[row["uri"]][:6] if explain else [],
                }
            )

        return {
            "hits": hits,
            "plan": {
                "source": "index",
                "candidateCount": len(filtered_rows),
                "semantic": bool(semantic_rows),
                "rerank": rerank_used,
            },
        }

    def reindex_scope(self, *, user_id: str, scope_uri: str, documents: list[IndexedDocument]) -> dict[str, Any]:
        seen = {document.uri for document in documents}
        indexed = 0
        unchanged = 0
        scope_sql, scope_params = self._scope_clause(user_id=user_id, scope_uri=scope_uri)

        with self._connect() as connection:
            existing_hashes = {
                row["uri"]: row["content_hash"]
                for row in connection.execute(
                    f"SELECT uri, content_hash FROM fs_search_documents WHERE {scope_sql}",
                    scope_params,
                ).fetchall()
            }

            changed: list[tuple[IndexedDocument, str, list[str]]] = []
            for document in documents:
                content_hash = hashlib.sha256(document.body.encode("utf-8")).hexdigest()
                if existing_hashes.get(document.uri) == content_hash:
                    unchanged += 1
                    continue
                changed.append((document, content_hash, _chunk_text(document.body)))

            all_chunks = [chunk for _, _, chunks in changed for chunk in chunks]
            all_embeddings = self._bulk_embed_chunks(all_chunks)
            offset = 0
            timestamp = time.time()
            for document, content_hash, chunks in changed:
                embeddings = None
                if all_embeddings is not None:
                    embeddings = all_embeddings[offset : offset + len(chunks)]
                offset += len(chunks)
                self._replace_document(
                    connection,
                    document=document,
                    content_hash=content_hash,
                    timestamp=timestamp,
                    chunks=chunks,
                    embeddings=embeddings,
                )
                indexed += 1

            stale_rows = connection.execute(
                f"SELECT uri FROM fs_search_documents WHERE {scope_sql}",
                scope_params,
            ).fetchall()
            removed = 0
            for row in stale_rows:
                if row["uri"] not in seen:
                    removed += self._delete_uri(connection, row["uri"])
        return {"indexed": indexed, "unchanged": unchanged, "removed": removed}

    def _empty_result(self, *, semantic: bool, rerank: bool, candidate_count: int) -> dict[str, Any]:
        return {
            "hits": [],
            "plan": {
                "source": "index",
                "candidateCount": candidate_count,
                "semantic": semantic,
                "rerank": rerank,
            },
        }

    def _replace_document(
        self,
        connection: sqlite3.Connection,
        *,
        document: IndexedDocument,
        content_hash: str,
        timestamp: float,
        chunks: list[str],
        embeddings: list[list[float]] | None,
    ) -> None:
        self._delete_uri(connection, document.uri)
        connection.execute(
            """
            INSERT INTO fs_search_documents (
                uri, user_id, workspace_kind, agent_id, relative_path, doc_type, title, body, content_hash, updated_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                document.uri,
                document.user_id,
                document.workspace_kind,
                document.agent_id,
                document.relative_path,
                document.doc_type,
                document.title,
                document.body,
                content_hash,
                timestamp,
            ),
        )
        connection.execute(
            "INSERT INTO fs_search_fts (uri, title, body, relative_path, doc_type) VALUES (?, ?, ?, ?, ?)",
            (document.uri, document.title, document.body, document.relative_path, document.doc_type),
        )
        for index, chunk in enumerate(chunks):
            chunk_id = f"{document.uri}#chunk:{index}"
            embedding = embeddings[index] if embeddings and index < len(embeddings) else None
            connection.execute(
                "INSERT INTO fs_search_chunks (chunk_id, uri, chunk_index, chunk_text, embedding_json) VALUES (?, ?, ?, ?, ?)",
                (chunk_id, document.uri, index, chunk, _to_json(embedding) if embedding is not None else None),
            )

    def _bulk_embed_chunks(self, chunks: list[str], *, batch_size: int = 24) -> list[list[float]] | None:
        if not chunks:
            return []
        if not self.embedder:
            return None
        outputs: list[list[float]] = []
        for start in range(0, len(chunks), batch_size):
            batch = chunks[start : start + batch_size]
            embedded = self._safe_embed(batch)
            if embedded is None:
                return None
            outputs.extend(embedded)
        return outputs

    def _delete_uri(self, connection: sqlite3.Connection, uri: str) -> int:
        connection.execute("DELETE FROM fs_search_chunks WHERE uri = ?", (uri,))
        connection.execute("DELETE FROM fs_search_fts WHERE uri = ?", (uri,))
        result = connection.execute("DELETE FROM fs_search_documents WHERE uri = ?", (uri,))
        return result.rowcount or 0

    def _lexical_candidates(
        self,
        *,
        user_id: str,
        scope_uri: str,
        rewrites: list[str],
        search_terms: list[str],
        limit: int,
    ) -> dict[str, dict[str, Any]]:
        fts_query = _build_fts_query(rewrites=rewrites, search_terms=search_terms)
        if not fts_query:
            return {}
        where_sql, params = self._scope_clause(user_id=user_id, scope_uri=scope_uri, alias="d")
        sql = f"""
            SELECT
                d.uri,
                d.title,
                d.doc_type,
                d.workspace_kind,
                d.agent_id,
                d.relative_path,
                d.body,
                d.updated_at,
                bm25(fs_search_fts, 4.0, 1.0, 2.5, 1.0) AS rank
            FROM fs_search_fts
            JOIN fs_search_documents d ON d.uri = fs_search_fts.uri
            WHERE fs_search_fts MATCH ? AND {where_sql}
            ORDER BY rank
            LIMIT ?
        """
        with self._connect() as connection:
            rows = connection.execute(sql, (fts_query, *params, limit)).fetchall()
        output: dict[str, dict[str, Any]] = {}
        for row in rows:
            snippet, line_number = _best_snippet(row["body"], rewrites=rewrites, search_terms=search_terms, max_chars=self.settings.retrieval.snippet_chars)
            lexical_reason = _top_matching_terms(row["body"], rewrites=rewrites, search_terms=search_terms)
            reasons = []
            if row["title"] and any(value.lower() in row["title"].lower() for value in rewrites + search_terms):
                reasons.append(f"title match: {row['title']}")
            if any(value.lower() in row["relative_path"].lower() for value in rewrites + search_terms):
                reasons.append(f"path match: {row['relative_path']}")
            if lexical_reason:
                reasons.append(f"body match: {', '.join(lexical_reason)}")
            output[row["uri"]] = {
                "uri": row["uri"],
                "title": row["title"],
                "docType": row["doc_type"],
                "workspaceKind": row["workspace_kind"],
                "agentId": row["agent_id"],
                "relative_path": row["relative_path"],
                "updatedAt": row["updated_at"],
                "snippet": snippet,
                "lineNumber": line_number,
                "lexical": 1.0 / (1.0 + abs(float(row["rank"]))),
                "semantic": 0.0,
                "reasons": reasons,
            }
        return output

    def _semantic_candidates(self, *, user_id: str, scope_uri: str, query: str, limit: int) -> dict[str, dict[str, Any]]:
        query_vector = self._safe_embed([query])
        if not query_vector:
            return {}
        query_embedding = query_vector[0]
        where_sql, params = self._scope_clause(user_id=user_id, scope_uri=scope_uri, alias="d")
        sql = f"""
            SELECT
                d.uri,
                d.title,
                d.doc_type,
                d.workspace_kind,
                d.agent_id,
                d.relative_path,
                d.updated_at,
                c.chunk_text,
                c.embedding_json
            FROM fs_search_chunks c
            JOIN fs_search_documents d ON d.uri = c.uri
            WHERE {where_sql}
        """
        with self._connect() as connection:
            rows = connection.execute(sql, params).fetchall()
        best_by_uri: dict[str, dict[str, Any]] = {}
        for row in rows:
            embedding = _from_json(row["embedding_json"])
            score = _cosine_similarity(query_embedding, embedding)
            if score <= 0:
                continue
            current = best_by_uri.get(row["uri"])
            if current and current["semantic"] >= score:
                continue
            snippet, line_number = _best_snippet(row["chunk_text"], rewrites=[query], search_terms=_tokenize_search_text(query), max_chars=self.settings.retrieval.snippet_chars)
            best_by_uri[row["uri"]] = {
                "uri": row["uri"],
                "title": row["title"],
                "docType": row["doc_type"],
                "workspaceKind": row["workspace_kind"],
                "agentId": row["agent_id"],
                "relative_path": row["relative_path"],
                "updatedAt": row["updated_at"],
                "snippet": snippet,
                "lineNumber": line_number,
                "lexical": 0.0,
                "semantic": score,
                "reasons": [],
            }
        rows = list(best_by_uri.values())
        rows.sort(key=lambda item: item["semantic"], reverse=True)
        return {row["uri"]: row for row in rows[:limit]}

    def _scope_clause(self, *, user_id: str, scope_uri: str | None, alias: str | None = None) -> tuple[str, list[Any]]:
        col = f"{alias}." if alias else ""
        if scope_uri is None:
            return f"{col}user_id = ?", [user_id]

        parsed = parse_ctx_uri(scope_uri)
        if parsed.is_user_root:
            return f"{col}user_id = ?", [parsed.user_id]

        if parsed.is_workspace_root:
            return (
                f"{col}user_id = ? AND {col}workspace_kind = ? AND {col}agent_id IS ?",
                [parsed.user_id, parsed.workspace_kind, parsed.agent_id],
            )

        prefix = parsed.relative_path.as_posix()
        return (
            f"{col}user_id = ? AND {col}workspace_kind = ? AND {col}agent_id IS ? AND ({col}relative_path = ? OR {col}relative_path LIKE ?)",
            [parsed.user_id, parsed.workspace_kind, parsed.agent_id, prefix, f"{prefix}/%"],
        )

    def _safe_embed(self, inputs: list[str]) -> list[list[float]] | None:
        if not self.embedder:
            return None
        try:
            return self.embedder.embed(inputs)
        except Exception:
            return None

    def _safe_rerank(self, query: str, documents: list[str]) -> list[dict[str, float]] | None:
        if not self.reranker:
            return None
        try:
            return self.reranker.rank(query, documents)
        except Exception:
            return None


def _chunk_text(text: str, *, max_chars: int = 900, overlap: int = 120) -> list[str]:
    cleaned = text.strip()
    if not cleaned:
        return [""]
    chunks: list[str] = []
    start = 0
    while start < len(cleaned):
        end = min(len(cleaned), start + max_chars)
        chunks.append(cleaned[start:end])
        if end >= len(cleaned):
            break
        start = max(0, end - overlap)
    return chunks


def _build_fts_query(*, rewrites: list[str], search_terms: list[str]) -> str:
    parts = []
    for value in rewrites:
        escaped = value.replace('"', ' ')
        parts.append(f'"{escaped}"')
    for term in search_terms:
        escaped = term.replace('"', ' ').strip()
        if escaped:
            parts.append(f'"{escaped}"')
    return " OR ".join(_dedupe_texts(parts[:12]))


def _tokenize_search_text(text: str) -> list[str]:
    tokens = re.findall(r"[A-Za-z0-9_./:-]+|[\u4e00-\u9fff]+", text)
    return _dedupe_texts([token for token in tokens if len(token) >= 2])


def _dedupe_texts(values: list[str]) -> list[str]:
    seen: set[str] = set()
    output: list[str] = []
    for value in values:
        key = value.lower()
        if key in seen:
            continue
        seen.add(key)
        output.append(value)
    return output


def _top_matching_terms(text: str, *, rewrites: list[str], search_terms: list[str]) -> list[str]:
    lowered = text.lower()
    matches: list[str] = []
    for value in rewrites + search_terms:
        cleaned = value.lower()
        if cleaned in lowered and value not in matches:
            matches.append(value)
        if len(matches) >= 3:
            break
    return matches


def _best_snippet(text: str, *, rewrites: list[str], search_terms: list[str], max_chars: int) -> tuple[str, int | None]:
    lines = text.splitlines() or [text]
    best_line = None
    best_score = 0.0
    for index, line in enumerate(lines, start=1):
        stripped = line.strip()
        if not stripped:
            continue
        score = sum(1.6 for value in rewrites if value.lower() in stripped.lower()) + sum(0.5 for value in search_terms if value.lower() in stripped.lower())
        if score > best_score:
            best_score = score
            best_line = (index, stripped)
    if best_line:
        return _trim_snippet(best_line[1], max_chars=max_chars), best_line[0]
    for index, line in enumerate(lines, start=1):
        stripped = line.strip()
        if stripped:
            return _trim_snippet(stripped, max_chars=max_chars), index
    return "", None


def _trim_snippet(text: str, *, max_chars: int) -> str:
    if len(text) <= max_chars:
        return text
    return text[: max_chars - 3].rstrip() + "..."


def _matches_optional_filters(relative_path: str, *, glob_pattern: str | None, path_prefix: str | None) -> bool:
    rel = relative_path.strip("/")
    if path_prefix:
        prefix = path_prefix.strip("/")
        if rel != prefix and not rel.startswith(prefix + "/"):
            return False
    if glob_pattern:
        from fnmatch import fnmatch

        if not (fnmatch(rel, glob_pattern) or fnmatch(PurePosixPath(rel).name, glob_pattern)):
            return False
    return True


def _cosine_similarity(left: list[float] | None, right: list[float] | None) -> float:
    if not left or not right or len(left) != len(right):
        return 0.0
    numerator = sum(a * b for a, b in zip(left, right))
    left_norm = math.sqrt(sum(a * a for a in left))
    right_norm = math.sqrt(sum(b * b for b in right))
    if left_norm == 0 or right_norm == 0:
        return 0.0
    return max(0.0, numerator / (left_norm * right_norm))


def _recency_boost(updated_at: float) -> float:
    if not updated_at:
        return 0.0
    age_seconds = max(0.0, time.time() - float(updated_at))
    days = age_seconds / 86400.0
    return max(0.0, 0.04 * math.exp(-days / 21.0))


def _to_json(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False)


def _from_json(value: str | None) -> Any:
    if not value:
        return None
    return json.loads(value)
