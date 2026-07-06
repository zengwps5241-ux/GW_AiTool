from types import SimpleNamespace


async def test_generate_chat_completion_uses_openai_sdk(monkeypatch):
    """通用封装应把系统提示词和用户指令透传给 OpenAI SDK。"""
    from app.integrations import openai as openai_integration

    recorded = {}

    class FakeCompletions:
        async def create(self, **kwargs):
            recorded.update(kwargs)
            message = SimpleNamespace(content=" 智能会话标题 ")
            choice = SimpleNamespace(message=message)
            return SimpleNamespace(choices=[choice])

    class FakeChat:
        def __init__(self):
            self.completions = FakeCompletions()

    class FakeClient:
        def __init__(self, **kwargs):
            recorded["client"] = kwargs
            self.chat = FakeChat()

    monkeypatch.setattr(openai_integration, "AsyncOpenAI", FakeClient)

    result = await openai_integration.generate_chat_completion(
        api_key="test-key",
        base_url="https://api.deepseek.com",
        model="deepseek-v4-flash",
        system_prompt="你是会话标题生成器",
        user_prompt="请分析这段需求",
        thinking={"type": "enabled"},
        reasoning_effort="high",
    )

    assert result == "智能会话标题"
    assert recorded["client"]["api_key"] == "test-key"
    assert recorded["client"]["base_url"] == "https://api.deepseek.com"
    assert recorded["model"] == "deepseek-v4-flash"
    assert recorded["messages"] == [
        {"role": "system", "content": "你是会话标题生成器"},
        {"role": "user", "content": "请分析这段需求"},
    ]
    assert recorded["extra_body"] == {"thinking": {"type": "enabled"}}
    assert recorded["reasoning_effort"] == "high"
    assert recorded["stream"] is False
