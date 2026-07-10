"""M3.4.2 项目级会话关联测试。

覆盖：
- 创建会话绑定项目（自动加载项目 Agent + 返回 project_id/project_name）
- 非成员绑定项目 → 403；不存在项目 → 404
- 显式 agent_id 不被项目 Agent 覆盖
- _build_draft_context：成员→上下文 / 非成员→None / 未绑定→None
- stream_session_chat 接线：项目会话→draft_context 传入 stream_chat；普通会话→不传
"""

import asyncio

import pytest


# ─── 辅助 ────────────────────────────────────────────────────


async def _make_project(client, customer_name="测试客户", project_name="测试项目"):
    """创建客户+项目，返回完整 ProjectOut（含 id 与自动生成的 agent_id）。"""
    cid = (
        await client.post("/api/customers", json={"name": customer_name})
    ).json()["id"]
    return (
        await client.post(
            "/api/projects", json={"customer_id": cid, "name": project_name}
        )
    ).json()


async def _fetch_user(username: str):
    """按用户名取 User ORM 对象（detached，expire_on_commit=False 属性可读）。"""
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


# ─── 创建会话绑定项目 ────────────────────────────────────────


@pytest.mark.asyncio
async def test_create_session_binds_project_and_loads_project_agent(logged_in_client):
    project = await _make_project(logged_in_client)
    pid = project["id"]
    project_agent_id = project["agent_id"]
    assert project_agent_id is not None  # M1.3.7 创建项目自动生成 Agent

    res = await logged_in_client.post(
        "/api/sessions", json={"project_id": pid, "title": "项目会话"}
    )
    assert res.status_code == 200, res.text
    body = res.json()
    assert body["project_id"] == pid
    assert body["project_name"] == "测试项目"
    # 未显式给 agent_id 时自动加载项目 Agent
    assert body["agent_id"] == project_agent_id


@pytest.mark.asyncio
async def test_create_session_rejects_non_member_project(
    logged_in_client, other_logged_in_client
):
    project = await _make_project(logged_in_client)  # alice 的项目
    pid = project["id"]

    res = await other_logged_in_client.post(  # bob 非成员
        "/api/sessions", json={"project_id": pid}
    )
    assert res.status_code == 403


@pytest.mark.asyncio
async def test_create_session_rejects_nonexistent_project(logged_in_client):
    res = await logged_in_client.post("/api/sessions", json={"project_id": 999999})
    assert res.status_code == 404


@pytest.mark.asyncio
async def test_explicit_agent_not_overridden_by_project_agent(logged_in_client):
    """显式给 agent_id 时，不被项目 Agent 覆盖（service 仅在 agent_id 为 None 时补）。"""
    project = await _make_project(logged_in_client)
    pid = project["id"]
    project_agent_id = project["agent_id"]

    # 取一个与项目 Agent 不同的智能体（migrations 注入的默认智能体）
    agents = (await logged_in_client.get("/api/agents")).json()
    other_agent = next(
        (a for a in agents if a["id"] != project_agent_id), None
    )
    assert other_agent is not None, "应至少存在默认智能体与项目智能体两个"

    res = await logged_in_client.post(
        "/api/sessions",
        json={"project_id": pid, "agent_id": other_agent["id"]},
    )
    assert res.status_code == 200, res.text
    body = res.json()
    assert body["project_id"] == pid  # 仍绑定项目
    assert body["agent_id"] == other_agent["id"]  # 但用显式 agent


@pytest.mark.asyncio
async def test_list_sessions_includes_project_fields(logged_in_client):
    project = await _make_project(logged_in_client, project_name="列出项目")
    pid = project["id"]
    await logged_in_client.post(
        "/api/sessions", json={"project_id": pid, "title": "p-session"}
    )

    sessions = (await logged_in_client.get("/api/sessions")).json()
    matched = [s for s in sessions if s.get("project_id") == pid]
    assert matched and matched[0]["project_name"] == "列出项目"


# ─── _build_draft_context 单元 ───────────────────────────────


@pytest.mark.asyncio
async def test_build_draft_context_for_project_member(logged_in_client):
    from app.modules.sessions.streaming import _build_draft_context

    project = await _make_project(logged_in_client)
    alice = await _fetch_user("alice")

    async def _noop(_evt):
        return None

    from app.db.session import async_session

    async with async_session() as db:
        ctx = await _build_draft_context(
            db,
            project_id=project["id"],
            user=alice,
            source_session_id="sess-1",
            publish=_noop,
        )
    assert ctx is not None
    assert ctx.project_id == project["id"]
    assert ctx.user_id == alice.id
    assert ctx.source_session_id == "sess-1"


@pytest.mark.asyncio
async def test_build_draft_context_none_for_non_member(
    logged_in_client, other_logged_in_client
):
    from app.modules.sessions.streaming import _build_draft_context
    from app.db.session import async_session

    project = await _make_project(logged_in_client)  # alice 的项目
    bob = await _fetch_user("bob")

    async def _noop(_evt):
        return None

    async with async_session() as db:
        ctx = await _build_draft_context(
            db,
            project_id=project["id"],
            user=bob,
            source_session_id="sess-2",
            publish=_noop,
        )
    assert ctx is None  # 非成员不挂载草稿工具


@pytest.mark.asyncio
async def test_build_draft_context_none_without_project():
    from app.db.session import async_session
    from app.modules.sessions.streaming import _build_draft_context

    async def _noop(_evt):
        return None

    async with async_session() as db:
        ctx = await _build_draft_context(
            db,
            project_id=None,
            user=None,
            source_session_id="sess-3",
            publish=_noop,
        )
    assert ctx is None


# ─── _build_draft_brief 单元（M3.4.3 Chat 调整循环上下文注入） ──


@pytest.mark.asyncio
async def test_build_draft_brief_none_when_no_drafts(logged_in_client):
    """无任何待采纳草稿 → 不注入 brief（返回 None）。"""
    from app.db.session import async_session
    from app.modules.sessions.streaming import _build_draft_brief

    project = await _make_project(logged_in_client)
    async with async_session() as db:
        brief = await _build_draft_brief(db, project["id"])
    assert brief is None


@pytest.mark.asyncio
async def test_build_draft_brief_summarizes_pending_drafts(logged_in_client):
    """有业务地图草稿 + draft 态角色卡 → brief 含概要（供 AI 基于原文重新生成）。"""
    from app.db.session import async_session
    from app.modules.sessions.streaming import _build_draft_brief

    project = await _make_project(logged_in_client)
    pid = project["id"]
    # 造一张业务地图 active 草稿 + 一张 draft 态角色卡
    await logged_in_client.put(
        f"/api/projects/{pid}/business-map/drafts",
        json={
            "draft_data": {
                "objects": [
                    {"level": "L1", "name": "价值链X"},
                    {"level": "L2", "name": "业务Y"},
                ]
            }
        },
    )
    await logged_in_client.post(
        f"/api/projects/{pid}/stakeholder-cards",
        json={"name": "王总监", "role_type": "technical_evaluator", "review_status": "draft"},
    )

    async with async_session() as db:
        brief = await _build_draft_brief(db, pid)
    assert brief is not None
    assert "业务地图草稿" in brief
    assert "价值链X" in brief
    assert "第 1 版" in brief  # 首次生成 revision=1
    assert "角色卡草稿" in brief
    assert "王总监" in brief


@pytest.mark.asyncio
async def test_stream_session_chat_passes_draft_brief_for_project_session(
    logged_in_client, monkeypatch
):
    """项目会话且存在待采纳草稿 → stream_chat 收到 draft_brief（注入 system prompt）。"""
    from app.modules.sessions import streaming

    project = await _make_project(logged_in_client)
    pid = project["id"]
    # 先造一张草稿，使 brief 非空
    await logged_in_client.put(
        f"/api/projects/{pid}/business-map/drafts",
        json={"draft_data": {"objects": [{"level": "L1", "name": "价值链Z"}]}},
    )
    sid = (
        await logged_in_client.post("/api/sessions", json={"project_id": pid})
    ).json()["id"]

    cs = await _fetch_session(sid)
    alice = await _fetch_user("alice")

    captured: dict = {}

    async def fake_stream_chat(**kwargs):
        captured.update(kwargs)
        return _fake_summary()

    monkeypatch.setattr(streaming, "stream_chat", fake_stream_chat)

    response = await streaming.stream_session_chat(cs, alice, "把 L1 改成业务全景")
    await _drain(response)

    assert "draft_brief" in captured
    assert "价值链Z" in captured["draft_brief"]


# ─── stream_session_chat 接线（mock stream_chat） ────────────


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
    """消费 StreamingResponse 直到结束，驱动后台 runner 完成。"""
    async for _ in response.body_iterator:
        pass
    await asyncio.sleep(0)  # 让 runner 的 finally 收尾


@pytest.mark.asyncio
async def test_stream_session_chat_passes_draft_context_for_project_session(
    logged_in_client, monkeypatch
):
    from app.modules.sessions import streaming

    project = await _make_project(logged_in_client)
    pid = project["id"]
    sid = (
        await logged_in_client.post("/api/sessions", json={"project_id": pid})
    ).json()["id"]

    cs = await _fetch_session(sid)
    alice = await _fetch_user("alice")

    captured: dict = {}

    async def fake_stream_chat(**kwargs):
        captured.update(kwargs)
        return _fake_summary()

    monkeypatch.setattr(streaming, "stream_chat", fake_stream_chat)

    response = await streaming.stream_session_chat(cs, alice, "帮我生成假设地图")
    await _drain(response)

    assert "draft_context" in captured, "项目会话应挂载草稿工具上下文"
    ctx = captured["draft_context"]
    assert ctx.project_id == pid
    assert ctx.user_id == alice.id
    assert ctx.source_session_id == sid


@pytest.mark.asyncio
async def test_stream_session_chat_no_draft_context_for_plain_session(
    logged_in_client, monkeypatch
):
    from app.modules.sessions import streaming

    # 普通会话：不绑定项目（用默认 agent，避免 agent_id 为 None 被清理）
    agents = (await logged_in_client.get("/api/agents")).json()
    default_agent = agents[0]
    sid = (
        await logged_in_client.post(
            "/api/sessions", json={"agent_id": default_agent["id"]}
        )
    ).json()["id"]

    cs = await _fetch_session(sid)
    alice = await _fetch_user("alice")

    captured: dict = {}

    async def fake_stream_chat(**kwargs):
        captured.update(kwargs)
        return _fake_summary()

    monkeypatch.setattr(streaming, "stream_chat", fake_stream_chat)

    response = await streaming.stream_session_chat(cs, alice, "你好")
    await _drain(response)

    assert "draft_context" not in captured, "非项目会话不应挂载草稿工具"


@pytest.mark.asyncio
async def test_draft_pending_event_recorded_in_run_state(
    logged_in_client, monkeypatch
):
    """草稿「待采纳」事件经 publish_draft_event 写入 run_state，可重连回放。"""
    from app.modules.sessions import streaming
    from app.modules.sessions.run_state import run_state_store

    project = await _make_project(logged_in_client)
    pid = project["id"]
    sid = (
        await logged_in_client.post("/api/sessions", json={"project_id": pid})
    ).json()["id"]
    cs = await _fetch_session(sid)
    alice = await _fetch_user("alice")

    # 让 fake stream_chat 在运行中通过 captured 的 publish 回调推送一条 draft_pending，
    # 验证它确实进入 run_state（供 /running/stream 回放）。
    async def fake_stream_chat(**kwargs):
        ctx = kwargs.get("draft_context")
        if ctx is not None:
            await ctx.publish(
                {
                    "type": "draft_pending",
                    "entity_type": "business_map_draft",
                    "draft_id": 1,
                    "project_id": pid,
                }
            )
        return _fake_summary()

    monkeypatch.setattr(streaming, "stream_chat", fake_stream_chat)

    response = await streaming.stream_session_chat(cs, alice, "生成地图")
    await _drain(response)

    snapshot = run_state_store.snapshot(sid, after_seq=0)
    assert snapshot is not None
    types = [e.payload.get("type") for e in snapshot.events if e.payload]
    assert "draft_pending" in types
