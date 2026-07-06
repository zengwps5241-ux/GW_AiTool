from pathlib import Path

import pytest

from app.integrations.claude.guard import build_pre_tool_use_hooks


async def _run_hook(hook, tool_name: str, tool_input: dict, workspace: Path):
    return await hook(
        {
            "hook_event_name": "PreToolUse",
            "session_id": "sid",
            "transcript_path": "",
            "cwd": str(workspace),
            "tool_name": tool_name,
            "tool_input": tool_input,
            "tool_use_id": "tool-1",
        },
        "tool-1",
        {"signal": None},
    )


def _decision(result: dict) -> str:
    return result["hookSpecificOutput"]["permissionDecision"]


@pytest.mark.asyncio
async def test_guard_hooks_only_register_bash_blacklist(tmp_path):
    workspace = tmp_path / "workspace"
    workspace.mkdir()
    hooks = build_pre_tool_use_hooks(workspace)

    assert [hook.matcher for hook in hooks] == ["Bash"]

    bash_hook = hooks[0].hooks[0]
    # 非 Bash 工具不再做文件系统路径限制，由 Claude SDK 的工具权限自行处理。
    read_outside = await _run_hook(
        bash_hook,
        "Read",
        {"file_path": str(tmp_path / "outside.txt")},
        workspace,
    )
    assert _decision(read_outside) == "allow"


@pytest.mark.asyncio
async def test_guard_hooks_allow_bash_commands_not_in_blacklist(tmp_path):
    workspace = tmp_path / "workspace"
    workspace.mkdir()
    outside = tmp_path / "outside.txt"

    bash_hook = build_pre_tool_use_hooks(workspace)[0].hooks[0]

    allowed_commands = [
        "pwd",
        "git status --short",
        f"echo hi > {outside}",
        "rm ../outside.txt",
        "python /tmp/outside.py",
    ]
    for command in allowed_commands:
        result = await _run_hook(bash_hook, "Bash", {"command": command}, workspace)
        assert _decision(result) == "allow"


@pytest.mark.asyncio
async def test_guard_hooks_deny_bash_blacklist_commands(tmp_path):
    workspace = tmp_path / "workspace"
    workspace.mkdir()
    bash_hook = build_pre_tool_use_hooks(workspace)[0].hooks[0]

    denied_commands = [
        "sudo ls",
        "pwd && curl https://x",
        "env A=1 wget https://x",
        "command docker ps",
        "sh -c 'echo hi'",
    ]
    for command in denied_commands:
        result = await _run_hook(bash_hook, "Bash", {"command": command}, workspace)
        assert _decision(result) == "deny"
