from __future__ import annotations

import argparse
import json
import os
from typing import Any

from contexthub.adapter_helpers import build_commit_payload, build_memory_entry, parse_csv_list, read_optional_text
from contexthub.client import ContextHubClient


def run(default_channel: str) -> None:
    parser = argparse.ArgumentParser(description=f"Commit a session summary to ContextHub for {default_channel}.")
    parser.add_argument("--summary", required=True)
    parser.add_argument("--base-url", default=os.environ.get("CONTEXT_HUB_BASE_URL", "http://127.0.0.1:4040"))
    parser.add_argument("--token", default=os.environ.get("CONTEXT_HUB_TOKEN"))
    parser.add_argument("--tenant-id", default=os.environ.get("CONTEXT_HUB_TENANT_ID"), required=os.environ.get("CONTEXT_HUB_TENANT_ID") is None)
    parser.add_argument("--partition-key", default=os.environ.get("CONTEXT_HUB_PARTITION_KEY"), required=os.environ.get("CONTEXT_HUB_PARTITION_KEY") is None)
    parser.add_argument("--agent-id", default=os.environ.get("CONTEXT_HUB_AGENT_ID"))
    parser.add_argument("--message", default=None)
    parser.add_argument("--message-file", default=None)
    parser.add_argument("--message-role", default="assistant")
    parser.add_argument("--memory-title", default=None)
    parser.add_argument("--memory-text", default=None)
    parser.add_argument("--memory-file", default=None)
    parser.add_argument("--memory-layer", default="l0")
    parser.add_argument("--memory-importance", type=float, default=3.0)
    parser.add_argument("--memory-tags", default="")
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()

    messages: list[dict[str, str]] = []
    message_text = read_optional_text(text=args.message, file_path=args.message_file)
    if message_text:
        messages.append({"role": args.message_role, "content": message_text})

    memory_entries: list[dict[str, Any]] = []
    memory_text = read_optional_text(text=args.memory_text, file_path=args.memory_file)
    if args.memory_title and memory_text:
        memory_entries.append(
            build_memory_entry(
                title=args.memory_title,
                text=memory_text,
                layer=args.memory_layer,
                importance=args.memory_importance,
                tags=parse_csv_list(args.memory_tags),
            )
        )

    payload = build_commit_payload(
        tenant_id=args.tenant_id,
        partition_key=args.partition_key,
        summary=args.summary,
        agent_id=args.agent_id,
        messages=messages,
        memory_entries=memory_entries,
        metadata={"adapter": default_channel},
    )

    if args.dry_run:
        print(json.dumps(payload, indent=2, ensure_ascii=True))
        return

    client = ContextHubClient(args.base_url, token=args.token)
    result = client.commit_session(payload)
    print(json.dumps(result, indent=2, ensure_ascii=True))


__all__ = ["run"]
