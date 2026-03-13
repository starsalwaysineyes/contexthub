#!/usr/bin/env bash
set -euo pipefail

HOST="${CONTEXT_HUB_DEPLOY_HOST:-root@38.55.39.92}"
PORT="${CONTEXT_HUB_DEPLOY_PORT:-2222}"
REMOTE_DIR="${CONTEXT_HUB_REMOTE_DIR:-/opt/contexthub}"
SERVICE_NAME="${CONTEXT_HUB_SERVICE_NAME:-contexthub}"
REPO_URL="${CONTEXT_HUB_REPO_URL:-https://github.com/starsalwaysineyes/contexthub.git}"
HEALTH_RETRIES="${CONTEXT_HUB_HEALTH_RETRIES:-20}"
HEALTH_INTERVAL_SECONDS="${CONTEXT_HUB_HEALTH_INTERVAL_SECONDS:-1}"

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
SSH=(ssh -p "$PORT" -o StrictHostKeyChecking=no "$HOST")
SCP=(scp -P "$PORT" -o StrictHostKeyChecking=no)
REMOTE_UV='export PATH="$HOME/.local/bin:$PATH"; command -v uv >/dev/null 2>&1 || curl -LsSf https://astral.sh/uv/install.sh | sh'

rendered_unit="$(mktemp)"
trap 'rm -f "$rendered_unit"' EXIT
sed "s|__REMOTE_DIR__|$REMOTE_DIR|g" "$ROOT_DIR/deploy/contexthub.service" > "$rendered_unit"

"${SSH[@]}" "mkdir -p '$REMOTE_DIR'"
"${SSH[@]}" "$REMOTE_UV"
"${SSH[@]}" 'export PATH="$HOME/.local/bin:$PATH"; uv python install 3.12'
"${SSH[@]}" "if [ ! -d '$REMOTE_DIR/.git' ]; then git clone '$REPO_URL' '$REMOTE_DIR'; else cd '$REMOTE_DIR' && git fetch origin && git checkout main && git pull --ff-only origin main; fi"
"${SSH[@]}" "cd '$REMOTE_DIR' && export PATH=\"\$HOME/.local/bin:\$PATH\" && uv sync --frozen"

"${SSH[@]}" "if [ ! -f '$REMOTE_DIR/.env' ]; then cp '$REMOTE_DIR/.env.example' '$REMOTE_DIR/.env'; python3 - <<'PY'
from pathlib import Path
path = Path('$REMOTE_DIR/.env')
lines = path.read_text().splitlines()
patched = []
for line in lines:
    if line.startswith('CONTEXT_HUB_DATA_DIR='):
        patched.append('CONTEXT_HUB_DATA_DIR=$REMOTE_DIR/var/data')
    elif line.startswith('CONTEXT_HUB_DATABASE_PATH='):
        patched.append('CONTEXT_HUB_DATABASE_PATH=$REMOTE_DIR/var/data/contexthub.db')
    elif line.startswith('CONTEXT_HUB_ENABLE_EMBEDDINGS='):
        patched.append('CONTEXT_HUB_ENABLE_EMBEDDINGS=false')
    elif line.startswith('CONTEXT_HUB_ENABLE_RERANK='):
        patched.append('CONTEXT_HUB_ENABLE_RERANK=false')
    else:
        patched.append(line)
path.write_text('\n'.join(patched) + '\n')
PY
fi"

"${SCP[@]}" "$rendered_unit" "$HOST:/etc/systemd/system/$SERVICE_NAME.service"
"${SSH[@]}" "systemctl daemon-reload && systemctl enable --now '$SERVICE_NAME'"

for ((attempt = 1; attempt <= HEALTH_RETRIES; attempt++)); do
  if "${SSH[@]}" "curl -fsS http://127.0.0.1:4040/health"; then
    exit 0
  fi
  sleep "$HEALTH_INTERVAL_SECONDS"
done

"${SSH[@]}" "systemctl status '$SERVICE_NAME' --no-pager -l"
exit 1
