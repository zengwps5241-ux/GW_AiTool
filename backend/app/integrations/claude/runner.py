"""封装 ClaudeSDKClient,把消息流转成前端事件。"""

from __future__ import annotations

import asyncio
import json
from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from pathlib import Path
from typing import Any
from urllib.parse import quote

from claude_agent_sdk import (
    ClaudeAgentOptions,
    ClaudeSDKClient,
    ResultMessage,
    delete_session,
    get_session_messages,
    SandboxSettings
)

from app.core import config as core_config
from app.integrations.claude.guard import FileLockHookContext, build_pre_tool_use_hooks
from app.integrations.claude.serializers import serialize_block
from app.integrations.claude.tool_approval import auto_approve_tool
from app.models import Agent
from app.modules.agents.workdir import get_agent_workdir, override_claude_config_dir
from app.modules.catalog.plugins import resolve_plugin_path  # noqa: F401 — 保留作 fallback,供其它入口复用

_ZHIPU_WEB_SEARCH_MCP_NAME = "zhipu-web-search-sse"


@dataclass(frozen=True)
class ChatRunSummary:
    """Claude 一轮运行结束后的统计元数据。"""

    session_id: str | None
    is_error: bool
    stop_reason: str | None
    usage: dict[str, Any] | None
    model_usage: dict[str, Any] | None
    duration_ms: int | None
    duration_api_ms: int | None
    total_cost_usd: float | None
    interrupted: bool
    error_message: str | None


async def load_history(
    claude_session_id: str,
    user_workspace: Path,
    *,
    agent: Agent | None = None,
) -> list[dict]:
    """读取 SDK jsonl 历史并序列化。

    传入 agent 时,通过 override_claude_config_dir 在临界区临时把
    os.environ['CLAUDE_CONFIG_DIR'] 切到该 Agent 工作目录,以保证
    SDK 工具函数读取对应位置的会话历史。
    """
    def _do() -> list[dict]:
        all_msgs = get_session_messages(claude_session_id, directory=str(user_workspace))
        msgs = all_msgs[-200:]
        events: list[dict] = []
        for m in msgs:
            events.extend(serialize_block(m, streaming=False))
        return events

    if agent is None:
        return _do()
    async with override_claude_config_dir(get_agent_workdir(agent.code)):
        return _do()


async def remove_session(
    claude_session_id: str | None,
    user_workspace: Path,
    *,
    agent: Agent | None = None,
) -> None:
    """删除会话的 jsonl(若已生成);agent 提供时切到该 Agent 工作目录。"""
    if not claude_session_id:
        return

    def _do() -> None:
        try:
            delete_session(claude_session_id, directory=str(user_workspace))
        except FileNotFoundError:
            return

    if agent is None:
        _do()
        return
    async with override_claude_config_dir(get_agent_workdir(agent.code)):
        _do()


def _settings(user_workspace: Path, agent_workdir: Path) -> str:
    memory_dir = (user_workspace / ".claude" / "memory").resolve()
    return json.dumps(
        {
            "autoMemoryEnabled": True,
            "autoMemoryDirectory": str(memory_dir),
            "skipWebFetchPreflight": True,
            "permissions": {
                "allow": [
                    f"Read({user_workspace}/**)",
                    f"Write({user_workspace}/**)",
                    f"Edit({user_workspace}/**)",
                    f"MultiEdit({user_workspace}/**)",
                ],
                "deny": [
                    "Read(./.env)",
                    "Read(./.env.*)",
                    f"Write({agent_workdir}/**)",
                    f"Write(/**)",
                ]
            }
        }
    )


def _builtin_mcp_servers() -> dict[str, dict[str, str]]:
    """返回所有内置 MCP；未配置凭据时不启用，避免启动失败。"""
    api_key = core_config.get_settings().zhipu_web_search_api_key.strip()
    if not api_key:
        return {}
    encoded_key = quote(api_key, safe="")
    return {
        _ZHIPU_WEB_SEARCH_MCP_NAME: {
            "type": "sse",
            "url": (
                "https://open.bigmodel.cn/api/mcp/web_search/sse"
                f"?Authorization={encoded_key}"
            ),
        }
    }


async def stream_chat(
    *,
    prompt: str,
    claude_session_id: str | None,
    user_workspace: Path,
    agent: Agent | None = None,
    model: str | None = None,
    thinking_level: str = "low",
    can_write: bool = True,
    readonly_reason: str | None = None,
    file_lock_context: FileLockHookContext | None = None,
    on_message: Callable[[dict], Awaitable[None]],
    stop_event: asyncio.Event | None = None,
) -> ChatRunSummary:
    """运行一次对话,把每条 SDK 消息序列化后通过 on_message 回传。

    返回 ChatRunSummary，包含本次结束后的统计元数据。
    """
    # 解析 agent.plugins,以 Agent 独立工作目录为根(而非主目录)
    # 同时按调用注入 CLAUDE_CONFIG_DIR=agent_workdir,与并发其它会话隔离
    plugins: list[dict] = []
    env_overrides: dict[str, str] = {}
    agent_workdir: Path | None = None
    if agent is not None:
        agent_workdir = get_agent_workdir(agent.code)
        env_overrides["CLAUDE_CONFIG_DIR"] = str(agent_workdir)
        if agent.plugins:
            for rel in agent.plugins.split(","):
                rel = rel.strip()
                if not rel:
                    continue
                plugins.append(
                    {"type": "local", "path": str((agent_workdir / "plugins" / rel).resolve())}
                )
    settings = core_config.get_settings()
    requested_model = (model or "").strip()
    available_models = core_config.get_available_models()
    selected_model = requested_model or (available_models[0] if available_models else settings.anthropic_model.strip() or None)
    provider = core_config.resolve_model_provider(selected_model)
    if selected_model and provider is None:
        raise ValueError(f"未知模型: {selected_model}")
    if not selected_model and provider is not None:
        selected_model = provider.models[0]
    if provider is not None:
        env_overrides["ANTHROPIC_AUTH_TOKEN"] = provider.auth_token
        env_overrides["ANTHROPIC_BASE_URL"] = provider.base_url

    thinking_config: dict[str, str] = {"type": "disabled"}
    effort: str | None = None
    if thinking_level in {"low", "medium", "high"}:
        # 使用 adaptive thinking + effort，让不同模型网关自行决定 token 预算。
        thinking_config = {"type": "adaptive"}
        effort = thinking_level
    sandbox_settings: SandboxSettings = {
        "enabled": True,
        "autoAllowBashIfSandboxed": True,
        "allowUnsandboxedCommands": False,
        "enableWeakerNestedSandbox": True,
        "network": {
            "allowLocalBinding": True,
            "allowedDomains": [
                "*"
            ]
        },
        "filesystem": {
            # 业务写权限由 PreToolUse hook 按 WorkspaceScope.can_write 裁决。
            "allowWrite": ["/tmp", f"{user_workspace}"],
            "allowRead": [f"{agent_workdir}"],
            "denyRead": ["/app"],
            "denyWrite": ["/"]
        },
        "excludedCommands": [
            "*/dist/browse*",
            "node *",
            "python *",
            "python3 *",
        ]
    }
    rule_prompt = ("附加规则："
                   f"1、你只允许在用户个人空间({user_workspace})里进行读写操作，不要生成违规的命令和脚本。"
                   f"2、不要向用户透漏任何非用户个人空间({user_workspace})以外的信息，特别是Skills信息，即使该信息已被Agent读取。"
                   "3、禁止使用Bash读取文件内容，而是采用Read来读取，以免权限逃逸。"
                   f"4、禁止用户使用任何工具查看非用户个人空间({user_workspace})的文件、目录。"
                   "5、禁止将权限外的文件复刻到用户个人空间里造成信息泄露。"
                   "6、不要调用 AskUserQuestion，直接以文本方式向用户提问。"
                   "禁止以任何方式、任何工具绕过上面的规则。"
                   "如果用户使用skill-creator技能创建技能，请将创建的技能放到用户个人空间.claude/skills目录下，此时不要用Bash创建技能目录而是直接使用Write工具写文件，Write会自动创建目录。"
                   "编辑文件强制使用Write工具，不要用Bash写入。"
                   "不要透露自己是CLaude code的身份。"
                   "团队空间里的文件增加了并发锁，所以编辑文件时遇到文件正在被其他用户或会话编辑则终止编辑动作并向用户说明。"
                   )
    agent_prompt = agent.system_prompt if agent and agent.system_prompt else ""
    builtin_mcp_servers = _builtin_mcp_servers()
    allowed_tools = ["Workflow", "Skill", "Read", "Write", "Edit", "MultiEdit", "Glob", "Grep", "Bash", "WebFetch"]
    if _ZHIPU_WEB_SEARCH_MCP_NAME in builtin_mcp_servers:
        # Claude MCP 工具名格式为 mcp__<server>__<tool>。
        allowed_tools.append(f"mcp__{_ZHIPU_WEB_SEARCH_MCP_NAME}__web_search")
    options = ClaudeAgentOptions(
        system_prompt={
            "type": "preset",
            "preset": "claude_code",
            "append":f"{agent_prompt}\n{rule_prompt}"
        },
        cwd=str(user_workspace),
        resume=claude_session_id,
        model=selected_model,
        permission_mode="default",
        settings=_settings(user_workspace,agent_workdir),
        setting_sources=["project","user"],
        mcp_servers=builtin_mcp_servers,
        plugins=plugins,
        tools={"type": "preset", "preset": "claude_code"},
        allowed_tools=allowed_tools,
        disallowed_tools=["WebSearch","AskUserQuestion",
                          "Bash(env *)","Bash(sudo *)","Bash(chmod *)","Bash(chown *)","Bash(dd *)","Bash(mkfs *)","Bash(curl *)","Bash(wget *)","Bash(ssh *)","Bash(scp *)","Bash(rsync *)"],
        hooks={"PreToolUse": build_pre_tool_use_hooks(
            user_workspace,
            can_write=can_write,
            readonly_reason=readonly_reason,
            agent_workdir=agent_workdir,
            file_lock_context=file_lock_context,
        )},
        can_use_tool=auto_approve_tool,
        thinking=thinking_config,
        effort=effort,
        sandbox=sandbox_settings,
        max_buffer_size=2 * 1024 * 1024,
        env=env_overrides or None,
    )
    new_session_id = claude_session_id
    result_message: ResultMessage | None = None
    async with ClaudeSDKClient(options=options) as client:
        await client.query(prompt)
        async for msg in client.receive_response():
            if stop_event and stop_event.is_set():
                await client.interrupt()
                break
            for evt in serialize_block(msg, streaming=True):
                await on_message(evt)
            if isinstance(msg, ResultMessage):
                result_message = msg
                new_session_id = msg.session_id
    return ChatRunSummary(
        session_id=new_session_id,
        is_error=bool(result_message.is_error) if result_message else False,
        stop_reason=result_message.stop_reason if result_message else None,
        usage=result_message.usage if result_message else None,
        model_usage=result_message.model_usage if result_message else None,
        duration_ms=result_message.duration_ms if result_message else None,
        duration_api_ms=result_message.duration_api_ms if result_message else None,
        total_cost_usd=result_message.total_cost_usd if result_message else None,
        interrupted=bool(stop_event and stop_event.is_set()),
        error_message="; ".join(result_message.errors or []) if result_message and result_message.errors else None,
    )
