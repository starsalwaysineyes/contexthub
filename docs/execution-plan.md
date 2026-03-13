# Execution Plan

## Current order

### Phase 1 - strengthen the backend core

- make `L0/L1/L2` explicit in the data model
- finish first-pass auth and partition ACL
- finalize upload + derivation design for `targetLayer + auto derive`
- add import jobs for local Markdown memory/archive material
- keep retrieval explainable and debuggable

Current status:

- `L0/L1/L2` explicit model: done
- first-pass auth + partition ACL: done
- upload + derivation design: done
- `/v1/resources/import` MVP (`inline_text`) + optional sync LiteLLM derivation: done
- derivation lineage persistence (`derivation_jobs` + `record_links`): done
- local markdown/archive bulk import jobs: done (first-pass CLI)
- first-pass true async derive lifecycle (`mode=async` background execution + persisted status): done
- next: retries policy hardening / restart recovery for queued jobs

### Phase 2 - adapter readiness

- ship OpenClaw adapter examples (done)
- ship Codex and Claude Code adapter examples (done)
- add one-command helper scripts for session commit and query (done)
- verify that agents can write `L0`, write `L1`, and query `L2` safely

### Phase 3 - plugin design for OpenClaw

Only start this when the backend side is stable enough.

Readiness conditions:

- layer model is stable
- auth + ACL exists
- import flow exists
- adapter behavior is no longer changing every day

At that point, the OpenClaw plugin should focus on:

- pre-answer query hook
- post-task/session commit hook
- channel or project to partition routing
- configurable recall policy by layer and partition

### Phase 4 - migration to the test server

Target server:

- `root@38.55.39.92 -p 2222`

Current status:

- baseline bootstrap is done: `uv` + Python 3.12 + repo sync + `systemd` service (`contexthub`) + localhost health check
- smoke write/query on server is validated
- remote provider env is now configured on the server
- async derive success path is validated on server with embeddings + rerank enabled
- deploy script now force-restarts the service after repo sync so freshly pulled code is actually loaded
- next: import selected local materials, then harden queued-job recovery after restart

Migration scope should include:

- ContextHub service
- environment and keys
- existing local memory/archive material selected for import
- service management (`systemd` preferred)
- backup and rollback path

### Phase 5 - cut local machine over

Only do this after server-side validation.

Cutover checklist:

- health checks stable
- write path verified
- query path verified
- import results spot-checked
- local OpenClaw/plugin points to server URL
- rollback path documented

## Near-term deliverables

1. explicit layer model done
2. upload + derivation design done
3. first-pass auth + ACL done
4. import pipeline for local materials
5. adapter examples
6. plugin design
7. server deployment
8. cutover
