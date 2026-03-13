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

Request:

```json
{
  "slug": "openclaw-china",
  "name": "OpenClaw China",
  "description": "Shared context space for agent experiments"
}
```

## `POST /v1/partitions`

Admin-only.

Create or return a partition inside a tenant.

Request:

```json
{
  "tenantId": "tenant_xxx",
  "key": "project-openclaw",
  "name": "Project OpenClaw",
  "kind": "project",
  "description": "Implementation notes and shipped decisions"
}
```

## `POST /v1/agents`

Admin-only.

Register an agent caller.

Request:

```json
{
  "tenantId": "tenant_xxx",
  "name": "openclaw-main",
  "kind": "assistant",
  "metadata": {
    "channel": "discord"
  }
}
```

## `POST /v1/principals`

Admin-only.

Create a caller principal and return its bearer token once.

Request:

```json
{
  "tenantId": "tenant_xxx",
  "name": "openclaw-main",
  "kind": "service",
  "metadata": {
    "channel": "discord"
  }
}
```

## `POST /v1/principals/{principalId}/acl`

Admin-only.

Create or update partition-level ACL for a principal.

Request:

```json
{
  "partitionKey": "memory",
  "canRead": true,
  "canWrite": true,
  "allowedLayers": ["l0", "l1"]
}
```

## `POST /v1/records`

Store a curated record.

Request:

```json
{
  "tenantId": "tenant_xxx",
  "partitionKey": "project-openclaw",
  "type": "memory",
  "layer": "l1",
  "title": "Architecture direction",
  "text": "Prefer manual curation first and explicit cross-partition controls.",
  "manualSummary": "First-pass backend direction",
  "importance": 4,
  "pinned": true,
  "tags": ["architecture", "retrieval"],
  "idempotencyKey": "project-openclaw:architecture-direction:v1"
}
```

Notes:

- `layer` should be one of `l0`, `l1`, `l2`
- the body is chunked automatically
- embeddings are attached if the provider is configured
- `idempotencyKey` is the simplest way to avoid duplicate writes from multiple agents
- when auth is enabled, caller must have `canWrite=true` on the target partition

## `POST /v1/query`

Search within a tenant and selected partitions.

Request:

```json
{
  "tenantId": "tenant_xxx",
  "query": "manual curation and multi-agent retrieval",
  "partitions": ["project-openclaw", "memory"],
  "types": ["memory", "resource"],
  "layers": ["l0", "l1"],
  "limit": 5,
  "rerank": true
}
```

Response shape:

```json
{
  "items": [
    {
      "recordId": "record_xxx",
      "chunkId": "chunk_xxx",
      "title": "Architecture direction",
      "type": "memory",
      "layer": "l1",
      "partitionKey": "project-openclaw",
      "score": 0.91,
      "snippet": "Prefer manual curation first...",
      "manualSummary": "First-pass backend direction",
      "source": null,
      "tags": ["architecture"],
      "createdAt": "2026-03-13T12:00:00.000Z",
      "trace": {
        "lexical": 0.75,
        "vector": 0.89,
        "manual": 0.86,
        "recency": 1,
        "rerank": 0.93
      }
    }
  ],
  "retrieval": {
    "candidateCount": 12,
    "scoredCount": 5,
    "usedEmbeddings": true,
    "usedRerank": true
  }
}
```

Auth notes:

- admin token can query everything
- principal token can query only readable partitions
- result rows are filtered by `allowedLayers` per partition

## `POST /v1/sessions/commit`

Persist a session and optionally emit curated memories.

Request:

```json
{
  "tenantId": "tenant_xxx",
  "partitionKey": "project-openclaw",
  "agentId": "agent_xxx",
  "summary": "Settled on single-instance multi-tenant design.",
  "messages": [
    {
      "role": "user",
      "content": "We should keep manual control over important memories."
    }
  ],
  "memoryEntries": [
    {
      "title": "Storage direction",
      "layer": "l0",
      "text": "Use local disk first, remote embedding, optional rerank.",
      "importance": 4,
      "tags": ["storage", "embedding"]
    }
  ]
}
```

This endpoint is the bridge between conversational work and durable context.

Recommended default:

- use `memoryEntries.layer = "l0"` for quick recall pointers
- use `POST /v1/records` with `layer = "l1"` for curated archive entries
- use `POST /v1/records` with `layer = "l2"` for raw source materials

## Next API extensions

- `GET /v1/catalog`
- `POST /v1/resources/import`
- `POST /v1/query/plan`
- `POST /v1/records/bulk`
- `POST /v1/attachments`
