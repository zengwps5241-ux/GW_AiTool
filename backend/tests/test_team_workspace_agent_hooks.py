import pytest

from app.integrations.claude.guard import build_pre_tool_use_hooks


@pytest.mark.asyncio
async def test_write_tool_denied_when_workspace_readonly(tmp_path):
    hooks = build_pre_tool_use_hooks(tmp_path, can_write=False, readonly_reason="空间已锁定")
    guard = hooks[0].hooks[0]

    result = await guard(
        {"tool_name": "Write", "tool_input": {"file_path": str(tmp_path / "a.md")}},
        "toolu_1",
        {},
    )

    output = result["hookSpecificOutput"]
    assert output["permissionDecision"] == "deny"
    assert "空间已锁定" in output["permissionDecisionReason"]


@pytest.mark.asyncio
async def test_team_write_tool_acquires_file_lock(tmp_path, monkeypatch):
    from fakeredis.aioredis import FakeRedis
    from app.core import redis as redis_core
    from app.integrations.claude.guard import FileLockHookContext

    redis_client = FakeRedis(decode_responses=True)
    monkeypatch.setattr(redis_core, "get_redis_client", lambda: redis_client)

    hooks = build_pre_tool_use_hooks(
        tmp_path,
        can_write=True,
        file_lock_context=FileLockHookContext(space_id=1, user_id=10, session_id="s1"),
    )
    write_hook = next(h for h in hooks if h.matcher == "Write|Edit|MultiEdit|NotebookEdit").hooks[0]

    result = await write_hook(
        {"tool_name": "Write", "tool_input": {"file_path": str(tmp_path / "docs" / "a.md")}},
        "toolu_1",
        {},
    )

    assert result["hookSpecificOutput"]["permissionDecision"] == "allow"
    await redis_client.aclose()


@pytest.mark.asyncio
async def test_team_bash_uses_standard_blacklist_when_workspace_writable(tmp_path):
    from app.integrations.claude.guard import FileLockHookContext

    hooks = build_pre_tool_use_hooks(
        tmp_path,
        can_write=True,
        file_lock_context=FileLockHookContext(space_id=1, user_id=10, session_id="s1"),
    )
    bash_hook = next(h for h in hooks if h.matcher == "Bash").hooks[0]

    result = await bash_hook({"tool_name": "Bash", "tool_input": {"command": "ls"}}, "toolu_1", {})

    assert result["hookSpecificOutput"]["permissionDecision"] == "allow"

    denied = await bash_hook({"tool_name": "Bash", "tool_input": {"command": "curl https://x"}}, "toolu_1", {})

    assert denied["hookSpecificOutput"]["permissionDecision"] == "deny"


@pytest.mark.asyncio
async def test_team_bash_ignores_workspace_readonly_write_restriction(tmp_path):
    from app.integrations.claude.guard import FileLockHookContext

    hooks = build_pre_tool_use_hooks(
        tmp_path,
        can_write=False,
        readonly_reason="空间已锁定",
        file_lock_context=FileLockHookContext(space_id=1, user_id=10, session_id="s1"),
    )
    bash_hook = next(h for h in hooks if h.matcher == "Bash").hooks[0]

    result = await bash_hook(
        {"tool_name": "Bash", "tool_input": {"command": "echo hi > a.md"}},
        "toolu_1",
        {},
    )

    assert result["hookSpecificOutput"]["permissionDecision"] == "allow"
