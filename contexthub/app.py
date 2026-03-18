from __future__ import annotations

from fastapi import Depends, FastAPI, Header, HTTPException, status
from fastapi.responses import HTMLResponse, JSONResponse, RedirectResponse

from contexthub.config import load_settings
from contexthub.panel import PANEL_HTML
from contexthub.schemas import (
    ApplyPatchRequest,
    CopyRequest,
    EditFileRequest,
    GlobRequest,
    GlobResponse,
    GrepRequest,
    GrepResponse,
    LsResponse,
    MkdirRequest,
    MoveRequest,
    ReadFileResponse,
    RegisterWorkspaceRequest,
    ReindexRequest,
    ReindexResponse,
    RemoveRequest,
    RgRequest,
    SearchRequest,
    SearchResponse,
    StatResponse,
    TreeNode,
    WriteFileRequest,
)
from contexthub.service import FilesystemError, FilesystemService


def create_app() -> FastAPI:
    settings = load_settings()
    service = FilesystemService(settings)
    app = FastAPI(title="ContextHub Phase-1 Filesystem API", version="0.1.0")

    def require_admin(authorization: str | None = Header(default=None)) -> None:
        if not settings.admin_token:
            return
        expected = f"Bearer {settings.admin_token}"
        if authorization != expected:
            raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Missing or invalid bearer token")

    @app.exception_handler(FilesystemError)
    async def filesystem_error_handler(_, exc: FilesystemError):
        return JSONResponse(status_code=400, content={"detail": str(exc)})

    @app.get("/", include_in_schema=False)
    def root() -> RedirectResponse:
        return RedirectResponse(url="/panel", status_code=307)

    @app.get("/panel", include_in_schema=False)
    def panel() -> HTMLResponse:
        return HTMLResponse(PANEL_HTML)

    @app.get("/health")
    def health() -> dict:
        return {
            "ok": True,
            "dataDir": str(settings.data_dir),
            "mode": "phase1-cloud-filesystem",
        }

    @app.post("/v1/workspaces/register")
    def register_workspace(payload: RegisterWorkspaceRequest, _: None = Depends(require_admin)) -> dict:
        return service.register_workspace(
            user_id=payload.user_id,
            workspace_kind=payload.workspace_kind,
            agent_id=payload.agent_id,
        )

    @app.post("/v1/fs/mkdir")
    def mkdir(payload: MkdirRequest, _: None = Depends(require_admin)) -> dict:
        return service.mkdir(payload.uri, parents=payload.parents)

    @app.get("/v1/fs/ls", response_model=LsResponse)
    def ls(uri: str, _: None = Depends(require_admin)) -> dict:
        return service.ls(uri)

    @app.get("/v1/fs/tree", response_model=TreeNode)
    def tree(uri: str, depth: int = 3, _: None = Depends(require_admin)) -> dict:
        return service.tree(uri, depth=depth)

    @app.get("/v1/fs/stat", response_model=StatResponse)
    def stat(uri: str, _: None = Depends(require_admin)) -> dict:
        return service.stat(uri)

    @app.get("/v1/fs/read", response_model=ReadFileResponse)
    def read(uri: str, _: None = Depends(require_admin)) -> dict:
        return service.read(uri)

    @app.post("/v1/fs/write")
    def write(payload: WriteFileRequest, _: None = Depends(require_admin)) -> dict:
        return service.write(
            payload.uri,
            text=payload.text,
            create_parents=payload.create_parents,
            overwrite=payload.overwrite,
        )

    @app.post("/v1/fs/edit")
    def edit(payload: EditFileRequest, _: None = Depends(require_admin)) -> dict:
        return service.edit(
            payload.uri,
            match_text=payload.match_text,
            replace_text=payload.replace_text,
            replace_all=payload.replace_all,
        )

    @app.post("/v1/fs/apply_patch")
    def apply_patch(payload: ApplyPatchRequest, _: None = Depends(require_admin)) -> dict:
        return service.apply_patch(payload.uri, patch=payload.patch)

    @app.post("/v1/fs/mv")
    def move(payload: MoveRequest, _: None = Depends(require_admin)) -> dict:
        return service.move(
            payload.source_uri,
            payload.destination_uri,
            create_parents=payload.create_parents,
            overwrite=payload.overwrite,
        )

    @app.post("/v1/fs/cp")
    def copy(payload: CopyRequest, _: None = Depends(require_admin)) -> dict:
        return service.copy(
            payload.source_uri,
            payload.destination_uri,
            create_parents=payload.create_parents,
            overwrite=payload.overwrite,
        )

    @app.post("/v1/fs/rm")
    def remove(payload: RemoveRequest, _: None = Depends(require_admin)) -> dict:
        return service.remove(payload.uri, recursive=payload.recursive)

    @app.post("/v1/fs/search", response_model=SearchResponse)
    def search(payload: SearchRequest, _: None = Depends(require_admin)) -> dict:
        return service.search(
            user_id=payload.user_id,
            query=payload.query,
            scope_uri=payload.scope_uri,
            limit=payload.limit,
            mode=payload.mode,
            expansions=payload.expansions,
            glob_pattern=payload.glob,
            path_prefix=payload.path_prefix,
            workspace_mode=payload.workspace_mode,
            doc_type_boosts=payload.doc_type_boosts,
            rerank=payload.rerank,
            explain=payload.explain,
        )

    @app.post("/v1/fs/reindex", response_model=ReindexResponse)
    def reindex(payload: ReindexRequest, _: None = Depends(require_admin)) -> dict:
        return service.reindex(user_id=payload.user_id, scope_uri=payload.scope_uri)

    @app.post("/v1/fs/glob", response_model=GlobResponse)
    def glob(payload: GlobRequest, _: None = Depends(require_admin)) -> dict:
        return service.glob(
            user_id=payload.user_id,
            pattern=payload.pattern,
            scope_uri=payload.scope_uri,
            limit=payload.limit,
        )

    @app.post("/v1/fs/grep", response_model=GrepResponse)
    def grep(payload: GrepRequest, _: None = Depends(require_admin)) -> dict:
        return service.grep(
            user_id=payload.user_id,
            pattern=payload.pattern,
            scope_uri=payload.scope_uri,
            limit=payload.limit,
            case_sensitive=payload.case_sensitive,
            glob_pattern=payload.glob,
        )

    @app.post("/v1/fs/rg", response_model=GrepResponse)
    def rg(payload: RgRequest, _: None = Depends(require_admin)) -> dict:
        return service.rg(
            user_id=payload.user_id,
            pattern=payload.pattern,
            scope_uri=payload.scope_uri,
            limit=payload.limit,
            case_sensitive=payload.case_sensitive,
            glob_pattern=payload.glob,
        )

    return app
