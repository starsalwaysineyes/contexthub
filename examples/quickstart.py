from __future__ import annotations

import json
import os

from contexthub.client import ContextHubClient


def main() -> None:
    client = ContextHubClient(os.environ.get("CONTEXT_HUB_BASE_URL", "http://127.0.0.1:4040"))

    tenant = client.create_tenant({"slug": "openclaw-china", "name": "OpenClaw China"})
    client.create_partition(
        {
            "tenantId": tenant["id"],
            "key": "project-openclaw",
            "name": "Project OpenClaw",
            "kind": "project",
        }
    )
    client.create_record(
        {
            "tenantId": tenant["id"],
            "partitionKey": "project-openclaw",
            "type": "memory",
            "title": "ContextHub direction",
            "text": "Single instance multi-tenant, manual curation first, optional rerank.",
            "importance": 4,
            "pinned": True,
            "idempotencyKey": "project-openclaw:direction:v1",
        }
    )
    result = client.query(
        {
            "tenantId": tenant["id"],
            "query": "manual curation and multi-tenant",
            "partitions": ["project-openclaw"],
            "rerank": False,
            "limit": 3,
        }
    )
    print(json.dumps(result, indent=2))


if __name__ == "__main__":
    main()
