# Stack decision

## Decision

ContextHub switches from Node.js MVP to Python as the primary runtime, with `uv` as package/dependency manager.

## Why switch now

- Stability and operational predictability are more important than ultra-fast prototyping at this stage.
- Python ecosystem fit is better for future ingestion/indexing/retrieval experiments.
- `uv` gives fast, reproducible environment management and a clear lockfile-based CI path.

## What stays unchanged

- API contract and endpoint shape stay close to the original MVP.
- Multi-tenant + partitioned context model stays unchanged.
- Manual curation first, automation second.
- Embedding/rerank provider interfaces remain OpenAI-compatible.

## What changes

- Runtime: `fastapi + uvicorn`
- Storage: SQLite-backed metadata by default
- Dependency management: `pyproject.toml + uv.lock`
- CI: `uv sync --frozen` + `uv run pytest`

## Migration note

The previous Node implementation is preserved at `legacy/node-mvp/` for reference.

This keeps migration auditable while allowing the main branch to move forward on Python.
