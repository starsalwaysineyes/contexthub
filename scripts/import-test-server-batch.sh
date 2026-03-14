#!/usr/bin/env bash
set -euo pipefail

if [[ $# -lt 1 ]]; then
  echo "usage: $0 <notes-contexthub|repo-docs|workspace-memory-daily|workspace-memory-archive|all|all-migration> [extra import-markdown args...]" >&2
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
MEMORY_PARTITION_KEY="${CONTEXT_HUB_MEMORY_PARTITION_KEY:-memory}"
REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
NOTES_ROOT="${CONTEXT_HUB_NOTES_ROOT:-/Users/shiuing/Desktop/notes/contexthub}"
DOCS_ROOT="${CONTEXT_HUB_DOCS_ROOT:-$REPO_ROOT/docs}"
WORKSPACE_MEMORY_ROOT="${CONTEXT_HUB_WORKSPACE_MEMORY_ROOT:-/Users/shiuing/.openclaw/workspace/memory}"
WORKSPACE_MEMORY_ARCHIVE_ROOT="${CONTEXT_HUB_WORKSPACE_MEMORY_ARCHIVE_ROOT:-$WORKSPACE_MEMORY_ROOT/archive}"

run_import() {
  local batch_name="$1"
  local root="$2"
  local partition_key="$3"
  local layer="$4"
  local record_type="$5"
  shift 5

  uv run python -m contexthub import-markdown \
    --base-url "$BASE_URL" \
    --tenant-id "$CONTEXT_HUB_TENANT_ID" \
    --partition-key "$partition_key" \
    --layer "$layer" \
    --root "$root" \
    --type "$record_type" \
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
    run_import notes-contexthub "$NOTES_ROOT" "$PARTITION_KEY" l1 resource \
      --derive-layers l0 \
      --derive-mode async \
      "$@"
    ;;
  repo-docs)
    run_import repo-docs "$DOCS_ROOT" "$PARTITION_KEY" l1 resource \
      --derive-layers l0 \
      --derive-mode async \
      "$@"
    ;;
  workspace-memory-daily)
    run_import workspace-memory-daily "$WORKSPACE_MEMORY_ROOT" "$MEMORY_PARTITION_KEY" l0 memory \
      --source-kind workspace_memory_file \
      --relative-path-prefix memory/daily \
      --metadata-json '{"migrationPreset":"workspace-daily-memory"}' \
      --tag migration \
      --tag daily-memory \
      --include '2026-*.md' \
      --exclude 'archive/**' \
      --exclude 'auto-memory/**' \
      "$@"
    ;;
  workspace-memory-archive)
    run_import workspace-memory-archive "$WORKSPACE_MEMORY_ARCHIVE_ROOT" "$MEMORY_PARTITION_KEY" l1 summary \
      --derive-layers l0 \
      --derive-mode async \
      --source-kind workspace_memory_archive_file \
      --relative-path-prefix memory/archive \
      --metadata-json '{"migrationPreset":"workspace-memory-archive"}' \
      --tag migration \
      --tag archive \
      "$@"
    ;;
  all)
    run_import notes-contexthub "$NOTES_ROOT" "$PARTITION_KEY" l1 resource \
      --derive-layers l0 \
      --derive-mode async \
      "$@"
    run_import repo-docs "$DOCS_ROOT" "$PARTITION_KEY" l1 resource \
      --derive-layers l0 \
      --derive-mode async \
      "$@"
    ;;
  all-migration)
    run_import workspace-memory-daily "$WORKSPACE_MEMORY_ROOT" "$MEMORY_PARTITION_KEY" l0 memory \
      --source-kind workspace_memory_file \
      --relative-path-prefix memory/daily \
      --metadata-json '{"migrationPreset":"workspace-daily-memory"}' \
      --tag migration \
      --tag daily-memory \
      --include '2026-*.md' \
      --exclude 'archive/**' \
      --exclude 'auto-memory/**' \
      "$@"
    run_import workspace-memory-archive "$WORKSPACE_MEMORY_ARCHIVE_ROOT" "$MEMORY_PARTITION_KEY" l1 summary \
      --derive-layers l0 \
      --derive-mode async \
      --source-kind workspace_memory_archive_file \
      --relative-path-prefix memory/archive \
      --metadata-json '{"migrationPreset":"workspace-memory-archive"}' \
      --tag migration \
      --tag archive \
      "$@"
    ;;
  *)
    echo "unknown batch: $BATCH" >&2
    exit 1
    ;;
esac
