"""Claude SDK 工具权限审批处理。"""

from __future__ import annotations

from typing import Any

from claude_agent_sdk import PermissionResultAllow, ToolPermissionContext


async def auto_approve_tool(
    _tool_name: str,
    input_data: dict[str, Any],
    _context: ToolPermissionContext,
) -> PermissionResultAllow:
    """对 SDK 发起的工具权限申请自动放行。

    安全边界仍由 PreToolUse hook 负责；这里仅替代交互式审批，避免服务端
    等待人工确认或因无交互环境拒绝工具调用。
    """
    return PermissionResultAllow(updated_input=input_data)
