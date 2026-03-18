from __future__ import annotations

from dataclasses import dataclass
from fnmatch import fnmatch
import math
from pathlib import Path, PurePosixPath
import re
import shutil
import time
from typing import Any

from contexthub.config import Settings
from contexthub.providers import EmbeddingClient, RerankClient
from contexthub.search_index import IndexedDocument, SearchIndex
from contexthub.uri import CtxUri, UriError, build_user_root_uri, build_workspace_uri, parse_ctx_uri


class FilesystemError(RuntimeError):
    pass


@dataclass(frozen=True)
class WorkspaceRoot:
    user_id: str
    workspace_kind: str
    agent_id: str | None
    path: Path

    @property
    def uri(self) -> str:
        return build_workspace_uri(
            user_id=self.user_id,
            workspace_kind=self.workspace_kind,
            agent_id=self.agent_id,
        )


@dataclass(frozen=True)
class SearchDocument:
    uri: str
    path: Path
    relative_path: PurePosixPath
    workspace_kind: str
    agent_id: str | None
    doc_type: str
    title: str
    body: str


class FilesystemService:
    def __init__(
        self,
        settings: Settings,
        *,
        embedder: EmbeddingClient | Any | None = None,
        reranker: RerankClient | Any | None = None,
    ):
        self.settings = settings
        self.embedder = embedder or EmbeddingClient(settings.embedding)
        self.reranker = reranker or RerankClient(settings.rerank)
        self.search_index = SearchIndex(settings, embedder=self.embedder, reranker=self.reranker)
        self._users_root.mkdir(parents=True, exist_ok=True)

    @property
    def _users_root(self) -> Path:
        return self.settings.data_dir / "users"

    def register_workspace(self, *, user_id: str, workspace_kind: str, agent_id: str | None) -> dict:
        workspace_uri = build_workspace_uri(
            user_id=user_id,
            workspace_kind=workspace_kind,
            agent_id=agent_id,
        )
        parsed = parse_ctx_uri(workspace_uri)
        root = self._workspace_root(parsed)
        root.mkdir(parents=True, exist_ok=True)
        return {
            "uri": workspace_uri,
            "workspaceKind": workspace_kind,
            "agentId": agent_id,
        }

    def mkdir(self, uri: str, *, parents: bool) -> dict:
        parsed = self._parse(uri)
        target = self._target_path(parsed)
        if parsed.is_user_root:
            target.mkdir(parents=True, exist_ok=True)
            return {"uri": parsed.raw, "created": True}
        if parsed.is_workspace_root:
            self._workspace_root(parsed).mkdir(parents=True, exist_ok=True)
            return {"uri": parsed.raw, "created": True}
        target.mkdir(parents=parents, exist_ok=True)
        return {"uri": parsed.raw, "created": True}

    def ls(self, uri: str) -> dict:
        parsed = self._parse(uri)
        target = self._target_path(parsed)
        if not target.exists():
            raise FilesystemError(f"path does not exist: {uri}")
        if not target.is_dir():
            raise FilesystemError(f"path is not a directory: {uri}")
        entries = []
        if parsed.is_user_root:
            default_root = target / "defaultWorkspace"
            if default_root.exists():
                entries.append({"name": "defaultWorkspace", "uri": f"{parsed.raw}/defaultWorkspace", "kind": "dir"})
            agent_root = target / "agentWorkspaces"
            if agent_root.exists():
                for child in sorted(agent_root.iterdir(), key=lambda item: item.name):
                    if child.is_dir():
                        entries.append(
                            {
                                "name": f"agentWorkspace/{child.name}",
                                "uri": f"{parsed.raw}/agentWorkspace/{child.name}",
                                "kind": "dir",
                            }
                        )
            return {"uri": parsed.raw, "entries": entries}

        for child in sorted(target.iterdir(), key=lambda item: (not item.is_dir(), item.name)):
            entries.append(
                {
                    "name": child.name,
                    "uri": self._child_uri(parsed, child.name),
                    "kind": "dir" if child.is_dir() else "file",
                }
            )
        return {"uri": parsed.raw, "entries": entries}

    def stat(self, uri: str) -> dict:
        parsed = self._parse(uri)
        target = self._target_path(parsed)
        if not target.exists():
            raise FilesystemError(f"path does not exist: {uri}")

        if parsed.is_user_root:
            name = parsed.user_id
            kind = "dir"
            child_count = len(self.ls(uri)["entries"])
            return {
                "uri": parsed.raw,
                "name": name,
                "kind": kind,
                "sizeBytes": None,
                "lineCount": None,
                "childCount": child_count,
            }

        name = parsed.workspace_label if parsed.is_workspace_root else target.name
        if target.is_dir():
            return {
                "uri": parsed.raw,
                "name": name,
                "kind": "dir",
                "sizeBytes": None,
                "lineCount": None,
                "childCount": len(list(target.iterdir())),
            }

        text = target.read_text(encoding="utf-8")
        return {
            "uri": parsed.raw,
            "name": name,
            "kind": "file",
            "sizeBytes": target.stat().st_size,
            "lineCount": len(text.splitlines()) if text else 0,
            "childCount": None,
        }

    def tree(self, uri: str, *, depth: int) -> dict:
        parsed = self._parse(uri)
        target = self._target_path(parsed)
        if not target.exists():
            raise FilesystemError(f"path does not exist: {uri}")

        def walk(current_path: Path, current_uri: str, remaining: int) -> dict:
            node = {
                "name": current_path.name if current_path.name else current_uri,
                "uri": current_uri,
                "kind": "dir" if current_path.is_dir() else "file",
                "children": [],
            }
            if current_path.is_dir() and remaining > 0:
                for child in sorted(current_path.iterdir(), key=lambda item: (not item.is_dir(), item.name)):
                    child_uri = f"{current_uri.rstrip('/')}/{child.name}"
                    node["children"].append(walk(child, child_uri, remaining - 1))
            return node

        return walk(target, parsed.raw, max(depth, 0))

    def read(self, uri: str) -> dict:
        parsed = self._parse(uri)
        if parsed.is_user_root or parsed.is_workspace_root:
            raise FilesystemError(f"path is not a file: {uri}")
        target = self._target_path(parsed)
        if not target.exists():
            raise FilesystemError(f"path does not exist: {uri}")
        if not target.is_file():
            raise FilesystemError(f"path is not a file: {uri}")
        text = target.read_text(encoding="utf-8")
        return {
            "uri": parsed.raw,
            "text": text,
            "lineCount": len(text.splitlines()) if text else 0,
        }

    def write(self, uri: str, *, text: str, create_parents: bool, overwrite: bool) -> dict:
        parsed = self._parse(uri)
        if parsed.is_user_root or parsed.is_workspace_root:
            raise FilesystemError("cannot write to a workspace root")
        target = self._target_path(parsed)
        if target.exists() and target.is_dir():
            raise FilesystemError(f"path is a directory: {uri}")
        if target.exists() and not overwrite:
            raise FilesystemError(f"file already exists: {uri}")
        if create_parents:
            target.parent.mkdir(parents=True, exist_ok=True)
        elif not target.parent.exists():
            raise FilesystemError(f"parent directory does not exist: {target.parent}")
        target.write_text(text, encoding="utf-8")
        self._index_uri(parsed.raw)
        return {"uri": parsed.raw, "written": True}

    def edit(self, uri: str, *, match_text: str, replace_text: str, replace_all: bool) -> dict:
        current = self.read(uri)
        text = current["text"]
        match_count = _count_substring_occurrences(text, match_text)
        if match_count == 0:
            raise FilesystemError("matchText not found")
        if match_count > 1 and not replace_all:
            raise FilesystemError("matchText matched multiple locations; set replaceAll=true")
        next_text = text.replace(match_text, replace_text, -1 if replace_all else 1)
        self.write(uri, text=next_text, create_parents=True, overwrite=True)
        return {
            "uri": uri,
            "matched": match_count,
            "replaced": match_count if replace_all else 1,
        }

    def apply_patch(self, uri: str, *, patch: str) -> dict:
        current = self.read(uri)
        current_lines = current["text"].splitlines()
        hunks = _parse_patch_hunks(patch)
        if not hunks:
            raise FilesystemError("no patch hunks found")

        applied = []
        for index, hunk in enumerate(hunks, start=1):
            preimage = [line[1:] for line in hunk if line.startswith((" ", "-"))]
            postimage = [line[1:] for line in hunk if line.startswith((" ", "+"))]
            if not preimage:
                raise FilesystemError("patch hunks must include context or removed lines")
            positions = _find_block_positions(current_lines, preimage)
            if not positions:
                raise FilesystemError(f"patch hunk {index} did not match current file")
            if len(positions) > 1:
                raise FilesystemError(f"patch hunk {index} matched multiple locations")
            start = positions[0]
            current_lines = current_lines[:start] + postimage + current_lines[start + len(preimage) :]
            applied.append(
                {
                    "index": index,
                    "startLine": start + 1,
                    "removedLines": len([line for line in hunk if line.startswith("-")]),
                    "addedLines": len([line for line in hunk if line.startswith("+")]),
                }
            )

        next_text = "\n".join(current_lines)
        self.write(uri, text=next_text, create_parents=True, overwrite=True)
        return {"uri": uri, "hunks": len(hunks), "applied": applied}

    def move(self, source_uri: str, destination_uri: str, *, create_parents: bool, overwrite: bool) -> dict:
        source = self._parse(source_uri)
        destination = self._parse(destination_uri)
        source_path = self._target_path(source)
        destination_path = self._target_path(destination)
        self._validate_mutating_uri(source)
        self._validate_mutating_uri(destination)
        if not source_path.exists():
            raise FilesystemError(f"path does not exist: {source_uri}")
        if destination_path.exists() and not overwrite:
            raise FilesystemError(f"destination already exists: {destination_uri}")
        if create_parents:
            destination_path.parent.mkdir(parents=True, exist_ok=True)
        elif not destination_path.parent.exists():
            raise FilesystemError(f"parent directory does not exist: {destination_path.parent}")
        if destination_path.exists():
            if destination_path.is_dir() and not source_path.is_dir():
                raise FilesystemError(f"destination is a directory: {destination_uri}")
            if destination_path.is_file():
                destination_path.unlink()
            else:
                shutil.rmtree(destination_path)
        shutil.move(str(source_path), str(destination_path))
        self.search_index.delete_prefix(source_uri)
        self._index_path_recursive(destination_uri)
        return {"sourceUri": source_uri, "destinationUri": destination_uri, "moved": True}

    def copy(self, source_uri: str, destination_uri: str, *, create_parents: bool, overwrite: bool) -> dict:
        source = self._parse(source_uri)
        destination = self._parse(destination_uri)
        source_path = self._target_path(source)
        destination_path = self._target_path(destination)
        self._validate_mutating_uri(source)
        self._validate_mutating_uri(destination)
        if not source_path.exists():
            raise FilesystemError(f"path does not exist: {source_uri}")
        if destination_path.exists() and not overwrite:
            raise FilesystemError(f"destination already exists: {destination_uri}")
        if create_parents:
            destination_path.parent.mkdir(parents=True, exist_ok=True)
        elif not destination_path.parent.exists():
            raise FilesystemError(f"parent directory does not exist: {destination_path.parent}")
        if destination_path.exists():
            if destination_path.is_file():
                destination_path.unlink()
            else:
                shutil.rmtree(destination_path)
        if source_path.is_dir():
            shutil.copytree(source_path, destination_path)
        else:
            shutil.copy2(source_path, destination_path)
        self._index_path_recursive(destination_uri)
        return {"sourceUri": source_uri, "destinationUri": destination_uri, "copied": True}

    def remove(self, uri: str, *, recursive: bool) -> dict:
        parsed = self._parse(uri)
        self._validate_mutating_uri(parsed)
        target = self._target_path(parsed)
        if not target.exists():
            raise FilesystemError(f"path does not exist: {uri}")
        kind = "dir" if target.is_dir() else "file"
        if target.is_file():
            target.unlink()
            self.search_index.delete_uri(uri)
            return {"uri": uri, "kind": kind, "removed": True}
        if recursive:
            shutil.rmtree(target)
            self.search_index.delete_prefix(uri)
            return {"uri": uri, "kind": kind, "removed": True}
        try:
            target.rmdir()
        except OSError as exc:
            raise FilesystemError(f"directory is not empty: {uri}; set recursive=true") from exc
        self.search_index.delete_prefix(uri)
        return {"uri": uri, "kind": kind, "removed": True}

    def search(
        self,
        *,
        user_id: str,
        query: str,
        scope_uri: str | None,
        limit: int,
        mode: str = "auto",
        expansions: list[str] | None = None,
        glob_pattern: str | None = None,
        path_prefix: str | None = None,
        workspace_mode: str = "default-only",
        doc_type_boosts: dict[str, float] | None = None,
        rerank: bool | None = None,
        explain: bool = True,
    ) -> dict:
        cleaned_query = query.strip()
        if not cleaned_query:
            raise FilesystemError("query is required")
        rewrites = _dedupe_texts([cleaned_query, *(expansions or [])])
        effective_scope_uri = self._effective_search_scope(user_id=user_id, scope_uri=scope_uri, workspace_mode=workspace_mode)
        search_mode = self._resolve_search_mode(cleaned_query, requested=mode)
        search_terms = _tokenize_search_text("\n".join(rewrites))
        default_doc_type_boosts = {"docs": 1.15, "archive": 1.08, "memory": 1.0, "tasks": 0.9}
        if doc_type_boosts:
            for key, value in doc_type_boosts.items():
                try:
                    default_doc_type_boosts[key] = float(value)
                except (TypeError, ValueError):
                    continue

        rerank_requested = self.reranker.status().get("ready") and (rerank if rerank is not None else search_mode in {"hybrid", "semantic"})
        index_result = self.search_index.search(
            user_id=user_id,
            scope_uri=effective_scope_uri,
            query=cleaned_query,
            rewrites=rewrites,
            search_terms=search_terms,
            mode=search_mode,
            workspace_mode=workspace_mode,
            doc_type_boosts=default_doc_type_boosts,
            glob_pattern=glob_pattern,
            path_prefix=path_prefix,
            rerank_requested=rerank_requested,
            explain=explain,
        )
        if index_result is not None:
            return {
                "query": query,
                "normalizedQuery": cleaned_query,
                "scopeUri": effective_scope_uri,
                "workspaceMode": workspace_mode,
                "mode": search_mode,
                "rewrites": rewrites[1:],
                "plan": {
                    "source": index_result["plan"]["source"],
                    "lexical": search_mode in {"lexical", "hybrid"},
                    "semantic": index_result["plan"]["semantic"],
                    "rerank": index_result["plan"]["rerank"],
                    "explain": explain,
                    "candidateCount": index_result["plan"]["candidateCount"],
                    "fallback": None,
                },
                "hits": index_result["hits"][: (limit or self.settings.retrieval.default_limit)],
            }

        documents = self._collect_search_documents(
            user_id=user_id,
            scope_uri=effective_scope_uri,
            glob_pattern=glob_pattern,
            path_prefix=path_prefix,
        )
        plan_fallbacks: list[str] = []
        if not documents:
            return {
                "query": query,
                "normalizedQuery": cleaned_query,
                "scopeUri": effective_scope_uri,
                "workspaceMode": workspace_mode,
                "mode": search_mode,
                "rewrites": rewrites[1:],
                "plan": {
                    "source": "live-scan",
                    "lexical": search_mode in {"lexical", "hybrid"},
                    "semantic": False,
                    "rerank": False,
                    "explain": explain,
                    "candidateCount": 0,
                    "fallback": None,
                },
                "hits": [],
            }

        lexical_rows: list[dict[str, Any]] = []
        for document in documents:
            lexical = self._lexical_signal(document=document, rewrites=rewrites, search_terms=search_terms)
            snippet, line_number = _best_snippet(document.body, rewrites=rewrites, search_terms=search_terms, max_chars=self.settings.retrieval.snippet_chars)
            lexical_rows.append(
                {
                    "document": document,
                    "lexical": lexical,
                    "snippet": snippet,
                    "lineNumber": line_number,
                    "semantic": 0.0,
                    "rerank": None,
                    "score": 0.0,
                }
            )

        semantic_ready = bool(self.embedder.status().get("ready"))
        semantic_used = False
        if search_mode in {"semantic", "hybrid"}:
            semantic_payload = [self._semantic_text(cleaned_query, rewrites=rewrites)] + [self._semantic_text(row["document"], rewrites=None) for row in lexical_rows]
            vectors = self._safe_embed(semantic_payload)
            if vectors and len(vectors) == len(semantic_payload):
                query_vector = vectors[0]
                semantic_used = True
                for index, row in enumerate(lexical_rows, start=1):
                    row["semantic"] = _cosine_similarity(query_vector, vectors[index])
            else:
                plan_fallbacks.append("semantic requested but embeddings are not ready; falling back to lexical scoring")
        elif mode == "auto" and semantic_ready:
            semantic_used = False

        if search_mode == "semantic" and not semantic_used:
            search_mode = "lexical"
        elif search_mode == "hybrid" and not semantic_used:
            search_mode = "lexical"

        for row in lexical_rows:
            document = row["document"]
            lexical_score = _saturating_score(row["lexical"]["score"])
            semantic_score = max(0.0, row["semantic"])
            if search_mode == "lexical":
                base_score = lexical_score
            elif search_mode == "semantic":
                base_score = semantic_score
            else:
                base_score = (
                    lexical_score * self.settings.retrieval.lexical_weight
                    + semantic_score * self.settings.retrieval.semantic_weight
                )
            if base_score <= 0:
                continue
            workspace_boost = self._workspace_boost(document=document, workspace_mode=workspace_mode)
            doc_boost = default_doc_type_boosts.get(document.doc_type, 1.0)
            recency = _recency_boost(document.path)
            row["score"] = base_score * workspace_boost * doc_boost + recency
            reasons = list(row["lexical"]["reasons"])
            if workspace_boost > 1.0:
                reasons.append("workspace boost: defaultWorkspace")
            if doc_boost != 1.0:
                reasons.append(f"doc type boost: {document.doc_type}")
            if semantic_used and semantic_score > 0.18:
                reasons.append(f"semantic similarity: {semantic_score:.2f}")
            row["reasons"] = reasons[:6]

        scored = [row for row in lexical_rows if row["score"] > 0]
        scored.sort(key=lambda item: item["score"], reverse=True)
        scored = scored[: self.settings.retrieval.candidate_limit]

        rerank_used = False
        if rerank_requested and scored:
            rerank_window = scored[: self.settings.retrieval.rerank_top_n]
            rerank_results = self._safe_rerank(cleaned_query, [self._rerank_text(row["document"], row["snippet"]) for row in rerank_window])
            if rerank_results:
                rerank_used = True
                rerank_map = {item["index"]: item["score"] for item in rerank_results}
                for index, row in enumerate(rerank_window):
                    rerank_score = max(0.0, rerank_map.get(index, 0.0))
                    row["rerank"] = rerank_score
                    row["score"] = row["score"] * 0.65 + rerank_score * 0.35
                    row["reasons"] = (row["reasons"] + [f"rerank score: {rerank_score:.2f}"])[:6]
            else:
                plan_fallbacks.append("rerank requested but reranker is not ready")
        elif rerank is True and not self.reranker.status().get("ready"):
            plan_fallbacks.append("rerank requested but reranker is not ready")

        scored.sort(key=lambda item: item["score"], reverse=True)
        final_limit = limit or self.settings.retrieval.default_limit
        hits = []
        for row in scored[:final_limit]:
            document = row["document"]
            hit = {
                "uri": document.uri,
                "title": document.title,
                "kind": "file",
                "docType": document.doc_type,
                "workspaceKind": document.workspace_kind,
                "agentId": document.agent_id,
                "score": round(row["score"], 6),
                "snippet": row["snippet"],
                "lineNumber": row["lineNumber"],
                "reasons": row["reasons"] if explain else [],
            }
            hits.append(hit)

        return {
            "query": query,
            "normalizedQuery": cleaned_query,
            "scopeUri": effective_scope_uri,
            "workspaceMode": workspace_mode,
            "mode": search_mode,
            "rewrites": rewrites[1:],
            "plan": {
                "source": "live-scan",
                "lexical": search_mode in {"lexical", "hybrid"},
                "semantic": semantic_used,
                "rerank": rerank_used,
                "explain": explain,
                "candidateCount": len(documents),
                "fallback": "; ".join(plan_fallbacks) if plan_fallbacks else None,
            },
            "hits": hits,
        }

    def glob(self, *, user_id: str, pattern: str, scope_uri: str | None, limit: int) -> dict:
        cleaned = pattern.strip()
        if not cleaned:
            raise FilesystemError("pattern is required")
        hits = []
        for path, uri, kind, relative in self._iter_scope_nodes(user_id=user_id, scope_uri=scope_uri):
            rel_value = relative.as_posix() if relative else path.name
            if fnmatch(rel_value, cleaned) or fnmatch(path.name, cleaned):
                hits.append({"uri": uri, "kind": kind})
                if len(hits) >= limit:
                    break
        return {"pattern": pattern, "scopeUri": scope_uri, "hits": hits}

    def grep(self, *, user_id: str, pattern: str, scope_uri: str | None, limit: int, case_sensitive: bool, glob_pattern: str | None) -> dict:
        hits = self._grep_hits(
            user_id=user_id,
            pattern=pattern,
            scope_uri=scope_uri,
            limit=limit,
            case_sensitive=case_sensitive,
            glob_pattern=glob_pattern,
            regex_mode=False,
        )
        return {"pattern": pattern, "scopeUri": scope_uri, "hits": hits}

    def rg(self, *, user_id: str, pattern: str, scope_uri: str | None, limit: int, case_sensitive: bool, glob_pattern: str | None) -> dict:
        hits = self._grep_hits(
            user_id=user_id,
            pattern=pattern,
            scope_uri=scope_uri,
            limit=limit,
            case_sensitive=case_sensitive,
            glob_pattern=glob_pattern,
            regex_mode=True,
        )
        return {"pattern": pattern, "scopeUri": scope_uri, "hits": hits}

    def _parse(self, uri: str) -> CtxUri:
        try:
            return parse_ctx_uri(uri)
        except UriError as exc:
            raise FilesystemError(str(exc)) from exc

    def _workspace_root(self, parsed: CtxUri) -> Path:
        user_root = self._users_root / parsed.user_id
        if parsed.workspace_kind == "defaultWorkspace":
            return user_root / "defaultWorkspace"
        if parsed.workspace_kind == "agentWorkspace":
            return user_root / "agentWorkspaces" / str(parsed.agent_id)
        return user_root

    def _target_path(self, parsed: CtxUri) -> Path:
        root = self._workspace_root(parsed)
        if parsed.is_user_root or parsed.is_workspace_root:
            return root
        return root / Path(str(parsed.relative_path))

    def _child_uri(self, parent: CtxUri, child_name: str) -> str:
        base = parent.raw.rstrip("/")
        return f"{base}/{child_name}"

    def _all_workspace_roots(self, user_id: str) -> list[WorkspaceRoot]:
        user_root = self._users_root / user_id
        roots = [
            WorkspaceRoot(
                user_id=user_id,
                workspace_kind="defaultWorkspace",
                agent_id=None,
                path=user_root / "defaultWorkspace",
            )
        ]
        agent_root = user_root / "agentWorkspaces"
        if agent_root.exists():
            for child in sorted(agent_root.iterdir()):
                if child.is_dir():
                    roots.append(
                        WorkspaceRoot(
                            user_id=user_id,
                            workspace_kind="agentWorkspace",
                            agent_id=child.name,
                            path=child,
                        )
                    )
        return roots

    def _scope_roots(self, parsed: CtxUri) -> list[WorkspaceRoot]:
        if parsed.is_user_root:
            return self._all_workspace_roots(parsed.user_id)
        return [
            WorkspaceRoot(
                user_id=parsed.user_id,
                workspace_kind=parsed.workspace_kind,
                agent_id=parsed.agent_id,
                path=self._workspace_root(parsed),
            )
        ]

    def _validate_mutating_uri(self, parsed: CtxUri) -> None:
        if parsed.is_user_root or parsed.is_workspace_root:
            raise FilesystemError("cannot mutate a user root or workspace root directly")

    def reindex(self, *, user_id: str, scope_uri: str | None) -> dict:
        effective_scope_uri = scope_uri or build_user_root_uri(user_id=user_id)
        documents: list[IndexedDocument] = []
        skipped = 0
        for path, uri, kind, relative in self._iter_scope_nodes(user_id=user_id, scope_uri=effective_scope_uri):
            if kind != "file":
                continue
            try:
                body = path.read_text(encoding="utf-8")
            except UnicodeDecodeError:
                skipped += 1
                continue
            documents.append(self._document_for_uri(uri=uri, path=path, body=body))
        result = self.search_index.reindex_scope(user_id=user_id, scope_uri=effective_scope_uri, documents=documents)
        return {
            "userId": user_id,
            "scopeUri": effective_scope_uri,
            "indexed": result["indexed"],
            "unchanged": result["unchanged"],
            "removed": result["removed"],
            "skipped": skipped,
        }

    def _index_uri(self, uri: str) -> None:
        parsed = self._parse(uri)
        target = self._target_path(parsed)
        if not target.exists() or not target.is_file():
            return
        try:
            body = target.read_text(encoding="utf-8")
        except UnicodeDecodeError:
            return
        self.search_index.upsert_document(self._document_for_uri(uri=uri, path=target, body=body))

    def _index_path_recursive(self, uri: str) -> None:
        parsed = self._parse(uri)
        target = self._target_path(parsed)
        if not target.exists():
            return
        if target.is_file():
            self._index_uri(uri)
            return
        for child in sorted(target.rglob("*")):
            if not child.is_file():
                continue
            relative = PurePosixPath(child.relative_to(target).as_posix())
            child_uri = f"{parsed.raw.rstrip('/')}/{relative.as_posix()}"
            self._index_uri(child_uri)

    def _document_for_uri(self, *, uri: str, path: Path, body: str) -> IndexedDocument:
        parsed = self._parse(uri)
        relative_path = parsed.relative_path.as_posix()
        doc_type = parsed.relative_path.parts[0] if parsed.relative_path.parts else "root"
        return IndexedDocument(
            uri=uri,
            user_id=parsed.user_id,
            workspace_kind=parsed.workspace_kind,
            agent_id=parsed.agent_id,
            relative_path=relative_path,
            doc_type=doc_type,
            title=_extract_title(path=path, text=body),
            body=body,
        )

    def _iter_scope_nodes(self, *, user_id: str, scope_uri: str | None):
        if scope_uri is None:
            for root in self._all_workspace_roots(user_id):
                if not root.path.exists():
                    continue
                yield from self._iter_root_nodes(root)
            return

        scope = self._parse(scope_uri)
        if scope.is_user_root:
            for root in self._all_workspace_roots(scope.user_id):
                if not root.path.exists():
                    continue
                yield from self._iter_root_nodes(root)
            return

        root = WorkspaceRoot(
            user_id=scope.user_id,
            workspace_kind=scope.workspace_kind,
            agent_id=scope.agent_id,
            path=self._workspace_root(scope),
        )
        scope_path = self._target_path(scope)
        if not scope_path.exists():
            raise FilesystemError(f"path does not exist: {scope_uri}")
        if scope_path.is_file():
            yield scope_path, scope.raw, "file", PurePosixPath(scope_path.name)
            return
        yield scope_path, scope.raw, "dir", PurePosixPath(".")
        for child in sorted(scope_path.rglob("*")):
            relative = PurePosixPath(child.relative_to(scope_path).as_posix())
            child_uri = f"{scope.raw.rstrip('/')}/{relative.as_posix()}"
            yield child, child_uri, ("dir" if child.is_dir() else "file"), relative

    def _iter_root_nodes(self, root: WorkspaceRoot):
        yield root.path, root.uri, "dir", PurePosixPath(".")
        for path in sorted(root.path.rglob("*")):
            relative = PurePosixPath(path.relative_to(root.path).as_posix())
            yield path, self._path_to_uri(root, path), ("dir" if path.is_dir() else "file"), relative

    def _grep_hits(
        self,
        *,
        user_id: str,
        pattern: str,
        scope_uri: str | None,
        limit: int,
        case_sensitive: bool,
        glob_pattern: str | None,
        regex_mode: bool,
    ) -> list[dict]:
        cleaned = pattern.strip()
        if not cleaned:
            raise FilesystemError("pattern is required")
        flags = 0 if case_sensitive else re.IGNORECASE
        compiled = re.compile(cleaned, flags) if regex_mode else None
        literal = cleaned if case_sensitive else cleaned.lower()
        hits = []
        for path, uri, kind, relative in self._iter_scope_nodes(user_id=user_id, scope_uri=scope_uri):
            if kind != "file":
                continue
            rel_value = relative.as_posix() if relative else path.name
            if glob_pattern and not (fnmatch(rel_value, glob_pattern) or fnmatch(path.name, glob_pattern)):
                continue
            try:
                text = path.read_text(encoding="utf-8")
            except UnicodeDecodeError:
                continue
            for line_number, line in enumerate(text.splitlines(), start=1):
                matched = bool(compiled.search(line)) if compiled else (literal in (line if case_sensitive else line.lower()))
                if matched:
                    hits.append({"uri": uri, "lineNumber": line_number, "text": line})
                    if len(hits) >= limit:
                        return hits
        return hits

    def _path_to_uri(self, root: WorkspaceRoot, path: Path) -> str:
        rel = PurePosixPath(path.relative_to(root.path).as_posix())
        base = root.uri
        if str(rel) == ".":
            return base
        return f"{base}/{rel.as_posix()}"

    def _effective_search_scope(self, *, user_id: str, scope_uri: str | None, workspace_mode: str) -> str:
        if scope_uri:
            return scope_uri
        if workspace_mode == "default-only":
            return build_workspace_uri(user_id=user_id, workspace_kind="defaultWorkspace")
        if workspace_mode not in {"default-first", "user"}:
            raise FilesystemError("workspaceMode must be default-only, default-first, or user")
        return build_user_root_uri(user_id=user_id)

    def _resolve_search_mode(self, query: str, *, requested: str) -> str:
        allowed = {"lexical", "semantic", "hybrid", "auto"}
        if requested not in allowed:
            raise FilesystemError("mode must be lexical, semantic, hybrid, or auto")
        if requested != "auto":
            return requested
        if _looks_structured_query(query):
            return "lexical"
        return "hybrid" if self.embedder.status().get("ready") else "lexical"

    def _collect_search_documents(
        self,
        *,
        user_id: str,
        scope_uri: str,
        glob_pattern: str | None,
        path_prefix: str | None,
    ) -> list[SearchDocument]:
        documents: list[SearchDocument] = []
        cleaned_prefix = path_prefix.strip("/") if path_prefix else None
        for path, uri, kind, relative in self._iter_scope_nodes(user_id=user_id, scope_uri=scope_uri):
            if kind != "file":
                continue
            rel_value = relative.as_posix() if relative else path.name
            if glob_pattern and not (fnmatch(rel_value, glob_pattern) or fnmatch(path.name, glob_pattern)):
                continue
            if cleaned_prefix and not rel_value.startswith(cleaned_prefix):
                continue
            try:
                body = path.read_text(encoding="utf-8")
            except UnicodeDecodeError:
                continue
            parsed = self._parse(uri)
            doc_type = parsed.relative_path.parts[0] if parsed.relative_path.parts else "root"
            documents.append(
                SearchDocument(
                    uri=uri,
                    path=path,
                    relative_path=parsed.relative_path,
                    workspace_kind=parsed.workspace_kind,
                    agent_id=parsed.agent_id,
                    doc_type=doc_type,
                    title=_extract_title(path=path, text=body),
                    body=body,
                )
            )
        return documents

    def _lexical_signal(self, *, document: SearchDocument, rewrites: list[str], search_terms: list[str]) -> dict[str, Any]:
        title_score = _field_match_score(document.title, rewrites=rewrites, search_terms=search_terms)
        path_score = _field_match_score(document.relative_path.as_posix(), rewrites=rewrites, search_terms=search_terms)
        body_score = _field_match_score(document.body, rewrites=rewrites, search_terms=search_terms)
        score = title_score * 3.0 + path_score * 2.0 + body_score
        reasons = []
        if title_score > 0:
            reasons.append(f"title match: {document.title}")
        if path_score > 0:
            reasons.append(f"path match: {document.relative_path.as_posix()}")
        if body_score > 0:
            matched_terms = _top_matching_terms(document.body, rewrites=rewrites, search_terms=search_terms)
            if matched_terms:
                reasons.append(f"body match: {', '.join(matched_terms)}")
            else:
                reasons.append("body match")
        return {"score": score, "reasons": reasons[:3]}

    def _workspace_boost(self, *, document: SearchDocument, workspace_mode: str) -> float:
        if workspace_mode == "default-first" and document.workspace_kind == "defaultWorkspace":
            return self.settings.retrieval.default_workspace_boost
        return 1.0

    def _semantic_text(self, item: str | SearchDocument, *, rewrites: list[str] | None) -> str:
        if isinstance(item, str):
            joined = "\n".join(rewrites or [item])
            return joined[: self.settings.retrieval.semantic_max_chars]
        text = f"{item.title}\n{item.relative_path.as_posix()}\n{item.body}"
        return text[: self.settings.retrieval.semantic_max_chars]

    def _rerank_text(self, document: SearchDocument, snippet: str) -> str:
        return f"{document.title}\n{document.relative_path.as_posix()}\n{snippet}"[: self.settings.retrieval.semantic_max_chars]

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


def _count_substring_occurrences(text: str, needle: str) -> int:
    if not needle:
        return 0
    count = start = 0
    while True:
        index = text.find(needle, start)
        if index < 0:
            return count
        count += 1
        start = index + len(needle)


def _parse_patch_hunks(patch_text: str) -> list[list[str]]:
    hunks: list[list[str]] = []
    current: list[str] = []
    saw_patch_marker = False

    for raw_line in patch_text.splitlines():
        if raw_line.startswith("*** Begin Patch"):
            saw_patch_marker = True
            continue
        if raw_line.startswith("*** End Patch"):
            break
        if raw_line.startswith(("*** Update File:", "*** Delete File:", "*** Add File:", "--- ", "+++ ")):
            saw_patch_marker = True
            continue
        if raw_line.startswith("@@"):
            saw_patch_marker = True
            if current:
                hunks.append(current)
                current = []
            continue
        if raw_line.startswith("\\"):
            continue
        if raw_line.startswith((" ", "+", "-")):
            saw_patch_marker = True
            current.append(raw_line)
            continue
        if raw_line.strip() == "":
            if current:
                raise FilesystemError("blank lines inside hunks must keep a diff prefix")
            continue
        if saw_patch_marker:
            raise FilesystemError(f"invalid patch line: {raw_line}")

    if current:
        hunks.append(current)
    return hunks


def _find_block_positions(lines: list[str], needle: list[str]) -> list[int]:
    positions = []
    if not needle:
        return positions
    max_start = len(lines) - len(needle)
    for start in range(max_start + 1):
        if lines[start : start + len(needle)] == needle:
            positions.append(start)
    return positions


def _extract_title(*, path: Path, text: str) -> str:
    for line in text.splitlines():
        stripped = line.strip()
        if stripped.startswith("#"):
            return stripped.lstrip("#").strip() or path.stem
    return path.stem


def _dedupe_texts(values: list[str]) -> list[str]:
    seen: set[str] = set()
    output: list[str] = []
    for value in values:
        cleaned = value.strip()
        if not cleaned:
            continue
        key = cleaned.lower()
        if key in seen:
            continue
        seen.add(key)
        output.append(cleaned)
    return output


def _tokenize_search_text(text: str) -> list[str]:
    tokens = re.findall(r"[A-Za-z0-9_./:-]+|[\u4e00-\u9fff]+", text)
    return _dedupe_texts([token for token in tokens if len(token) >= 2])


def _field_match_score(text: str, *, rewrites: list[str], search_terms: list[str]) -> float:
    lowered = text.lower()
    score = 0.0
    for phrase in rewrites:
        count = _count_substring_occurrences(lowered, phrase.lower())
        if count:
            score += min(3.0, 1.8 * count)
    for term in search_terms:
        count = _count_substring_occurrences(lowered, term.lower())
        if count:
            score += min(2.0, 0.6 * count)
    return score


def _top_matching_terms(text: str, *, rewrites: list[str], search_terms: list[str]) -> list[str]:
    lowered = text.lower()
    matches: list[str] = []
    for value in rewrites + search_terms:
        if value.lower() in lowered and value not in matches:
            matches.append(value)
        if len(matches) >= 3:
            break
    return matches


def _best_snippet(text: str, *, rewrites: list[str], search_terms: list[str], max_chars: int) -> tuple[str, int | None]:
    lines = text.splitlines()
    best_line = None
    best_score = 0.0
    for index, line in enumerate(lines, start=1):
        stripped = line.strip()
        if not stripped:
            continue
        score = _field_match_score(stripped, rewrites=rewrites, search_terms=search_terms)
        if score > best_score:
            best_score = score
            best_line = (index, stripped)
    if best_line is not None:
        return _trim_snippet(best_line[1], max_chars=max_chars), best_line[0]
    for index, line in enumerate(lines, start=1):
        stripped = line.strip()
        if stripped:
            return _trim_snippet(stripped, max_chars=max_chars), index
    return "", None


def _trim_snippet(text: str, *, max_chars: int) -> str:
    stripped = text.strip()
    if len(stripped) <= max_chars:
        return stripped
    return stripped[: max_chars - 3].rstrip() + "..."


def _looks_structured_query(query: str) -> bool:
    if "ctx://" in query:
        return True
    if any(marker in query for marker in ["/", ":", "_", ".md", ".py", "-p "]):
        return True
    return bool(re.search(r"\b\d{3,}\b", query))


def _saturating_score(value: float) -> float:
    if value <= 0:
        return 0.0
    return 1.0 - math.exp(-value / 4.0)


def _cosine_similarity(left: list[float] | None, right: list[float] | None) -> float:
    if not left or not right or len(left) != len(right):
        return 0.0
    numerator = sum(a * b for a, b in zip(left, right))
    left_norm = math.sqrt(sum(a * a for a in left))
    right_norm = math.sqrt(sum(b * b for b in right))
    if left_norm == 0 or right_norm == 0:
        return 0.0
    return max(0.0, numerator / (left_norm * right_norm))


def _recency_boost(path: Path) -> float:
    try:
        age_seconds = max(0.0, time.time() - path.stat().st_mtime)
    except OSError:
        return 0.0
    days = age_seconds / 86400.0
    return max(0.0, 0.04 * math.exp(-days / 21.0))
