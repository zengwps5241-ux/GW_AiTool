"""OpenAI 兼容 Chat Completions 调用封装。"""

from __future__ import annotations

from typing import Any

from openai import AsyncOpenAI


async def generate_chat_completion(
    *,
    api_key: str,
    base_url: str,
    model: str,
    system_prompt: str,
    user_prompt: str,
    thinking: dict[str, Any] | None = None,
    reasoning_effort: str | None = None,
    timeout: float = 20.0,
) -> str:
    """调用 OpenAI 兼容接口，返回第一条文本回复。"""
    client = AsyncOpenAI(api_key=api_key, base_url=base_url, timeout=timeout)
    payload: dict[str, Any] = {
        "model": model,
        "messages": [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_prompt},
        ],
        "stream": False,
    }
    if thinking is not None:
        payload["extra_body"] = {"thinking": thinking}
    if reasoning_effort is not None:
        payload["reasoning_effort"] = reasoning_effort

    response = await client.chat.completions.create(**payload)
    if not response.choices:
        return ""
    content = response.choices[0].message.content
    if isinstance(content, str):
        return content.strip()
    return ""
