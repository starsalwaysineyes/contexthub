# Roadmap

## Phase 0 - Python baseline (done)

- switch core runtime to Python + uv
- ship FastAPI service with current MVP endpoints
- move metadata store to SQLite
- keep Node MVP snapshot in `legacy/node-mvp/`
- add uv-based CI and secrets scan

## Phase 1 - backend core (mostly done)

- explicit `L0/L1/L2` model
- first-pass bearer auth + partition ACL
- upload/derivation design with LiteLLM as abstraction gateway
- `POST /v1/resources/import` MVP (`inline_text`) with optional sync derivation
- derivation lineage persistence (`derivation_jobs` + `record_links`)
- first-pass async derive lifecycle with persisted status + inspection endpoints
- bulk import for Markdown archives and daily memory files
- next: retry policy hardening and restart recovery for queued jobs

## Phase 2 - make it agent-friendly

- publish adapter examples for OpenClaw, Codex, and Claude Code (done)
- add session commit helpers and idempotent write wrappers (done for first-pass examples)
- next: expose a generic write/import surface where clients can explicitly target `L0` / `L1` / `L2`
- next: treat local archive/daily-memory behavior as optional migration presets, not product assumptions
- next: add query-plan and citation-focused retrieval responses
- next: add operator-facing export/import commands

## Phase 3 - make it production-worthy

- add richer authn/authz, token rotation, and audit logs
- add background indexing workers
- add attachment storage and references
- optionally split heavy ingestion/retrieval workers into dedicated processes
- add metrics, logs, and repair tooling

## Strong opinions that should stay

- do not force full auto-memory extraction everywhere
- do not hide important ranking logic from operators
- do not collapse all context into one global namespace
- do not make agent integration depend on a single vendor runtime
