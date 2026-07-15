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


# ─── M7.1：会话列表按 project_id 过滤 ─────────────────────────
# 决策 #72（严格过滤）/ #77（自由对话会话仅全量可见）/ #74（与工作区维度 AND 叠加）
# / #75（不额外查项目权限，复用现有可见性闭环）


@pytest.mark.asyncio
async def test_list_sessions_filters_by_project_excluding_free_sessions(logged_in_client):
    """选项目1 → 只显示项目1会话，排除 project_id=null 的自由对话会话（决策 #72/#77）。"""
    proj1 = await _make_project(logged_in_client, project_name="项目1")
    proj2 = await _make_project(
        logged_in_client, customer_name="客户2", project_name="项目2"
    )

    # 项目1 的会话
    p1_sid = (
        await logged_in_client.post("/api/sessions", json={"project_id": proj1["id"]})
    ).json()["id"]
    # 项目2 的会话
    p2_sid = (
        await logged_in_client.post("/api/sessions", json={"project_id": proj2["id"]})
    ).json()["id"]
    # 自由对话会话（project_id=null，绑定默认 agent 避免 agent_id=None 被清理）
    agents = (await logged_in_client.get("/api/agents")).json()
    default_agent = agents[0]
    free_sid = (
        await logged_in_client.post(
            "/api/sessions", json={"agent_id": default_agent["id"]}
        )
    ).json()["id"]

    # 选项目1：只有 p1_sid
    p1_list = (
        await logged_in_client.get(f"/api/sessions?project_id={proj1['id']}")
    ).json()
    p1_ids = [s["id"] for s in p1_list]
    assert p1_sid in p1_ids
    assert p2_sid not in p1_ids
    assert free_sid not in p1_ids  # 自由对话会话被排除

    # 选项目2：只有 p2_sid
    p2_list = (
        await logged_in_client.get(f"/api/sessions?project_id={proj2['id']}")
    ).json()
    p2_ids = [s["id"] for s in p2_list]
    assert p2_sid in p2_ids
    assert p1_sid not in p2_ids
    assert free_sid not in p2_ids

    # 不选项目：全部可见（含自由对话会话）
    all_list = (await logged_in_client.get("/api/sessions")).json()
    all_ids = [s["id"] for s in all_list]
    assert p1_sid in all_ids
    assert p2_sid in all_ids
    assert free_sid in all_ids


@pytest.mark.asyncio
async def test_list_sessions_project_filter_stacks_with_workspace_kind(logged_in_client):
    """project_id 与 workspace_kind=mine_only AND 叠加（决策 #74）。"""
    proj = await _make_project(logged_in_client, project_name="叠加项目")
    pid = proj["id"]
    # 项目会话 + 一个默认 agent 的自由对话会话
    p_sid = (
        await logged_in_client.post("/api/sessions", json={"project_id": pid})
    ).json()["id"]
    agents = (await logged_in_client.get("/api/agents")).json()
    free_sid = (
        await logged_in_client.post(
            "/api/sessions", json={"agent_id": agents[0]["id"]}
        )
    ).json()["id"]

    # mine_only + project_id 叠加：只该项目且只自己的
    listed = (
        await logged_in_client.get(
            f"/api/sessions?mine_only=true&project_id={pid}"
        )
    ).json()
    ids = [s["id"] for s in listed]
    assert p_sid in ids
    assert free_sid not in ids


@pytest.mark.asyncio
async def test_list_sessions_project_filter_no_cross_user_leak(
    logged_in_client, other_logged_in_client
):
    """传 project_id 不会越权泄露他人个人会话（决策 #75：复用现有可见性闭环）。"""
    proj = await _make_project(logged_in_client, project_name="隔离项目")
    pid = proj["id"]
    # alice 建项目会话
    alice_sid = (
        await logged_in_client.post("/api/sessions", json={"project_id": pid})
    ).json()["id"]

    # bob 非项目成员，即使传 project_id 也看不到 alice 的个人项目会话
    bob_view = (
        await other_logged_in_client.get(f"/api/sessions?project_id={pid}")
    ).json()
    assert alice_sid not in [s["id"] for s in bob_view]


@pytest.mark.asyncio
async def test_list_sessions_project_filter_with_team_sessions(
    logged_in_client, other_logged_in_client
):
    """团队空间会话同样按 project_id 过滤（决策 #74 团队空间适用）。"""
    proj = await _make_project(logged_in_client, project_name="团队项目")
    pid = proj["id"]
    # alice 建团队空间 + 共享会话并绑定项目
    created = await logged_in_client.post("/api/team-spaces", json={"name": "团队资料"})
    space_id = created.json()["id"]
    other = (await other_logged_in_client.get("/api/me")).json()
    await logged_in_client.post(
        f"/api/team-spaces/{space_id}/members",
        json={"user_id": other["id"], "role": "editor"},
    )
    team_session = await logged_in_client.post(
        "/api/sessions",
        json={
            "workspace_kind": "team",
            "team_space_id": space_id,
            "is_shared": True,
            "project_id": pid,
        },
    )
    assert team_session.status_code == 200, team_session.text
    team_sid = team_session.json()["id"]

    # bob 是空间成员，在 workspace_kind=all 下选项目，能看到该共享团队会话
    bob_list = (
        await other_logged_in_client.get(
            f"/api/sessions?workspace_kind=all&project_id={pid}"
        )
    ).json()
    assert team_sid in [s["id"] for s in bob_list]
    # 选别的项目则看不到
    other_proj = await _make_project(
        logged_in_client, customer_name="客户X", project_name="其他项目"
    )
    bob_other = (
        await other_logged_in_client.get(
            f"/api/sessions?workspace_kind=all&project_id={other_proj['id']}"
        )
    ).json()
    assert team_sid not in [s["id"] for s in bob_other]


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
