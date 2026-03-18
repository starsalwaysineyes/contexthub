from __future__ import annotations

from fnmatch import fnmatch
import json
import os
from pathlib import Path, PurePosixPath
from typing import Any

import httpx
import typer

app = typer.Typer(no_args_is_help=True, add_completion=False)


def _base_url(value: str | None) -> str:
    return (value or os.getenv("CONTEXT_HUB_BASE_URL") or "http://127.0.0.1:4040").rstrip("/")


def _user_id(value: str | None) -> str:
    resolved = (value or os.getenv("CONTEXT_HUB_USER_ID") or "").strip()
    if not resolved:
        raise typer.BadParameter("provide --user-id or set CONTEXT_HUB_USER_ID")
    return resolved


def _request(method: str, path: str, *, base_url: str, payload: dict[str, Any] | None = None, params: dict[str, Any] | None = None) -> Any:
    headers: dict[str, str] = {}
    token = os.getenv("CONTEXT_HUB_TOKEN")
    if token:
        headers["Authorization"] = f"Bearer {token}"
    response = httpx.request(
        method,
        f"{_base_url(base_url)}{path}",
        json=payload,
        params=params,
        headers=headers,
        timeout=30.0,
    )
    if response.is_error:
        raise typer.BadParameter(f"request failed: {response.status_code} {response.text}")
    return response.json()


def _print(data: Any) -> None:
    typer.echo(json.dumps(data, ensure_ascii=False, indent=2))


def _join_ctx_uri(base_uri: str, relative_path: PurePosixPath) -> str:
    if str(relative_path) == ".":
        return base_uri.rstrip("/")
    return f"{base_uri.rstrip('/')}/{relative_path.as_posix()}"


def _should_keep(relative_path: PurePosixPath, includes: list[str], excludes: list[str], hidden: bool) -> bool:
    parts = relative_path.parts
    if not hidden and any(part.startswith(".") for part in parts):
        return False
    relative_text = relative_path.as_posix()
    if includes and not any(fnmatch(relative_text, pattern) or fnmatch(relative_path.name, pattern) for pattern in includes):
        return False
    if excludes and any(fnmatch(relative_text, pattern) or fnmatch(relative_path.name, pattern) for pattern in excludes):
        return False
    return True


@app.command("register-workspace")
def register_workspace(
    user_id: str | None = typer.Option(None, "--user-id", envvar="CONTEXT_HUB_USER_ID"),
    default: bool = typer.Option(False, "--default"),
    agent_id: str | None = typer.Option(None, "--agent-id"),
    base_url: str | None = typer.Option(None, "--base-url"),
) -> None:
    user_id = _user_id(user_id)
    workspace_kind = "defaultWorkspace" if default else "agentWorkspace"
    if not default and not agent_id:
        raise typer.BadParameter("--agent-id is required unless --default is used")
    result = _request(
        "POST",
        "/v1/workspaces/register",
        base_url=base_url,
        payload={
            "userId": user_id,
            "workspaceKind": workspace_kind,
            "agentId": agent_id,
        },
    )
    _print(result)


@app.command("mkdir")
def mkdir(
    uri: str,
    parents: bool = typer.Option(True, "--parents/--no-parents"),
    base_url: str | None = typer.Option(None, "--base-url"),
) -> None:
    _print(_request("POST", "/v1/fs/mkdir", base_url=base_url, payload={"uri": uri, "parents": parents}))


@app.command("ls")
def ls(
    uri: str,
    base_url: str | None = typer.Option(None, "--base-url"),
) -> None:
    _print(_request("GET", "/v1/fs/ls", base_url=base_url, params={"uri": uri}))


@app.command("tree")
def tree(
    uri: str,
    depth: int = typer.Option(3, "--depth"),
    base_url: str | None = typer.Option(None, "--base-url"),
) -> None:
    _print(_request("GET", "/v1/fs/tree", base_url=base_url, params={"uri": uri, "depth": depth}))


@app.command("stat")
def stat(
    uri: str,
    base_url: str | None = typer.Option(None, "--base-url"),
) -> None:
    _print(_request("GET", "/v1/fs/stat", base_url=base_url, params={"uri": uri}))


@app.command("read")
def read(
    uri: str,
    base_url: str | None = typer.Option(None, "--base-url"),
) -> None:
    result = _request("GET", "/v1/fs/read", base_url=base_url, params={"uri": uri})
    typer.echo(result["text"])


@app.command("write")
def write(
    uri: str,
    text: str | None = typer.Option(None, "--text"),
    from_file: Path | None = typer.Option(None, "--from-file"),
    overwrite: bool = typer.Option(True, "--overwrite/--no-overwrite"),
    create_parents: bool = typer.Option(True, "--create-parents/--no-create-parents"),
    base_url: str | None = typer.Option(None, "--base-url"),
) -> None:
    if text is None and from_file is None:
        raise typer.BadParameter("provide --text or --from-file")
    if text is not None and from_file is not None:
        raise typer.BadParameter("use either --text or --from-file, not both")
    body = text if text is not None else from_file.read_text(encoding="utf-8")
    _print(
        _request(
            "POST",
            "/v1/fs/write",
            base_url=base_url,
            payload={
                "uri": uri,
                "text": body,
                "overwrite": overwrite,
                "createParents": create_parents,
            },
        )
    )


@app.command("edit")
def edit(
    uri: str,
    match_text: str = typer.Option(..., "--match"),
    replace_text: str = typer.Option(..., "--replace"),
    replace_all: bool = typer.Option(False, "--all"),
    base_url: str | None = typer.Option(None, "--base-url"),
) -> None:
    _print(
        _request(
            "POST",
            "/v1/fs/edit",
            base_url=base_url,
            payload={
                "uri": uri,
                "matchText": match_text,
                "replaceText": replace_text,
                "replaceAll": replace_all,
            },
        )
    )


@app.command("apply-patch")
def apply_patch(
    uri: str,
    patch_file: Path | None = typer.Option(None, "--patch-file"),
    patch_text: str | None = typer.Option(None, "--patch-text"),
    base_url: str | None = typer.Option(None, "--base-url"),
) -> None:
    if patch_file is None and patch_text is None:
        raise typer.BadParameter("provide --patch-file or --patch-text")
    if patch_file is not None and patch_text is not None:
        raise typer.BadParameter("use either --patch-file or --patch-text, not both")
    patch = patch_text if patch_text is not None else patch_file.read_text(encoding="utf-8")
    _print(_request("POST", "/v1/fs/apply_patch", base_url=base_url, payload={"uri": uri, "patch": patch}))


@app.command("mv")
def move(
    source_uri: str,
    destination_uri: str,
    overwrite: bool = typer.Option(False, "--overwrite/--no-overwrite"),
    create_parents: bool = typer.Option(True, "--create-parents/--no-create-parents"),
    base_url: str | None = typer.Option(None, "--base-url"),
) -> None:
    _print(
        _request(
            "POST",
            "/v1/fs/mv",
            base_url=base_url,
            payload={
                "sourceUri": source_uri,
                "destinationUri": destination_uri,
                "overwrite": overwrite,
                "createParents": create_parents,
            },
        )
    )


@app.command("cp")
def copy(
    source_uri: str,
    destination_uri: str,
    overwrite: bool = typer.Option(False, "--overwrite/--no-overwrite"),
    create_parents: bool = typer.Option(True, "--create-parents/--no-create-parents"),
    base_url: str | None = typer.Option(None, "--base-url"),
) -> None:
    _print(
        _request(
            "POST",
            "/v1/fs/cp",
            base_url=base_url,
            payload={
                "sourceUri": source_uri,
                "destinationUri": destination_uri,
                "overwrite": overwrite,
                "createParents": create_parents,
            },
        )
    )


@app.command("rm")
def remove(
    uri: str,
    recursive: bool = typer.Option(False, "--recursive"),
    base_url: str | None = typer.Option(None, "--base-url"),
) -> None:
    _print(_request("POST", "/v1/fs/rm", base_url=base_url, payload={"uri": uri, "recursive": recursive}))


@app.command("reindex")
def reindex(
    user_id: str | None = typer.Option(None, "--user-id", envvar="CONTEXT_HUB_USER_ID"),
    scope_uri: str | None = typer.Option(None, "--scope-uri"),
    base_url: str | None = typer.Option(None, "--base-url"),
) -> None:
    user_id = _user_id(user_id)
    _print(
        _request(
            "POST",
            "/v1/fs/reindex",
            base_url=base_url,
            payload={
                "userId": user_id,
                "scopeUri": scope_uri,
            },
        )
    )


@app.command("glob")
def glob(
    user_id: str | None = typer.Option(None, "--user-id", envvar="CONTEXT_HUB_USER_ID"),
    pattern: str = typer.Option(..., "--pattern"),
    scope_uri: str | None = typer.Option(None, "--scope-uri"),
    limit: int = typer.Option(100, "--limit"),
    base_url: str | None = typer.Option(None, "--base-url"),
) -> None:
    user_id = _user_id(user_id)
    _print(
        _request(
            "POST",
            "/v1/fs/glob",
            base_url=base_url,
            payload={
                "userId": user_id,
                "pattern": pattern,
                "scopeUri": scope_uri,
                "limit": limit,
            },
        )
    )


@app.command("grep")
def grep(
    user_id: str | None = typer.Option(None, "--user-id", envvar="CONTEXT_HUB_USER_ID"),
    pattern: str = typer.Option(..., "--pattern"),
    scope_uri: str | None = typer.Option(None, "--scope-uri"),
    limit: int = typer.Option(100, "--limit"),
    case_sensitive: bool = typer.Option(False, "--case-sensitive"),
    glob_pattern: str | None = typer.Option(None, "--glob"),
    base_url: str | None = typer.Option(None, "--base-url"),
) -> None:
    user_id = _user_id(user_id)
    _print(
        _request(
            "POST",
            "/v1/fs/grep",
            base_url=base_url,
            payload={
                "userId": user_id,
                "pattern": pattern,
                "scopeUri": scope_uri,
                "limit": limit,
                "caseSensitive": case_sensitive,
                "glob": glob_pattern,
            },
        )
    )


@app.command("rg")
def rg(
    user_id: str | None = typer.Option(None, "--user-id", envvar="CONTEXT_HUB_USER_ID"),
    pattern: str = typer.Option(..., "--pattern"),
    scope_uri: str | None = typer.Option(None, "--scope-uri"),
    limit: int = typer.Option(100, "--limit"),
    case_sensitive: bool = typer.Option(False, "--case-sensitive"),
    glob_pattern: str | None = typer.Option(None, "--glob"),
    base_url: str | None = typer.Option(None, "--base-url"),
) -> None:
    user_id = _user_id(user_id)
    _print(
        _request(
            "POST",
            "/v1/fs/rg",
            base_url=base_url,
            payload={
                "userId": user_id,
                "pattern": pattern,
                "scopeUri": scope_uri,
                "limit": limit,
                "caseSensitive": case_sensitive,
                "glob": glob_pattern,
            },
        )
    )


@app.command("search")
def search(
    user_id: str | None = typer.Option(None, "--user-id", envvar="CONTEXT_HUB_USER_ID"),
    query: str = typer.Option(..., "--query"),
    scope_uri: str | None = typer.Option(None, "--scope-uri"),
    mode: str = typer.Option("auto", "--mode"),
    expansion: list[str] = typer.Option(None, "--expansion"),
    glob_pattern: str | None = typer.Option(None, "--glob"),
    path_prefix: str | None = typer.Option(None, "--path-prefix"),
    workspace_mode: str = typer.Option("default-only", "--workspace-mode"),
    rerank: bool | None = typer.Option(None, "--rerank/--no-rerank"),
    explain: bool = typer.Option(True, "--explain/--no-explain"),
    limit: int = typer.Option(20, "--limit"),
    base_url: str | None = typer.Option(None, "--base-url"),
) -> None:
    user_id = _user_id(user_id)
    _print(
        _request(
            "POST",
            "/v1/fs/search",
            base_url=base_url,
            payload={
                "userId": user_id,
                "query": query,
                "scopeUri": scope_uri,
                "mode": mode,
                "expansions": expansion or [],
                "glob": glob_pattern,
                "pathPrefix": path_prefix,
                "workspaceMode": workspace_mode,
                "rerank": rerank,
                "explain": explain,
                "limit": limit,
            },
        )
    )


@app.command("import-tree")
def import_tree(
    source_root: Path,
    destination_uri: str,
    include: list[str] = typer.Option(None, "--include"),
    exclude: list[str] = typer.Option(None, "--exclude"),
    limit: int | None = typer.Option(None, "--limit"),
    overwrite: bool = typer.Option(True, "--overwrite/--no-overwrite"),
    hidden: bool = typer.Option(False, "--hidden"),
    dry_run: bool = typer.Option(False, "--dry-run"),
    base_url: str | None = typer.Option(None, "--base-url"),
) -> None:
    source_root = source_root.expanduser().resolve()
    if not source_root.exists() or not source_root.is_dir():
        raise typer.BadParameter("source_root must be an existing directory")

    includes = include or []
    excludes = exclude or []
    directories: set[str] = set()
    created_directories: set[str] = set()
    files: list[str] = []
    skipped: list[dict[str, str]] = []

    if not dry_run:
        _request("POST", "/v1/fs/mkdir", base_url=base_url, payload={"uri": destination_uri, "parents": True})

    for path in sorted(source_root.rglob("*")):
        relative_path = PurePosixPath(path.relative_to(source_root).as_posix())
        if not _should_keep(relative_path, includes, excludes, hidden):
            continue
        if path.is_dir():
            directories.add(_join_ctx_uri(destination_uri, relative_path))
            continue
        if limit is not None and len(files) >= limit:
            break
        try:
            text = path.read_text(encoding="utf-8")
        except UnicodeDecodeError:
            skipped.append({"path": str(path), "reason": "non-utf8"})
            continue
        target_uri = _join_ctx_uri(destination_uri, relative_path)
        for parent in reversed(relative_path.parents):
            if str(parent) == ".":
                continue
            directories.add(_join_ctx_uri(destination_uri, parent))
        files.append(target_uri)
        if not dry_run:
            for directory_uri in sorted(directories, key=lambda item: item.count("/")):
                if directory_uri in created_directories:
                    continue
                _request("POST", "/v1/fs/mkdir", base_url=base_url, payload={"uri": directory_uri, "parents": True})
                created_directories.add(directory_uri)
            _request(
                "POST",
                "/v1/fs/write",
                base_url=base_url,
                payload={
                    "uri": target_uri,
                    "text": text,
                    "overwrite": overwrite,
                    "createParents": True,
                },
            )

    directory_list = sorted(directories)
    _print(
        {
            "sourceRoot": str(source_root),
            "destinationUri": destination_uri,
            "dryRun": dry_run,
            "directoriesCreated": len(directory_list),
            "filesImported": len(files),
            "skipped": skipped,
            "sampleDirectories": directory_list[:10],
            "sampleFiles": files[:10],
        }
    )
