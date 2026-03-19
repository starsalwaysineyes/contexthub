# Cloudflare Free Deploy Guide

This guide is intentionally limited to Cloudflare features that are available on the free plan for an individual user.

## What this path assumes

- One Worker
- One D1 database
- No Durable Objects
- No R2
- No Queues
- No Vectorize

## Fastest path: Deploy to Cloudflare button

If the repo is public, you can start from the button flow:

```md
[![Deploy to Cloudflare](https://deploy.workers.cloudflare.com/button)](https://deploy.workers.cloudflare.com/?url=https://github.com/starsalwaysineyes/contexthub/tree/main/cloudflare)
```

The button flow is the closest thing to a one-click personal deployment:

- Cloudflare clones the template into the user's GitHub/GitLab account
- the user fills Worker/resource names in the setup page
- Workers Builds deploys the Worker
- D1 is provisioned from `wrangler.jsonc`
- package scripts prefill build/deploy, including D1 migrations via the `DB` binding

## Bootstrap

From the `cloudflare/` directory:

```bash
npm install
npm run bootstrap:free
```

Optional environment overrides before bootstrap:

```bash
export CTX_CF_WORKER_NAME="my-ctx-worker"
export CTX_CF_DB_NAME="my-ctx-worker-db"
export CTX_CF_DB_BINDING="DB"
```

The bootstrap script will:

1. rewrite `wrangler.jsonc` with your chosen Worker and D1 names
2. create a remote D1 database
3. inject the D1 database id into `wrangler.jsonc`
4. print the remaining deploy and `ctx_cli` onboarding commands

## Optional auth secret

If you want bearer auth enabled on the Worker:

```bash
printf '%s' 'YOUR_TOKEN' | npx wrangler secret put CONTEXT_HUB_ADMIN_TOKEN
```

If you skip this, the Worker runs without auth.

## Deploy

```bash
npm run deploy
```

## Verify

```bash
curl https://YOUR_WORKER_HOST/health
```

## Connect agents with ctx_cli

```bash
npm install -g @shiuing/ctx-cli
ctx_cli config set baseUrl https://YOUR_WORKER_HOST
ctx_cli config set userId YOUR_USER_ID
printf '%s' 'YOUR_TOKEN' | ctx_cli config set token --stdin
ctx_cli doctor
```

## Why the button flow works here

This repo is intentionally shaped to work with the Deploy to Cloudflare setup page:

- `wrangler.jsonc` contains a default Worker name and D1 binding
- `package.json` exposes `build`, `deploy`, and `db:migrations:apply`
- `package.json` also provides a description for the optional `CONTEXT_HUB_ADMIN_TOKEN` secret
- the implementation stays within Cloudflare Free-friendly primitives (`Workers + D1`)

## Current Worker feature set

Implemented now:

- `register-workspace`
- `mkdir`
- `ls`
- `stat`
- `tree`
- `read`
- `write`
- `edit`
- `apply_patch`
- `mv`
- `cp`
- `rm`
- `search` (lexical-first)
- `reindex` (small scope, sync)

Still intentionally simple:

- no semantic search in Worker
- no background queue pipeline yet
- no multi-tenant ACL model yet beyond optional bearer token
