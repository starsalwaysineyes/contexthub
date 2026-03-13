from __future__ import annotations

import argparse
import json
import os

from contexthub.adapter_helpers import build_query_payload, parse_csv_list
from contexthub.client import ContextHubClient


def main() -> None:
    parser = argparse.ArgumentParser(description="Query ContextHub the way an OpenClaw recall hook would.")
    parser.add_argument("query")
    parser.add_argument("--base-url", default=os.environ.get("CONTEXT_HUB_BASE_URL", "http://127.0.0.1:4040"))
    parser.add_argument("--token", default=os.environ.get("CONTEXT_HUB_TOKEN"))
    parser.add_argument("--tenant-id", default=os.environ.get("CONTEXT_HUB_TENANT_ID"), required=os.environ.get("CONTEXT_HUB_TENANT_ID") is None)
    parser.add_argument("--partitions", default=os.environ.get("CONTEXT_HUB_PARTITIONS", ""))
    parser.add_argument("--layers", default=os.environ.get("CONTEXT_HUB_LAYERS", "l0,l1"))
    parser.add_argument("--limit", type=int, default=5)
    parser.add_argument("--rerank", action="store_true")
    args = parser.parse_args()

    client = ContextHubClient(args.base_url, token=args.token)
    payload = build_query_payload(
        tenant_id=args.tenant_id,
        query=args.query,
        partitions=parse_csv_list(args.partitions),
        layers=parse_csv_list(args.layers),
        limit=args.limit,
        rerank=args.rerank,
    )
    result = client.query(payload)
    print(json.dumps(result, indent=2, ensure_ascii=True))


if __name__ == "__main__":
    main()
