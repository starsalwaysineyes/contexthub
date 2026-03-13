# Stack decision

## Question

Should ContextHub stay on Node.js, or should it move to Python early?

## Short answer

For now, keep the service layer in Node.js.

But do not design the system as Node-only.

The right long-term shape is likely:

- Node.js or TypeScript for the HTTP API, adapters, and operator-facing control plane
- Python for optional ingestion, indexing, or ML-heavy worker pipelines if those become substantial

## Why Node.js is acceptable right now

### 1. The current product surface is API-first, not model-first

The MVP mostly needs:

- HTTP endpoints
- adapter glue for OpenClaw, Codex, Claude Code, and other agents
- light persistence
- predictable JSON contracts

Node handles this well, with very low ceremony.

### 2. The surrounding ecosystem is already JS-friendly

OpenClaw itself is Node-based, and many integration points around agent tooling are easiest to wire from JavaScript or TypeScript.

That makes Node a pragmatic choice for the first few iterations.

### 3. The current code is intentionally thin

This repo is not trying to run local embedding models, train rerankers, or do heavyweight NLP.

It is mostly coordinating:

- storage
- ranking orchestration
- adapter contracts
- session commit semantics

That is not where Node usually becomes painful.

## Where Python would be stronger

Python becomes more attractive if ContextHub starts owning much more of:

- large-scale ingestion pipelines
- offline indexing jobs
- document parsing and data science tooling
- local embedding or reranking models
- retrieval experiments that depend on the Python ML ecosystem

If the project shifts in that direction, Python workers may be the better place for those subsystems.

## Decision for now

### Keep the current MVP in Node.js

Reason:

- fastest iteration from where the repo already is
- easiest path to adapter examples for agent ecosystems we care about immediately
- lowest rewrite cost while the object model is still unstable

### Design for polyglot evolution

This means:

- keep the API contract clean and language-agnostic
- keep the storage model explicit
- avoid runtime-specific magic in the core protocol
- treat embedding and rerank providers as replaceable services

## Practical next step

Do not rewrite to Python yet.

Instead:

1. stabilize the API and storage schema
2. add adapters and ACLs
3. add deployment shape
4. re-evaluate after ingestion and indexing become real bottlenecks

## Likely upgrade path

If the project grows, a sensible evolution path is:

- migrate Node.js codebase to TypeScript for stronger schema safety
- move durable metadata from JSON to SQLite or Postgres
- add Python worker processes only when ingestion or retrieval experiments justify them

That avoids a premature rewrite while keeping the door open for a mixed stack later.
