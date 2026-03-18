# Cloudflare Worker TODO

## MVP

- [x] Define D1 schema for user / workspace / file / chunk / search metadata
- [x] Define Worker routing for the first `/v1/fs/*` slice
- [x] Land `read/write/stat/ls/tree` first
- [ ] Land `search` with lexical-first behavior
- [ ] Land `edit` / `apply_patch` with lightweight optimistic concurrency
- [ ] Decide whether `reindex` is sync-for-small-scope or queue-backed
- [x] Add `wrangler` project skeleton with a minimal Worker entrypoint and first D1 migration

## Architecture questions

- [ ] Whether file text should live fully in D1 at phase-1 scale
- [ ] Whether semantic search should stay on external providers or move to a Worker-adjacent vector service
- [ ] Whether DO is needed from day 1 for patch/edit contention
- [ ] Whether panel stays separate or is later served by the same Worker bundle
