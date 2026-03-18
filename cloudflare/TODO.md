# Cloudflare Worker TODO

## MVP

- [ ] Define D1 schema for user / workspace / file / chunk / search metadata
- [ ] Define Worker routing for `/v1/fs/*`
- [ ] Land `read/write/stat/ls/tree` first
- [ ] Land `search` with lexical-first behavior
- [ ] Decide whether `reindex` is sync-for-small-scope or queue-backed
- [ ] Add `wrangler` project skeleton only after the API surface is agreed

## Architecture questions

- [ ] Whether file text should live fully in D1 at phase-1 scale
- [ ] Whether semantic search should stay on external providers or move to a Worker-adjacent vector service
- [ ] Whether DO is needed from day 1 for patch/edit contention
- [ ] Whether panel stays separate or is later served by the same Worker bundle
