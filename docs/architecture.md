# Architecture

## Problem

Multiple agents need a shared context layer, but the usual choices are awkward:

- plain vector DBs are too low-level
- fully automatic memory systems are hard to steer
- local Markdown archives are flexible but not easy to reuse across agents

The target system should keep the flexibility of human-curated archives while adding a stable service layer that any agent can call.

## Principles

### 1. Human semantic control stays first-class

The operator should be able to decide:

- what gets stored
- which partition it belongs to
- which items are pinned or high-importance
- whether a session commit should materialize memory entries

Automation is useful, but it should augment the operator instead of replacing them.

### 2. One instance, many tenants

A single deployment should be able to serve:

- multiple users
- multiple projects
- multiple agents under the same project

That is why tenant and partition are explicit top-level concepts.

### 3. Retrieval is layered

The retrieval pipeline is intentionally layered:

1. lexical filtering for cheap candidate generation
2. optional vector similarity if embeddings exist
3. manual curation boosts
4. optional rerank for the final shortlist

This mirrors the practical conclusion that retrieval should be progressive, controllable, and explainable.

### 4. Storage is local and inspectable

The first version uses local disk state so operators can inspect, back up, migrate, and debug the system without a hidden managed dependency.

## Domain model

### Tenant

A top-level namespace.

Example:

- `openclaw-china`
- `jiangtao-personal`

### Partition

A retrieval and governance boundary inside a tenant.

Example:

- `memory`
- `project-openclaw`
- `research-agent-memory`
- `ops`

Partitions are the unit that lets us say "this agent can search here, but not there".

### Agent

A registered caller or producer.

Example:

- `openclaw-main`
- `codex-reviewer`
- `claude-ops`

### Record

The canonical stored knowledge object.

A record can represent:

- memory
- resource
- skill
- note
- summary

Each record keeps curated metadata such as `importance`, `pinned`, `tags`, and `manualSummary`.

### Chunk

A retrieval unit derived from a record body.

Chunks may carry embeddings if the embedding provider is configured.

### Session

A persisted conversation or task commit.

A session can optionally emit curated memory entries into the same partition.

## Retrieval flow

```text
query
  -> filter tenant + partition + type
  -> lexical candidate scoring
  -> optional embedding similarity
  -> manual curation and recency boosts
  -> optional rerank
  -> cited result list
```

## Why partitions matter

The hard part is not just search quality. The hard part is safe reuse.

Agents should be able to share a backend without automatically sharing everything. Partitioning gives us a clean control point for:

- privacy boundaries
- project boundaries
- testing vs production separation
- selective cross-zone recall

## Why not copy OpenViking literally

OpenViking is a useful reference because it treats context as a system, not just as top-k retrieval.

But this project deliberately avoids a blind copy because the current preference is:

- keep manual archive freedom
- keep operator-visible semantics
- let automatic summaries stay optional
- make the backend easy to adapt to very different agents

So the design is inspired by that direction, but opinionated toward explicit human curation.

## MVP storage choice

Current choice: local JSON state on disk.

Why it is acceptable for MVP:

- tiny operational surface
- easy inspection
- fast iteration on schemas
- easy migration later to SQLite or Postgres

Planned next step after schema stabilizes:

- move metadata to SQLite
- keep large raw content on disk or object storage
- optionally add background indexing workers

## Integration contract

Every agent should only need three core patterns:

1. write a record
2. commit a session
3. run a query

That keeps adapters thin and portable.

## Suggested future adapters

- OpenClaw plugin hook
- Codex CLI helper script
- Claude Code post-task commit helper
- generic REST client for any MCP/agent runtime

## Open questions

- should partition ACLs be static or policy-evaluated per agent
- when should session commits auto-suggest memory entries
- do we need a dedicated `skill` pipeline or keep it as tagged records first
- when to introduce object storage for large attachments
