# Roadmap

## Phase 0 - repo bootstrap

Done in this pass:

- create the repository skeleton
- define the MVP object model
- ship a disk-backed HTTP service
- wire optional embedding and rerank clients
- document the design stance

## Phase 1 - make the backend practical

- add `.env` loading and config validation
- add bulk import for Markdown archives and daily memory files
- add partition policy checks per agent
- add stable schema versioning and migration scripts
- add better duplicate control and update semantics

## Phase 2 - make it agent-friendly

- publish adapter examples for OpenClaw, Codex, Claude Code, Gemini, and generic MCP clients
- add session commit helpers and idempotent write wrappers
- add query plan and citation-focused retrieval responses
- add operator-facing export/import commands

## Phase 3 - make it production-worthy

- move metadata to SQLite or Postgres
- add background indexing workers
- add attachment storage and references
- add authn/authz, API keys, and per-agent policies
- add metrics, logs, and repair tooling

## Strong opinions that should stay

- do not force full auto-memory extraction everywhere
- do not hide important ranking logic from operators
- do not collapse all context into one global namespace
- do not make agent integration depend on a single vendor runtime
