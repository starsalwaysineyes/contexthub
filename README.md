# ContextHub

ContextHub is a small, agent-native context backend prototype.

The target is not "yet another RAG demo". The target is a single backend that lets many agents share a controlled memory and retrieval layer without forcing everything into one opaque auto-generated blob.

## Design stance

- Manual curation first, automation second.
- Single instance, multi-tenant.
- Local disk for durable storage.
- Remote Embedding and optional remote Rerank.
- Cross-partition retrieval stays explicit and controllable.
- Agent integration should be boring: plain HTTP, simple JSON, no framework lock-in.

## What is in this repo today

- A runnable HTTP MVP in `src/`
- Disk-backed state storage in `var/data/state.json`
- Core objects: tenants, partitions, agents, records, sessions
- Retrieval pipeline with lexical scoring, optional embeddings, optional rerank
- Session commit flow that can materialize curated memory entries
- Tiny JS client SDK in `src/client/contextHubClient.js`
- Architecture and API notes in `docs/`

## Why this shape

The current working conclusion is:

- existing `memory -> archive -> raw materials` already behaves like a human-curated `L0/L1/L2`
- OpenViking is useful as an engineering reference, but not as something to copy blindly
- the better long-term move is a cloud context backend that keeps human semantic control while offering system-level retrieval and multi-agent reuse

This repo is the first implementation pass for that direction.

## Quick start

```bash
cp .env.example .env
# fill the API keys only if you want remote embedding or rerank
npm test
npm start

# in another terminal
npm run example
```

Default server:

- `GET /health`
- `POST /v1/tenants`
- `POST /v1/partitions`
- `POST /v1/agents`
- `POST /v1/records`
- `POST /v1/query`
- `POST /v1/sessions/commit`

## Example flow

```bash
curl http://127.0.0.1:4040/v1/tenants \
  -H 'Content-Type: application/json' \
  -d '{"slug":"openclaw-china","name":"OpenClaw China"}'

curl http://127.0.0.1:4040/v1/partitions \
  -H 'Content-Type: application/json' \
  -d '{"tenantId":"tenant_xxx","key":"project-openclaw","name":"Project OpenClaw"}'

curl http://127.0.0.1:4040/v1/records \
  -H 'Content-Type: application/json' \
  -d '{
    "tenantId":"tenant_xxx",
    "partitionKey":"project-openclaw",
    "type":"memory",
    "title":"Architecture direction",
    "text":"Prefer manual curation first, optional auto-abstraction, and controlled cross-partition retrieval.",
    "importance":4,
    "pinned":true
  }'

curl http://127.0.0.1:4040/v1/query \
  -H 'Content-Type: application/json' \
  -d '{
    "tenantId":"tenant_xxx",
    "query":"manual curation and cross-partition retrieval",
    "partitions":["project-openclaw"],
    "rerank":true
  }'
```

## Configuration

Use `.env.example` as the template.

The loader checks `.env.local` then `.env`, and you can override with `CONTEXT_HUB_ENV_FILE=/path/to/file`.

Recommended initial provider values:

- embedding base URL: `https://cloud.infini-ai.com/maas/v1`
- embedding model: `bge-m3`
- rerank base URL: `https://cloud.infini-ai.com/maas/v1`
- rerank model: `bge-reranker-v2-m3`

The repo does not commit real keys.

Before pushing, run:

```bash
npm run check:secrets
```

## TODO

- [x] Bootstrap a minimal multi-tenant HTTP MVP
- [x] Ship initial docs and OpenAPI description
- [x] Add a tiny JS client for agent-side integration
- [x] Add local and CI secret scanning
- [ ] Add OpenClaw adapter examples and one-command helper scripts
- [ ] Add Codex and Claude Code adapter examples
- [ ] Add first-pass auth and partition ACL enforcement
- [ ] Replace JSON metadata store with SQLite after schema stabilizes
- [ ] Add Markdown/archive import jobs
- [ ] Deploy the first managed instance on the target server

## Repo layout

```text
src/
  client/
  config.js
  server.js
  router.js
  providers/
  retrieval/
  services/
  storage/
  utils/
scripts/
  check-secrets.js
docs/
  architecture.md
  api.md
  openapi.yaml
  agent-integration.md
  roadmap.md
  stack-decision.md
test/
```

## Stack note

The current decision is: keep the service layer in Node.js for now, but keep the protocol clean enough that Python workers can be added later if ingestion or ML-heavy indexing becomes the real center of gravity. See `docs/stack-decision.md`.

## Near-term roadmap

1. Add stable object schemas and migrations.
2. Add richer partition policy and cross-zone ACL checks.
3. Add adapter examples for OpenClaw, Codex CLI, Claude Code, and generic OpenAI-style agents.
4. Add ingestion jobs for Markdown archives and session transcripts.
5. Add a thin dashboard for operators.

## Non-goals for this MVP

- perfect ranking
- distributed storage
- background worker cluster
- implicit magic memory extraction without operator control
