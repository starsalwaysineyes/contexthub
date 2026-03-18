from contexthub.uri import build_user_root_uri, build_workspace_uri, parse_ctx_uri


def test_parse_user_root_uri() -> None:
    parsed = parse_ctx_uri("ctx://alice")
    assert parsed.user_id == "alice"
    assert parsed.workspace_kind == "userRoot"
    assert parsed.is_user_root is True


def test_parse_default_workspace_uri() -> None:
    parsed = parse_ctx_uri("ctx://alice/defaultWorkspace/tasks/today.md")
    assert parsed.user_id == "alice"
    assert parsed.workspace_kind == "defaultWorkspace"
    assert parsed.agent_id is None
    assert parsed.relative_path.as_posix() == "tasks/today.md"


def test_parse_agent_workspace_uri() -> None:
    parsed = parse_ctx_uri("ctx://alice/agentWorkspace/codex/session/log.md")
    assert parsed.user_id == "alice"
    assert parsed.workspace_kind == "agentWorkspace"
    assert parsed.agent_id == "codex"
    assert parsed.relative_path.as_posix() == "session/log.md"


def test_build_workspace_uri() -> None:
    assert build_user_root_uri(user_id="alice") == "ctx://alice"
    assert build_workspace_uri(user_id="alice", workspace_kind="defaultWorkspace") == "ctx://alice/defaultWorkspace"
    assert build_workspace_uri(user_id="alice", workspace_kind="agentWorkspace", agent_id="codex") == "ctx://alice/agentWorkspace/codex"
