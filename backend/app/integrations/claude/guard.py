"""Claude SDK tool use hooks，仅保留 Bash 黑名单限制。"""

from __future__ import annotations

import shlex
from dataclasses import dataclass
from pathlib import Path

from claude_agent_sdk import HookMatcher

from app.core import redis as redis_core
from app.core.config import get_settings
from app.modules.team_spaces.file_locks import FileLockService, agent_lock_token, normalize_lock_path


_BASH_COMMAND_SEPARATORS = {";", "&&", "||", "|"}
_BASH_WRITE_COMMANDS = {
    "rm",
    "mv",
    "cp",
    "mkdir",
    "touch",
    "tee",
    "cat",
    "sed",
    "python",
    "python3",
    "node",
}
_BASH_BLACKLIST_COMMANDS = {
    "sudo",
    "su",
    "passwd",
    "chmod",
    "chown",
    "dd",
    "mkfs",
    "mount",
    "umount",
    "fdisk",
    "parted",
    "curl",
    "wget",
    "ssh",
    "scp",
    "rsync",
    "nc",
    "netcat",
    "kill",
    "killall",
    "pkill",
    "reboot",
    "shutdown",
    "systemctl",
    "service",
    "apt",
    "apt-get",
    "yum",
    "dnf",
    "brew",
    "yarn",
    "docker",
    "kubectl",
    # 禁止再启动一层 shell 绕过本 hook 对命令片段的黑名单检查。
    "sh",
    "bash",
    "zsh",
    "fish",
}
_BASH_COMMAND_WRAPPERS = {"command", "builtin", "exec", "nohup", "time"}


@dataclass(frozen=True)
class FileLockHookContext:
    space_id: int
    user_id: int
    session_id: str


def build_pre_tool_use_hooks(
    user_workspace: Path,
    *,
    can_write: bool = True,
    readonly_reason: str | None = None,
    agent_workdir: Path | None = None,
    file_lock_context: FileLockHookContext | None = None,
) -> list[HookMatcher]:
    if file_lock_context is not None:
        # 团队空间内 Bash 只保留通用黑名单，不再受空间锁定/只读状态限制。
        bash_hook = HookMatcher(
            matcher="Bash",
            hooks=[_bash_safety_hook(user_workspace)],
        )
        if not can_write:
            reason = readonly_reason or "当前工作空间不可写"
            return [
                HookMatcher(
                    matcher="Write|Edit|MultiEdit|NotebookEdit",
                    hooks=[_readonly_tool_hook(reason)],
                ),
                bash_hook,
            ]
        return [
            HookMatcher(
                matcher="Write|Edit|MultiEdit|NotebookEdit",
                hooks=[_team_file_lock_hook(user_workspace, file_lock_context)],
            ),
            bash_hook,
        ]

    hooks = [
        HookMatcher(
            matcher="Bash",
            hooks=[_bash_safety_hook(user_workspace, can_write=can_write, readonly_reason=readonly_reason)],
        ),
    ]
    if not can_write:
        hooks.insert(
            0,
            HookMatcher(
                matcher="Write|Edit|MultiEdit|NotebookEdit",
                hooks=[_readonly_tool_hook(readonly_reason or "当前工作空间不可写")],
            ),
        )
    return hooks


def _split_shell_tokens(command: str) -> list[str] | None:
    try:
        lexer = shlex.shlex(command, posix=True, punctuation_chars=True)
        lexer.whitespace_split = True
        return list(lexer)
    except ValueError:
        return None


def _split_shell_segments(tokens: list[str]) -> list[list[str]]:
    segments: list[list[str]] = []
    current: list[str] = []
    for token in tokens:
        if token in _BASH_COMMAND_SEPARATORS:
            if current:
                segments.append(current)
                current = []
            continue
        current.append(token)
    if current:
        segments.append(current)
    return segments


def _looks_like_assignment(token: str) -> bool:
    name, sep, _value = token.partition("=")
    return bool(sep and name and name.replace("_", "").isalnum() and not name[0].isdigit())


def _command_name(segment: list[str]) -> str | None:
    idx = 0
    while idx < len(segment) and _looks_like_assignment(segment[idx]):
        idx += 1
    while idx < len(segment) and segment[idx] in _BASH_COMMAND_WRAPPERS:
        idx += 1
    if idx >= len(segment):
        return None
    if segment[idx] == "env":
        idx += 1
        while idx < len(segment):
            token = segment[idx]
            if token.startswith("-") or _looks_like_assignment(token):
                idx += 1
                continue
            break
        if idx >= len(segment):
            return None
    return Path(segment[idx]).name


def _bash_command_is_allowed(command: str) -> bool:
    tokens = _split_shell_tokens(command)
    if tokens is None:
        return True
    # 只按命令片段识别黑名单，不再限制管道、重定向、路径或其他 Bash 语法。
    return all(
        _command_name(segment) not in _BASH_BLACKLIST_COMMANDS
        for segment in _split_shell_segments(tokens)
    )


def _bash_command_may_write(command: str) -> bool:
    if ">" in command or ">>" in command:
        return True
    tokens = _split_shell_tokens(command)
    if tokens is None:
        return True
    for segment in _split_shell_segments(tokens):
        name = _command_name(segment)
        if name in _BASH_WRITE_COMMANDS:
            return True
    return False


def _readonly_tool_hook(reason: str):
    async def guard(input_data, _tool_use_id, _context):
        return _deny(reason)

    return guard


def _team_file_lock_hook(user_workspace: Path, context: FileLockHookContext):
    async def guard(input_data, _tool_use_id, _context):
        tool_name = input_data.get("tool_name")
        tool_input = input_data.get("tool_input") or {}
        raw_path = tool_input.get("notebook_path") if tool_name == "NotebookEdit" else tool_input.get("file_path")
        if not raw_path:
            return _deny("缺少文件路径，已阻止团队空间写入")
        try:
            workspace_root = user_workspace.resolve()
            abs_path = Path(raw_path)
            if not abs_path.is_absolute():
                abs_path = user_workspace / abs_path
            resolved = abs_path.resolve()
            rel = resolved.relative_to(workspace_root).as_posix()
            normalized = normalize_lock_path(rel)
        except Exception:
            return _deny("文件路径不在当前团队空间内，已阻止写入")

        settings = get_settings()
        service = FileLockService(
            redis_core.get_redis_client(),
            ttl_seconds=settings.team_space_file_lock_ttl_seconds,
            cleanup_grace_seconds=settings.team_space_file_lock_cleanup_grace_seconds,
        )
        result = await service.try_lock_file(
            space_id=context.space_id,
            path=normalized,
            holder_type="agent_session",
            holder_user_id=context.user_id,
            session_id=context.session_id,
            lock_token=agent_lock_token(context.session_id),
        )
        if result.ok:
            return _allow()
        return _deny(f"文件正在被其他用户或会话编辑，已阻止本次写入。path={normalized}")

    return guard


def _bash_safety_hook(
    user_workspace: Path,
    *,
    can_write: bool = True,
    readonly_reason: str | None = None,
):
    async def guard(input_data, _tool_use_id, _context):
        if input_data.get("tool_name") != "Bash":
            return _allow()
        command = input_data.get("tool_input", {}).get("command", "")
        if not can_write and isinstance(command, str) and _bash_command_may_write(command):
            return _deny(readonly_reason or "当前工作空间不可写")
        if isinstance(command, str) and _bash_command_is_allowed(command):
            return _allow()
        return _deny(f"Bash 禁止执行黑名单命令({user_workspace})。")

    return guard


def _allow() -> dict:
    return {
        "hookSpecificOutput": {
            "hookEventName": "PreToolUse",
            "permissionDecision": "allow",
        }
    }


def _deny(reason: str) -> dict:
    return {
        "hookSpecificOutput": {
            "hookEventName": "PreToolUse",
            "permissionDecision": "deny",
            "permissionDecisionReason": reason,
            "additionalContext": reason,
        }
    }
