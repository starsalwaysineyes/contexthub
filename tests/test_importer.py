from __future__ import annotations

from pathlib import Path

from contexthub.importer import (
    ImportMarkdownOptions,
    build_import_payload,
    extract_markdown_title,
    import_markdown_tree,
    make_file_idempotency_key,
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
        tags=("imported",),
    )
    client = RecordingClient()

    summary = import_markdown_tree(options, client=client)

    assert summary["count"] == 1
    assert len(client.payloads) == 1
    payload = client.payloads[0]
    assert payload["title"] == "Imported Note"
    assert payload["targetLayer"] == "l1"
    assert payload["derive"]["emitLayers"] == ["l0"]
    assert payload["metadata"]["relativePath"] == "example.md"


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
    assert payload["derive"]["enabled"] is False
