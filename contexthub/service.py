from __future__ import annotations

import uuid
from datetime import datetime, timezone
from typing import Any

from contexthub.config import AppConfig
from contexthub.providers import EmbeddingClient, RerankClient
from contexthub.schemas import (
    CommitSessionRequest,
    CreatePartitionRequest,
    CreateRecordRequest,
    CreateTenantRequest,
    QueryRequest,
    RegisterAgentRequest,
)
from contexthub.store import SQLiteStore, from_json, to_json
from contexthub.text import (
    clamp,
    cosine_similarity,
    lexical_score,
    manual_score,
    recency_score,
    split_into_chunks,
)


class HubError(RuntimeError):
    pass


def create_id(prefix: str) -> str:
    return f"{prefix}_{uuid.uuid4().hex}"


def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def normalize_key(value: str) -> str:
    return value.strip().lower()


def text_for_chunk(record: dict[str, Any], chunk_text: str) -> str:
    return "\n\n".join(
        part for part in [record["title"], record.get("manualSummary", ""), chunk_text] if part
    )


class HubService:
    def __init__(
        self,
        *,
        store: SQLiteStore,
        embedder: EmbeddingClient,
        reranker: RerankClient,
        config: AppConfig,
    ) -> None:
        self.store = store
        self.embedder = embedder
        self.reranker = reranker
        self.config = config

    def health(self) -> dict[str, Any]:
        return {
            "ok": True,
            "counts": self.store.counts(),
            "providers": {
                "embedding": self.embedder.status(),
                "rerank": self.reranker.status(),
            },
        }

    def create_tenant(self, payload: CreateTenantRequest) -> dict[str, Any]:
        slug = normalize_key(payload.slug)
        with self.store.connection() as conn:
            row = conn.execute("SELECT * FROM tenants WHERE slug = ?", (slug,)).fetchone()
            if row is not None:
                return self._serialize_tenant(dict(row))

            tenant = {
                "id": create_id("tenant"),
                "slug": slug,
                "name": payload.name.strip(),
                "description": payload.description.strip(),
                "created_at": now_iso(),
            }
            conn.execute(
                "INSERT INTO tenants (id, slug, name, description, created_at) VALUES (?, ?, ?, ?, ?)",
                (
                    tenant["id"],
                    tenant["slug"],
                    tenant["name"],
                    tenant["description"],
                    tenant["created_at"],
                ),
            )
            return self._serialize_tenant(tenant)

    def create_partition(self, payload: CreatePartitionRequest) -> dict[str, Any]:
        key = normalize_key(payload.key)
        with self.store.connection() as conn:
            self._assert_tenant(conn, payload.tenant_id)
            row = conn.execute(
                "SELECT * FROM partitions WHERE tenant_id = ? AND key = ?",
                (payload.tenant_id, key),
            ).fetchone()
            if row is not None:
                return self._serialize_partition(dict(row))

            partition = {
                "id": create_id("partition"),
                "tenant_id": payload.tenant_id,
                "key": key,
                "name": payload.name.strip(),
                "kind": normalize_key(payload.kind),
                "description": payload.description.strip(),
                "allow_cross_query_from": to_json([normalize_key(item) for item in payload.allow_cross_query_from]),
                "created_at": now_iso(),
            }
            conn.execute(
                """
                INSERT INTO partitions (id, tenant_id, key, name, kind, description, allow_cross_query_from, created_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    partition["id"],
                    partition["tenant_id"],
                    partition["key"],
                    partition["name"],
                    partition["kind"],
                    partition["description"],
                    partition["allow_cross_query_from"],
                    partition["created_at"],
                ),
            )
            return self._serialize_partition(partition)

    def register_agent(self, payload: RegisterAgentRequest) -> dict[str, Any]:
        with self.store.connection() as conn:
            self._assert_tenant(conn, payload.tenant_id)
            agent = {
                "id": create_id("agent"),
                "tenant_id": payload.tenant_id,
                "name": payload.name.strip(),
                "kind": normalize_key(payload.kind),
                "metadata": to_json(payload.metadata),
                "created_at": now_iso(),
            }
            conn.execute(
                "INSERT INTO agents (id, tenant_id, name, kind, metadata, created_at) VALUES (?, ?, ?, ?, ?, ?)",
                (
                    agent["id"],
                    agent["tenant_id"],
                    agent["name"],
                    agent["kind"],
                    agent["metadata"],
                    agent["created_at"],
                ),
            )
            return self._serialize_agent(agent)

    def create_record(self, payload: CreateRecordRequest) -> dict[str, Any]:
        partition_key = normalize_key(payload.partition_key)
        idempotency_key = normalize_key(payload.idempotency_key) if payload.idempotency_key else None
        chunks = split_into_chunks(payload.text)
        embeddings = self._safe_embed(chunks)
        timestamp = now_iso()

        with self.store.connection() as conn:
            self._assert_tenant(conn, payload.tenant_id)
            self._assert_partition(conn, payload.tenant_id, partition_key)

            if idempotency_key:
                existing = conn.execute(
                    "SELECT * FROM records WHERE tenant_id = ? AND idempotency_key = ?",
                    (payload.tenant_id, idempotency_key),
                ).fetchone()
                if existing is not None:
                    return self._serialize_record(dict(existing))

            record = {
                "id": create_id("record"),
                "tenant_id": payload.tenant_id,
                "partition_key": partition_key,
                "type": normalize_key(payload.type),
                "layer": normalize_key(payload.layer),
                "title": payload.title.strip(),
                "text": payload.text.strip(),
                "source": to_json(payload.source) if payload.source is not None else None,
                "tags": to_json([item.strip() for item in payload.tags if item.strip()]),
                "metadata": to_json(payload.metadata),
                "manual_summary": payload.manual_summary.strip(),
                "importance": clamp(float(payload.importance), 0.0, 5.0),
                "pinned": int(payload.pinned),
                "idempotency_key": idempotency_key,
                "created_at": timestamp,
                "updated_at": timestamp,
            }
            conn.execute(
                """
                INSERT INTO records (
                  id, tenant_id, partition_key, type, layer, title, text, source, tags, metadata,
                  manual_summary, importance, pinned, idempotency_key, created_at, updated_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    record["id"],
                    record["tenant_id"],
                    record["partition_key"],
                    record["type"],
                    record["layer"],
                    record["title"],
                    record["text"],
                    record["source"],
                    record["tags"],
                    record["metadata"],
                    record["manual_summary"],
                    record["importance"],
                    record["pinned"],
                    record["idempotency_key"],
                    record["created_at"],
                    record["updated_at"],
                ),
            )

            for index, chunk_text in enumerate(chunks):
                vector = embeddings[index] if embeddings and index < len(embeddings) else None
                conn.execute(
                    """
                    INSERT INTO chunks (id, record_id, tenant_id, partition_key, chunk_index, text, vector, created_at)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        create_id("chunk"),
                        record["id"],
                        record["tenant_id"],
                        record["partition_key"],
                        index,
                        chunk_text,
                        to_json(vector) if vector is not None else None,
                        timestamp,
                    ),
                )

            return self._serialize_record(record)

    def commit_session(self, payload: CommitSessionRequest) -> dict[str, Any]:
        partition_key = normalize_key(payload.partition_key)
        session_id = payload.session_id or create_id("session")
        timestamp = now_iso()

        with self.store.connection() as conn:
            self._assert_tenant(conn, payload.tenant_id)
            self._assert_partition(conn, payload.tenant_id, partition_key)
            session = {
                "id": session_id,
                "tenant_id": payload.tenant_id,
                "partition_key": partition_key,
                "agent_id": payload.agent_id,
                "summary": payload.summary.strip(),
                "metadata": to_json(payload.metadata),
                "messages": to_json([message.model_dump() for message in payload.messages]),
                "created_at": timestamp,
            }
            conn.execute(
                "INSERT INTO sessions (id, tenant_id, partition_key, agent_id, summary, metadata, messages, created_at) VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
                (
                    session["id"],
                    session["tenant_id"],
                    session["partition_key"],
                    session["agent_id"],
                    session["summary"],
                    session["metadata"],
                    session["messages"],
                    session["created_at"],
                ),
            )

        created_memories = []
        for entry in payload.memory_entries:
            created_memories.append(
                self.create_record(
                    CreateRecordRequest(
                        tenantId=payload.tenant_id,
                        partitionKey=partition_key,
                        type=entry.type,
                        layer=entry.layer,
                        title=entry.title,
                        text=entry.text,
                        manualSummary=entry.manual_summary or payload.summary,
                        source={"sessionId": session_id, "kind": "session-commit"},
                        tags=entry.tags,
                        metadata={**entry.metadata, "sessionId": session_id},
                        importance=entry.importance,
                        pinned=entry.pinned,
                        idempotencyKey=entry.idempotency_key,
                    )
                )
            )

        return {
            "session": self._serialize_session(session),
            "createdMemories": created_memories,
        }

    def query(self, payload: QueryRequest) -> dict[str, Any]:
        with self.store.connection() as conn:
            self._assert_tenant(conn, payload.tenant_id)
            partition_keys = [normalize_key(item) for item in payload.partitions if item.strip()]
            if not partition_keys:
                partition_rows = conn.execute(
                    "SELECT key FROM partitions WHERE tenant_id = ?",
                    (payload.tenant_id,),
                ).fetchall()
                partition_keys = [str(row["key"]) for row in partition_rows]

            if not partition_keys:
                return {
                    "items": [],
                    "retrieval": {
                        "candidateCount": 0,
                        "scoredCount": 0,
                        "usedEmbeddings": False,
                        "usedRerank": False,
                    },
                }

            types = [normalize_key(item) for item in payload.types if item.strip()]
            layers = [normalize_key(item) for item in payload.layers if item.strip()]
            clauses = ["records.tenant_id = ?"]
            parameters: list[Any] = [payload.tenant_id]

            partition_placeholders = ", ".join("?" for _ in partition_keys)
            clauses.append(f"records.partition_key IN ({partition_placeholders})")
            parameters.extend(partition_keys)

            if types:
                type_placeholders = ", ".join("?" for _ in types)
                clauses.append(f"records.type IN ({type_placeholders})")
                parameters.extend(types)

            if layers:
                layer_placeholders = ", ".join("?" for _ in layers)
                clauses.append(f"records.layer IN ({layer_placeholders})")
                parameters.extend(layers)

            rows = conn.execute(
                f"""
                SELECT
                  records.*, chunks.id AS chunk_id, chunks.text AS chunk_text, chunks.vector AS chunk_vector
                FROM records
                JOIN chunks ON chunks.record_id = records.id
                WHERE {' AND '.join(clauses)}
                ORDER BY records.updated_at DESC, chunks.chunk_index ASC
                """,
                parameters,
            ).fetchall()

        query_vector_list = self._safe_embed([payload.query])
        query_vector = query_vector_list[0] if query_vector_list else None
        retrieval = self.config.retrieval
        scored: list[dict[str, Any]] = []

        for row in rows:
            record = self._serialize_record(dict(row))
            chunk_text = str(row["chunk_text"])
            chunk_vector = from_json(row["chunk_vector"], None)
            lexical = lexical_score(payload.query, text_for_chunk(record, chunk_text))
            vector = cosine_similarity(query_vector, chunk_vector)
            manual = manual_score(
                importance=float(record["importance"]),
                pinned=bool(record["pinned"]),
                manual_summary=record.get("manualSummary"),
            )
            recency = recency_score(record.get("updatedAt") or record.get("createdAt"))
            score = (
                lexical * retrieval.lexical_weight
                + vector * retrieval.vector_weight
                + manual * retrieval.manual_weight
                + recency * retrieval.recency_weight
            )
            if score <= 0:
                continue
            scored.append(
                {
                    "record": record,
                    "chunkId": row["chunk_id"],
                    "chunkText": chunk_text,
                    "lexical": lexical,
                    "vector": vector,
                    "manual": manual,
                    "recency": recency,
                    "score": score,
                    "rerank": None,
                }
            )

        scored.sort(key=lambda item: item["score"], reverse=True)
        scored = scored[: retrieval.candidate_limit]

        wants_rerank = payload.rerank if payload.rerank is not None else self.config.rerank.enabled
        if wants_rerank and scored:
            rerank_window = scored[: retrieval.rerank_top_n]
            rerank_results = self._safe_rerank(
                payload.query,
                [text_for_chunk(item["record"], item["chunkText"]) for item in rerank_window],
            )
            if rerank_results:
                rerank_map = {item["index"]: item["score"] for item in rerank_results}
                for index, item in enumerate(rerank_window):
                    item["rerank"] = rerank_map.get(index, 0.0)
                    item["score"] = item["score"] * 0.65 + item["rerank"] * 0.35

        scored.sort(key=lambda item: item["score"], reverse=True)
        limit = payload.limit or retrieval.default_limit
        items = [
            {
                "recordId": item["record"]["id"],
                "chunkId": item["chunkId"],
                "title": item["record"]["title"],
                "type": item["record"]["type"],
                "layer": item["record"]["layer"],
                "partitionKey": item["record"]["partitionKey"],
                "score": round(item["score"], 6),
                "snippet": item["chunkText"],
                "manualSummary": item["record"]["manualSummary"],
                "source": item["record"]["source"],
                "tags": item["record"]["tags"],
                "createdAt": item["record"]["createdAt"],
                "trace": {
                    "lexical": round(item["lexical"], 6),
                    "vector": round(item["vector"], 6),
                    "manual": round(item["manual"], 6),
                    "recency": round(item["recency"], 6),
                    "rerank": None if item["rerank"] is None else round(item["rerank"], 6),
                },
            }
            for item in scored[:limit]
        ]
        return {
            "items": items,
            "retrieval": {
                "candidateCount": len(rows),
                "scoredCount": len(scored),
                "usedEmbeddings": bool(query_vector),
                "usedRerank": any(item["trace"]["rerank"] is not None for item in items),
            },
        }

    def _assert_tenant(self, conn: Any, tenant_id: str) -> None:
        row = conn.execute("SELECT id FROM tenants WHERE id = ?", (tenant_id,)).fetchone()
        if row is None:
            raise HubError(f"Unknown tenant: {tenant_id}")

    def _assert_partition(self, conn: Any, tenant_id: str, partition_key: str) -> None:
        row = conn.execute(
            "SELECT id FROM partitions WHERE tenant_id = ? AND key = ?",
            (tenant_id, partition_key),
        ).fetchone()
        if row is None:
            raise HubError(f"Unknown partition: {partition_key}")

    def _safe_embed(self, inputs: list[str]) -> list[list[float]] | None:
        try:
            return self.embedder.embed(inputs)
        except Exception:
            return None

    def _safe_rerank(self, query: str, documents: list[str]) -> list[dict[str, float]] | None:
        try:
            return self.reranker.rank(query, documents)
        except Exception:
            return None

    def _serialize_tenant(self, tenant: dict[str, Any]) -> dict[str, Any]:
        return {
            "id": tenant["id"],
            "slug": tenant["slug"],
            "name": tenant["name"],
            "description": tenant.get("description", ""),
            "createdAt": tenant["created_at"],
        }

    def _serialize_partition(self, partition: dict[str, Any]) -> dict[str, Any]:
        return {
            "id": partition["id"],
            "tenantId": partition["tenant_id"],
            "key": partition["key"],
            "name": partition["name"],
            "kind": partition["kind"],
            "description": partition.get("description", ""),
            "allowCrossQueryFrom": from_json(partition.get("allow_cross_query_from"), []),
            "createdAt": partition["created_at"],
        }

    def _serialize_agent(self, agent: dict[str, Any]) -> dict[str, Any]:
        return {
            "id": agent["id"],
            "tenantId": agent["tenant_id"],
            "name": agent["name"],
            "kind": agent["kind"],
            "metadata": from_json(agent.get("metadata"), {}),
            "createdAt": agent["created_at"],
        }

    def _serialize_record(self, record: dict[str, Any]) -> dict[str, Any]:
        return {
            "id": record["id"],
            "tenantId": record["tenant_id"],
            "partitionKey": record["partition_key"],
            "type": record["type"],
            "layer": record.get("layer", "l1"),
            "title": record["title"],
            "text": record["text"],
            "source": from_json(record.get("source"), None),
            "tags": from_json(record.get("tags"), []),
            "metadata": from_json(record.get("metadata"), {}),
            "manualSummary": record.get("manual_summary", ""),
            "importance": float(record.get("importance", 0.0)),
            "pinned": bool(record.get("pinned", 0)),
            "idempotencyKey": record.get("idempotency_key"),
            "createdAt": record["created_at"],
            "updatedAt": record["updated_at"],
        }

    def _serialize_session(self, session: dict[str, Any]) -> dict[str, Any]:
        return {
            "id": session["id"],
            "tenantId": session["tenant_id"],
            "partitionKey": session["partition_key"],
            "agentId": session.get("agent_id"),
            "summary": session.get("summary", ""),
            "metadata": from_json(session.get("metadata"), {}),
            "messages": from_json(session.get("messages"), []),
            "createdAt": session["created_at"],
        }
