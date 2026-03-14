from __future__ import annotations

import hashlib
import posixpath
import re
import secrets
import uuid
from datetime import datetime, timezone
from typing import Any, Callable

from contexthub.config import AppConfig
from contexthub.providers import EmbeddingClient, LiteLLMAbstractionClient, RerankClient
from contexthub.schemas import (
    BrowseTreeRequest,
    CommitSessionRequest,
    CreatePartitionRequest,
    CreatePrincipalRequest,
    CreateRecordRequest,
    CreateTenantRequest,
    GrepRequest,
    ImportResourceRequest,
    ListRecordsRequest,
    QueryRequest,
    RegisterAgentRequest,
    UpdateRecordRequest,
    UpsertPrincipalAclRequest,
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


def hash_token(token: str) -> str:
    return hashlib.sha256(token.encode("utf-8")).hexdigest()


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
        abstractor: LiteLLMAbstractionClient | None,
        config: AppConfig,
    ) -> None:
        self.store = store
        self.embedder = embedder
        self.reranker = reranker
        self.abstractor = abstractor
        self.config = config

    def health(self) -> dict[str, Any]:
        return {
            "ok": True,
            "counts": self.store.counts(),
            "providers": {
                "embedding": self.embedder.status(),
                "rerank": self.reranker.status(),
                "abstraction": self.abstractor.status() if self.abstractor is not None else {
                    "enabled": False,
                    "ready": False,
                    "provider": None,
                    "model": None,
                    "baseUrl": None,
                },
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

    def create_principal(self, payload: CreatePrincipalRequest) -> dict[str, Any]:
        token = f"ctx_{secrets.token_urlsafe(32)}"
        token_hash = hash_token(token)
        timestamp = now_iso()

        with self.store.connection() as conn:
            self._assert_tenant(conn, payload.tenant_id)
            principal = {
                "id": create_id("principal"),
                "tenant_id": payload.tenant_id,
                "name": payload.name.strip(),
                "kind": normalize_key(payload.kind),
                "token_hash": token_hash,
                "metadata": to_json(payload.metadata),
                "disabled": 0,
                "created_at": timestamp,
                "last_used_at": None,
            }
            conn.execute(
                """
                INSERT INTO principals (id, tenant_id, name, kind, token_hash, metadata, disabled, created_at, last_used_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    principal["id"],
                    principal["tenant_id"],
                    principal["name"],
                    principal["kind"],
                    principal["token_hash"],
                    principal["metadata"],
                    principal["disabled"],
                    principal["created_at"],
                    principal["last_used_at"],
                ),
            )

        serialized = self._serialize_principal(principal)
        serialized["token"] = token
        return serialized

    def upsert_principal_acl(self, principal_id: str, payload: UpsertPrincipalAclRequest) -> dict[str, Any]:
        partition_key = normalize_key(payload.partition_key)
        timestamp = now_iso()

        with self.store.connection() as conn:
            principal_row = conn.execute(
                "SELECT * FROM principals WHERE id = ?",
                (principal_id,),
            ).fetchone()
            if principal_row is None:
                raise HubError(f"Unknown principal: {principal_id}")

            principal = dict(principal_row)
            self._assert_partition(conn, principal["tenant_id"], partition_key)
            existing = conn.execute(
                "SELECT * FROM principal_partition_acl WHERE principal_id = ? AND partition_key = ?",
                (principal_id, partition_key),
            ).fetchone()

            allowed_layers = sorted({normalize_key(layer) for layer in payload.allowed_layers})

            if existing is None:
                acl = {
                    "id": create_id("acl"),
                    "principal_id": principal_id,
                    "tenant_id": principal["tenant_id"],
                    "partition_key": partition_key,
                    "can_read": int(payload.can_read),
                    "can_write": int(payload.can_write),
                    "allowed_layers": to_json(allowed_layers),
                    "created_at": timestamp,
                    "updated_at": timestamp,
                }
                conn.execute(
                    """
                    INSERT INTO principal_partition_acl (
                      id, principal_id, tenant_id, partition_key, can_read, can_write, allowed_layers, created_at, updated_at
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        acl["id"],
                        acl["principal_id"],
                        acl["tenant_id"],
                        acl["partition_key"],
                        acl["can_read"],
                        acl["can_write"],
                        acl["allowed_layers"],
                        acl["created_at"],
                        acl["updated_at"],
                    ),
                )
            else:
                acl = dict(existing)
                acl.update(
                    {
                        "can_read": int(payload.can_read),
                        "can_write": int(payload.can_write),
                        "allowed_layers": to_json(allowed_layers),
                        "updated_at": timestamp,
                    }
                )
                conn.execute(
                    """
                    UPDATE principal_partition_acl
                    SET can_read = ?, can_write = ?, allowed_layers = ?, updated_at = ?
                    WHERE principal_id = ? AND partition_key = ?
                    """,
                    (
                        acl["can_read"],
                        acl["can_write"],
                        acl["allowed_layers"],
                        acl["updated_at"],
                        principal_id,
                        partition_key,
                    ),
                )

            return self._serialize_acl(acl)

    def list_principal_acl(self, principal_id: str) -> list[dict[str, Any]]:
        with self.store.connection() as conn:
            rows = conn.execute(
                "SELECT * FROM principal_partition_acl WHERE principal_id = ? ORDER BY partition_key",
                (principal_id,),
            ).fetchall()
        return [self._serialize_acl(dict(row)) for row in rows]

    def get_record(self, record_id: str) -> dict[str, Any]:
        with self.store.connection() as conn:
            row = conn.execute(
                "SELECT * FROM records WHERE id = ?",
                (record_id,),
            ).fetchone()
        if row is None:
            raise HubError(f"Unknown record: {record_id}")
        return self._serialize_record(dict(row))

    def update_record(self, record_id: str, payload: UpdateRecordRequest) -> dict[str, Any]:
        updated_fields = set(payload.model_fields_set)
        if not updated_fields:
            return self.get_record(record_id)

        timestamp = now_iso()
        with self.store.connection() as conn:
            row = conn.execute(
                "SELECT * FROM records WHERE id = ?",
                (record_id,),
            ).fetchone()
            if row is None:
                raise HubError(f"Unknown record: {record_id}")
            record = dict(row)
            self._assert_tenant(conn, record["tenant_id"])
            self._assert_partition(conn, record["tenant_id"], record["partition_key"])

            if "type" in updated_fields and payload.type is not None:
                record["type"] = normalize_key(payload.type)
            if "layer" in updated_fields and payload.layer is not None:
                record["layer"] = normalize_key(payload.layer)
            if "title" in updated_fields and payload.title is not None:
                record["title"] = payload.title.strip()
            if "text" in updated_fields and payload.text is not None:
                record["text"] = payload.text.strip()
            if "source" in updated_fields:
                record["source"] = to_json(payload.source) if payload.source is not None else None
            if "tags" in updated_fields and payload.tags is not None:
                record["tags"] = to_json([item.strip() for item in payload.tags if item.strip()])
            if "metadata" in updated_fields and payload.metadata is not None:
                record["metadata"] = to_json(payload.metadata)
            if "manual_summary" in updated_fields and payload.manual_summary is not None:
                record["manual_summary"] = payload.manual_summary.strip()
            if "importance" in updated_fields and payload.importance is not None:
                record["importance"] = clamp(float(payload.importance), 0.0, 5.0)
            if "pinned" in updated_fields and payload.pinned is not None:
                record["pinned"] = int(payload.pinned)
            record["updated_at"] = timestamp

            conn.execute(
                """
                UPDATE records
                SET type = ?, layer = ?, title = ?, text = ?, source = ?, tags = ?, metadata = ?,
                    manual_summary = ?, importance = ?, pinned = ?, updated_at = ?
                WHERE id = ?
                """,
                (
                    record["type"],
                    record["layer"],
                    record["title"],
                    record["text"],
                    record.get("source"),
                    record["tags"],
                    record["metadata"],
                    record["manual_summary"],
                    record["importance"],
                    record["pinned"],
                    record["updated_at"],
                    record_id,
                ),
            )

            if "text" in updated_fields and payload.text is not None:
                chunks = split_into_chunks(record["text"])
                embeddings = self._safe_embed(chunks)
                conn.execute("DELETE FROM chunks WHERE record_id = ?", (record_id,))
                for index, chunk_text in enumerate(chunks):
                    vector = embeddings[index] if embeddings and index < len(embeddings) else None
                    conn.execute(
                        """
                        INSERT INTO chunks (id, record_id, tenant_id, partition_key, chunk_index, text, vector, created_at)
                        VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                        """,
                        (
                            create_id("chunk"),
                            record_id,
                            record["tenant_id"],
                            record["partition_key"],
                            index,
                            chunk_text,
                            to_json(vector) if vector is not None else None,
                            timestamp,
                        ),
                    )

        return self._serialize_record(record)

    def read_record_lines(self, record_id: str, *, line_start: int = 1, line_limit: int = 80) -> dict[str, Any]:
        record = self.get_record(record_id)
        lines = record["text"].splitlines()
        start = max(line_start, 1)
        limit = max(min(line_limit, 500), 1)
        start_index = start - 1
        selected = lines[start_index : start_index + limit]
        return {
            "record": record,
            "fromLine": start,
            "limit": limit,
            "totalLines": len(lines),
            "returnedLines": len(selected),
            "hasMore": start_index + len(selected) < len(lines),
            "items": [
                {"lineNumber": start_index + index + 1, "text": text}
                for index, text in enumerate(selected)
            ],
        }

    def list_records(
        self,
        payload: ListRecordsRequest,
        *,
        partition_layer_rules: dict[str, set[str]] | None = None,
    ) -> dict[str, Any]:
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
                    "page": {
                        "offset": max(payload.offset, 0),
                        "limit": max(min(payload.limit, 200), 1),
                        "returned": 0,
                        "totalMatched": 0,
                        "hasMore": False,
                    },
                }

            types = [normalize_key(item) for item in payload.types if item.strip()]
            layers = [normalize_key(item) for item in payload.layers if item.strip()]
            clauses = ["tenant_id = ?"]
            parameters: list[Any] = [payload.tenant_id]

            partition_placeholders = ", ".join("?" for _ in partition_keys)
            clauses.append(f"partition_key IN ({partition_placeholders})")
            parameters.extend(partition_keys)

            if types:
                type_placeholders = ", ".join("?" for _ in types)
                clauses.append(f"type IN ({type_placeholders})")
                parameters.extend(types)

            if layers:
                layer_placeholders = ", ".join("?" for _ in layers)
                clauses.append(f"layer IN ({layer_placeholders})")
                parameters.extend(layers)

            rows = conn.execute(
                f"SELECT * FROM records WHERE {' AND '.join(clauses)} ORDER BY updated_at DESC, created_at DESC",
                parameters,
            ).fetchall()

        tag_filters = {normalize_key(item) for item in payload.tags if item.strip()}
        title_contains = (payload.title_contains or "").strip().lower()
        source_kind = normalize_key(payload.source_kind) if payload.source_kind else None
        source_path_prefix = (payload.source_path_prefix or "").strip().lower()

        filtered: list[dict[str, Any]] = []
        for row in rows:
            partition_key = str(row["partition_key"])
            if partition_layer_rules is not None:
                allowed_layers = partition_layer_rules.get(partition_key)
                if not allowed_layers or str(row["layer"]) not in allowed_layers:
                    continue

            record = self._serialize_record(dict(row))
            source = record.get("source") if isinstance(record.get("source"), dict) else {}
            record_tags = {normalize_key(item) for item in record.get("tags", [])}
            source_paths = [
                str(source.get("path", "")).lower(),
                str(source.get("relativePath", "")).lower(),
            ]

            if tag_filters and not (record_tags & tag_filters):
                continue
            if title_contains and title_contains not in record["title"].lower():
                continue
            if source_kind and normalize_key(str(source.get("kind", ""))) != source_kind:
                continue
            if source_path_prefix and not any(path.startswith(source_path_prefix) for path in source_paths if path):
                continue

            lines = record["text"].splitlines()
            filtered.append(
                {
                    "id": record["id"],
                    "tenantId": record["tenantId"],
                    "partitionKey": record["partitionKey"],
                    "type": record["type"],
                    "layer": record["layer"],
                    "title": record["title"],
                    "manualSummary": record["manualSummary"],
                    "tags": record["tags"],
                    "source": record["source"],
                    "lineCount": len(lines),
                    "textPreview": record["text"][:240],
                    "importance": record["importance"],
                    "pinned": record["pinned"],
                    "createdAt": record["createdAt"],
                    "updatedAt": record["updatedAt"],
                }
            )

        offset = max(payload.offset, 0)
        limit = max(min(payload.limit, 200), 1)
        items = filtered[offset : offset + limit]
        return {
            "items": items,
            "page": {
                "offset": offset,
                "limit": limit,
                "returned": len(items),
                "totalMatched": len(filtered),
                "hasMore": offset + len(items) < len(filtered),
            },
        }

    def browse_record_tree(
        self,
        payload: BrowseTreeRequest,
        *,
        partition_layer_rules: dict[str, set[str]] | None = None,
    ) -> dict[str, Any]:
        listed = self.list_records(
            ListRecordsRequest(
                tenantId=payload.tenant_id,
                partitions=payload.partitions,
                types=payload.types,
                layers=payload.layers,
                sourceKind=payload.source_kind,
                sourcePathPrefix=payload.path_prefix,
                offset=0,
                limit=100000,
            ),
            partition_layer_rules=partition_layer_rules,
        )
        prefix = (payload.path_prefix or "").strip().strip("/")
        nodes: dict[str, dict[str, Any]] = {}
        for item in listed["items"]:
            source = item.get("source") if isinstance(item.get("source"), dict) else {}
            candidate_path = str(source.get("relativePath") or source.get("path") or "").replace("\\", "/").strip("/")
            if not candidate_path:
                continue
            relative = candidate_path
            if prefix:
                if candidate_path == prefix:
                    relative = ""
                elif candidate_path.startswith(prefix + "/"):
                    relative = candidate_path[len(prefix) + 1 :]
                else:
                    continue
            if not relative:
                continue
            head = relative.split("/", 1)[0]
            is_dir = "/" in relative
            node_path = posixpath.join(prefix, head) if prefix else head
            node = nodes.setdefault(
                node_path,
                {
                    "name": head,
                    "path": node_path,
                    "kind": "dir" if is_dir else "file",
                    "recordCount": 0,
                    "layers": {},
                    "partitions": {},
                },
            )
            if is_dir:
                node["kind"] = "dir"
            node["recordCount"] += 1
            node["layers"][item["layer"]] = node["layers"].get(item["layer"], 0) + 1
            node["partitions"][item["partitionKey"]] = node["partitions"].get(item["partitionKey"], 0) + 1

        limit = max(min(payload.limit, 500), 1)
        items = sorted(nodes.values(), key=lambda item: (item["kind"], item["name"]))[:limit]
        return {
            "pathPrefix": prefix,
            "items": items,
            "summary": {
                "nodeCount": len(items),
                "totalMatchedRecords": listed["page"]["totalMatched"],
                "limited": len(nodes) > limit,
            },
        }

    def grep_records(
        self,
        payload: GrepRequest,
        *,
        partition_layer_rules: dict[str, set[str]] | None = None,
    ) -> dict[str, Any]:
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
                    "search": {
                        "scannedRecords": 0,
                        "matchedRecords": 0,
                        "returnedMatches": 0,
                    },
                }

            types = [normalize_key(item) for item in payload.types if item.strip()]
            layers = [normalize_key(item) for item in payload.layers if item.strip()]
            clauses = ["tenant_id = ?"]
            parameters: list[Any] = [payload.tenant_id]

            partition_placeholders = ", ".join("?" for _ in partition_keys)
            clauses.append(f"partition_key IN ({partition_placeholders})")
            parameters.extend(partition_keys)

            if types:
                type_placeholders = ", ".join("?" for _ in types)
                clauses.append(f"type IN ({type_placeholders})")
                parameters.extend(types)

            if layers:
                layer_placeholders = ", ".join("?" for _ in layers)
                clauses.append(f"layer IN ({layer_placeholders})")
                parameters.extend(layers)

            rows = conn.execute(
                f"SELECT * FROM records WHERE {' AND '.join(clauses)} ORDER BY updated_at DESC",
                parameters,
            ).fetchall()

        filtered_rows = []
        for row in rows:
            if partition_layer_rules is None:
                filtered_rows.append(row)
                continue
            partition_key = str(row["partition_key"])
            allowed_layers = partition_layer_rules.get(partition_key)
            if not allowed_layers:
                continue
            if str(row["layer"]) not in allowed_layers:
                continue
            filtered_rows.append(row)

        flags = 0 if payload.case_sensitive else re.IGNORECASE
        pattern = payload.pattern if payload.regex else re.escape(payload.pattern)
        compiled = re.compile(pattern, flags)
        limit = max(min(payload.limit or 20, 500), 1)
        before_context = max(min(payload.before_context, 20), 0)
        after_context = max(min(payload.after_context, 20), 0)

        items: list[dict[str, Any]] = []
        matched_records = 0
        for row in filtered_rows:
            record = self._serialize_record(dict(row))
            record_lines = record["text"].splitlines()
            record_matches = 0
            for line_number, line_text in enumerate(record_lines, start=1):
                matches = list(compiled.finditer(line_text))
                if not matches:
                    continue
                record_matches += 1
                before_slice = record_lines[max(0, line_number - before_context - 1) : line_number - 1]
                after_slice = record_lines[line_number : line_number + after_context]
                items.append(
                    {
                        "recordId": record["id"],
                        "title": record["title"],
                        "type": record["type"],
                        "layer": record["layer"],
                        "partitionKey": record["partitionKey"],
                        "lineNumber": line_number,
                        "text": line_text,
                        "matchCount": len(matches),
                        "matchRanges": [
                            {"start": match.start(), "end": match.end()}
                            for match in matches
                        ],
                        "contextBefore": [
                            {
                                "lineNumber": line_number - len(before_slice) + index,
                                "text": text,
                            }
                            for index, text in enumerate(before_slice)
                        ],
                        "contextAfter": [
                            {
                                "lineNumber": line_number + index + 1,
                                "text": text,
                            }
                            for index, text in enumerate(after_slice)
                        ],
                    }
                )
                if len(items) >= limit:
                    break
            if record_matches > 0:
                matched_records += 1
            if len(items) >= limit:
                break

        return {
            "items": items,
            "search": {
                "pattern": payload.pattern,
                "regex": payload.regex,
                "caseSensitive": payload.case_sensitive,
                "scannedRecords": len(filtered_rows),
                "matchedRecords": matched_records,
                "returnedMatches": len(items),
            },
        }

    def get_derivation_job(self, job_id: str) -> dict[str, Any]:
        with self.store.connection() as conn:
            row = conn.execute(
                "SELECT * FROM derivation_jobs WHERE id = ?",
                (job_id,),
            ).fetchone()
        if row is None:
            raise HubError(f"Unknown derivation job: {job_id}")
        return self._serialize_derivation_job(dict(row))

    def list_record_links(self, record_id: str) -> list[dict[str, Any]]:
        with self.store.connection() as conn:
            rows = conn.execute(
                "SELECT * FROM record_links WHERE source_record_id = ? ORDER BY created_at, target_record_id",
                (record_id,),
            ).fetchall()
        return [self._serialize_record_link(dict(row)) for row in rows]

    def import_resource(
        self,
        payload: ImportResourceRequest,
        *,
        schedule_async: Callable[[str], None] | None = None,
    ) -> dict[str, Any]:
        if payload.content.kind != "inline_text":
            raise HubError("Only content.kind=inline_text is implemented in the current MVP")
        if not payload.content.text or not payload.content.text.strip():
            raise HubError("content.text is required for content.kind=inline_text")

        source_record = self.create_record(
            CreateRecordRequest(
                tenantId=payload.tenant_id,
                partitionKey=payload.partition_key,
                type=payload.type,
                layer=payload.target_layer,
                title=payload.title,
                text=payload.content.text,
                source=payload.source,
                tags=payload.tags,
                metadata={**payload.metadata, "importKind": payload.content.kind},
                manualSummary=payload.manual_summary,
                importance=payload.importance,
                pinned=payload.pinned,
                idempotencyKey=payload.idempotency_key,
            )
        )

        derivation = {
            "status": "disabled",
            "mode": payload.derive.mode,
            "effectiveMode": payload.derive.mode,
            "plannedLayers": payload.derive.emit_layers,
            "job": None,
            "records": [],
            "links": [],
        }

        if payload.derive.enabled:
            requested_async = payload.derive.mode == "async"
            effective_mode = "async" if requested_async and schedule_async is not None else "sync"
            job = self._create_derivation_job(
                payload,
                source_record,
                status="queued" if effective_mode == "async" else "running",
                effective_mode=effective_mode,
            )

            if effective_mode == "async":
                schedule_async(job["id"])
                derivation = {
                    "status": "queued",
                    "mode": payload.derive.mode,
                    "effectiveMode": effective_mode,
                    "plannedLayers": payload.derive.emit_layers,
                    "job": job,
                    "records": [],
                    "links": [],
                }
            else:
                job = self.run_derivation_job(job["id"], max_attempts=1)
                if job["status"] != "completed":
                    raise HubError(job.get("errorMessage") or "Derivation failed")
                derived_record_ids = job["metadata"].get("derivedRecordIds", [])
                derivation = {
                    "status": job["status"],
                    "mode": payload.derive.mode,
                    "effectiveMode": effective_mode,
                    "plannedLayers": payload.derive.emit_layers,
                    "job": job,
                    "records": [self.get_record(record_id) for record_id in derived_record_ids],
                    "links": self.list_record_links(source_record["id"]),
                }

        return {
            "record": source_record,
            "derivation": derivation,
        }

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

    def query(
        self,
        payload: QueryRequest,
        *,
        partition_layer_rules: dict[str, set[str]] | None = None,
    ) -> dict[str, Any]:
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

        filtered_rows = []
        for row in rows:
            if partition_layer_rules is None:
                filtered_rows.append(row)
                continue

            partition_key = str(row["partition_key"])
            allowed_layers = partition_layer_rules.get(partition_key)
            if not allowed_layers:
                continue
            row_layer = str(row["layer"])
            if row_layer not in allowed_layers:
                continue
            filtered_rows.append(row)

        query_vector_list = self._safe_embed([payload.query])
        query_vector = query_vector_list[0] if query_vector_list else None
        retrieval = self.config.retrieval
        scored: list[dict[str, Any]] = []

        for row in filtered_rows:
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
                "candidateCount": len(filtered_rows),
                "scoredCount": len(scored),
                "usedEmbeddings": bool(query_vector),
                "usedRerank": any(item["trace"]["rerank"] is not None for item in items),
            },
        }

    def run_derivation_job(self, job_id: str, *, max_attempts: int = 2) -> dict[str, Any]:
        row = self._get_derivation_job_row(job_id)
        source_record = self.get_record(row["source_record_id"])
        effective_mode = row.get("effective_mode") or "sync"
        attempts = max(1, max_attempts)
        last_error = None

        for attempt in range(1, attempts + 1):
            self._update_derivation_job(
                job_id,
                status="running",
                effective_mode=effective_mode,
                error_message=None,
                metadata={"attemptCount": attempt},
                finished_at=None,
            )
            try:
                payload = self._build_import_request_from_job(row, source_record)
                derived_records = self._derive_records(payload, source_record)
                links = [
                    self._create_record_link(
                        tenant_id=source_record["tenantId"],
                        source_record_id=source_record["id"],
                        target_record_id=record["id"],
                        relation="derived_from",
                        metadata={
                            "jobId": job_id,
                            "sourceLayer": source_record["layer"],
                            "targetLayer": record["layer"],
                        },
                    )
                    for record in derived_records
                ]
                return self._update_derivation_job(
                    job_id,
                    status="completed",
                    effective_mode=effective_mode,
                    metadata={
                        "attemptCount": attempt,
                        "derivedRecordIds": [record["id"] for record in derived_records],
                        "linkIds": [link["id"] for link in links],
                    },
                    finished_at=now_iso(),
                )
            except Exception as error:
                last_error = str(error)

        return self._update_derivation_job(
            job_id,
            status="failed",
            effective_mode=effective_mode,
            error_message=last_error,
            metadata={"attemptCount": attempts},
            finished_at=now_iso(),
        )

    def _get_derivation_job_row(self, job_id: str) -> dict[str, Any]:
        with self.store.connection() as conn:
            row = conn.execute(
                "SELECT * FROM derivation_jobs WHERE id = ?",
                (job_id,),
            ).fetchone()
        if row is None:
            raise HubError(f"Unknown derivation job: {job_id}")
        return dict(row)

    def _build_import_request_from_job(
        self,
        job: dict[str, Any],
        source_record: dict[str, Any],
    ) -> ImportResourceRequest:
        metadata = from_json(job.get("metadata"), {})
        return ImportResourceRequest(
            tenantId=job["tenant_id"],
            partitionKey=job["partition_key"],
            type=metadata.get("recordType", "resource"),
            targetLayer=source_record["layer"],
            title=source_record["title"],
            content={"kind": "inline_text", "text": source_record["text"]},
            source=metadata.get("source"),
            tags=metadata.get("tags", []),
            metadata=metadata.get("baseMetadata", {}),
            derive={
                "enabled": True,
                "mode": job["mode"],
                "emitLayers": from_json(job.get("requested_layers"), []),
                "strategy": metadata.get("strategy", "preserve_manual"),
                "promptPreset": job["prompt_preset"],
                "provider": job["provider"],
                "model": job.get("model"),
            },
        )

    def _create_derivation_job(
        self,
        payload: ImportResourceRequest,
        source_record: dict[str, Any],
        *,
        status: str,
        effective_mode: str,
    ) -> dict[str, Any]:
        timestamp = now_iso()
        job = {
            "id": create_id("derive"),
            "tenant_id": payload.tenant_id,
            "partition_key": normalize_key(payload.partition_key),
            "source_record_id": source_record["id"],
            "status": status,
            "mode": payload.derive.mode,
            "effective_mode": effective_mode,
            "requested_layers": to_json([normalize_key(layer) for layer in payload.derive.emit_layers]),
            "provider": payload.derive.provider,
            "model": payload.derive.model or self.config.abstraction.model,
            "prompt_preset": payload.derive.prompt_preset,
            "error_message": None,
            "metadata": to_json(
                {
                    "strategy": payload.derive.strategy,
                    "baseMetadata": payload.metadata,
                    "tags": payload.tags,
                    "source": payload.source,
                    "recordType": payload.type,
                    "attemptCount": 0,
                    "derivedRecordIds": [],
                    "linkIds": [],
                }
            ),
            "created_at": timestamp,
            "updated_at": timestamp,
            "finished_at": None,
        }
        with self.store.connection() as conn:
            conn.execute(
                """
                INSERT INTO derivation_jobs (
                  id, tenant_id, partition_key, source_record_id, status, mode, effective_mode,
                  requested_layers, provider, model, prompt_preset, error_message, metadata,
                  created_at, updated_at, finished_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    job["id"],
                    job["tenant_id"],
                    job["partition_key"],
                    job["source_record_id"],
                    job["status"],
                    job["mode"],
                    job["effective_mode"],
                    job["requested_layers"],
                    job["provider"],
                    job["model"],
                    job["prompt_preset"],
                    job["error_message"],
                    job["metadata"],
                    job["created_at"],
                    job["updated_at"],
                    job["finished_at"],
                ),
            )
        return self._serialize_derivation_job(job)

    def _update_derivation_job(
        self,
        job_id: str,
        *,
        status: str,
        effective_mode: str | None,
        error_message: str | None = None,
        metadata: dict[str, Any] | None = None,
        finished_at: str | None = None,
    ) -> dict[str, Any]:
        timestamp = now_iso()
        with self.store.connection() as conn:
            row = conn.execute(
                "SELECT * FROM derivation_jobs WHERE id = ?",
                (job_id,),
            ).fetchone()
            if row is None:
                raise HubError(f"Unknown derivation job: {job_id}")
            existing = dict(row)
            merged_metadata = from_json(existing.get("metadata"), {})
            if metadata:
                merged_metadata.update(metadata)
            conn.execute(
                """
                UPDATE derivation_jobs
                SET status = ?, effective_mode = ?, error_message = ?, metadata = ?, updated_at = ?, finished_at = ?
                WHERE id = ?
                """,
                (
                    status,
                    effective_mode,
                    error_message,
                    to_json(merged_metadata),
                    timestamp,
                    finished_at,
                    job_id,
                ),
            )
            updated = conn.execute(
                "SELECT * FROM derivation_jobs WHERE id = ?",
                (job_id,),
            ).fetchone()
        return self._serialize_derivation_job(dict(updated))

    def _create_record_link(
        self,
        *,
        tenant_id: str,
        source_record_id: str,
        target_record_id: str,
        relation: str,
        metadata: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        timestamp = now_iso()
        payload = {
            "id": create_id("link"),
            "tenant_id": tenant_id,
            "source_record_id": source_record_id,
            "target_record_id": target_record_id,
            "relation": normalize_key(relation),
            "metadata": to_json(metadata or {}),
            "created_at": timestamp,
        }
        with self.store.connection() as conn:
            existing = conn.execute(
                "SELECT * FROM record_links WHERE source_record_id = ? AND target_record_id = ? AND relation = ?",
                (source_record_id, target_record_id, payload["relation"]),
            ).fetchone()
            if existing is not None:
                existing_link = dict(existing)
                if metadata:
                    merged_metadata = from_json(existing_link.get("metadata"), {})
                    merged_metadata.update(metadata)
                    conn.execute(
                        "UPDATE record_links SET metadata = ? WHERE id = ?",
                        (to_json(merged_metadata), existing_link["id"]),
                    )
                    existing_link["metadata"] = to_json(merged_metadata)
                return self._serialize_record_link(existing_link)
            conn.execute(
                """
                INSERT INTO record_links (id, tenant_id, source_record_id, target_record_id, relation, metadata, created_at)
                VALUES (?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    payload["id"],
                    payload["tenant_id"],
                    payload["source_record_id"],
                    payload["target_record_id"],
                    payload["relation"],
                    payload["metadata"],
                    payload["created_at"],
                ),
            )
        return self._serialize_record_link(payload)

    def _derive_records(self, payload: ImportResourceRequest, source_record: dict[str, Any]) -> list[dict[str, Any]]:
        if payload.derive.provider.lower() != "litellm":
            raise HubError("Only derive.provider=litellm is implemented in the current MVP")
        if self.abstractor is None:
            raise HubError("Abstraction client is not configured")

        requested_layers = [normalize_key(layer) for layer in payload.derive.emit_layers]
        requested_layers = [layer for layer in requested_layers if layer != source_record["layer"]]
        if not requested_layers:
            return []

        derived_payload = self.abstractor.derive(
            title=source_record["title"],
            text=source_record["text"],
            source_layer=source_record["layer"],
            emit_layers=requested_layers,
            prompt_preset=payload.derive.prompt_preset,
            model=payload.derive.model,
        )

        created_records = []
        for layer in requested_layers:
            layer_payload = derived_payload.get(layer)
            if not isinstance(layer_payload, dict):
                continue

            derived_text = str(layer_payload.get("text", "")).strip()
            if not derived_text:
                continue

            default_type = "summary" if layer == "l1" else "memory"
            metadata = {
                **payload.metadata,
                "derivedFromRecordId": source_record["id"],
                "derivationProvider": payload.derive.provider,
                "derivationModel": payload.derive.model or self.config.abstraction.model,
                "derivationPromptPreset": payload.derive.prompt_preset,
                "managedByDerivation": True,
            }
            record = self.create_record(
                CreateRecordRequest(
                    tenantId=payload.tenant_id,
                    partitionKey=payload.partition_key,
                    type=layer_payload.get("type", default_type),
                    layer=layer,
                    title=layer_payload.get("title", f"{source_record['title']} ({layer.upper()})"),
                    text=derived_text,
                    source={
                        "kind": "derived",
                        "originRecordId": source_record["id"],
                        "source": payload.source,
                    },
                    tags=layer_payload.get("tags", payload.tags),
                    metadata=metadata,
                    manualSummary=layer_payload.get("manualSummary", ""),
                    importance=self._coerce_importance(layer_payload.get("importance", 3.0)),
                    pinned=bool(layer_payload.get("pinned", False)),
                    idempotencyKey=f"derive:{source_record['id']}:{layer}:{payload.derive.prompt_preset}",
                )
            )
            created_records.append(record)

        return created_records

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

    def _coerce_importance(self, value: Any, default: float = 3.0) -> float:
        if value is None or isinstance(value, bool):
            return default
        if isinstance(value, (int, float)):
            return float(value)
        if isinstance(value, str):
            normalized = value.strip().lower()
            if not normalized:
                return default
            mapped = {
                "low": 2.0,
                "medium": 3.0,
                "med": 3.0,
                "high": 4.0,
                "critical": 5.0,
            }.get(normalized)
            if mapped is not None:
                return mapped
            try:
                return float(normalized)
            except ValueError:
                return default
        return default

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

    def _serialize_principal(self, principal: dict[str, Any]) -> dict[str, Any]:
        return {
            "id": principal["id"],
            "tenantId": principal["tenant_id"],
            "name": principal["name"],
            "kind": principal["kind"],
            "metadata": from_json(principal.get("metadata"), {}),
            "disabled": bool(principal.get("disabled", 0)),
            "createdAt": principal["created_at"],
            "lastUsedAt": principal.get("last_used_at"),
        }

    def _serialize_acl(self, acl: dict[str, Any]) -> dict[str, Any]:
        return {
            "id": acl["id"],
            "principalId": acl["principal_id"],
            "tenantId": acl["tenant_id"],
            "partitionKey": acl["partition_key"],
            "canRead": bool(acl["can_read"]),
            "canWrite": bool(acl["can_write"]),
            "allowedLayers": from_json(acl.get("allowed_layers"), ["l0", "l1", "l2"]),
            "createdAt": acl["created_at"],
            "updatedAt": acl["updated_at"],
        }

    def _serialize_derivation_job(self, job: dict[str, Any]) -> dict[str, Any]:
        return {
            "id": job["id"],
            "tenantId": job["tenant_id"],
            "partitionKey": job["partition_key"],
            "sourceRecordId": job["source_record_id"],
            "status": job["status"],
            "mode": job["mode"],
            "effectiveMode": job.get("effective_mode"),
            "requestedLayers": from_json(job.get("requested_layers"), []),
            "provider": job["provider"],
            "model": job.get("model"),
            "promptPreset": job["prompt_preset"],
            "errorMessage": job.get("error_message"),
            "metadata": from_json(job.get("metadata"), {}),
            "createdAt": job["created_at"],
            "updatedAt": job["updated_at"],
            "finishedAt": job.get("finished_at"),
        }

    def _serialize_record_link(self, link: dict[str, Any]) -> dict[str, Any]:
        return {
            "id": link["id"],
            "tenantId": link["tenant_id"],
            "sourceRecordId": link["source_record_id"],
            "targetRecordId": link["target_record_id"],
            "relation": link["relation"],
            "metadata": from_json(link.get("metadata"), {}),
            "createdAt": link["created_at"],
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
