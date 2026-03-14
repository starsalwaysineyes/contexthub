# ContextHub

ContextHub is an agent-native context backend for multi-agent memory and retrieval.

This repo now uses a Python + uv stack for better runtime stability and dependency control.

## Design stance

- Manual curation first, automation second.
- Single instance, multi-tenant.
- SQLite-backed metadata.
- Remote Embedding and optional remote Rerank.
- Cross-partition retrieval stays explicit and controllable.
- Agent integration should stay boring: plain HTTP + JSON.

## What is in this repo

- FastAPI service in `contexthub/`
- SQLite storage schema in `contexthub/store.py`
- Core objects: tenants, partitions, agents, principals, ACL rules, records, sessions
- Explicit `L0/L1/L2` layer model on records and query filters
- First-pass bearer auth + partition ACL
- Import MVP: `POST /v1/resources/import` (`inline_text`)
- LiteLLM-backed derivation for `L1/L0` with real `sync` / `async` execution modes
- Derivation lineage persistence (`derivation_jobs` + `record_links`)
- Retrieval pipeline with lexical score + optional embeddings + optional rerank
- Python client SDK in `contexthub/client.py`
- Adapter helper module and example scripts for OpenClaw/Codex/Claude Code
- Test-server deployment bootstrap script + systemd unit template
- Architecture/API docs in `docs/`

## Quick start (uv)

```bash
cp .env.example .env
uv sync --group dev
uv run pytest
uv run python -m contexthub serve --host 127.0.0.1 --port 4040
```

In another terminal:

```bash
uv run python examples/quickstart.py
```

For local Markdown import jobs:

```bash
uv run python -m contexthub import-markdown \
  --tenant-id tenant_xxx \
  --partition-key project-openclaw \
  --layer l1 \
  --root /path/to/markdown/tree \
  --dry-run
```

Default endpoints:

- `GET /health`
- `GET /v1/auth/me`
- `POST /v1/tenants`
- `POST /v1/partitions`
- `POST /v1/agents`
- `POST /v1/principals`
- `POST /v1/principals/{principalId}/acl`
- `POST /v1/records`
- `GET /v1/records/{recordId}`
- `PATCH /v1/records/{recordId}`
- `POST /v1/resources/import`
- `GET /v1/derivation-jobs/{jobId}`
- `GET /v1/records/{recordId}/links`
- `POST /v1/query`
- `POST /v1/sessions/commit`

## Configuration

Use `.env.example` as the template.

Loader order:

1. `CONTEXT_HUB_ENV_FILE` (if set)
2. `.env.local`
3. `.env`

Recommended provider values:

- embedding base URL: `https://cloud.infini-ai.com/maas/v1`
- embedding model: `bge-m3`
- rerank base URL: `https://cloud.infini-ai.com/maas/v1`
- rerank model: `bge-reranker-v2-m3`

Auth-related values:

- `CONTEXT_HUB_ENABLE_AUTH=true` to enable bearer auth
- `CONTEXT_HUB_ADMIN_TOKEN=...` to bootstrap tenant/principal/ACL management

## Security checks

Before pushing:

```bash
uv run python scripts/check_secrets.py
```

GitHub Actions runs the same secret scan and pytest on every push/PR.

## TODO

- [x] Switch runtime stack to Python + uv
- [x] Keep Node MVP as legacy snapshot under `legacy/node-mvp/`
- [x] Add Python CI workflow with uv
- [x] Add Python-based secrets scan in CI/local
- [x] Make `L0/L1/L2` explicit in the backend data model
- [x] Finish upload + derivation design with LiteLLM as the abstraction gateway
- [x] Add first-pass auth and partition ACL enforcement
- [x] Implement `POST /v1/resources/import` MVP (`inline_text` + optional sync derivation)
- [x] Add local Markdown import CLI (`contexthub import-markdown`)
- [x] Add OpenClaw adapter examples + one-command helper scripts
- [x] Add Codex and Claude Code adapter examples
- [x] Add Markdown/archive ingestion jobs
- [x] Persist derivation lineage (`derivation_jobs` + `record_links`)
- [x] Add first-pass real async derivation execution via persisted jobs
- [x] Deploy first managed instance bootstrap to target server (`systemd` + health/write/query smoke)
- [x] Configure remote provider env and validate successful derive path on server
- [x] Add basic record get/update APIs (`GET/PATCH /v1/records/{recordId}`)
- [ ] Add generic file/session-oriented upload, get, and update semantics for explicit `L0` / `L1` / `L2` targeting
- [ ] Strengthen retrieval into a more file-system-like experience: cross-file hits, explicit cross-partition search, and multi-hit results for agent workflows
- [ ] Record a future `queryTask` / agentic-search workflow where the service can perform retrieval + extraction for the caller (idea only, not in current scope)
- [ ] Import selected local materials to the test server and spot-check mapping quality

## Repo layout

```text
contexthub/
  __main__.py
  app.py
  service.py
  security.py
  store.py
  schemas.py
  providers.py
  config.py
  env.py
  client.py
  text.py
scripts/
  check_secrets.py
  deploy-test-server.sh
  import-test-server-batch.sh
  openclaw-query.sh
  openclaw-commit.sh
  codex-commit.sh
  claude-code-commit.sh
deploy/
  contexthub.service
docs/
  architecture.md
  api.md
  openapi.yaml
  auth-acl.md
  layer-model.md
  upload-derivation-design.md
  import-jobs.md
  adapter-examples.md
  deploy-test-server.md
  execution-plan.md
  agent-integration.md
  roadmap.md
  stack-decision.md
legacy/
  node-mvp/
```

## Notes

- Legacy Node MVP is preserved in `legacy/node-mvp/` for design reference and migration diff.
- The current implementation keeps API shape close to the original MVP to reduce adapter churn.
- Layer mapping is documented in `docs/layer-model.md`.
- Upload and auto-derivation design is documented in `docs/upload-derivation-design.md`.
- Auth and partition ACL are documented in `docs/auth-acl.md`.
- Import CLI usage is documented in `docs/import-jobs.md`.
- Adapter examples are documented in `docs/adapter-examples.md`.
- Next-step rollout order is documented in `docs/execution-plan.md`.
