from __future__ import annotations

import hashlib
import hmac
import secrets
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any

from fastapi import HTTPException, Request, status

from contexthub.config import AuthConfig
from contexthub.store import SQLiteStore, from_json


@dataclass(slots=True)
class AuthContext:
    kind: str
    principal: dict[str, Any] | None = None

    @property
    def tenant_id(self) -> str | None:
        return None if self.principal is None else self.principal.get("tenant_id")

    @property
    def principal_id(self) -> str | None:
        return None if self.principal is None else self.principal.get("id")


def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def hash_token(token: str) -> str:
    return hashlib.sha256(token.encode("utf-8")).hexdigest()


class SecurityManager:
    def __init__(self, store: SQLiteStore, config: AuthConfig) -> None:
        self.store = store
        self.config = config

    def issue_token(self) -> str:
        return f"ctx_{secrets.token_urlsafe(32)}"

    def authenticate_request(self, request: Request) -> AuthContext:
        if not self.config.enabled:
            return AuthContext(kind="admin")

        token = self._extract_bearer_token(request)
        if not token:
            raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Missing bearer token")

        if self.config.admin_token and hmac.compare_digest(token, self.config.admin_token):
            return AuthContext(kind="admin")

        token_hash = hash_token(token)
        with self.store.connection() as conn:
            row = conn.execute(
                "SELECT * FROM principals WHERE token_hash = ? AND disabled = 0",
                (token_hash,),
            ).fetchone()
            if row is None:
                raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid bearer token")

            principal = dict(row)
            conn.execute(
                "UPDATE principals SET last_used_at = ? WHERE id = ?",
                (now_iso(), principal["id"]),
            )
            return AuthContext(kind="principal", principal=principal)

    def require_admin(self, auth: AuthContext) -> None:
        if auth.kind != "admin":
            raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Admin token required")

    def require_tenant_match(self, auth: AuthContext, tenant_id: str) -> None:
        if auth.kind == "admin":
            return
        if auth.tenant_id != tenant_id:
            raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Tenant mismatch")

    def get_principal_acl(self, principal_id: str) -> list[dict[str, Any]]:
        with self.store.connection() as conn:
            rows = conn.execute(
                "SELECT * FROM principal_partition_acl WHERE principal_id = ?",
                (principal_id,),
            ).fetchall()
        return [self._serialize_acl(dict(row)) for row in rows]

    def ensure_partition_read(self, auth: AuthContext, tenant_id: str, partition_key: str) -> None:
        if auth.kind == "admin":
            return
        self.require_tenant_match(auth, tenant_id)
        acl = self._lookup_acl(auth.principal_id, partition_key)
        if acl is None or not acl["canRead"]:
            raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Read access denied")

    def ensure_partition_write(self, auth: AuthContext, tenant_id: str, partition_key: str) -> None:
        if auth.kind == "admin":
            return
        self.require_tenant_match(auth, tenant_id)
        acl = self._lookup_acl(auth.principal_id, partition_key)
        if acl is None or not acl["canWrite"]:
            raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Write access denied")

    def query_scope(
        self,
        auth: AuthContext,
        tenant_id: str,
        requested_partitions: list[str],
    ) -> tuple[list[str], dict[str, set[str]] | None]:
        if auth.kind == "admin":
            return requested_partitions, None

        self.require_tenant_match(auth, tenant_id)
        acls = self.get_principal_acl(auth.principal_id)
        readable = {acl["partitionKey"]: set(acl["allowedLayers"]) for acl in acls if acl["canRead"]}

        if requested_partitions:
            missing = [partition for partition in requested_partitions if partition not in readable]
            if missing:
                raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail=f"Read access denied: {', '.join(missing)}")
            return requested_partitions, {partition: readable[partition] for partition in requested_partitions}

        if not readable:
            raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="No readable partitions configured")

        partitions = sorted(readable)
        return partitions, {partition: readable[partition] for partition in partitions}

    def _lookup_acl(self, principal_id: str | None, partition_key: str) -> dict[str, Any] | None:
        if principal_id is None:
            return None
        with self.store.connection() as conn:
            row = conn.execute(
                "SELECT * FROM principal_partition_acl WHERE principal_id = ? AND partition_key = ?",
                (principal_id, partition_key),
            ).fetchone()
        return None if row is None else self._serialize_acl(dict(row))

    def _serialize_acl(self, acl: dict[str, Any]) -> dict[str, Any]:
        return {
            "id": acl["id"],
            "principalId": acl["principal_id"],
            "tenantId": acl["tenant_id"],
            "partitionKey": acl["partition_key"],
            "canRead": bool(acl["can_read"]),
            "canWrite": bool(acl["can_write"]),
            "allowedLayers": from_json(acl.get("allowed_layers"), ["l0", "l1", "l2"]),
            "createdAt": acl["created_at"],
            "updatedAt": acl["updated_at"],
        }

    def _extract_bearer_token(self, request: Request) -> str | None:
        authorization = request.headers.get("Authorization", "")
        scheme, _, token = authorization.partition(" ")
        if scheme.lower() != "bearer" or not token:
            return None
        return token
