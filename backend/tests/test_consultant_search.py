"""M3.3.2 consultant-search 搜索工具集测试。

覆盖：
- 3 个工具 JSON Schema 校验（合法/拒绝）
- build_search_tool_server 经 list_tools 暴露三工具 + allowed_names
- _safe_slug / _archive_public_info（写入 + 同名去重）/ _html_to_text
- handle_search_web：未配置兜底 / 已配置归档 / 调用失败 / 入参非法
- handle_search_company_registry：未配置兜底 / 已配置
- handle_fetch_webpage：成功归档 / 非 http 拒绝 / 抓取失败
- streaming 集成：项目会话（绑定 consultant-search）→ search_context 传入 stream_chat
"""

import asyncio
from pathlib import Path

import pytest


# ─── Schema 校验 ───────────────────────────────────────────


def test_search_web_schema_accepts_valid():
    from app.integrations.claude.search_tools import SEARCH_WEB_SCHEMA
    from app.integrations.claude.tools import validate_tool_input

    assert validate_tool_input(SEARCH_WEB_SCHEMA, {"query": "abc"}) is None
    assert validate_tool_input(
        SEARCH_WEB_SCHEMA, {"query": "abc", "max_results": 5}
    ) is None


def test_search_web_schema_rejects_missing_query():
    from app.integrations.claude.search_tools import SEARCH_WEB_SCHEMA
    from app.integrations.claude.tools import validate_tool_input

    assert validate_tool_input(SEARCH_WEB_SCHEMA, {"max_results": 5}) is not None


def test_company_registry_schema_rejects_missing_name():
    from app.integrations.claude.search_tools import COMPANY_REGISTRY_SCHEMA
    from app.integrations.claude.tools import validate_tool_input

    assert validate_tool_input(COMPANY_REGISTRY_SCHEMA, {}) is not None


def test_fetch_webpage_schema_rejects_missing_url():
    from app.integrations.claude.search_tools import FETCH_WEBPAGE_SCHEMA
    from app.integrations.claude.tools import validate_tool_input

    assert validate_tool_input(FETCH_WEBPAGE_SCHEMA, {}) is not None


# ─── build_search_tool_server ─────────────────────────────


@pytest.mark.asyncio
async def test_build_search_tool_server_registers_three_tools(tmp_path):
    from mcp.types import ListToolsRequest

    from app.integrations.claude.search_tools import (
        SEARCH_SERVER_NAME,
        SearchToolContext,
        build_search_tool_server,
    )

    ctx = SearchToolContext(
        workspace_root=tmp_path, project_id=1, user_id=1, source_session_id="s"
    )
    cfg = build_search_tool_server(ctx)
    assert cfg["type"] == "sdk"
    assert cfg["name"] == SEARCH_SERVER_NAME
    srv = cfg["instance"]

    resp = await srv.request_handlers[ListToolsRequest](
        ListToolsRequest(method="tools/list")
    )
    names = {t.name for t in resp.root.tools}
    assert names == {"search_web", "search_company_registry", "fetch_webpage"}


def test_search_tool_allowed_names_are_mcp_prefixed():
    from app.integrations.claude.search_tools import search_tool_allowed_names

    names = search_tool_allowed_names()
    assert names == [
        "mcp__consultant_search__search_web",
        "mcp__consultant_search__search_company_registry",
        "mcp__consultant_search__fetch_webpage",
    ]


# ─── 辅助函数 ─────────────────────────────────────────────


def test_safe_slug_preserves_chinese_and_strips():
    from app.integrations.claude.search_tools import _safe_slug

    assert _safe_slug("假设 地图!") == "假设-地图"
    assert _safe_slug("a/b?c=1") == "a-b-c-1"


def test_safe_slug_empty_fallback():
    from app.integrations.claude.search_tools import _safe_slug

    assert _safe_slug("!!!") == "search"
    assert _safe_slug("") == "search"


def test_archive_writes_and_dedups(tmp_path):
    from app.integrations.claude.search_tools import SearchToolContext, _archive_public_info

    ctx = SearchToolContext(
        workspace_root=tmp_path, project_id=1, user_id=1, source_session_id="s"
    )
    path1, newly1 = _archive_public_info(ctx, "q.md", "内容A")
    assert newly1 is True and path1 is not None
    assert path1.read_text(encoding="utf-8") == "内容A"

    # 同名再次归档：去重，不覆盖
    path2, newly2 = _archive_public_info(ctx, "q.md", "内容B")
    assert newly2 is False
    assert path2.read_text(encoding="utf-8") == "内容A"  # 仍是 A


def test_archive_with_project_name(tmp_path):
    """M5.5.8：有 project_name 时归档到 {项目名}/资料/公开信息/（§6.2）。"""
    from app.integrations.claude.search_tools import SearchToolContext, _archive_public_info

    ctx = SearchToolContext(
        workspace_root=tmp_path,
        project_id=1,
        user_id=1,
        source_session_id="s",
        project_name="信创迁移项目",
    )
    path, newly = _archive_public_info(ctx, "search.md", "搜索结果")
    assert newly is True
    # 路径应为 <workspace>/信创迁移项目/资料/公开信息/search.md
    assert "信创迁移项目" in str(path)
    assert "资料" in str(path)
    assert "公开信息" in str(path)
    assert path.read_text(encoding="utf-8") == "搜索结果"


def test_archive_without_project_name_fallback(tmp_path):
    """M5.5.8：无 project_name 时退回根 公开信息/（向后兼容）。"""
    from app.integrations.claude.search_tools import SearchToolContext, _archive_public_info

    ctx = SearchToolContext(
        workspace_root=tmp_path, project_id=None, user_id=1, source_session_id="s"
    )
    path, newly = _archive_public_info(ctx, "q.md", "内容")
    assert newly is True
    # 路径应为 <workspace>/公开信息/q.md（向后兼容）
    parts = path.relative_to(tmp_path).parts
    assert parts[0] == "公开信息"


def test_archive_no_workspace_returns_none():
    from app.integrations.claude.search_tools import SearchToolContext, _archive_public_info

    ctx = SearchToolContext(
        workspace_root=None, project_id=1, user_id=1, source_session_id="s"
    )
    assert _archive_public_info(ctx, "q.md", "x") == (None, False)


def test_html_to_text_strips_tags():
    from app.integrations.claude.search_tools import _html_to_text

    raw = "<html><body><script>bad()</script><h1>标题</h1><p>段落&amp;内容</p></body></html>"
    text = _html_to_text(raw)
    assert "bad" not in text
    assert "标题" in text and "段落&内容" in text  # &amp; 反转义


# ─── handle_search_web ────────────────────────────────────


def _ctx(tmp_path):
    from app.integrations.claude.search_tools import SearchToolContext

    return SearchToolContext(
        workspace_root=Path(tmp_path), project_id=1, user_id=1, source_session_id="s"
    )


@pytest.mark.asyncio
async def test_search_web_not_configured_graceful(tmp_path, monkeypatch):
    from app.integrations.claude import search_tools

    monkeypatch.setattr(search_tools, "_web_search_configured", lambda: False)
    res = await search_tools.handle_search_web(_ctx(tmp_path), {"query": "测试"})
    assert res["is_error"] is False
    assert "未配置" in res["content"][0]["text"]
    # 未配置不归档
    assert not (Path(tmp_path) / "公开信息").exists()


@pytest.mark.asyncio
async def test_search_web_configured_archives_and_dedups(tmp_path, monkeypatch):
    from app.integrations.claude import search_tools

    monkeypatch.setattr(search_tools, "_web_search_configured", lambda: True)

    async def fake_http(query, max_results):  # noqa: ANN001
        return [{"title": "T", "url": "http://x", "snippet": "S"}]

    monkeypatch.setattr(search_tools, "_http_web_search", fake_http)

    res = await search_tools.handle_search_web(_ctx(tmp_path), {"query": "测试查询"})
    assert res["is_error"] is False
    body = res["content"][0]["text"]
    assert "T" in body and "已归档" in body
    archive = Path(tmp_path) / "公开信息" / "测试查询.md"
    assert archive.exists()

    # 第二次：去重，不再写「已归档」标注
    res2 = await search_tools.handle_search_web(_ctx(tmp_path), {"query": "测试查询"})
    assert "已归档" not in res2["content"][0]["text"]


@pytest.mark.asyncio
async def test_search_web_call_failure_returns_error(tmp_path, monkeypatch):
    from app.integrations.claude import search_tools

    monkeypatch.setattr(search_tools, "_web_search_configured", lambda: True)

    async def boom(query, max_results):  # noqa: ANN001
        raise RuntimeError("net")

    monkeypatch.setattr(search_tools, "_http_web_search", boom)
    res = await search_tools.handle_search_web(_ctx(tmp_path), {"query": "x"})
    assert res["is_error"] is True
    assert "net" in res["content"][0]["text"]


@pytest.mark.asyncio
async def test_search_web_invalid_input_returns_error(tmp_path):
    from app.integrations.claude import search_tools

    res = await search_tools.handle_search_web(_ctx(tmp_path), {"max_results": 5})
    assert res["is_error"] is True


# ─── handle_search_company_registry ───────────────────────


@pytest.mark.asyncio
async def test_registry_not_configured_graceful(tmp_path, monkeypatch):
    from app.integrations.claude import search_tools

    monkeypatch.setattr(search_tools, "_company_registry_configured", lambda: False)
    res = await search_tools.handle_search_company_registry(
        _ctx(tmp_path), {"company_name": "某公司"}
    )
    assert res["is_error"] is False
    assert "尚未对接" in res["content"][0]["text"]


@pytest.mark.asyncio
async def test_registry_configured_returns_info(tmp_path, monkeypatch):
    from app.integrations.claude import search_tools

    monkeypatch.setattr(search_tools, "_company_registry_configured", lambda: True)

    async def fake_http(name):  # noqa: ANN001
        return {"统一社会信用代码": "91110...", "法定代表人": "张三"}

    monkeypatch.setattr(search_tools, "_http_company_registry", fake_http)
    res = await search_tools.handle_search_company_registry(
        _ctx(tmp_path), {"company_name": "某公司"}
    )
    assert res["is_error"] is False
    assert "张三" in res["content"][0]["text"]
    assert (Path(tmp_path) / "公开信息" / "某公司-工商.md").exists()


@pytest.mark.asyncio
async def test_registry_no_result(tmp_path, monkeypatch):
    from app.integrations.claude import search_tools

    monkeypatch.setattr(search_tools, "_company_registry_configured", lambda: True)

    async def none(name):  # noqa: ANN001
        return None

    monkeypatch.setattr(search_tools, "_http_company_registry", none)
    res = await search_tools.handle_search_company_registry(
        _ctx(tmp_path), {"company_name": "某公司"}
    )
    assert "未查询到" in res["content"][0]["text"]


# ─── handle_fetch_webpage ─────────────────────────────────


@pytest.mark.asyncio
async def test_fetch_webpage_success_archives(tmp_path, monkeypatch):
    from app.integrations.claude import search_tools

    async def fake_http(url):  # noqa: ANN001
        return "<p>页面正文</p>"

    monkeypatch.setattr(search_tools, "_http_fetch_webpage", fake_http)
    res = await search_tools.handle_fetch_webpage(
        _ctx(tmp_path), {"url": "https://example.com/x"}
    )
    assert res["is_error"] is False
    assert "页面正文" in res["content"][0]["text"]
    assert (Path(tmp_path) / "公开信息").exists()


@pytest.mark.asyncio
async def test_fetch_webpage_rejects_non_http(tmp_path):
    from app.integrations.claude import search_tools

    res = await search_tools.handle_fetch_webpage(
        _ctx(tmp_path), {"url": "ftp://example.com/x"}
    )
    assert res["is_error"] is True
    assert "http" in res["content"][0]["text"]


@pytest.mark.asyncio
async def test_fetch_webpage_failure_returns_error(tmp_path, monkeypatch):
    from app.integrations.claude import search_tools

    async def boom(url):  # noqa: ANN001
        raise RuntimeError("404")

    monkeypatch.setattr(search_tools, "_http_fetch_webpage", boom)
    res = await search_tools.handle_fetch_webpage(
        _ctx(tmp_path), {"url": "https://example.com/x"}
    )
    assert res["is_error"] is True
    assert "404" in res["content"][0]["text"]


# ─── search_plugin_active ─────────────────────────────────


def test_search_plugin_active():
    from app.integrations.claude.search_tools import search_plugin_active

    class A:
        pass

    a = A()
    a.plugins = "consultant-router,consultant-search,consultant-defense"
    assert search_plugin_active(a) is True
    a2 = A()
    a2.plugins = "consultant-router,consultant-defense"
    assert search_plugin_active(a2) is False


# ─── streaming 集成（项目会话 → search_context） ──────────


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
async def test_stream_session_chat_passes_search_context(logged_in_client, monkeypatch):
    from app.modules.sessions import streaming

    cid = (
        await logged_in_client.post("/api/customers", json={"name": "搜索测试客户"})
    ).json()["id"]
    pid = (
        await logged_in_client.post(
            "/api/projects", json={"customer_id": cid, "name": "搜索测试项目"}
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
    assert "consultant-search" in (agent.plugins or "")

    captured: dict = {}

    async def fake_stream_chat(**kwargs):
        captured.update(kwargs)
        return _fake_summary()

    monkeypatch.setattr(streaming, "stream_chat", fake_stream_chat)

    response = await streaming.stream_session_chat(cs, alice, "查一下这家公司", agent=agent)
    await _drain(response)

    assert "search_context" in captured, "项目会话应挂载搜索工具上下文"
    sctx = captured["search_context"]
    assert sctx.project_id == pid
    assert sctx.user_id == alice.id
    assert sctx.source_session_id == sid


@pytest.mark.asyncio
async def test_stream_session_chat_no_search_context_for_plain_session(
    logged_in_client, monkeypatch
):
    """普通会话（默认 Agent，未绑定 consultant-search）不挂载搜索工具。"""
    from app.modules.sessions import streaming

    agents = (await logged_in_client.get("/api/agents")).json()
    default_agent_id = agents[0]["id"]
    sid = (
        await logged_in_client.post(
            "/api/sessions", json={"agent_id": default_agent_id}
        )
    ).json()["id"]
    cs = await _fetch_session(sid)
    alice = await _fetch_user("alice")

    captured: dict = {}

    async def fake_stream_chat(**kwargs):
        captured.update(kwargs)
        return _fake_summary()

    monkeypatch.setattr(streaming, "stream_chat", fake_stream_chat)

    response = await streaming.stream_session_chat(cs, alice, "你好", agent=None)
    await _drain(response)

    assert "search_context" not in captured
