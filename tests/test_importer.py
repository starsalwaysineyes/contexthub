from __future__ import annotations

from pathlib import Path

from contexthub.importer import (
    ImportMarkdownOptions,
    build_effective_relative_path,
    build_import_payload,
    discover_markdown_files,
    extract_markdown_title,
    import_markdown_tree,
    make_file_idempotency_key,
    matches_any_glob,
)


class RecordingClient:
    def __init__(self) -> None:
        self.payloads = []

    def import_resource(self, payload: dict) -> dict:
        self.payloads.append(payload)
        return {
            "record": {"id": f"record_{len(self.payloads)}", "layer": payload["targetLayer"]},
            "derivation": {"status": "disabled", "records": []},
        }


def test_extract_markdown_title_prefers_heading() -> None:
    content = "# Hello World\n\nBody"
    assert extract_markdown_title(content, "fallback") == "Hello World"


def test_make_file_idempotency_key_is_stable() -> None:
    left = make_file_idempotency_key("archive/test.md", "l1")
    right = make_file_idempotency_key("archive/test.md", "l1")
    assert left == right


def test_build_effective_relative_path_applies_prefix() -> None:
    assert build_effective_relative_path("daily/2026-03-14.md", None) == "daily/2026-03-14.md"
    assert build_effective_relative_path("daily/2026-03-14.md", "memory") == "memory/daily/2026-03-14.md"


def test_discover_markdown_files_supports_include_exclude_globs(tmp_path: Path) -> None:
    root = tmp_path / "memory"
    (root / "archive" / "2026").mkdir(parents=True)
    (root / "auto-memory").mkdir(parents=True)
    (root / "2026-03-14.md").write_text("daily", encoding="utf-8")
    (root / "archive" / "2026" / "case.md").write_text("archive", encoding="utf-8")
    (root / "auto-memory" / "README.md").write_text("auto", encoding="utf-8")

    files = discover_markdown_files(root, include_globs=("2026-*.md",), exclude_globs=("archive/**", "auto-memory/**"))

    assert [path.relative_to(root).as_posix() for path in files] == ["2026-03-14.md"]
    assert matches_any_glob("archive/2026/case.md", ("archive/**",)) is True


def test_import_markdown_tree_builds_expected_payload(tmp_path: Path) -> None:
    root = tmp_path / "notes"
    root.mkdir()
    file_path = root / "example.md"
    file_path.write_text("# Imported Note\n\nBody text", encoding="utf-8")

    options = ImportMarkdownOptions(
        base_url="http://127.0.0.1:4040",
        token="demo-token",
        tenant_id="tenant_demo",
        partition_key="memory",
        layer="l1",
        root=root,
        derive_layers=("l0",),
        prompt_preset="memory_only",
        record_type="summary",
        source_kind="local_file",
        relative_path_prefix="migration/archive",
        metadata={"preset": "archive"},
        include_globs=("*.md",),
        exclude_globs=("ignore/**",),
        tags=("imported",),
    )
    client = RecordingClient()

    summary = import_markdown_tree(options, client=client)

    assert summary["count"] == 1
    assert len(client.payloads) == 1
    payload = client.payloads[0]
    assert payload["title"] == "Imported Note"
    assert payload["type"] == "summary"
    assert payload["targetLayer"] == "l1"
    assert payload["source"]["kind"] == "local_file"
    assert payload["source"]["relativePath"] == "migration/archive/example.md"
    assert payload["derive"]["emitLayers"] == ["l0"]
    assert payload["derive"]["promptPreset"] == "memory_only"
    assert payload["metadata"]["relativePath"] == "migration/archive/example.md"
    assert payload["metadata"]["originalRelativePath"] == "example.md"
    assert payload["metadata"]["preset"] == "archive"


def test_build_import_payload_dry_run_shape(tmp_path: Path) -> None:
    root = tmp_path / "archive"
    root.mkdir()
    file_path = root / "log.md"
    file_path.write_text("Body only", encoding="utf-8")

    options = ImportMarkdownOptions(
        base_url="http://127.0.0.1:4040",
        token=None,
        tenant_id="tenant_demo",
        partition_key="archive",
        layer="l2",
        root=root,
        dry_run=True,
    )

    payload = build_import_payload(file_path, root=root, options=options)

    assert payload["title"] == "log"
    assert payload["content"]["kind"] == "inline_text"
    assert payload["source"]["relativePath"] == "log.md"
    assert payload["derive"]["enabled"] is False
