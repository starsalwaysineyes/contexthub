#!/usr/bin/env bash
set -euo pipefail

if [[ -z "${CONTEXT_HUB_TENANT_ID:-}" ]]; then
  echo "CONTEXT_HUB_TENANT_ID is required" >&2
  exit 1
fi

HOST="${CONTEXT_HUB_DEPLOY_HOST:-root@38.55.39.92}"
PORT="${CONTEXT_HUB_DEPLOY_PORT:-2222}"
BASE_URL="${CONTEXT_HUB_INSPECT_BASE_URL:-http://127.0.0.1:4041}"
PARTITION_KEY="${CONTEXT_HUB_PARTITION_KEY:-memory}"
TOKEN="${CONTEXT_HUB_TOKEN:-}"

cleanup() {
  if [[ -n "${TUNNEL_PID:-}" ]]; then
    kill "$TUNNEL_PID" >/dev/null 2>&1 || true
  fi
}
trap cleanup EXIT

if [[ -z "${CONTEXT_HUB_INSPECT_BASE_URL:-}" ]]; then
  ssh -p "$PORT" -o ExitOnForwardFailure=yes -o StrictHostKeyChecking=no -N -L 4041:127.0.0.1:4040 "$HOST" &
  TUNNEL_PID=$!
  sleep 2
fi

export BASE_URL
export PARTITION_KEY
export TOKEN

python3 - <<'PY'
import json
import os
from urllib.request import Request, urlopen

base = os.environ.get("BASE_URL", "http://127.0.0.1:4041").rstrip("/")
tenant_id = os.environ["CONTEXT_HUB_TENANT_ID"]
partition_key = os.environ.get("PARTITION_KEY", "memory")
token = os.environ.get("TOKEN", "")

headers = {"Content-Type": "application/json"}
if token:
    headers["Authorization"] = f"Bearer {token}"


def post(path: str, payload: dict) -> dict:
    req = Request(
        base + path,
        data=json.dumps(payload).encode("utf-8"),
        method="POST",
        headers=headers,
    )
    with urlopen(req, timeout=30) as response:
        return json.loads(response.read().decode("utf-8"))


def list_records(*, layer: str, tags: list[str], source_prefix: str, limit: int = 5) -> dict:
    return post(
        "/v1/records/list",
        {
            "tenantId": tenant_id,
            "partitions": [partition_key],
            "layers": [layer],
            "tags": tags,
            "sourcePathPrefix": source_prefix,
            "limit": limit,
            "offset": 0,
        },
    )


def titles(items: list[dict]) -> list[str]:
    return [str(item.get("title", "")) for item in items]


daily = list_records(
    layer="l0",
    tags=["workspace-memory-daily"],
    source_prefix="memory/daily",
)
archive = list_records(
    layer="l1",
    tags=["workspace-memory-archive"],
    source_prefix="memory/archive",
)

summary = {
    "tenantId": tenant_id,
    "partitionKey": partition_key,
    "daily": {
        "totalMatched": daily.get("page", {}).get("totalMatched", 0),
        "sampleTitles": titles(daily.get("items", [])),
        "scope": daily.get("scope", {}),
    },
    "archive": {
        "totalMatched": archive.get("page", {}).get("totalMatched", 0),
        "sampleTitles": titles(archive.get("items", [])),
        "scope": archive.get("scope", {}),
    },
}

print(json.dumps(summary, indent=2, ensure_ascii=True))
PY
