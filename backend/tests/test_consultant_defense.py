"""M3.3.3 consultant-defense 两道防线测试。

覆盖：
- 防线1：load_dao_layer_prompt 加载资产；runner 在绑定 defense 时把道层注入
  system_prompt.append（项目 Agent 有 / 普通 Agent 无）
- 防线2：load_never_visible_rules + apply_output_filter（substring / regex /
  多规则叠加 / 无命中原样 / 非法正则跳过 / 资产加载）
- defense_plugin_active 判定
- plugin seed 资产齐备 + scan_plugins 发现
- streaming 集成：项目会话 assistant_text 经指纹过滤后入 run_state/SSE；
  assistant_thinking 不过滤
"""

import asyncio
from pathlib import Path

import pytest

PLUGINS_DIR = Path(__file__).resolve().parent.parent / "app" / "plugins_seed"


# ─── 防线1：道层资产 + 注入 ───────────────────────────────


def test_dao_layer_asset_present():
    assert (PLUGINS_DIR / "consultant-defense" / "rules" / "dao_layer.md").exists()


def test_load_dao_layer_prompt_nonempty():
    from app.integrations.claude.defense import load_dao_layer_prompt

    text = load_dao_layer_prompt()
    assert text.strip()
    assert "道层" in text or "方法论" in text


# ─── 防线2：never_visible 规则 + 过滤 ─────────────────────


def test_never_visible_asset_present_and_loadable():
    from app.integrations.claude.defense import load_never_visible_rules

    assert (PLUGINS_DIR / "consultant-defense" / "rules" / "never_visible.json").exists()
    rules = load_never_visible_rules()
    assert isinstance(rules, list) and len(rules) >= 3
    # 每条至少有 pattern
    assert all(r.get("pattern") for r in rules)


def test_apply_filter_substring():
    from app.integrations.claude.defense import apply_output_filter

    rules = [{"id": "t", "type": "substring", "pattern": "Claude Code"}]
    out = apply_output_filter("我其实是 Claude Code 驱动的", rules)
    assert "Claude Code" not in out
    assert "[已过滤]" in out


def test_apply_filter_regex():
    from app.integrations.claude.defense import apply_output_filter

    rules = [{"id": "k", "type": "regex", "pattern": "sk-[A-Za-z0-9]{32,}"}]
    out = apply_output_filter("密钥是 sk-" + "a" * 40 + " 请保密", rules)
    assert "sk-" + "a" * 40 not in out
    assert "[已过滤]" in out


def test_apply_filter_multiple_rules_stack():
    from app.integrations.claude.defense import apply_output_filter

    rules = [
        {"id": "a", "type": "substring", "pattern": "Claude Code"},
        {"id": "b", "type": "regex", "pattern": "sk-[0-9]+"},
    ]
    out = apply_output_filter("Claude Code 用 sk-123 调用", rules)
    assert "Claude Code" not in out
    assert "sk-123" not in out


def test_apply_filter_no_match_returns_original():
    from app.integrations.claude.defense import apply_output_filter

    rules = [{"id": "x", "type": "substring", "pattern": "ZZZ_NOT_EXIST"}]
    text = "这是一段正常的顾问回复。"
    assert apply_output_filter(text, rules) == text


def test_apply_filter_empty_rules_returns_original():
    from app.integrations.claude.defense import apply_output_filter

    assert apply_output_filter("abc", []) == "abc"
    # 传 None 走默认资产规则，"abc" 不命中任何指纹 → 原样
    assert apply_output_filter("abc", None) == "abc"


def test_apply_filter_invalid_regex_skipped():
    from app.integrations.claude.defense import apply_output_filter

    # 非法正则应被跳过，不抛异常；合法规则仍生效
    rules = [
        {"id": "bad", "type": "regex", "pattern": "["},  # 非法
        {"id": "good", "type": "substring", "pattern": "秘密"},
    ]
    out = apply_output_filter("这是秘密内容", rules)
    assert "秘密" not in out  # 合法规则生效


def test_apply_filter_loads_default_asset():
    """不传 rules 时加载默认资产，能过滤资产中的指纹（如 Claude Code）。"""
    from app.integrations.claude.defense import apply_output_filter

    out = apply_output_filter("底层是 Claude Code 实现的")
    assert "Claude Code" not in out


# ─── defense_plugin_active ───────────────────────────────


def test_defense_plugin_active():
    from app.integrations.claude.defense import defense_plugin_active

    class A:
        pass

    a = A()
    a.plugins = "consultant-router,consultant-search,consultant-defense"
    assert defense_plugin_active(a) is True
    a2 = A()
    a2.plugins = "consultant-router,consultant-search"
    assert defense_plugin_active(a2) is False


# ─── seed / scan ─────────────────────────────────────────


def test_defense_plugin_manifest_present():
    assert (PLUGINS_DIR / "consultant-defense" / ".claude-plugin" / "plugin.json").exists()


def test_scan_plugins_discovers_consultant_defense(monkeypatch):
    from app.modules.catalog import plugins as plugins_module

    monkeypatch.setattr(plugins_module, "_plugins_dir", lambda: PLUGINS_DIR)
    names = {p["name"] for p in plugins_module.scan_plugins()}
    assert {"consultant-router", "consultant-search", "consultant-defense"} <= names


# ─── streaming 集成（防线2：assistant_text 过滤） ─────────


async def _fetch_user(username: str):
    from app.db.session import async_session
    from app.models import User
    from sqlalchemy import select

    async with async_session() as db:
        return (
            await db.execute(select(User).where(User.username == username))
        ).scalar_one()


async def _fetch_session(session_id: str):
    from app.db.session import async_session
    from app.models import ChatSession

    async with async_session() as db:
        return await db.get(ChatSession, session_id)


def _fake_summary():
    from app.integrations.claude.runner import ChatRunSummary

    return ChatRunSummary(
        session_id="fake-claude-sid",
        is_error=False,
        stop_reason="end_turn",
        usage=None,
        model_usage=None,
        duration_ms=1,
        duration_api_ms=1,
        total_cost_usd=0.0,
        interrupted=False,
        error_message=None,
    )


async def _drain(response):
    async for _ in response.body_iterator:
        pass
    await asyncio.sleep(0)


@pytest.mark.asyncio
async def test_stream_session_chat_filters_assistant_text(logged_in_client, monkeypatch):
    """项目会话（绑定 defense）的 assistant_text 经指纹过滤后入 run_state。"""
    from app.modules.sessions import streaming
    from app.modules.sessions.run_state import run_state_store

    cid = (
        await logged_in_client.post("/api/customers", json={"name": "防线测试客户"})
    ).json()["id"]
    pid = (
        await logged_in_client.post(
            "/api/projects", json={"customer_id": cid, "name": "防线测试项目"}
        )
    ).json()["id"]
    sid = (
        await logged_in_client.post("/api/sessions", json={"project_id": pid})
    ).json()["id"]
    cs = await _fetch_session(sid)
    alice = await _fetch_user("alice")

    from app.db.session import async_session
    from app.models import Agent

    async with async_session() as db:
        agent = await db.get(Agent, cs.agent_id)
    assert "consultant-defense" in (agent.plugins or "")

    # fake stream_chat 推送一条含指纹的 assistant_text + 一条 thinking
    async def fake_stream_chat(**kwargs):
        await kwargs["on_message"](
            {"type": "assistant_text", "text": "底层其实是 Claude Code 实现"}
        )
        await kwargs["on_message"](
            {"type": "assistant_thinking", "thinking": "我内部用 mcp__consultant_drafts__"}
        )
        return _fake_summary()

    monkeypatch.setattr(streaming, "stream_chat", fake_stream_chat)

    response = await streaming.stream_session_chat(cs, alice, "你是谁", agent=agent)
    await _drain(response)

    snapshot = run_state_store.snapshot(sid, after_seq=0)
    texts = [
        e.payload.get("text")
        for e in snapshot.events
        if e.payload and e.payload.get("type") == "assistant_text"
    ]
    thinkings = [
        e.payload.get("thinking")
        for e in snapshot.events
        if e.payload and e.payload.get("type") == "assistant_thinking"
    ]
    # 防线2：assistant_text 的指纹被过滤
    assert texts and "Claude Code" not in texts[0]
    assert "[已过滤]" in texts[0]
    # 思维链不过滤（§8.2）
    assert thinkings and "mcp__consultant_drafts__" in thinkings[0]


@pytest.mark.asyncio
async def test_stream_session_chat_no_filter_for_plain_session(
    logged_in_client, monkeypatch
):
    """普通会话（默认 Agent，未绑定 defense）不过滤 assistant_text。"""
    from app.modules.sessions import streaming
    from app.modules.sessions.run_state import run_state_store

    agents = (await logged_in_client.get("/api/agents")).json()
    default_agent_id = agents[0]["id"]
    sid = (
        await logged_in_client.post(
            "/api/sessions", json={"agent_id": default_agent_id}
        )
    ).json()["id"]
    cs = await _fetch_session(sid)
    alice = await _fetch_user("alice")

    async def fake_stream_chat(**kwargs):
        await kwargs["on_message"](
            {"type": "assistant_text", "text": "底层其实是 Claude Code 实现"}
        )
        return _fake_summary()

    monkeypatch.setattr(streaming, "stream_chat", fake_stream_chat)

    response = await streaming.stream_session_chat(cs, alice, "你是谁", agent=None)
    await _drain(response)

    snapshot = run_state_store.snapshot(sid, after_seq=0)
    texts = [
        e.payload.get("text")
        for e in snapshot.events
        if e.payload and e.payload.get("type") == "assistant_text"
    ]
    # 未绑定 defense → 原样不过滤
    assert texts and "Claude Code" in texts[0]
