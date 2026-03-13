# Adapter Examples

## Goal

Provide immediately usable examples for the first three target callers:

- OpenClaw
- Codex
- Claude Code

These are not the final plugin. They are thin adapter examples and helper scripts that exercise the stable backend API.

## Files

### Python examples

- `examples/openclaw_query.py`
- `examples/openclaw_commit.py`
- `examples/codex_commit.py`
- `examples/claude_code_commit.py`

### Helper scripts

- `scripts/openclaw-query.sh`
- `scripts/openclaw-commit.sh`
- `scripts/codex-commit.sh`
- `scripts/claude-code-commit.sh`

## Shared environment variables

```text
CONTEXT_HUB_BASE_URL=http://127.0.0.1:4040
CONTEXT_HUB_TOKEN=...
CONTEXT_HUB_TENANT_ID=tenant_xxx
CONTEXT_HUB_PARTITION_KEY=project-openclaw
CONTEXT_HUB_AGENT_ID=agent_xxx
```

## OpenClaw recall example

```bash
./scripts/openclaw-query.sh \
  "latest context backend decision" \
  --partitions project-openclaw,memory \
  --layers l0,l1 \
  --limit 5
```

This is the shape the future plugin can call before answering.

## OpenClaw commit example

```bash
./scripts/openclaw-commit.sh \
  --summary "Settled on first-pass auth and partition ACL" \
  --memory-title "Auth baseline" \
  --memory-text "ContextHub now supports principals and partition ACL." \
  --memory-layer l0 \
  --memory-tags auth,acl
```

## Codex commit example

```bash
./scripts/codex-commit.sh \
  --summary "Implemented markdown import CLI and tests" \
  --message-file ./CHANGELOG_SNIPPET.md \
  --memory-title "Import CLI shipped" \
  --memory-text "contexthub import-markdown now exists for local migration work."
```

## Claude Code commit example

```bash
./scripts/claude-code-commit.sh \
  --summary "Refined docs for auth and import flows" \
  --memory-title "Docs improved" \
  --memory-text "API, auth, and import docs are now aligned with the code."
```

## Current limits

- examples are manual wrappers, not automatic hooks yet
- they assume tokens and partition choices are already configured
- they do not replace the future OpenClaw plugin

## Why these examples matter

They let us validate:

- query path from agents
- session commit path from agents
- token and ACL behavior
- human-usable workflows before the plugin is frozen
