# Roadmap

## Phase 0 - Python baseline (done)

- switch core runtime to Python + uv
- ship FastAPI service with current MVP endpoints
- move metadata store to SQLite
- keep Node MVP snapshot in `legacy/node-mvp/`
- add uv-based CI and secrets scan

## Phase 1 - make the backend practical

- add stable schema migration scripts
- add bulk import for Markdown archives and daily memory files
- add partition policy checks per agent
- add stronger duplicate control and write throttling hooks

## Phase 2 - make it agent-friendly

- publish adapter examples for OpenClaw, Codex, Claude Code, Gemini, and generic MCP clients
- add session commit helpers and idempotent write wrappers
- add query-plan and citation-focused retrieval responses
- add operator-facing export/import commands

## Phase 3 - make it production-worthy

- add authn/authz, API keys, and per-agent ACL policies
- add background indexing workers
- add attachment storage and references
- optionally split heavy ingestion/retrieval workers into dedicated processes
- add metrics, logs, and repair tooling

## Strong opinions that should stay

- do not force full auto-memory extraction everywhere
- do not hide important ranking logic from operators
- do not collapse all context into one global namespace
- do not make agent integration depend on a single vendor runtime
