# Auth and ACL

## Goal

Add a first-pass access-control layer before plugin work and server migration.

The current model is intentionally simple:

- one optional environment admin token
- per-tenant principals with bearer tokens
- per-partition ACL rules
- per-partition allowed layer sets

## Auth modes

### Auth disabled

If `CONTEXT_HUB_ENABLE_AUTH=false`, the service behaves as open local dev mode.

### Auth enabled

If `CONTEXT_HUB_ENABLE_AUTH=true`, every `/v1/*` endpoint except `/health` requires a bearer token.

Two token types exist:

- admin token from `CONTEXT_HUB_ADMIN_TOKEN`
- principal token created by the service and stored hashed in SQLite

## Data model

### `principals`

Represents a caller identity.

Fields include:

- tenant binding
- name
- kind
- token hash
- metadata
- disabled flag
- last-used timestamp

### `principal_partition_acl`

Represents partition-level access.

Fields include:

- `canRead`
- `canWrite`
- `allowedLayers`

This makes it possible to say:

- principal A can write to `memory`
- principal A can only read `l0/l1` in `project-openclaw`
- principal A cannot access `private`

## Current endpoint set

### `GET /v1/auth/me`

Returns current auth identity and ACL summary.

### `POST /v1/principals`

Admin-only.

Creates a principal and returns the bearer token once.

### `POST /v1/principals/{principalId}/acl`

Admin-only.

Creates or updates ACL for a partition.

## Enforcement rules

### Admin token

Can access all tenants, partitions, and layers.

### Principal token

- must stay inside its own tenant
- may query only readable partitions
- may write only writable partitions
- may only read layers listed in `allowedLayers`

## Query behavior

When auth is enabled and the caller is a principal:

- requested partitions are intersected with readable ACLs
- rows are filtered again by layer allowlist per partition
- attempts to query unreadable partitions return `403`

## Write behavior

`POST /v1/records` and `POST /v1/sessions/commit` require `canWrite=true` on the target partition.

## Recommended bootstrap flow

1. set `CONTEXT_HUB_ENABLE_AUTH=true`
2. set `CONTEXT_HUB_ADMIN_TOKEN`
3. create tenant
4. create partitions
5. create principals
6. assign ACL per partition
7. hand principal tokens to adapter/plugin configs

## Example

### Create principal

```bash
curl http://127.0.0.1:4040/v1/principals \
  -H 'Authorization: Bearer admin-secret' \
  -H 'Content-Type: application/json' \
  -d '{
    "tenantId": "tenant_xxx",
    "name": "openclaw-main",
    "kind": "service"
  }'
```

### Grant ACL

```bash
curl http://127.0.0.1:4040/v1/principals/principal_xxx/acl \
  -H 'Authorization: Bearer admin-secret' \
  -H 'Content-Type: application/json' \
  -d '{
    "partitionKey": "memory",
    "canRead": true,
    "canWrite": true,
    "allowedLayers": ["l0", "l1"]
  }'
```

## What is still missing

- principal rotation and revocation helpers
- per-tenant admin roles stored in DB
- richer action scopes for import/derivation/attachments
- audit log for access decisions

This is enough for first controlled multi-agent access, but not the final security model.
