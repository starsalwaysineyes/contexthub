# Import Jobs

## Goal

Provide an operator-friendly path to import local Markdown trees into ContextHub before server migration and plugin work.

## Current command

Use the built-in CLI:

```bash
uv run python -m contexthub import-markdown \
  --base-url http://127.0.0.1:4040 \
  --token "$CONTEXT_HUB_TOKEN" \
  --tenant-id tenant_xxx \
  --partition-key memory \
  --layer l1 \
  --root /path/to/markdown/tree
```

## Useful options

- `--limit N` import only the first N Markdown files
- `--dry-run` print payloads without sending them
- `--derive-layers l1,l0` request derivation during import
- `--prompt-preset archive_and_memory`
- `--derive-mode sync|async`
- `--type resource|summary|memory|note`
- `--tag imported --tag local`

## Current behavior

- discovers `*.md` recursively
- uses the first Markdown heading as title if available
- otherwise uses filename stem
- sends each file via `POST /v1/resources/import`
- sets deterministic `idempotencyKey` from relative path + layer
- records `relativePath` in metadata

## Recommended mapping for local materials

### Daily memory files

- source: `memory/YYYY-MM-DD.md`
- target layer: `l0`
- partition suggestion: `memory`

### Archive documents

- source: `archive/**/*.md`
- target layer: `l1`
- partition suggestion: project-specific archive partition

### Raw project notes / transcripts

- source: imported raw materials, transcripts, copied docs
- target layer: `l2`
- optional derivation: `--derive-layers l1,l0`

## Example sequences

### Dry-run archive import

```bash
uv run python -m contexthub import-markdown \
  --tenant-id tenant_xxx \
  --partition-key project-openclaw \
  --layer l1 \
  --root ~/Desktop/notes/contexthub \
  --dry-run
```

### Import raw materials and derive summaries

```bash
uv run python -m contexthub import-markdown \
  --tenant-id tenant_xxx \
  --partition-key project-openclaw \
  --layer l2 \
  --root ~/Desktop/notes/contexthub \
  --derive-layers l1,l0 \
  --prompt-preset archive_and_memory
```

## Current limitations

- imports only Markdown text
- no binary attachments yet
- no async job queue yet
- no per-file resume cursor yet

This is enough to begin structured migration work.
