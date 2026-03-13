# Upload and Derivation Design

## Goal

Allow callers to:

- upload or write content directly to a chosen layer
- optionally ask the service to derive higher-abstraction layers automatically
- keep manual content as source of truth
- route LLM calls through LiteLLM for easier model governance

This is the missing bridge between:

- direct `L0/L1/L2` writes
- future import jobs
- future OpenClaw plugin automation

## Current MVP status

Implemented now:

- `POST /v1/resources/import`
- `content.kind = inline_text`
- optional derivation through LiteLLM abstraction client
- `mode=async` currently accepted but executed as sync (`effectiveMode=sync`)

Still pending:

- async job queue and retry model
- file/path/blob import kinds
- record link and derivation job tables

## Core rules

- Caller chooses the target layer explicitly.
- Automatic abstraction is optional, never mandatory.
- Manual records always win over derived records.
- Derived records must be linked back to their source record.
- `L2 -> L1 -> L0` is the main derivation direction.
- `L1 -> L0` is also valid.
- `L0` does not derive further upward.

## Recommended API shape

## `POST /v1/resources/import`

This is the preferred endpoint for uploads, imports, and derivation requests.

Request shape:

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
  "source": {
    "kind": "transcript",
    "origin": "meeting-2026-03-14"
  },
  "derive": {
    "enabled": true,
    "mode": "async",
    "emitLayers": ["l1", "l0"],
    "strategy": "preserve_manual",
    "promptPreset": "archive_and_memory",
    "provider": "litellm",
    "model": "gpt-5.4"
  },
  "metadata": {
    "channel": "discord"
  }
}
```

## `content.kind`

Recommended values:

- `inline_text`
- `markdown_file`
- `external_ref`
- `blob_ref`

For MVP implementation, `inline_text` is enough.

## `derive` parameters

- `enabled`: whether abstraction should run
- `mode`: `sync` or `async`
- `emitLayers`: target derived layers, usually `[`l1`, `l0`]` or `[`l0`]`
- `strategy`: default `preserve_manual`
- `promptPreset`: which derivation prompt family to use
- `provider`: use `litellm`
- `model`: routed model alias managed by LiteLLM

## Response shape

```json
{
  "record": {
    "id": "record_source_xxx",
    "layer": "l2"
  },
  "derivation": {
    "status": "queued",
    "jobId": "job_xxx",
    "plannedLayers": ["l1", "l0"]
  }
}
```

If `mode = sync`, the response may include generated records directly.

## Derived record behavior

Every derived record should carry link metadata such as:

```json
{
  "derivedFromRecordId": "record_source_xxx",
  "derivationJobId": "job_xxx",
  "derivationProvider": "litellm",
  "derivationModel": "gpt-5.4",
  "derivationPromptPreset": "archive_and_memory"
}
```

## Manual-first override policy

The system must not overwrite a human-curated record silently.

Recommended behavior:

- if manual `L1` already exists, auto-generated `L1` becomes a sidecar draft or is skipped
- if manual `L0` already exists, auto-generated `L0` is skipped unless explicitly forced
- default strategy: `preserve_manual`

Possible strategies:

- `preserve_manual`
- `create_sidecar`
- `replace_derived_only`

## LiteLLM integration

Use LiteLLM as the abstraction gateway.

Why:

- model routing stays centralized
- API keys stay easier to manage
- switching models later is cheap
- logging, retries, and quota policy can stay in one place

## Suggested config

```text
CONTEXT_HUB_ABSTRACTION_PROVIDER=litellm
CONTEXT_HUB_ABSTRACTION_BASE_URL=http://127.0.0.1:4000
CONTEXT_HUB_ABSTRACTION_API_KEY=
CONTEXT_HUB_ABSTRACTION_MODEL=gpt-5.4
CONTEXT_HUB_ABSTRACTION_TIMEOUT_SECONDS=60
```

ContextHub should call LiteLLM using an OpenAI-compatible chat/completions or responses API shape. The exact backend model can then be changed inside LiteLLM without changing ContextHub.

## Local test strategy

For local testing, the abstraction route can point LiteLLM at the current local `openai-codex/gpt-5.4` compatible configuration without committing any private credentials into the repo.

## Prompt presets

Recommended initial presets:

- `archive_and_memory`
  - input: `L2`
  - output: `L1` detailed archive + `L0` concise memory pointer
- `memory_only`
  - input: `L1`
  - output: `L0`
- `archive_only`
  - input: `L2`
  - output: `L1`

## Suggested storage additions

To support this cleanly, add the following later:

- `derivation_jobs`
- `record_links`
- optional `attachments`

### `derivation_jobs`

Track:

- source record
- requested layers
- provider/model
- status
- error message
- timestamps

### `record_links`

Track:

- `source_record_id`
- `derived_record_id`
- relation type such as `derived_from`

## OpenClaw plugin implications

This design is important because the future plugin can do:

- upload raw channel transcripts to `L2`
- request `L1/L0` derivation asynchronously
- retrieve only `L0/L1` by default during recall
- avoid pulling raw `L2` unless explicitly needed

## Implementation order

1. keep this as design only for now
2. implement first-pass auth + partition ACL (done)
3. implement `resources/import` with `inline_text` (done)
4. add LiteLLM abstraction client (done, sync path)
5. add async derivation jobs (next)
6. expose plugin-facing helper endpoints
