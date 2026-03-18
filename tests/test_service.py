from pathlib import Path

from contexthub.config import Settings
from contexthub.search_index import IndexedDocument
from contexthub.service import FilesystemService


def build_service(tmp_path: Path) -> FilesystemService:
    data_dir = tmp_path / "data"
    return FilesystemService(Settings(data_dir=data_dir, database_path=data_dir / "contexthub.db", admin_token=None))


def test_workspace_roundtrip(tmp_path: Path) -> None:
    service = build_service(tmp_path)
    workspace = service.register_workspace(user_id="alice", workspace_kind="defaultWorkspace", agent_id=None)
    assert workspace["uri"] == "ctx://alice/defaultWorkspace"
    service.register_workspace(user_id="alice", workspace_kind="agentWorkspace", agent_id="codex")

    root_listing = service.ls("ctx://alice")
    assert [entry["uri"] for entry in root_listing["entries"]] == [
        "ctx://alice/defaultWorkspace",
        "ctx://alice/agentWorkspace/codex",
    ]

    service.mkdir("ctx://alice/defaultWorkspace/tasks", parents=True)
    service.write("ctx://alice/defaultWorkspace/tasks/today.md", text="hello\nworld", create_parents=True, overwrite=True)

    listing = service.ls("ctx://alice/defaultWorkspace/tasks")
    assert listing["entries"][0]["uri"] == "ctx://alice/defaultWorkspace/tasks/today.md"

    read_back = service.read("ctx://alice/defaultWorkspace/tasks/today.md")
    assert read_back["text"] == "hello\nworld"


def test_edit_and_patch(tmp_path: Path) -> None:
    service = build_service(tmp_path)
    service.register_workspace(user_id="alice", workspace_kind="agentWorkspace", agent_id="codex")
    uri = "ctx://alice/agentWorkspace/codex/note.md"
    service.write(uri, text="alpha\nbeta\ngamma", create_parents=True, overwrite=True)

    edited = service.edit(uri, match_text="beta", replace_text="beta updated", replace_all=False)
    assert edited["replaced"] == 1
    assert service.read(uri)["text"] == "alpha\nbeta updated\ngamma"

    patched = service.apply_patch(
        uri,
        patch="""*** Begin Patch
*** Update File: note.md
@@
 alpha
-beta updated
+beta final
 gamma
*** End Patch""",
    )
    assert patched["hunks"] == 1
    assert service.read(uri)["text"] == "alpha\nbeta final\ngamma"


def test_search_across_workspaces(tmp_path: Path) -> None:
    service = build_service(tmp_path)
    service.register_workspace(user_id="alice", workspace_kind="defaultWorkspace", agent_id=None)
    service.register_workspace(user_id="alice", workspace_kind="agentWorkspace", agent_id="codex")
    service.write("ctx://alice/defaultWorkspace/shared.md", text="shared memory lives here", create_parents=True, overwrite=True)
    service.write("ctx://alice/agentWorkspace/codex/work.md", text="codex completed task here", create_parents=True, overwrite=True)

    result = service.search(user_id="alice", query="task", scope_uri=None, limit=10, workspace_mode="user")
    assert result["plan"]["source"] == "index"
    assert result["hits"][0]["uri"] == "ctx://alice/agentWorkspace/codex/work.md"


def test_search_defaults_to_default_workspace(tmp_path: Path) -> None:
    service = build_service(tmp_path)
    service.register_workspace(user_id="alice", workspace_kind="defaultWorkspace", agent_id=None)
    service.register_workspace(user_id="alice", workspace_kind="agentWorkspace", agent_id="codex")
    service.write("ctx://alice/defaultWorkspace/shared.md", text="shared note", create_parents=True, overwrite=True)
    service.write("ctx://alice/agentWorkspace/codex/work.md", text="codex task only", create_parents=True, overwrite=True)

    result = service.search(user_id="alice", query="task", scope_uri=None, limit=10)
    assert result["scopeUri"] == "ctx://alice/defaultWorkspace"
    assert result["plan"]["source"] == "index"
    assert result["hits"] == []


def test_stat_glob_grep_rg_mv_cp_rm(tmp_path: Path) -> None:
    service = build_service(tmp_path)
    service.register_workspace(user_id="alice", workspace_kind="defaultWorkspace", agent_id=None)
    service.write(
        "ctx://alice/defaultWorkspace/tasks/today.md",
        text="alpha cloud\nBeta cloud",
        create_parents=True,
        overwrite=True,
    )
    service.write(
        "ctx://alice/defaultWorkspace/tasks/log.txt",
        text="plain log",
        create_parents=True,
        overwrite=True,
    )

    stat_file = service.stat("ctx://alice/defaultWorkspace/tasks/today.md")
    assert stat_file["kind"] == "file"
    assert stat_file["lineCount"] == 2
    assert stat_file["sizeBytes"] is not None

    stat_dir = service.stat("ctx://alice/defaultWorkspace/tasks")
    assert stat_dir["kind"] == "dir"
    assert stat_dir["childCount"] == 2

    globbed = service.glob(user_id="alice", pattern="tasks/*.md", scope_uri="ctx://alice/defaultWorkspace", limit=20)
    assert globbed["hits"][0]["uri"] == "ctx://alice/defaultWorkspace/tasks/today.md"

    grepped = service.grep(
        user_id="alice",
        pattern="cloud",
        scope_uri="ctx://alice/defaultWorkspace",
        limit=20,
        case_sensitive=False,
        glob_pattern="tasks/*.md",
    )
    assert len(grepped["hits"]) == 2

    regex_hits = service.rg(
        user_id="alice",
        pattern=r"B[a-z]+ cloud",
        scope_uri="ctx://alice/defaultWorkspace",
        limit=20,
        case_sensitive=True,
        glob_pattern="tasks/*.md",
    )
    assert regex_hits["hits"][0]["text"] == "Beta cloud"

    moved = service.move(
        "ctx://alice/defaultWorkspace/tasks/today.md",
        "ctx://alice/defaultWorkspace/archive/today.md",
        create_parents=True,
        overwrite=False,
    )
    assert moved["moved"] is True

    copied = service.copy(
        "ctx://alice/defaultWorkspace/archive/today.md",
        "ctx://alice/defaultWorkspace/archive/today-copy.md",
        create_parents=True,
        overwrite=False,
    )
    assert copied["copied"] is True
    assert service.read("ctx://alice/defaultWorkspace/archive/today-copy.md")["text"].startswith("alpha cloud")

    removed_file = service.remove("ctx://alice/defaultWorkspace/archive/today-copy.md", recursive=False)
    assert removed_file["removed"] is True

    try:
        service.remove("ctx://alice/defaultWorkspace/archive", recursive=False)
    except Exception as exc:
        assert "directory is not empty" in str(exc)
    else:
        raise AssertionError("expected non-recursive remove to fail for non-empty directory")

    removed_dir = service.remove("ctx://alice/defaultWorkspace/archive", recursive=True)
    assert removed_dir["kind"] == "dir"
    assert removed_dir["removed"] is True


def test_search_workspace_mode_and_expansions(tmp_path: Path) -> None:
    service = build_service(tmp_path)
    service.register_workspace(user_id="alice", workspace_kind="defaultWorkspace", agent_id=None)
    service.register_workspace(user_id="alice", workspace_kind="agentWorkspace", agent_id="codex")
    service.write(
        "ctx://alice/defaultWorkspace/docs/note.md",
        text="# Context\nCloud filesystem migration baseline.",
        create_parents=True,
        overwrite=True,
    )
    service.write(
        "ctx://alice/agentWorkspace/codex/work.md",
        text="# Codex\nHybrid retrieval checklist with rerank.",
        create_parents=True,
        overwrite=True,
    )

    default_only = service.search(
        user_id="alice",
        query="retrieval",
        scope_uri=None,
        limit=10,
        workspace_mode="default-only",
    )
    assert default_only["scopeUri"] == "ctx://alice/defaultWorkspace"
    assert default_only["plan"]["source"] == "index"
    assert all(hit["workspaceKind"] == "defaultWorkspace" for hit in default_only["hits"])

    across_user = service.search(
        user_id="alice",
        query="migration",
        expansions=["rerank"],
        scope_uri=None,
        limit=10,
        workspace_mode="user",
        mode="lexical",
    )
    uris = [hit["uri"] for hit in across_user["hits"]]
    assert "ctx://alice/defaultWorkspace/docs/note.md" in uris
    assert "ctx://alice/agentWorkspace/codex/work.md" in uris
    assert across_user["plan"]["source"] == "index"
    assert across_user["plan"]["candidateCount"] >= 2


def test_reindex_cleans_stale_rows(tmp_path: Path) -> None:
    service = build_service(tmp_path)
    service.register_workspace(user_id="alice", workspace_kind="defaultWorkspace", agent_id=None)

    # Seed one stale index row that does not exist on disk.
    service.search_index.upsert_document(
        IndexedDocument(
            uri="ctx://alice/defaultWorkspace/docs/stale.md",
            user_id="alice",
            workspace_kind="defaultWorkspace",
            agent_id=None,
            relative_path="docs/stale.md",
            doc_type="docs",
            title="Stale",
            body="obsolete",
        )
    )

    result = service.reindex(user_id="alice", scope_uri="ctx://alice/defaultWorkspace")
    assert result["removed"] >= 1

    search = service.search(
        user_id="alice",
        query="obsolete",
        scope_uri="ctx://alice/defaultWorkspace",
        limit=10,
        workspace_mode="default-only",
    )
    assert search["hits"] == []
