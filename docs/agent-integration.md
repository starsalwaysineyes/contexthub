# Agent integration

## Goal

An agent should not need to understand the full storage internals.

The minimum contract is:

1. identify the tenant
2. identify one or more partitions
3. write curated records or commit sessions
4. query with an explicit scope

## Recommended adapter shape

Each adapter should expose a small standard surface:

```ts
query(input)
writeRecord(input)
commitSession(input)
uploadFile(input)
importBatch(input)
inspectJob(input)
inspectLinks(input)
```

That covers:

- chat agents
- coding agents
- cron or workflow agents
- review bots
- migration utilities
- operator/debug tooling

## OpenClaw adapter idea

### Write side

- after a meaningful task, call `POST /v1/sessions/commit`
- include the final summary
- include only curated `memoryEntries`, not every raw turn
- set `idempotencyKey` on memory entries when possible
- allow explicit user-facing actions such as:
  - save text directly to `L0` / `L1` / `L2`
  - upload a local file directly to `L0` / `L1` / `L2`
  - import a local folder with an optional preset

### Read side

- before answering, call `POST /v1/query`
- scope partitions per channel, task, or project
- ask for a small result set with citations
- expose retrieval trace when operators need to inspect why something was recalled

## Codex or Claude Code adapter idea

### Before work

- query the relevant project partition
- inject the top cited summaries into the task prompt

### After work

- commit a session summary
- optionally write one or two durable records: decision, gotcha, migration note

## Generic HTTP example

```bash
curl http://127.0.0.1:4040/v1/query \
  -H 'Content-Type: application/json' \
  -d '{
    "tenantId":"tenant_xxx",
    "query":"latest context backend decision",
    "partitions":["project-openclaw"],
    "limit":3,
    "rerank":true
  }'
```

## Integration rules worth keeping

- scope every read by tenant and partition
- avoid global writes without idempotency keys
- write summaries, not full noisy transcripts, unless explicitly needed
- keep citations in the return path so agents can explain where context came from

## Future adapter package plan

- `contexthub.client.ContextHubClient` (already in this repo)
- optional `@contexthub/client` for plain Node consumers
- `@contexthub/openclaw-adapter`
- adapter presets for local migration (`archive-to-l1`, `daily-to-l0`, `raw-doc-to-l2-derive`) without baking those rules into the backend contract
