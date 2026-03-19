# Cloudflare Worker TODO

## MVP

- [x] Define D1 schema for user / workspace / file / chunk / search metadata
- [x] Define Worker routing for the first `/v1/fs/*` slice
- [x] Land `read/write/stat/ls/tree` first
- [x] Land `search` with lexical-first behavior
- [ ] Land `apply_patch` with lightweight optimistic concurrency
- [x] Land a first small-scope synchronous `reindex`
- [ ] Decide whether larger `reindex` should later move to queue-backed execution
- [x] Add `wrangler` project skeleton with a minimal Worker entrypoint and first D1 migration

## Architecture questions

- [ ] Whether file text should live fully in D1 at phase-1 scale
- [ ] Whether semantic search should stay on external providers or move to a Worker-adjacent vector service
- [ ] Whether DO is needed from day 1 for patch/edit contention
- [ ] Whether panel stays separate or is later served by the same Worker bundle
