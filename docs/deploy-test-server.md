# Deploy To Test Server

## Goal

Deploy ContextHub to the test host `root@38.55.39.92 -p 2222` with a repeatable `uv` + `systemd` flow.

## Current deployment shape

- remote repo path: `/opt/contexthub`
- service name: `contexthub`
- systemd unit template: `deploy/contexthub.service`
- bootstrap script: `scripts/deploy-test-server.sh`
- bind address: `127.0.0.1:4040` on the server for initial validation

## Bootstrap behavior

`scripts/deploy-test-server.sh` currently does the following:

1. installs `uv` if missing
2. installs Python `3.12` through `uv`
3. clones or fast-forwards the repo into `/opt/contexthub`
4. runs `uv sync --frozen`
5. creates `/opt/contexthub/.env` from `.env.example` if it does not exist yet
6. patches safe bootstrap defaults:
   - local data dir under `/opt/contexthub/var/data`
   - SQLite DB under `/opt/contexthub/var/data/contexthub.db`
   - embeddings disabled
   - rerank disabled
7. installs the `systemd` unit and starts the service
8. retries `http://127.0.0.1:4040/health` until success (default 20 attempts, 1s interval)

## Run it

```bash
./scripts/deploy-test-server.sh
```

Optional overrides:

```bash
CONTEXT_HUB_DEPLOY_HOST=root@38.55.39.92 \
CONTEXT_HUB_DEPLOY_PORT=2222 \
CONTEXT_HUB_REMOTE_DIR=/opt/contexthub \
CONTEXT_HUB_HEALTH_RETRIES=30 \
./scripts/deploy-test-server.sh
```

## Important notes

- initial bootstrap is intentionally conservative: it validates service lifecycle first, not full remote provider integration
- because the service binds to `127.0.0.1`, it is reachable only from the server itself until a reverse proxy or tunnel is added
- if remote derivation/embedding is needed, fill in `/opt/contexthub/.env` with the real provider credentials after bootstrap
- the next hardening step is queued-job recovery after process restart

## Manual validation

```bash
ssh -p 2222 root@38.55.39.92 'systemctl status contexthub --no-pager'
ssh -p 2222 root@38.55.39.92 'curl -fsS http://127.0.0.1:4040/health'
```
