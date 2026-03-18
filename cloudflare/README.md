# Cloudflare Worker Track

This directory is reserved for a Worker-native ContextHub implementation.

The goal is not to transplant the current Python/FastAPI service 1:1. The goal is to preserve the external phase-1 `ctx://` contract while re-implementing the backend around Cloudflare-native primitives.

## Why this exists

Phase-1 ContextHub is now mostly document-centric:

- filesystem-like `ctx://` paths
- text-heavy records and markdown docs
- low CPU request handling
- external model calls for embeddings / rerank when needed

That makes the service a plausible fit for Cloudflare Workers, provided storage and indexing are redesigned for the platform instead of copied from the current local-disk/sqlite shape.

## Proposed platform mapping

### Primary storage

Use `D1` as the canonical metadata and text store for phase-1.

Suggested shape:

- workspace / directory / file metadata in relational tables
- file text stored directly in D1 for the document-first phase
- content hash stored for idempotent writes and reindex skip logic

### Optional object storage

Use `R2` only for larger blobs or imported attachments later.

For the current markdown-first phase, `R2` is optional and should not be the first dependency.

### Search

Split into two layers:

1. lexical / metadata search
   - D1 + FTS-oriented tables or equivalent token/chunk tables
2. semantic / rerank
   - external embedding + rerank provider, or a later Worker-compatible vector path

### Coordination

Start without `Durable Objects` unless write contention becomes a real problem.

If phase-1 later needs stronger serialized writes, add a DO per user or workspace for:

- edit/apply_patch serialization
- mv/cp/rm conflict control
- long-running reindex coordination

### Background work

Do not force large `import-tree` or `reindex` jobs into a single synchronous request.

Prefer Worker-native async patterns later:

- Queues
- Cron Triggers
- Workflows

## Current skeleton

This directory now includes a first runnable Worker skeleton:

- `package.json`
- `tsconfig.json`
- `wrangler.jsonc`
- `src/index.ts`
- `migrations/0001_init.sql`

Local bootstrap:

```bash
cd cloudflare
npm install
npm run check
npx wrangler d1 migrations apply contexthub-phase1 --local
npm run dev
```

Current implemented routes:

- `GET /`
- `GET /health`
- `POST /v1/workspaces/register`
- `POST /v1/fs/mkdir`
- `GET /v1/fs/ls`
- `GET /v1/fs/stat`
- `GET /v1/fs/tree`
- `GET /v1/fs/read`
- `POST /v1/fs/write`
- remaining `/v1/fs/*` routes currently return `501` placeholders

## Recommended MVP scope

Good first Worker-native slice:

- `GET /health`
- `GET /v1/fs/read`
- `POST /v1/fs/write`
- `POST /v1/fs/edit`
- `GET /v1/fs/stat`
- `GET /v1/fs/ls`
- `GET /v1/fs/tree`
- `POST /v1/fs/search`
- `POST /v1/fs/reindex` as async job submission or small-scope sync path

Defer or simplify at first:

- full local-disk style import semantics
- giant synchronous reindex jobs
- ACL-heavy policy modeling
- exact parity with every internal Python implementation detail

## Non-goal

This folder is not for bundling the current Python server into Workers. It is for a protocol-compatible, Worker-native reimplementation.
