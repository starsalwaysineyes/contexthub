# API

## Conventions

- JSON request and response bodies
- caller supplies `tenantId`
- partition is addressed by `partitionKey`
- record layer is explicit via `layer`
- item citations come back as `recordId` + `chunkId`
- when auth is enabled, `/v1/*` requires `Authorization: Bearer <token>` except `/health`

## `GET /health`

Returns storage counts and provider readiness.

## `GET /v1/auth/me`

Returns the current auth identity.

- admin token -> returns admin identity
- principal token -> returns principal identity plus ACL summary

## `POST /v1/tenants`

Admin-only.

Create or return a tenant by slug.

## `POST /v1/partitions`

Admin-only.

Create or return a partition inside a tenant.

## `POST /v1/agents`

Admin-only.

Register an agent caller.

## `POST /v1/principals`

Admin-only.

Create a caller principal and return its bearer token once.

## `POST /v1/principals/{principalId}/acl`

Admin-only.

Create or update partition-level ACL for a principal.

## `POST /v1/records`

Store a curated record.

Notes:

- `layer` should be one of `l0`, `l1`, `l2`
- the body is chunked automatically
- embeddings are attached if the provider is configured
- `idempotencyKey` is the simplest way to avoid duplicate writes from multiple agents
- when auth is enabled, caller must have `canWrite=true` on the target partition

## `GET /v1/records/{recordId}`

Fetch one record directly.

Notes:

- useful when callers want file-like open/get behavior instead of search-only access
- when auth is enabled, caller must have `canRead=true` on the record partition

## `PATCH /v1/records/{recordId}`

Update one record in place.

Current patch scope:

- `type`
- `layer`
- `title`
- `text`
- `source`
- `tags`
- `metadata`
- `manualSummary`
- `importance`
- `pinned`

Notes:

- if `text` changes, chunks are rebuilt and embeddings are recalculated when available
- partition/tenant reassignment is intentionally not part of this first patch API

## `GET /v1/records/{recordId}/lines`

Read one record as numbered lines.

Query params:

- `from_line` (default `1`)
- `limit` (default `80`, capped server-side)

Notes:

- this is the first file-like read API for agents that want bounded reads instead of whole-record fetches
- response includes `totalLines`, `returnedLines`, and `hasMore`

## `POST /v1/records/list`

List records with structural filters instead of semantic search.

Body fields:

- `tenantId`
- `partitions`
- `types`
- `layers`
- `tags`
- `titleContains`
- `sourceKind`
- `sourcePathPrefix`

This `tags` field is the current lightweight collaboration rule surface for multi-agent sharing, e.g. `agent:openclaw`, `agent:codex`, `scope:shared`.
- `offset`
- `limit`

Notes:

- intended for browse/find/list workflows when the caller does not yet know a `recordId`
- returns lightweight record summaries with `textPreview`, `lineCount`, and source metadata
- this is the first browse-style API toward a more file-system-like experience

## `POST /v1/records/tree`

Browse one path level at a time using `source.relativePath` / `source.path`.

Body fields:

- `tenantId`
- `partitions`
- `types`
- `layers`
- `tags`
- `sourceKind`
- `pathPrefix`
- `limit`

Notes:

- returns immediate child nodes under `pathPrefix`
- each node reports whether it is a `file` or `dir`
- each node includes aggregated `recordCount`, `layers`, and `partitions`
- this is the first step toward a virtual directory tree over ContextHub records

## `POST /v1/records/grep`

Search record text line-by-line and return line numbers.

Body fields:

- same scoping fields as `POST /v1/query`: `tenantId`, `partitions`, `types`, `layers`, `tags`
- `pattern`
- `regex`
- `caseSensitive`
- `limit`
- `beforeContext`
- `afterContext`

Notes:

- returns line-level hits with `lineNumber`, `text`, `matchRanges`, `contextBefore`, and `contextAfter`
- this is meant to feel closer to `grep` / `rg` than semantic recall
- current output is line-oriented with small surrounding windows, not yet full file-level navigation

## `POST /v1/resources/import`

Import a resource into a target layer and optionally derive abstraction layers.

Current MVP supports:

- `content.kind = "inline_text"`
- optional derivation via LiteLLM in `sync` or background `async` mode
- persisted derivation job inspection via `GET /v1/derivation-jobs/{jobId}`
- persisted lineage via `GET /v1/records/{recordId}/links`

Request example:

```json
{
  "tenantId": "tenant_xxx",
  "partitionKey": "project-openclaw",
  "type": "resource",
  "targetLayer": "l2",
  "title": "Raw meeting transcript",
  "content": {
    "kind": "inline_text",
    "text": "Full raw transcript..."
  },
  "derive": {
    "enabled": true,
    "mode": "sync",
    "emitLayers": ["l1", "l0"],
    "provider": "litellm",
    "promptPreset": "archive_and_memory"
  }
}
```

Sync response example:

```json
{
  "record": {
    "id": "record_source_xxx",
    "layer": "l2"
  },
  "derivation": {
    "status": "completed",
    "mode": "sync",
    "effectiveMode": "sync",
    "plannedLayers": ["l1", "l0"],
    "job": {
      "id": "derive_xxx",
      "status": "completed",
      "requestedLayers": ["l1", "l0"]
    },
    "records": [
      { "id": "record_l1_xxx", "layer": "l1" },
      { "id": "record_l0_xxx", "layer": "l0" }
    ],
    "links": [
      { "sourceRecordId": "record_source_xxx", "targetRecordId": "record_l1_xxx", "relation": "derived_from" },
      { "sourceRecordId": "record_source_xxx", "targetRecordId": "record_l0_xxx", "relation": "derived_from" }
    ]
  }
}
```

Async response example:

```json
{
  "record": {
    "id": "record_source_xxx",
    "layer": "l2"
  },
  "derivation": {
    "status": "queued",
    "mode": "async",
    "effectiveMode": "async",
    "plannedLayers": ["l1", "l0"],
    "job": {
      "id": "derive_xxx",
      "status": "queued"
    },
    "records": [],
    "links": []
  }
}
```

## `GET /v1/derivation-jobs/{jobId}`

Fetch a persisted derivation job.

Notes:

- useful for debugging import/derive behavior
- `status` now transitions through `queued -> running -> completed|failed` for async jobs
- current async worker is in-process background execution; restart recovery is the next hardening step

## `GET /v1/records/{recordId}/links`

List record links where the given record is the source.

Notes:

- current relation emitted by import derive is `derived_from`
- link metadata carries `jobId` and layer mapping

## `POST /v1/query`

Search within a tenant and selected partitions.

Body fields:

- `tenantId`
- `query`
- `partitions`
- `types`
- `layers`
- `tags`
- `limit`
- `rerank`

Notes:

- `tags` is the current lightweight collaboration filter surface for multi-agent recall and shared-memory routing

Auth notes:

- admin token can query everything
- principal token can query only readable partitions
- result rows are filtered by `allowedLayers` per partition

## `POST /v1/sessions/commit`

Persist a session and optionally emit curated memories.

Recommended default:

- use `memoryEntries.layer = "l0"` for quick recall pointers
- use `POST /v1/records` with `layer = "l1"` for curated archive entries
- use `POST /v1/records` with `layer = "l2"` for raw source materials

## Next API extensions

- `GET /v1/catalog`
- `POST /v1/query/plan`
- `POST /v1/records/bulk`
- `POST /v1/attachments`
