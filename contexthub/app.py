from __future__ import annotations

from typing import Any

from fastapi import BackgroundTasks, Depends, FastAPI, Request
from fastapi.responses import JSONResponse

from contexthub.config import load_config
from contexthub.env import load_env_files
from contexthub.providers import EmbeddingClient, LiteLLMAbstractionClient, RerankClient
from contexthub.schemas import (
    CommitSessionRequest,
    CreatePartitionRequest,
    CreatePrincipalRequest,
    BrowseTreeRequest,
    CreateRecordRequest,
    CreateTenantRequest,
    GrepRequest,
    HealthResponse,
    ImportResourceRequest,
    ListRecordsRequest,
    QueryRequest,
    RegisterAgentRequest,
    UpdateRecordRequest,
    UpsertPrincipalAclRequest,
)
from contexthub.security import AuthContext, SecurityManager
from contexthub.service import HubError, HubService
from contexthub.store import SQLiteStore


def create_app() -> FastAPI:
    load_env_files()
    config = load_config()
    store = SQLiteStore(config.database_path)
    store.init()
    abstraction_client = LiteLLMAbstractionClient(config.abstraction)
    service = HubService(
        store=store,
        embedder=EmbeddingClient(config.embedding),
        reranker=RerankClient(config.rerank),
        abstractor=abstraction_client,
        config=config,
    )
    security = SecurityManager(store, config.auth)

    app = FastAPI(title="ContextHub API", version="0.12.0")

    def get_auth(request: Request) -> AuthContext:
        return security.authenticate_request(request)

    def attach_scope(
        result: dict[str, Any],
        *,
        auth: AuthContext,
        payload: Any,
        requested_partitions: list[str],
        effective_partitions: list[str],
        partition_layer_rules: dict[str, set[str]] | None,
    ) -> dict[str, Any]:
        scope: dict[str, Any] = {
            "tenantId": payload.tenant_id,
            "authKind": auth.kind,
            "authScoped": auth.kind != "admin",
            "requestedPartitions": requested_partitions,
            "effectivePartitions": effective_partitions,
            "requestedTypes": [str(item).strip() for item in getattr(payload, "types", []) if str(item).strip()],
            "requestedLayers": [str(item).strip() for item in getattr(payload, "layers", []) if str(item).strip()],
            "requestedTags": [str(item).strip() for item in getattr(payload, "tags", []) if str(item).strip()],
            "effectiveLayerRules": None
            if partition_layer_rules is None
            else {partition: sorted(layers) for partition, layers in sorted(partition_layer_rules.items())},
        }
        if hasattr(payload, "source_kind") and getattr(payload, "source_kind", None):
            scope["sourceKind"] = payload.source_kind
        if hasattr(payload, "source_path_prefix") and getattr(payload, "source_path_prefix", None):
            scope["sourcePathPrefix"] = payload.source_path_prefix
        if hasattr(payload, "path_prefix") and getattr(payload, "path_prefix", None):
            scope["pathPrefix"] = payload.path_prefix
        if hasattr(payload, "title_contains") and getattr(payload, "title_contains", None):
            scope["titleContains"] = payload.title_contains
        result["scope"] = scope
        return result

    @app.get("/health", response_model=HealthResponse)
    def health() -> dict:
        return service.health()

    @app.get("/v1/auth/me")
    def auth_me(auth: AuthContext = Depends(get_auth)) -> dict:
        if auth.kind == "admin":
            return {"kind": "admin", "authEnabled": config.auth.enabled}

        return {
            "kind": auth.kind,
            "authEnabled": config.auth.enabled,
            "principal": {
                "id": auth.principal["id"],
                "tenantId": auth.principal["tenant_id"],
                "name": auth.principal["name"],
                "kind": auth.principal["kind"],
            },
            "acl": security.get_principal_acl(auth.principal["id"]),
        }

    @app.post("/v1/tenants", status_code=201)
    def create_tenant(payload: CreateTenantRequest, auth: AuthContext = Depends(get_auth)) -> dict:
        security.require_admin(auth)
        return service.create_tenant(payload)

    @app.post("/v1/partitions", status_code=201)
    def create_partition(payload: CreatePartitionRequest, auth: AuthContext = Depends(get_auth)) -> dict:
        security.require_admin(auth)
        return service.create_partition(payload)

    @app.post("/v1/agents", status_code=201)
    def register_agent(payload: RegisterAgentRequest, auth: AuthContext = Depends(get_auth)) -> dict:
        security.require_admin(auth)
        return service.register_agent(payload)

    @app.post("/v1/principals", status_code=201)
    def create_principal(payload: CreatePrincipalRequest, auth: AuthContext = Depends(get_auth)) -> dict:
        security.require_admin(auth)
        return service.create_principal(payload)

    @app.post("/v1/principals/{principal_id}/acl", status_code=201)
    def upsert_principal_acl(
        principal_id: str,
        payload: UpsertPrincipalAclRequest,
        auth: AuthContext = Depends(get_auth),
    ) -> dict:
        security.require_admin(auth)
        return service.upsert_principal_acl(principal_id, payload)

    @app.post("/v1/records", status_code=201)
    def create_record(payload: CreateRecordRequest, auth: AuthContext = Depends(get_auth)) -> dict:
        security.ensure_partition_write(auth, payload.tenant_id, payload.partition_key)
        return service.create_record(payload)

    @app.get("/v1/records/{record_id}")
    def get_record(record_id: str, auth: AuthContext = Depends(get_auth)) -> dict:
        record = service.get_record(record_id)
        security.ensure_partition_read(auth, record["tenantId"], record["partitionKey"])
        return record

    @app.patch("/v1/records/{record_id}")
    def update_record(record_id: str, payload: UpdateRecordRequest, auth: AuthContext = Depends(get_auth)) -> dict:
        record = service.get_record(record_id)
        security.ensure_partition_write(auth, record["tenantId"], record["partitionKey"])
        return service.update_record(record_id, payload)

    @app.get("/v1/records/{record_id}/lines")
    def read_record_lines(
        record_id: str,
        from_line: int = 1,
        limit: int = 80,
        auth: AuthContext = Depends(get_auth),
    ) -> dict:
        record = service.get_record(record_id)
        security.ensure_partition_read(auth, record["tenantId"], record["partitionKey"])
        return service.read_record_lines(record_id, line_start=from_line, line_limit=limit)

    @app.post("/v1/records/list")
    def list_records(payload: ListRecordsRequest, auth: AuthContext = Depends(get_auth)) -> dict:
        security.require_tenant_match(auth, payload.tenant_id)
        requested_partitions = [partition.strip().lower() for partition in payload.partitions if partition.strip()]
        scoped_partitions, partition_layer_rules = security.query_scope(
            auth,
            payload.tenant_id,
            requested_partitions,
        )
        scoped_payload = payload.model_copy(update={"partitions": scoped_partitions})
        result = service.list_records(scoped_payload, partition_layer_rules=partition_layer_rules)
        return attach_scope(
            result,
            auth=auth,
            payload=payload,
            requested_partitions=requested_partitions,
            effective_partitions=scoped_partitions,
            partition_layer_rules=partition_layer_rules,
        )

    @app.post("/v1/records/tree")
    def browse_record_tree(payload: BrowseTreeRequest, auth: AuthContext = Depends(get_auth)) -> dict:
        security.require_tenant_match(auth, payload.tenant_id)
        requested_partitions = [partition.strip().lower() for partition in payload.partitions if partition.strip()]
        scoped_partitions, partition_layer_rules = security.query_scope(
            auth,
            payload.tenant_id,
            requested_partitions,
        )
        scoped_payload = payload.model_copy(update={"partitions": scoped_partitions})
        result = service.browse_record_tree(scoped_payload, partition_layer_rules=partition_layer_rules)
        return attach_scope(
            result,
            auth=auth,
            payload=payload,
            requested_partitions=requested_partitions,
            effective_partitions=scoped_partitions,
            partition_layer_rules=partition_layer_rules,
        )

    @app.post("/v1/records/grep")
    def grep_records(payload: GrepRequest, auth: AuthContext = Depends(get_auth)) -> dict:
        security.require_tenant_match(auth, payload.tenant_id)
        requested_partitions = [partition.strip().lower() for partition in payload.partitions if partition.strip()]
        scoped_partitions, partition_layer_rules = security.query_scope(
            auth,
            payload.tenant_id,
            requested_partitions,
        )
        scoped_payload = payload.model_copy(update={"partitions": scoped_partitions})
        result = service.grep_records(scoped_payload, partition_layer_rules=partition_layer_rules)
        return attach_scope(
            result,
            auth=auth,
            payload=payload,
            requested_partitions=requested_partitions,
            effective_partitions=scoped_partitions,
            partition_layer_rules=partition_layer_rules,
        )

    @app.post("/v1/resources/import", status_code=201)
    def import_resource(
        payload: ImportResourceRequest,
        background_tasks: BackgroundTasks,
        auth: AuthContext = Depends(get_auth),
    ) -> dict:
        security.ensure_partition_write(auth, payload.tenant_id, payload.partition_key)
        return service.import_resource(
            payload,
            schedule_async=lambda job_id: background_tasks.add_task(
                service.run_derivation_job,
                job_id,
                max_attempts=2,
            ),
        )

    @app.get("/v1/derivation-jobs/{job_id}")
    def get_derivation_job(job_id: str, auth: AuthContext = Depends(get_auth)) -> dict:
        job = service.get_derivation_job(job_id)
        security.ensure_partition_read(auth, job["tenantId"], job["partitionKey"])
        return job

    @app.get("/v1/records/{record_id}/links")
    def list_record_links(record_id: str, auth: AuthContext = Depends(get_auth)) -> dict:
        record = service.get_record(record_id)
        security.ensure_partition_read(auth, record["tenantId"], record["partitionKey"])
        return {"items": service.list_record_links(record_id)}

    @app.post("/v1/query")
    def query(payload: QueryRequest, auth: AuthContext = Depends(get_auth)) -> dict:
        security.require_tenant_match(auth, payload.tenant_id)
        requested_partitions = [partition.strip().lower() for partition in payload.partitions if partition.strip()]
        scoped_partitions, partition_layer_rules = security.query_scope(
            auth,
            payload.tenant_id,
            requested_partitions,
        )
        scoped_payload = payload.model_copy(update={"partitions": scoped_partitions})
        result = service.query(scoped_payload, partition_layer_rules=partition_layer_rules)
        return attach_scope(
            result,
            auth=auth,
            payload=payload,
            requested_partitions=requested_partitions,
            effective_partitions=scoped_partitions,
            partition_layer_rules=partition_layer_rules,
        )

    @app.post("/v1/sessions/commit", status_code=201)
    def commit_session(payload: CommitSessionRequest, auth: AuthContext = Depends(get_auth)) -> dict:
        security.ensure_partition_write(auth, payload.tenant_id, payload.partition_key)
        return service.commit_session(payload)

    @app.exception_handler(HubError)
    async def hub_error_handler(_, exc: HubError):
        return JSONResponse(status_code=400, content={"detail": str(exc)})

    return app
