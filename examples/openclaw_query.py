from __future__ import annotations

import argparse
import json
import os

from contexthub.adapter_helpers import build_openclaw_recall_config, build_query_payload, parse_csv_list
from contexthub.client import ContextHubClient


def env_flag(name: str, default: bool) -> bool:
    raw = os.environ.get(name)
    if raw is None:
        return default
    return raw.strip().lower() not in {"0", "false", "no", "off"}


def main() -> None:
    parser = argparse.ArgumentParser(description="Query ContextHub the way an OpenClaw pre-answer recall hook would.")
    parser.add_argument("query")
    parser.add_argument("--base-url", default=os.environ.get("CONTEXT_HUB_BASE_URL", "http://127.0.0.1:4040"))
    parser.add_argument("--token", default=os.environ.get("CONTEXT_HUB_TOKEN"))
    parser.add_argument("--tenant-id", default=os.environ.get("CONTEXT_HUB_TENANT_ID"), required=os.environ.get("CONTEXT_HUB_TENANT_ID") is None)
    parser.add_argument("--partitions", default=os.environ.get("CONTEXT_HUB_RECALL_PARTITIONS", os.environ.get("CONTEXT_HUB_PARTITIONS", "")))
    parser.add_argument("--layers", default=os.environ.get("CONTEXT_HUB_RECALL_LAYERS", os.environ.get("CONTEXT_HUB_LAYERS", "l0")))
    parser.add_argument("--limit", type=int, default=int(os.environ.get("CONTEXT_HUB_RECALL_LIMIT", "5")))
    parser.add_argument("--rerank", action="store_true", default=env_flag("CONTEXT_HUB_RECALL_RERANK", False))
    parser.add_argument("--disabled", action="store_true", default=not env_flag("CONTEXT_HUB_RECALL_ENABLED", True))
    args = parser.parse_args()

    recall_config = build_openclaw_recall_config(
        enabled=not args.disabled,
        partitions=parse_csv_list(args.partitions),
        layers=parse_csv_list(args.layers),
        limit=args.limit,
        rerank=args.rerank,
    )
    if not recall_config["enabled"]:
        print(json.dumps({"enabled": False, "reason": "pre-answer recall disabled by configuration"}, indent=2, ensure_ascii=True))
        return

    client = ContextHubClient(args.base_url, token=args.token)
    payload = build_query_payload(
        tenant_id=args.tenant_id,
        query=args.query,
        partitions=recall_config["partitions"],
        layers=recall_config["layers"],
        limit=recall_config["limit"],
        rerank=recall_config["rerank"],
    )
    result = client.query(payload)
    print(json.dumps({"recall": recall_config, "result": result}, indent=2, ensure_ascii=True))


if __name__ == "__main__":
    main()
