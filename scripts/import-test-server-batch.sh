#!/usr/bin/env bash
set -euo pipefail

if [[ $# -lt 1 ]]; then
  echo "usage: $0 <notes-contexthub|repo-docs|all> [extra import-markdown args...]" >&2
  exit 1
fi

BATCH="$1"
shift

if [[ -z "${CONTEXT_HUB_TENANT_ID:-}" ]]; then
  echo "CONTEXT_HUB_TENANT_ID is required" >&2
  exit 1
fi

HOST="${CONTEXT_HUB_DEPLOY_HOST:-root@38.55.39.92}"
PORT="${CONTEXT_HUB_DEPLOY_PORT:-2222}"
BASE_URL="${CONTEXT_HUB_IMPORT_BASE_URL:-http://127.0.0.1:4041}"
PARTITION_KEY="${CONTEXT_HUB_PARTITION_KEY:-project-contexthub}"
REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
NOTES_ROOT="${CONTEXT_HUB_NOTES_ROOT:-/Users/shiuing/Desktop/notes/contexthub}"
DOCS_ROOT="${CONTEXT_HUB_DOCS_ROOT:-$REPO_ROOT/docs}"

run_import() {
  local batch_name="$1"
  local root="$2"
  shift 2

  uv run python -m contexthub import-markdown \
    --base-url "$BASE_URL" \
    --tenant-id "$CONTEXT_HUB_TENANT_ID" \
    --partition-key "$PARTITION_KEY" \
    --layer l1 \
    --root "$root" \
    --derive-layers l0 \
    --derive-mode async \
    --type resource \
    --tag contexthub \
    --tag server-import \
    --tag "$batch_name" \
    "$@"
}

cleanup() {
  if [[ -n "${TUNNEL_PID:-}" ]]; then
    kill "$TUNNEL_PID" >/dev/null 2>&1 || true
  fi
}
trap cleanup EXIT

if [[ -z "${CONTEXT_HUB_IMPORT_BASE_URL:-}" ]]; then
  ssh -p "$PORT" -o ExitOnForwardFailure=yes -o StrictHostKeyChecking=no -N -L 4041:127.0.0.1:4040 "$HOST" &
  TUNNEL_PID=$!
  sleep 2
fi

case "$BATCH" in
  notes-contexthub)
    run_import notes-contexthub "$NOTES_ROOT" "$@"
    ;;
  repo-docs)
    run_import repo-docs "$DOCS_ROOT" "$@"
    ;;
  all)
    run_import notes-contexthub "$NOTES_ROOT" "$@"
    run_import repo-docs "$DOCS_ROOT" "$@"
    ;;
  *)
    echo "unknown batch: $BATCH" >&2
    exit 1
    ;;
esac
