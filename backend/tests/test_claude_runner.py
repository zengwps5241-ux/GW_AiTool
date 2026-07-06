import json

import pytest


async def test_load_history_passes_directory(monkeypatch, tmp_path):
    monkeypatch.setenv("APP_SECRET", "s")
    monkeypatch.setenv("ANTHROPIC_AUTH_TOKEN", "t")
    monkeypatch.setenv("ANTHROPIC_BASE_URL", "https://x")
    monkeypatch.chdir(tmp_path)

    from importlib import reload
    from app.core import config as core_config
    reload(core_config)

    captured = {}

    def fake_get_session_messages(session_id, directory=None, **kw):
        captured["session_id"] = session_id
        captured["directory"] = directory
        return []

    from app.integrations.claude import runner as claude_runner
    monkeypatch.setattr("app.integrations.claude.runner.get_session_messages", fake_get_session_messages)

    out = await claude_runner.load_history("abc", tmp_path / "ws")  # agent=None
    assert out == []
    assert captured["session_id"] == "abc"
    assert captured["directory"] == str(tmp_path / "ws")


async def test_load_history_returns_latest_ten_messages(monkeypatch, tmp_path):
    monkeypatch.setenv("APP_SECRET", "s")
    monkeypatch.setenv("ANTHROPIC_AUTH_TOKEN", "t")
    monkeypatch.setenv("ANTHROPIC_BASE_URL", "https://x")
    monkeypatch.chdir(tmp_path)

    from importlib import reload
    from app.core import config as core_config
    reload(core_config)

    captured = {}

    def fake_get_session_messages(session_id, directory=None, **kw):
        captured["kwargs"] = kw
        return list(range(15))

    def fake_serialize_block(msg, streaming=False):
        return [{"type": "msg", "value": msg, "streaming": streaming}]

    from app.integrations.claude import runner as claude_runner
    monkeypatch.setattr("app.integrations.claude.runner.get_session_messages", fake_get_session_messages)
    monkeypatch.setattr("app.integrations.claude.runner.serialize_block", fake_serialize_block)

    out = await claude_runner.load_history("abc", tmp_path / "ws")

    assert captured["kwargs"] == {}
    assert [item["value"] for item in out] == list(range(5, 15))
    assert all(item["streaming"] is False for item in out)


async def test_remove_session_calls_delete(monkeypatch, tmp_path):
    monkeypatch.setenv("APP_SECRET", "s")
    monkeypatch.setenv("ANTHROPIC_AUTH_TOKEN", "t")
    monkeypatch.setenv("ANTHROPIC_BASE_URL", "https://x")
    monkeypatch.chdir(tmp_path)

    from importlib import reload
    from app.core import config as core_config
    reload(core_config)

    calls = []
    def fake_delete(session_id, directory=None, **kw):
        calls.append((session_id, directory))

    from app.integrations.claude import runner as claude_runner
    monkeypatch.setattr("app.integrations.claude.runner.delete_session", fake_delete)

    await claude_runner.remove_session("abc", tmp_path / "ws")
    assert calls == [("abc", str(tmp_path / "ws"))]


async def test_remove_session_noop_when_id_missing(monkeypatch, tmp_path):
    monkeypatch.setenv("APP_SECRET", "s")
    monkeypatch.setenv("ANTHROPIC_AUTH_TOKEN", "t")
    monkeypatch.setenv("ANTHROPIC_BASE_URL", "https://x")
    monkeypatch.chdir(tmp_path)

    from importlib import reload
    from app.core import config as core_config
    reload(core_config)

    calls = []
    from app.integrations.claude import runner as claude_runner
    monkeypatch.setattr("app.integrations.claude.runner.delete_session", lambda *a, **k: calls.append(a))

    await claude_runner.remove_session(None, tmp_path / "ws")
    assert calls == []


async def test_tool_approval_auto_allows_original_input():
    """工具权限申请应自动放行，并保留 SDK 原始工具输入。"""
    from claude_agent_sdk import ToolPermissionContext
    from app.integrations.claude.tool_approval import auto_approve_tool

    tool_input = {"file_path": "hello.txt"}
    result = await auto_approve_tool(
        "Read",
        tool_input,
        ToolPermissionContext(tool_use_id="tool-1"),
    )

    assert result.behavior == "allow"
    assert result.updated_input is tool_input


async def test_stream_chat_uses_resume_and_returns_new_session_id(monkeypatch, tmp_path):
    monkeypatch.setenv("APP_SECRET", "s")
    monkeypatch.setenv("ANTHROPIC_AUTH_TOKEN", "t")
    monkeypatch.setenv("ANTHROPIC_BASE_URL", "https://x")
    monkeypatch.setenv("ANTHROPIC_MODEL", "claude-sonnet-4-5")
    monkeypatch.chdir(tmp_path)

    from importlib import reload
    from app.core import config as core_config
    reload(core_config)

    from app.integrations.claude import runner as claude_runner

    # 桩 ClaudeSDKClient:记录 options,产出固定 message 序列。
    recorded = {}

    class FakeClient:
        def __init__(self, options=None):
            recorded["options"] = options
        async def __aenter__(self):
            return self
        async def __aexit__(self, *a):
            return False
        async def query(self, prompt):
            recorded["prompt"] = prompt
        async def receive_response(self):
            from claude_agent_sdk import AssistantMessage, ResultMessage, TextBlock
            yield AssistantMessage(
                content=[TextBlock(text="hi")], model="c", parent_tool_use_id=None,
                error=None, usage=None, message_id="m", stop_reason=None,
                session_id="new-sid", uuid="u1",
            )
            yield ResultMessage(
                subtype="success", duration_ms=1, duration_api_ms=1, is_error=False,
                num_turns=1, session_id="new-sid", stop_reason=None,
                total_cost_usd=None, usage=None, result=None, structured_output=None,
                model_usage=None, permission_denials=[], deferred_tool_use=None,
                errors=None, api_error_status=None, uuid="u2",
            )

    monkeypatch.setattr("app.integrations.claude.runner.ClaudeSDKClient", FakeClient)

    events: list[dict] = []
    async def collect(evt):
        events.append(evt)

    ws = tmp_path / "ws"
    ws.mkdir()
    summary = await claude_runner.stream_chat(
        prompt="hello",
        claude_session_id="old-sid",
        user_workspace=ws,
        on_message=collect,
    )
    assert summary.session_id == "new-sid"
    assert recorded["prompt"] == "hello"
    opts = recorded["options"]
    assert opts.resume == "old-sid"
    assert opts.cwd == str(ws)
    assert opts.model == "claude-sonnet-4-5"
    assert opts.permission_mode == "default"
    assert opts.can_use_tool is claude_runner.auto_approve_tool
    assert "你只允许在用户个人空间" in opts.system_prompt["append"]
    claude_settings = json.loads(opts.settings)
    assert claude_settings["autoMemoryEnabled"] is True
    assert claude_settings["autoMemoryDirectory"] == str((ws / ".claude" / "memory").resolve())
    assert "Bash" in opts.allowed_tools
    assert [matcher.matcher for matcher in opts.hooks["PreToolUse"]] == ["Bash"]
    assert all(
        not matcher.matcher or "Skill" not in matcher.matcher
        for matcher in opts.hooks["PreToolUse"]
    )
    bash_hook = next(
        matcher.hooks[0]
        for matcher in opts.hooks["PreToolUse"]
        if matcher.matcher == "Bash"
    )
    pwd_allowed = await bash_hook(
        {
            "hook_event_name": "PreToolUse",
            "session_id": "new-sid",
            "transcript_path": "",
            "cwd": str(ws),
            "tool_name": "Bash",
            "tool_input": {"command": "pwd"},
            "tool_use_id": "tool-1",
        },
        "tool-1",
        {"signal": None},
    )
    assert pwd_allowed["hookSpecificOutput"]["permissionDecision"] == "allow"
    ls_allowed = await bash_hook(
        {
            "hook_event_name": "PreToolUse",
            "session_id": "new-sid",
            "transcript_path": "",
            "cwd": str(ws),
            "tool_name": "Bash",
            "tool_input": {"command": "ls -la"},
            "tool_use_id": "tool-ls",
        },
        "tool-ls",
        {"signal": None},
    )
    assert ls_allowed["hookSpecificOutput"]["permissionDecision"] == "allow"
    script = ws / "hello.py"
    script.write_text("print('hi')\n")
    allowed = await bash_hook(
        {
            "hook_event_name": "PreToolUse",
            "session_id": "new-sid",
            "transcript_path": "",
            "cwd": str(ws),
            "tool_name": "Bash",
            "tool_input": {"command": "python hello.py"},
            "tool_use_id": "tool-2",
        },
        "tool-2",
        {"signal": None},
    )
    assert allowed["hookSpecificOutput"]["permissionDecision"] == "allow"
    outside_script = tmp_path / "outside.py"
    outside_script.write_text("print('outside')\n")
    outside_allowed = await bash_hook(
        {
            "hook_event_name": "PreToolUse",
            "session_id": "new-sid",
            "transcript_path": "",
            "cwd": str(ws),
            "tool_name": "Bash",
            "tool_input": {"command": f"python {outside_script}"},
            "tool_use_id": "tool-3",
        },
        "tool-3",
        {"signal": None},
    )
    assert outside_allowed["hookSpecificOutput"]["permissionDecision"] == "allow"
    python_with_args = await bash_hook(
        {
            "hook_event_name": "PreToolUse",
            "session_id": "new-sid",
            "transcript_path": "",
            "cwd": str(ws),
            "tool_name": "Bash",
            "tool_input": {"command": f"python {outside_script} --keyword 张三"},
            "tool_use_id": "tool-4",
        },
        "tool-4",
        {"signal": None},
    )
    assert python_with_args["hookSpecificOutput"]["permissionDecision"] == "allow"
    piped_json = await bash_hook(
        {
            "hook_event_name": "PreToolUse",
            "session_id": "new-sid",
            "transcript_path": "",
            "cwd": str(ws),
            "tool_name": "Bash",
            "tool_input": {
                "command": f"echo '{{\"keyword\": \"张三\"}}' | python {outside_script}"
            },
            "tool_use_id": "tool-5",
        },
        "tool-5",
        {"signal": None},
    )
    assert piped_json["hookSpecificOutput"]["permissionDecision"] == "allow"
    heredoc_json = await bash_hook(
        {
            "hook_event_name": "PreToolUse",
            "session_id": "new-sid",
            "transcript_path": "",
            "cwd": str(ws),
            "tool_name": "Bash",
            "tool_input": {
                "command": f"python {outside_script} <<'JSON'\n{{\"keyword\": \"张三\"}}\nJSON"
            },
            "tool_use_id": "tool-6",
        },
        "tool-6",
        {"signal": None},
    )
    assert heredoc_json["hookSpecificOutput"]["permissionDecision"] == "allow"
    # 至少包含一个 assistant_text 和一个 result
    types = [e["type"] for e in events]
    assert "assistant_text" in types
    assert "result" in types


async def test_stream_chat_uses_selected_provider_and_thinking_effort(monkeypatch, tmp_path):
    """选中模型后应注入对应供应商环境变量，并启用指定思考级别。"""
    monkeypatch.setenv("APP_SECRET", "s")
    monkeypatch.setenv("ANTHROPIC_PROVIDER_DEEPSEEK_AUTH_TOKEN", "deepseek-token")
    monkeypatch.setenv("ANTHROPIC_PROVIDER_DEEPSEEK_BASE_URL", "https://deepseek.example")
    monkeypatch.setenv("ANTHROPIC_PROVIDER_DEEPSEEK_MODELS", '["deepseek-v4-pro"]')
    monkeypatch.setenv("ANTHROPIC_PROVIDER_MINIMAX_AUTH_TOKEN", "minimax-token")
    monkeypatch.setenv("ANTHROPIC_PROVIDER_MINIMAX_BASE_URL", "https://minimax.example")
    monkeypatch.setenv("ANTHROPIC_PROVIDER_MINIMAX_MODELS", '["MiniMax-M2.7-highspeed"]')
    monkeypatch.chdir(tmp_path)

    from importlib import reload
    from app.core import config as core_config
    reload(core_config)

    from app.integrations.claude import runner as claude_runner
    reload(claude_runner)

    recorded = {}

    class FakeClient:
        def __init__(self, options=None):
            recorded["options"] = options
        async def __aenter__(self):
            return self
        async def __aexit__(self, *a):
            return False
        async def query(self, prompt):
            pass
        async def receive_response(self):
            from claude_agent_sdk import ResultMessage
            yield ResultMessage(
                subtype="success", duration_ms=1, duration_api_ms=1, is_error=False,
                num_turns=1, session_id="sid", stop_reason=None,
                total_cost_usd=None, usage=None, result=None, structured_output=None,
                model_usage=None, permission_denials=[], deferred_tool_use=None,
                errors=None, api_error_status=None, uuid="u",
            )

    monkeypatch.setattr("app.integrations.claude.runner.ClaudeSDKClient", FakeClient)

    ws = tmp_path / "ws"
    ws.mkdir()

    async def noop(evt):
        pass

    await claude_runner.stream_chat(
        prompt="hello",
        claude_session_id=None,
        user_workspace=ws,
        model="MiniMax-M2.7-highspeed",
        thinking_level="medium",
        on_message=noop,
    )

    opts = recorded["options"]
    assert opts.model == "MiniMax-M2.7-highspeed"
    assert opts.env["ANTHROPIC_AUTH_TOKEN"] == "minimax-token"
    assert opts.env["ANTHROPIC_BASE_URL"] == "https://minimax.example"
    assert opts.thinking == {"type": "adaptive"}
    assert opts.effort == "medium"


async def test_stream_chat_defaults_to_first_available_model(monkeypatch, tmp_path):
    """未显式选择模型时，应使用配置模型列表里的第一项。"""
    monkeypatch.setenv("APP_SECRET", "s")
    monkeypatch.setenv("ANTHROPIC_AUTH_TOKEN", "legacy-token")
    monkeypatch.setenv("ANTHROPIC_BASE_URL", "https://legacy.example")
    monkeypatch.setenv("ANTHROPIC_MODEL", '["claude-sonnet-4-5", "claude-haiku-4-5"]')
    monkeypatch.chdir(tmp_path)

    from importlib import reload
    from app.core import config as core_config
    reload(core_config)

    from app.integrations.claude import runner as claude_runner
    reload(claude_runner)

    recorded = {}

    class FakeClient:
        def __init__(self, options=None):
            recorded["options"] = options
        async def __aenter__(self):
            return self
        async def __aexit__(self, *a):
            return False
        async def query(self, prompt):
            pass
        async def receive_response(self):
            from claude_agent_sdk import ResultMessage
            yield ResultMessage(
                subtype="success", duration_ms=1, duration_api_ms=1, is_error=False,
                num_turns=1, session_id="sid", stop_reason=None,
                total_cost_usd=None, usage=None, result=None, structured_output=None,
                model_usage=None, permission_denials=[], deferred_tool_use=None,
                errors=None, api_error_status=None, uuid="u",
            )

    monkeypatch.setattr("app.integrations.claude.runner.ClaudeSDKClient", FakeClient)

    ws = tmp_path / "ws"
    ws.mkdir()

    async def noop(evt):
        pass

    await claude_runner.stream_chat(
        prompt="hello",
        claude_session_id=None,
        user_workspace=ws,
        on_message=noop,
    )

    opts = recorded["options"]
    assert opts.model == "claude-sonnet-4-5"
    assert opts.env["ANTHROPIC_AUTH_TOKEN"] == "legacy-token"


async def test_stream_chat_injects_builtin_zhipu_web_search_mcp(monkeypatch, tmp_path):
    """配置智谱 Key 后，应为 Claude Agent 内置智谱联网搜索 MCP。"""
    monkeypatch.setenv("APP_SECRET", "s")
    monkeypatch.setenv("ANTHROPIC_AUTH_TOKEN", "t")
    monkeypatch.setenv("ANTHROPIC_BASE_URL", "https://x")
    monkeypatch.setenv("ZHIPU_WEB_SEARCH_API_KEY", "zhipu-key")
    monkeypatch.chdir(tmp_path)

    from importlib import reload
    from app.core import config as core_config
    reload(core_config)

    from app.integrations.claude import runner as claude_runner
    reload(claude_runner)

    recorded = {}

    class FakeClient:
        def __init__(self, options=None):
            recorded["options"] = options
        async def __aenter__(self):
            return self
        async def __aexit__(self, *a):
            return False
        async def query(self, prompt):
            pass
        async def receive_response(self):
            from claude_agent_sdk import ResultMessage
            yield ResultMessage(
                subtype="success", duration_ms=1, duration_api_ms=1, is_error=False,
                num_turns=1, session_id="sid", stop_reason=None,
                total_cost_usd=None, usage=None, result=None, structured_output=None,
                model_usage=None, permission_denials=[], deferred_tool_use=None,
                errors=None, api_error_status=None, uuid="u",
            )

    monkeypatch.setattr("app.integrations.claude.runner.ClaudeSDKClient", FakeClient)

    ws = tmp_path / "ws"
    ws.mkdir()

    async def noop(evt):
        pass

    await claude_runner.stream_chat(
        prompt="hello",
        claude_session_id=None,
        user_workspace=ws,
        on_message=noop,
    )

    opts = recorded["options"]
    assert opts.mcp_servers == {
        "zhipu-web-search-sse": {
            "type": "sse",
            "url": "https://open.bigmodel.cn/api/mcp/web_search/sse?Authorization=zhipu-key",
        }
    }
    assert "mcp__zhipu-web-search-sse__web_search" in opts.allowed_tools


async def test_stream_chat_passes_agent_skills_and_plugins(monkeypatch, tmp_path):
    """Agent.skills 和 Agent.plugins 应解析后传给 SDK,plugin 路径走 agent 工作目录。"""
    monkeypatch.setenv("APP_SECRET", "s")
    monkeypatch.setenv("ANTHROPIC_AUTH_TOKEN", "t")
    monkeypatch.setenv("ANTHROPIC_BASE_URL", "https://x")
    monkeypatch.chdir(tmp_path)

    from importlib import reload
    from app.core import config as core_config
    from app.modules.catalog import plugins as plugins_scanner
    from app.modules.agents import workdir as agent_workdir_mod
    reload(core_config)
    reload(plugins_scanner)
    reload(agent_workdir_mod)

    # 模板源: tmp_path/claude_data/plugins/<rel>,init_agent_workdir 会按勾选拷贝过去
    plugins_dir = tmp_path / "claude_data" / "plugins"
    (plugins_dir / "demo" / "1.0.0").mkdir(parents=True, exist_ok=True)
    (plugins_dir / "demo" / "1.0.0" / "manifest.json").write_text("{}", encoding="utf-8")
    (plugins_dir / "custom").mkdir(parents=True, exist_ok=True)
    (plugins_dir / "custom" / "manifest.json").write_text("{}", encoding="utf-8")

    from app.integrations.claude import runner as claude_runner
    reload(claude_runner)

    recorded = {}

    class FakeClient:
        def __init__(self, options=None):
            recorded["options"] = options
        async def __aenter__(self):
            return self
        async def __aexit__(self, *a):
            return False
        async def query(self, prompt):
            pass
        async def receive_response(self):
            from claude_agent_sdk import ResultMessage
            yield ResultMessage(
                subtype="success", duration_ms=1, duration_api_ms=1, is_error=False,
                num_turns=1, session_id="sid", stop_reason=None,
                total_cost_usd=None, usage=None, result=None, structured_output=None,
                model_usage=None, permission_denials=[], deferred_tool_use=None,
                errors=None, api_error_status=None, uuid="u",
            )

    monkeypatch.setattr("app.integrations.claude.runner.ClaudeSDKClient", FakeClient)

    # 模拟一个含 skills 与 plugins 的 Agent
    class FakeAgent:
        id = 1
        code = "agent-1"
        system_prompt = "测试提示词"
        skills = "alpha, beta"  # 允许逗号后留空格
        plugins = "demo/1.0.0,custom"

    # 预先建立 Agent=1 的独立工作目录(拷贝勾选插件)
    agent_workdir_mod.init_agent_workdir(FakeAgent())

    ws = tmp_path / "ws"
    ws.mkdir()

    async def noop(evt):  # 序列化产物丢弃即可
        pass

    await claude_runner.stream_chat(
        prompt="hi",
        claude_session_id=None,
        user_workspace=ws,
        agent=FakeAgent(),
        on_message=noop,
    )
    opts = recorded["options"]
    expected_wd = (tmp_path / "agent_workspaces" / "agent-1").resolve()
    # skills 不再通过 options 传递(Agent 工作空间已独立隔离)
    assert opts.skills is None
    # plugins 应展开成 SDK 期望的 {type, path} 字典,且 path 前缀为 agent_workdir
    assert opts.plugins == [
        {"type": "local", "path": str((expected_wd / "plugins" / "demo" / "1.0.0").resolve())},
        {"type": "local", "path": str((expected_wd / "plugins" / "custom").resolve())},
    ]
    assert "测试提示词" in opts.system_prompt["append"]
    assert "你只允许在用户个人空间" in opts.system_prompt["append"]


async def test_stream_chat_injects_agent_workdir_env(monkeypatch, tmp_path):
    """stream_chat 应通过 ClaudeAgentOptions.env 注入 CLAUDE_CONFIG_DIR=agent_workdir,
    且 plugins 路径前缀为 agent_workdir,而非 claude_data_dir。"""
    monkeypatch.setenv("APP_SECRET", "s")
    monkeypatch.setenv("ANTHROPIC_AUTH_TOKEN", "t")
    monkeypatch.setenv("ANTHROPIC_BASE_URL", "https://x")
    monkeypatch.chdir(tmp_path)

    from importlib import reload
    from app.core import config as core_config
    from app.modules.agents import workdir as agent_workdir
    reload(core_config)
    reload(agent_workdir)

    # 准备主目录模板,使 agent_workdir 中有 plugins/alpha
    (tmp_path / "claude_data" / "plugins" / "alpha").mkdir(parents=True, exist_ok=True)
    (tmp_path / "claude_data" / "plugins" / "alpha" / "manifest.json").write_text("{}", encoding="utf-8")

    from app.integrations.claude import runner as claude_runner
    reload(claude_runner)

    recorded = {}

    class FakeClient:
        def __init__(self, options=None):
            recorded["options"] = options
        async def __aenter__(self):
            return self
        async def __aexit__(self, *a):
            return False
        async def query(self, prompt):
            pass
        async def receive_response(self):
            from claude_agent_sdk import ResultMessage
            yield ResultMessage(
                subtype="success", duration_ms=1, duration_api_ms=1, is_error=False,
                num_turns=1, session_id="sid", stop_reason=None,
                total_cost_usd=None, usage=None, result=None, structured_output=None,
                model_usage=None, permission_denials=[], deferred_tool_use=None,
                errors=None, api_error_status=None, uuid="u",
            )

    monkeypatch.setattr("app.integrations.claude.runner.ClaudeSDKClient", FakeClient)

    class FakeAgent:
        id = 7
        code = "agent-7"
        system_prompt = None
        skills = ""
        plugins = "alpha"

    # 先初始化 Agent 工作目录
    agent_workdir.init_agent_workdir(FakeAgent())

    ws = tmp_path / "ws"
    ws.mkdir()

    async def noop(evt):
        pass

    await claude_runner.stream_chat(
        prompt="hi",
        claude_session_id=None,
        user_workspace=ws,
        agent=FakeAgent(),
        on_message=noop,
    )

    opts = recorded["options"]
    expected_workdir = (tmp_path / "agent_workspaces" / "agent-7").resolve()
    # env 应包含 CLAUDE_CONFIG_DIR = 该 Agent 工作目录
    assert opts.env["CLAUDE_CONFIG_DIR"] == str(expected_workdir)
    # plugins 路径前缀应是 agent_workdir 而非 claude_data_dir
    assert opts.plugins == [
        {"type": "local", "path": str((expected_workdir / "plugins" / "alpha").resolve())}
    ]
    assert [matcher.matcher for matcher in opts.hooks["PreToolUse"]] == ["Bash"]


async def test_load_history_overrides_env_then_restores(monkeypatch, tmp_path):
    """load_history 调用期间 os.environ['CLAUDE_CONFIG_DIR'] 应为 agent_workdir,
    调用结束后恢复原值。"""
    monkeypatch.setenv("APP_SECRET", "s")
    monkeypatch.setenv("ANTHROPIC_AUTH_TOKEN", "t")
    monkeypatch.setenv("ANTHROPIC_BASE_URL", "https://x")
    monkeypatch.chdir(tmp_path)

    from importlib import reload
    from app.core import config as core_config
    from app.modules.agents import workdir as agent_workdir
    reload(core_config)
    reload(agent_workdir)
    from app.integrations.claude import runner as claude_runner
    reload(claude_runner)

    expected = (tmp_path / "agent_workspaces" / "agent-5").resolve()
    expected.mkdir(parents=True, exist_ok=True)
    observed = {}
    import os

    def fake_get_session_messages(session_id, directory=None, **kw):
        observed["env_during_call"] = os.environ.get("CLAUDE_CONFIG_DIR")
        observed["session_id"] = session_id
        observed["directory"] = directory
        return []

    monkeypatch.setattr("app.integrations.claude.runner.get_session_messages", fake_get_session_messages)

    class FakeAgent:
        id = 5
        code = "agent-5"

    original = os.environ.get("CLAUDE_CONFIG_DIR")
    out = await claude_runner.load_history("abc", tmp_path / "ws", agent=FakeAgent())
    assert out == []
    assert observed["env_during_call"] == str(expected)
    assert observed["session_id"] == "abc"
    assert os.environ.get("CLAUDE_CONFIG_DIR") == original


async def test_remove_session_overrides_env(monkeypatch, tmp_path):
    """remove_session 调用期间 os.environ['CLAUDE_CONFIG_DIR'] 应为 agent_workdir。"""
    monkeypatch.setenv("APP_SECRET", "s")
    monkeypatch.setenv("ANTHROPIC_AUTH_TOKEN", "t")
    monkeypatch.setenv("ANTHROPIC_BASE_URL", "https://x")
    monkeypatch.chdir(tmp_path)
    from importlib import reload
    from app.core import config as core_config
    from app.modules.agents import workdir as agent_workdir
    reload(core_config)
    reload(agent_workdir)
    from app.integrations.claude import runner as claude_runner
    reload(claude_runner)

    expected = (tmp_path / "agent_workspaces" / "agent-6").resolve()
    expected.mkdir(parents=True, exist_ok=True)
    observed = {}
    import os

    def fake_delete(session_id, directory=None, **kw):
        observed["env_during_call"] = os.environ.get("CLAUDE_CONFIG_DIR")

    monkeypatch.setattr("app.integrations.claude.runner.delete_session", fake_delete)

    class FakeAgent:
        id = 6
        code = "agent-6"

    await claude_runner.remove_session("xyz", tmp_path / "ws", agent=FakeAgent())
    assert observed["env_during_call"] == str(expected)
