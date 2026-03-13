# Execution Plan

## Current order

### Phase 1 - strengthen the backend core

- make `L0/L1/L2` explicit in the data model
- finish first-pass auth and partition ACL
- add import jobs for local Markdown memory/archive material
- keep retrieval explainable and debuggable

### Phase 2 - adapter readiness

- ship OpenClaw adapter examples
- ship Codex and Claude Code adapter examples
- add one-command helper scripts for session commit and query
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
2. first-pass auth + ACL
3. import pipeline for local materials
4. adapter examples
5. plugin design
6. server deployment
7. cutover
