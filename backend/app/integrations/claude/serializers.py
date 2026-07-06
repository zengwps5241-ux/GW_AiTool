"""把 SDK 消息对象序列化为前端友好的 {type, ...} dict 序列。

调用方:
- claude_runner.stream_chat 在收到每条 SDK message 时调本函数,把 yield 出的 dict
  逐条写入 SSE。
- routes/sessions.py 的 GET messages 在历史回放时调用,streaming=False。
"""

from __future__ import annotations

from collections.abc import Iterator
from typing import Any

from claude_agent_sdk import (
    AssistantMessage,
    ResultMessage,
    SessionMessage,
    SystemMessage,
    TextBlock,
    ThinkingBlock,
    ToolResultBlock,
    ToolUseBlock,
    UserMessage,
)


def _tool_result_text(content: Any) -> Any:
    """ToolResultBlock.content 可能是 str 或 ContentBlock 列表。"""
    if isinstance(content, list):
        parts: list[str] = []
        for b in content:
            text = getattr(b, "text", None)
            if isinstance(text, str):
                parts.append(text)
        return "\n".join(parts) if parts else content
    return content


def serialize_block(msg: object, *, streaming: bool = True) -> Iterator[dict]:
    """把一条 SDK message 摊平为零到多条前端事件。

    streaming=True:用于 SSE 实时流(用户自己输入不再回推)。
    streaming=False:用于历史回放(用户消息也要保留)。
    """
    if isinstance(msg, AssistantMessage):
        for block in msg.content:
            if isinstance(block, TextBlock):
                yield {"type": "assistant_text", "text": block.text}
            elif isinstance(block, ThinkingBlock):
                yield {"type": "assistant_thinking", "thinking": block.thinking}
            elif isinstance(block, ToolUseBlock):
                yield {
                    "type": "tool_use",
                    "id": block.id,
                    "name": block.name,
                    "input": block.input,
                }
        return

    if isinstance(msg, UserMessage):
        for block in msg.content:
            if isinstance(block, ToolResultBlock):
                if block.is_error:
                    yield {
                        "type": "tool_result",
                        "tool_use_id": block.tool_use_id,
                        "content": _tool_result_text(block.content),
                        "is_error": True,
                    }
                else:
                    yield {
                        "type": "tool_result",
                        "tool_use_id": block.tool_use_id,
                        "is_error": False,
                    }
            elif isinstance(block, TextBlock) and not streaming:
                yield {"type": "user_text", "text": block.text}
        return

    if isinstance(msg, ResultMessage):
        yield {
            "type": "result",
            "session_id": msg.session_id,
            "is_error": msg.is_error,
            "stop_reason": msg.stop_reason,
        }
        return

    if isinstance(msg, SessionMessage):
        m = msg.message
        content = m.get("content")
        if msg.type == "user":
            if isinstance(content, str):
                yield {"type": "user_text", "text": content}
            elif isinstance(content, list):
                for block in content:
                    bt = block.get("type")
                    if bt == "tool_result":
                        if bool(block.get("is_error", False)):
                            yield {
                                "type": "tool_result",
                                "tool_use_id": block.get("tool_use_id", ""),
                                "content": block.get("content", ""),
                                "is_error": True,
                            }
                        else:
                            yield {
                                "type": "tool_result",
                                "tool_use_id": block.get("tool_use_id", ""),
                                "is_error": False,
                            }
                    elif bt == "text" and not streaming:
                        yield {"type": "user_text", "text": block.get("text", "")}
            return

        if msg.type == "assistant":
            if isinstance(content, list):
                for block in content:
                    bt = block.get("type")
                    if bt == "text":
                        yield {"type": "assistant_text", "text": block.get("text", "")}
                    elif bt == "thinking":
                        yield {"type": "assistant_thinking", "thinking": block.get("thinking", "")}
                    elif bt == "tool_use":
                        yield {
                            "type": "tool_use",
                            "id": block.get("id", ""),
                            "name": block.get("name", ""),
                            "input": block.get("input", {}),
                        }
            return

        if msg.type == "result":
            yield {
                "type": "result",
                "session_id": m.get("session_id", ""),
                "is_error": bool(m.get("is_error", False)),
                "stop_reason": m.get("stop_reason"),
            }
            return

        return

    if isinstance(msg, SystemMessage):
        # MVP 阶段忽略 system init / 警告消息
        return
