# contexthub

ContextHub is being rebuilt around a phase-1 `ctx://` cloud filesystem direction.

This branch is no longer the old record-first prototype.
That history is preserved on `feat`.

## Phase 1 focus

The current goal is deliberately narrow:

- create cloud workspaces/directories
- expose a `ctx://` URI scheme
- make the cloud side feel close to a local filesystem
- provide a small `ctx_cli`
- support the core verbs first: `register-workspace`, `mkdir`, `ls`, `tree`, `stat`, `read`, `write`, `edit`, `apply-patch`, `search`, `grep`, `rg`, `glob`, `mv`, `cp`, `rm`
- expose a lightweight `/panel` so humans can browse the cloud filesystem without reconstructing the tree by hand

Permissions and fine-grained ACL are intentionally deferred, but the phase-1 service still honors a single bearer token via `CONTEXT_HUB_ADMIN_TOKEN` when that env var is set.

## Workspace model

Current skeleton supports these roots:

- `ctx://<userId>`
- `ctx://<userId>/defaultWorkspace`
- `ctx://<userId>/agentWorkspace/<agentId>`

Backed on disk by:

```text
var/data/
  users/
    <userId>/
      defaultWorkspace/
      agentWorkspaces/
        <agentId>/
```

## Run locally

```bash
uv run contexthub-serve
```

Or install direct executables for shell/Codex use:

```bash
uv tool install --from . contexthub --force
ctx_cli --help
contexthub-serve --help
```

Default bind:

- host: `127.0.0.1`
- port: `4040`
- data dir: `var/data`

Optional env:

- `CONTEXT_HUB_BIND_HOST`
- `CONTEXT_HUB_PORT`
- `CONTEXT_HUB_DATA_DIR`
- `CONTEXT_HUB_ADMIN_TOKEN`
- `CONTEXT_HUB_BASE_URL` for default `ctx_cli` cloud target
- `CONTEXT_HUB_USER_ID` for default `ctx_cli` user scope when commands would otherwise need `--user-id`
- client-side CLI requests read `CONTEXT_HUB_TOKEN` for bearer auth
- `CONTEXT_HUB_ENABLE_EMBEDDINGS` / `CONTEXT_HUB_EMBEDDING_BASE_URL` / `CONTEXT_HUB_EMBEDDING_API_KEY` / `CONTEXT_HUB_EMBEDDING_MODEL`
- `CONTEXT_HUB_ENABLE_RERANK` / `CONTEXT_HUB_RERANK_BASE_URL` / `CONTEXT_HUB_RERANK_API_KEY` / `CONTEXT_HUB_RERANK_MODEL`

## CLI

`ctx_cli` works both as `uv run ctx_cli ...` and as a direct executable after `uv tool install`.

If you set `CONTEXT_HUB_USER_ID`, commands that would otherwise need `--user-id` can stay shorter.

```bash
export CONTEXT_HUB_USER_ID=alice

ctx_cli register-workspace --default
ctx_cli register-workspace --agent-id codex
ctx_cli ls ctx://alice
ctx_cli mkdir ctx://alice/defaultWorkspace/tasks
ctx_cli stat ctx://alice/defaultWorkspace/tasks
ctx_cli write ctx://alice/defaultWorkspace/tasks/today.md --text "hello"
ctx_cli read ctx://alice/defaultWorkspace/tasks/today.md
ctx_cli edit ctx://alice/defaultWorkspace/tasks/today.md --match hello --replace world
ctx_cli grep --pattern world --scope-uri ctx://alice/defaultWorkspace --glob 'tasks/*.md'
ctx_cli rg --pattern 'w.*d' --scope-uri ctx://alice/defaultWorkspace
ctx_cli glob --pattern 'tasks/*.md' --scope-uri ctx://alice/defaultWorkspace
ctx_cli mv ctx://alice/defaultWorkspace/tasks/today.md ctx://alice/defaultWorkspace/archive/today.md
ctx_cli cp ctx://alice/defaultWorkspace/archive/today.md ctx://alice/defaultWorkspace/archive/today-copy.md
ctx_cli rm ctx://alice/defaultWorkspace/archive/today-copy.md
ctx_cli import-tree ~/my-memory ctx://alice/defaultWorkspace/memory --include '*.md'
ctx_cli search --query world
ctx_cli search --query "cloud cutover" --mode hybrid
ctx_cli search --query "phase1" --workspace-mode user --mode lexical --expansion 24040 --expansion import-tree
ctx_cli reindex --scope-uri ctx://alice/defaultWorkspace
```

## HTTP surface

- `GET /` -> redirects to `/panel`
- `GET /panel`
- `GET /health`
- `POST /v1/workspaces/register`
- `POST /v1/fs/mkdir`
- `GET /v1/fs/ls?uri=...`
- `GET /v1/fs/tree?uri=...&depth=...`
- `GET /v1/fs/stat?uri=...`
- `GET /v1/fs/read?uri=...`
- `POST /v1/fs/write`
- `POST /v1/fs/edit`
- `POST /v1/fs/apply_patch`
- `POST /v1/fs/mv`
- `POST /v1/fs/cp`
- `POST /v1/fs/rm`
- `POST /v1/fs/search` (`workspaceMode` now defaults to `default-only`; set `workspaceMode=user|default-first` when you want a wider scope; `plan.source=index|live-scan`)
- `POST /v1/fs/reindex`
- `POST /v1/fs/glob`
- `POST /v1/fs/grep`
- `POST /v1/fs/rg`

## Panel

Open the service root or `/panel` in a browser.

The page is intentionally operator-first:

- paste the same bearer token used for API calls
- start at `ctx://<userId>` or `ctx://<userId>/defaultWorkspace`
- inspect tree / entries / stats / file contents
- run search against `defaultWorkspace` by default, or widen to whole-user scope only when needed
- make small deliberate updates with overwrite, mkdir, and delete actions

It is not a full IDE; it is a management panel for understanding and searching what is already stored in `ctx://`.

## Cloudflare Track

A Worker-native implementation track now lives under `cloudflare/`.

[![Deploy to Cloudflare](https://deploy.workers.cloudflare.com/button)](https://deploy.workers.cloudflare.com/?url=https://github.com/starsalwaysineyes/contexthub/tree/main/cloudflare)

That directory is for a protocol-compatible reimplementation of the phase-1 `ctx://` service on Cloudflare primitives such as `D1`, optional `R2`, and later queue/do-based background coordination. It is not intended to bundle the current Python server unchanged.

See `cloudflare/README.md` and `cloudflare/DEPLOY.md` for the free-tier deployment path.

## Tests

```bash
uv run pytest
```
