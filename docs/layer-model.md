# Layer Model

## Goal

Make the user's working model explicit in the backend instead of leaving it as an informal convention.

The three layers are:

- `L0`: light memory pointers and quick recall entries
- `L1`: curated archive/detail summaries
- `L2`: raw source material and low-abstraction resources

## Current mapping in ContextHub

### `L0`

Use for:

- short daily memory notes
- decisions or reminders extracted from sessions
- concise retrieval anchors

Current representation:

- `records.layer = "l0"`
- usually `type = "memory"`
- often written through `POST /v1/sessions/commit` with `memoryEntries`

### `L1`

Use for:

- event archives
- implementation summaries
- structured detailed notes that are already human-curated

Current representation:

- `records.layer = "l1"`
- direct `POST /v1/records` is the default path
- `manualSummary`, `importance`, `pinned`, `tags` are the main curation signals

### `L2`

Use for:

- raw transcripts
- original documents copied as-is
- file-level or source-level material with minimal abstraction

Current representation:

- `records.layer = "l2"`
- usually paired with `type = "resource"` or `type = "note"`
- `source` and `metadata` can hold origin references

## What is already implemented

- explicit `layer` field on records
- explicit `layer` field on `memoryEntries`
- query-side `layers` filter
- SQLite persistence for the layer field
- layer values returned in query results

## What is still missing

- first-class attachments / binary assets for richer `L2`
- import pipeline from local Markdown archives and project files
- automatic L2 -> L1 -> L0 derivation pipeline implementation
- policy rules such as "this agent can read L0/L1 but not L2"

The derivation design is now documented in `docs/upload-derivation-design.md`, but it is not implemented yet.

## Recommended usage pattern

- session or chat recap -> write `L0`
- human-curated archive -> write `L1`
- raw materials, transcripts, original docs -> write `L2`

## Example

### Write an `L0` memory pointer

```json
{
  "tenantId": "tenant_xxx",
  "partitionKey": "memory",
  "type": "memory",
  "layer": "l0",
  "title": "Deployment decision",
  "text": "Prefer single-instance multi-tenant deployment first.",
  "importance": 4
}
```

### Write an `L1` archive note

```json
{
  "tenantId": "tenant_xxx",
  "partitionKey": "project-openclaw",
  "type": "summary",
  "layer": "l1",
  "title": "ContextHub architecture direction",
  "text": "Detailed archive of the current design direction.",
  "manualSummary": "Working baseline for implementation"
}
```

### Write an `L2` raw source record

```json
{
  "tenantId": "tenant_xxx",
  "partitionKey": "project-openclaw",
  "type": "resource",
  "layer": "l2",
  "title": "Raw meeting transcript",
  "text": "Full raw transcript content...",
  "source": {
    "kind": "transcript",
    "origin": "meeting-2026-03-14"
  }
}
```
