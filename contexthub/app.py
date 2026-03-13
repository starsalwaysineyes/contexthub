from __future__ import annotations

from fastapi import FastAPI
from fastapi.responses import JSONResponse

from contexthub.config import load_config
from contexthub.env import load_env_files
from contexthub.providers import EmbeddingClient, RerankClient
from contexthub.schemas import (
    CommitSessionRequest,
    CreatePartitionRequest,
    CreateRecordRequest,
    CreateTenantRequest,
    HealthResponse,
    QueryRequest,
    RegisterAgentRequest,
)
from contexthub.service import HubError, HubService
from contexthub.store import SQLiteStore


def create_app() -> FastAPI:
    load_env_files()
    config = load_config()
    store = SQLiteStore(config.database_path)
    store.init()
    service = HubService(
        store=store,
        embedder=EmbeddingClient(config.embedding),
        reranker=RerankClient(config.rerank),
        config=config,
    )

    app = FastAPI(title="ContextHub API", version="0.2.0")

    @app.get("/health", response_model=HealthResponse)
    def health() -> dict:
        return service.health()

    @app.post("/v1/tenants", status_code=201)
    def create_tenant(payload: CreateTenantRequest) -> dict:
        return service.create_tenant(payload)

    @app.post("/v1/partitions", status_code=201)
    def create_partition(payload: CreatePartitionRequest) -> dict:
        return service.create_partition(payload)

    @app.post("/v1/agents", status_code=201)
    def register_agent(payload: RegisterAgentRequest) -> dict:
        return service.register_agent(payload)

    @app.post("/v1/records", status_code=201)
    def create_record(payload: CreateRecordRequest) -> dict:
        return service.create_record(payload)

    @app.post("/v1/query")
    def query(payload: QueryRequest) -> dict:
        return service.query(payload)

    @app.post("/v1/sessions/commit", status_code=201)
    def commit_session(payload: CommitSessionRequest) -> dict:
        return service.commit_session(payload)

    @app.exception_handler(HubError)
    async def hub_error_handler(_, exc: HubError):
        return JSONResponse(status_code=400, content={"detail": str(exc)})

    return app

