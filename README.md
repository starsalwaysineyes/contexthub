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
- Retrieval pipeline with lexical score + optional embeddings + optional rerank
- Python client SDK in `contexthub/client.py`
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

Default endpoints:

- `GET /health`
- `GET /v1/auth/me`
- `POST /v1/tenants`
- `POST /v1/partitions`
- `POST /v1/agents`
- `POST /v1/principals`
- `POST /v1/principals/{principalId}/acl`
- `POST /v1/records`
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
- [ ] Add OpenClaw adapter examples + one-command helper scripts
- [ ] Add Codex and Claude Code adapter examples
- [ ] Add Markdown/archive ingestion jobs
- [ ] Deploy first managed instance to target server

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
docs/
  architecture.md
  api.md
  openapi.yaml
  auth-acl.md
  layer-model.md
  upload-derivation-design.md
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
- Next-step rollout order is documented in `docs/execution-plan.md`.
