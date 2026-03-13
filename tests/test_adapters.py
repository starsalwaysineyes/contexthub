from __future__ import annotations

from pathlib import Path

from contexthub.adapter_helpers import (
    build_commit_payload,
    build_memory_entry,
    build_query_payload,
    parse_csv_list,
    read_optional_text,
)


def test_parse_csv_list() -> None:
    assert parse_csv_list("l0, l1 ,l2") == ["l0", "l1", "l2"]
    assert parse_csv_list("") == []


def test_build_query_payload_defaults() -> None:
    payload = build_query_payload(tenant_id="tenant_x", query="hello")
    assert payload["layers"] == ["l0", "l1"]
    assert payload["limit"] == 5


def test_build_memory_entry() -> None:
    entry = build_memory_entry(title="Decision", text="Use ACL", tags=["auth"])
    assert entry["layer"] == "l0"
    assert entry["tags"] == ["auth"]


def test_build_commit_payload() -> None:
    payload = build_commit_payload(
        tenant_id="tenant_x",
        partition_key="memory",
        summary="Done",
        memory_entries=[{"title": "t", "text": "x"}],
    )
    assert payload["tenantId"] == "tenant_x"
    assert payload["partitionKey"] == "memory"
    assert payload["memoryEntries"][0]["title"] == "t"


def test_read_optional_text_from_file(tmp_path: Path) -> None:
    file_path = tmp_path / "note.txt"
    file_path.write_text("hello", encoding="utf-8")
    assert read_optional_text(file_path=str(file_path)) == "hello"
