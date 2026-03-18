from __future__ import annotations

from dataclasses import dataclass
from pathlib import PurePosixPath
from urllib.parse import urlparse


class UriError(ValueError):
    pass


@dataclass(frozen=True)
class CtxUri:
    raw: str
    user_id: str
    workspace_kind: str
    agent_id: str | None
    relative_path: PurePosixPath

    @property
    def is_user_root(self) -> bool:
        return self.workspace_kind == "userRoot"

    @property
    def is_workspace_root(self) -> bool:
        return not self.is_user_root and str(self.relative_path) == "."

    @property
    def workspace_label(self) -> str:
        if self.workspace_kind == "userRoot":
            return self.user_id
        if self.workspace_kind == "defaultWorkspace":
            return self.workspace_kind
        return f"{self.workspace_kind}/{self.agent_id}"


def _validate_segment(value: str, label: str) -> str:
    cleaned = value.strip()
    if not cleaned:
        raise UriError(f"{label} is required")
    if "/" in cleaned:
        raise UriError(f"{label} must not contain '/'")
    if cleaned in {".", ".."}:
        raise UriError(f"{label} must not be '.' or '..'")
    return cleaned


def _parse_relative_path(parts: list[str]) -> PurePosixPath:
    if not parts:
        return PurePosixPath(".")
    for part in parts:
        if not part:
            raise UriError("path must not contain empty segments")
        if part in {".", ".."}:
            raise UriError("path must not contain '.' or '..'")
    return PurePosixPath(*parts)


def parse_ctx_uri(raw_uri: str) -> CtxUri:
    parsed = urlparse(raw_uri)
    if parsed.scheme != "ctx":
        raise UriError("uri must start with ctx://")
    if parsed.params or parsed.query or parsed.fragment:
        raise UriError("ctx uri must not include params, query, or fragment")

    user_id = _validate_segment(parsed.netloc, "user id")
    segments = [segment for segment in parsed.path.split("/") if segment != ""]
    if not segments:
        return CtxUri(
            raw=raw_uri,
            user_id=user_id,
            workspace_kind="userRoot",
            agent_id=None,
            relative_path=PurePosixPath("."),
        )

    workspace_kind = segments[0]
    if workspace_kind == "defaultWorkspace":
        agent_id = None
        relative_path = _parse_relative_path(segments[1:])
    elif workspace_kind == "agentWorkspace":
        if len(segments) < 2:
            raise UriError("agentWorkspace requires an agent id")
        agent_id = _validate_segment(segments[1], "agent id")
        relative_path = _parse_relative_path(segments[2:])
    else:
        raise UriError("workspace must be defaultWorkspace or agentWorkspace")

    return CtxUri(
        raw=raw_uri,
        user_id=user_id,
        workspace_kind=workspace_kind,
        agent_id=agent_id,
        relative_path=relative_path,
    )


def build_user_root_uri(*, user_id: str) -> str:
    return f"ctx://{_validate_segment(user_id, 'user id')}"


def build_workspace_uri(*, user_id: str, workspace_kind: str, agent_id: str | None = None) -> str:
    user_id = _validate_segment(user_id, "user id")
    if workspace_kind == "defaultWorkspace":
        return f"ctx://{user_id}/defaultWorkspace"
    if workspace_kind == "agentWorkspace":
        if not agent_id:
            raise UriError("agentWorkspace requires an agent id")
        return f"ctx://{user_id}/agentWorkspace/{_validate_segment(agent_id, 'agent id')}"
    raise UriError("workspace must be defaultWorkspace or agentWorkspace")
