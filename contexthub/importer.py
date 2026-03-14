from __future__ import annotations

import hashlib
import json
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable, Sequence

from contexthub.client import ContextHubClient

HEADING_RE = re.compile(r"^#\s+(.+?)\s*$", re.MULTILINE)


@dataclass(slots=True)
class ImportMarkdownOptions:
    base_url: str
    token: str | None
    tenant_id: str
    partition_key: str
    layer: str
    root: Path
    file_limit: int | None = None
    derive_layers: tuple[str, ...] = ()
    prompt_preset: str = "archive_and_memory"
    derive_mode: str = "sync"
    record_type: str = "resource"
    source_kind: str = "markdown_file"
    relative_path_prefix: str | None = None
    metadata: dict[str, object] | None = None
    dry_run: bool = False
    tags: tuple[str, ...] = ()


def extract_markdown_title(content: str, fallback_name: str) -> str:
    match = HEADING_RE.search(content)
    if match:
        return match.group(1).strip()
    return fallback_name


def make_file_idempotency_key(relative_path: str, layer: str) -> str:
    digest = hashlib.sha1(relative_path.encode("utf-8")).hexdigest()[:16]
    return f"file-import:{layer}:{digest}"


def discover_markdown_files(root: Path) -> list[Path]:
    return sorted(path for path in root.rglob("*.md") if path.is_file())


def build_effective_relative_path(relative_path: str, prefix: str | None) -> str:
    normalized_prefix = (prefix or "").strip().strip("/")
    return relative_path if not normalized_prefix else f"{normalized_prefix}/{relative_path}"


def build_import_payload(path: Path, *, root: Path, options: ImportMarkdownOptions) -> dict:
    relative_path = path.relative_to(root).as_posix()
    effective_relative_path = build_effective_relative_path(relative_path, options.relative_path_prefix)
    content = path.read_text(encoding="utf-8")
    title = extract_markdown_title(content, path.stem)
    derive_enabled = bool(options.derive_layers)
    metadata = {
        "importJob": "markdown",
        "relativePath": effective_relative_path,
        **(options.metadata or {}),
    }
    if effective_relative_path != relative_path:
        metadata["originalRelativePath"] = relative_path

    return {
        "tenantId": options.tenant_id,
        "partitionKey": options.partition_key,
        "type": options.record_type,
        "targetLayer": options.layer,
        "title": title,
        "content": {
            "kind": "inline_text",
            "text": content,
        },
        "source": {
            "kind": options.source_kind,
            "path": str(path),
            "relativePath": effective_relative_path,
        },
        "tags": list(options.tags),
        "metadata": metadata,
        "idempotencyKey": make_file_idempotency_key(effective_relative_path, options.layer),
        "derive": {
            "enabled": derive_enabled,
            "mode": options.derive_mode,
            "emitLayers": list(options.derive_layers),
            "provider": "litellm",
            "promptPreset": options.prompt_preset,
        },
    }


def import_markdown_tree(
    options: ImportMarkdownOptions,
    *,
    client: ContextHubClient | None = None,
) -> dict:
    resolved_root = options.root.expanduser().resolve()
    files = discover_markdown_files(resolved_root)
    if options.file_limit is not None:
        files = files[: options.file_limit]

    effective_client = client or ContextHubClient(options.base_url, token=options.token)
    results = []

    for path in files:
        payload = build_import_payload(path, root=resolved_root, options=options)
        if options.dry_run:
            results.append({"path": str(path), "payload": payload})
            continue

        response = effective_client.import_resource(payload)
        results.append(
            {
                "path": str(path),
                "recordId": response["record"]["id"],
                "layer": response["record"]["layer"],
                "derivationStatus": response["derivation"]["status"],
                "derivedCount": len(response["derivation"]["records"]),
            }
        )

    return {
        "root": str(resolved_root),
        "count": len(results),
        "dryRun": options.dry_run,
        "results": results,
    }


def parse_derive_layers(value: str | None) -> tuple[str, ...]:
    if not value:
        return ()
    return tuple(item.strip().lower() for item in value.split(",") if item.strip())


def print_import_summary(summary: dict) -> None:
    print(json.dumps(summary, indent=2, ensure_ascii=True))
