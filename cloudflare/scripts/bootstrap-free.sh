#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd -- "$(dirname -- "$0")/.." && pwd)"
CONFIG_PATH="$ROOT_DIR/wrangler.jsonc"

WORKER_NAME="${CTX_CF_WORKER_NAME:-contexthub-phase1-worker}"
DB_NAME="${CTX_CF_DB_NAME:-${WORKER_NAME}-db}"
DB_BINDING="${CTX_CF_DB_BINDING:-DB}"

echo "[bootstrap] root: $ROOT_DIR"
echo "[bootstrap] worker name: $WORKER_NAME"
echo "[bootstrap] d1 database name: $DB_NAME"
echo "[bootstrap] d1 binding: $DB_BINDING"

node <<'NODE' "$CONFIG_PATH" "$WORKER_NAME" "$DB_NAME" "$DB_BINDING"
const fs = require('node:fs');
const [configPath, workerName, dbName, dbBinding] = process.argv.slice(2);
let text = fs.readFileSync(configPath, 'utf8');
text = text.replace(/"name":\s*"[^"]+"/, `"name": "${workerName}"`);
text = text.replace(/"binding":\s*"[^"]+"/, `"binding": "${dbBinding}"`);
text = text.replace(/"database_name":\s*"[^"]+"/, `"database_name": "${dbName}"`);
text = text.replace(/"database_id":\s*"[^"]+"/, '"database_id": "REPLACE_WITH_REAL_D1_DATABASE_ID"');
fs.writeFileSync(configPath, text);
NODE

echo "[bootstrap] updated wrangler.jsonc"

echo "[bootstrap] creating remote D1 database and updating config..."
cd "$ROOT_DIR"
npx wrangler d1 create "$DB_NAME" --binding "$DB_BINDING" --update-config

cat <<'EOF'

[bootstrap] next steps
1. Optional: set an admin token secret
   printf '%s' 'YOUR_TOKEN' | npx wrangler secret put CONTEXT_HUB_ADMIN_TOKEN

2. Deploy the worker
   npm run deploy

3. Verify health
   curl https://YOUR_WORKER_HOST/health

4. Connect agents with npm ctx_cli
   npm install -g @shiuing/ctx-cli
   ctx_cli config set baseUrl https://YOUR_WORKER_HOST
   ctx_cli config set userId YOUR_USER_ID
   printf '%s' 'YOUR_TOKEN' | ctx_cli config set token --stdin
   ctx_cli doctor
EOF
