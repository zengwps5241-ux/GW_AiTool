"""M3.3.1 consultant-router 意图路由测试。

覆盖：
- 7 类意图静态结构（标签 / 路由目标 Skill / file_upload·chat 无关键词）
- parse_slash_command / keyword_fallback / _parse_llm_json 纯逻辑
- route_user_prompt 三级路由（chip 直达 / LLM 高置信 / 关键词兜底 / chat 兜底）
- classify_intent_llm 的 env 处理与异常降级
- log_routing 落库 IntentRoutingLog
- router_plugin_active 判定
- plugin seed 模板齐备 + seed_default_plugins 非破坏性播种 + scan_plugins 发现
- streaming 集成：项目会话自然语言输入被路由改写 + IntentRoutingLog 落库
"""

import asyncio
from pathlib import Path

import pytest

PLUGINS_DIR = Path(__file__).resolve().parent.parent / "app" / "plugins_seed"

# 7 类意图 → 路由目标 Skill（chat 为 None）
EXPECTED_ROUTES = {
    "hypothesis_map": "consultant-hypothesis-map",
    "current_map_verify": "consultant-verify",
    "stakeholder_card": "consultant-stakeholder",
    "interview_summary": "consultant-interview",
    "visit_plan": "consultant-visit-plan",
    "file_upload": "consultant-upload",
    "chat": None,
}


# ─── 意图静态结构 ───────────────────────────────────────────


def test_intents_seven_labels():
    from app.modules.consultant.router import INTENTS

    assert set(INTENTS) == set(EXPECTED_ROUTES)


def test_intent_skill_map():
    from app.modules.consultant.router import INTENTS

    for label, skill in EXPECTED_ROUTES.items():
        assert INTENTS[label].skill == skill, f"{label} 路由目标不符"


def test_file_upload_and_chat_not_in_keyword_intents():
    from app.modules.consultant.router import INTENTS, KEYWORD_INTENTS

    assert INTENTS["file_upload"].keywords == ()
    assert INTENTS["chat"].keywords == ()
    assert "file_upload" not in KEYWORD_INTENTS
    assert "chat" not in KEYWORD_INTENTS


def test_skill_to_label_reverse_map():
    from app.modules.consultant.router import _SKILL_TO_LABEL

    assert _SKILL_TO_LABEL["consultant-hypothesis-map"] == "hypothesis_map"
    assert _SKILL_TO_LABEL["consultant-stakeholder"] == "stakeholder_card"
    # file_upload 的 skill 也在反查表里（供斜杠直达）
    assert _SKILL_TO_LABEL["consultant-upload"] == "file_upload"


# ─── parse_slash_command ───────────────────────────────────


def test_parse_slash_known_command():
    from app.modules.consultant.router import parse_slash_command

    cmd, rem = parse_slash_command("/consultant-hypothesis-map 生成地图 帮我")
    assert cmd == "consultant-hypothesis-map"
    assert rem == "生成地图 帮我"


def test_parse_slash_command_only():
    from app.modules.consultant.router import parse_slash_command

    cmd, rem = parse_slash_command("/consultant-verify")
    assert cmd == "consultant-verify"
    assert rem == ""


def test_parse_slash_no_slash():
    from app.modules.consultant.router import parse_slash_command

    assert parse_slash_command("画个假设地图") == (None, "画个假设地图")


def test_parse_slash_invalid_token_not_treated_as_command():
    from app.modules.consultant.router import parse_slash_command

    # 含路径分隔/特殊字符的 token 不当命令（避免误判普通文本）
    assert parse_slash_command("/path/to thing") == (None, "/path/to thing")


# ─── keyword_fallback ──────────────────────────────────────


def test_keyword_unique_hit():
    from app.modules.consultant.router import keyword_fallback

    assert keyword_fallback("帮我画一张假设地图") == ["hypothesis_map"]


def test_keyword_multi_hit_ambiguous():
    from app.modules.consultant.router import keyword_fallback

    hits = keyword_fallback("先画假设地图，再整理拜访记录")
    assert set(hits) == {"hypothesis_map", "interview_summary"}


def test_keyword_zero_hit():
    from app.modules.consultant.router import keyword_fallback

    assert keyword_fallback("你好，解释一下这段话") == []


def test_keyword_case_insensitive():
    from app.modules.consultant.router import keyword_fallback

    assert keyword_fallback("拆解到 L1 L2 L3 层级") == ["hypothesis_map"]


# ─── _parse_llm_json ───────────────────────────────────────


def test_parse_llm_json_plain():
    from app.modules.consultant.router import _parse_llm_json

    r = _parse_llm_json('{"label":"chat","confidence":0.8,"reason":"x"}')
    assert r == {"label": "chat", "confidence": 0.8, "reason": "x"}


def test_parse_llm_json_fenced():
    from app.modules.consultant.router import _parse_llm_json

    r = _parse_llm_json('```json\n{"label":"chat","confidence":0.9}\n```')
    assert r["label"] == "chat" and r["confidence"] == 0.9


def test_parse_llm_json_embedded():
    from app.modules.consultant.router import _parse_llm_json

    r = _parse_llm_json('结果是 {"label":"visit_plan","confidence":0.7} 完成')
    assert r and r["label"] == "visit_plan"


def test_parse_llm_json_invalid():
    from app.modules.consultant.router import _parse_llm_json

    assert _parse_llm_json("not json at all") is None
    assert _parse_llm_json(None) is None


def test_parse_llm_json_clamps_confidence():
    from app.modules.consultant.router import _parse_llm_json

    assert _parse_llm_json('{"label":"chat","confidence":1.5}')["confidence"] == 1.0
    assert _parse_llm_json('{"label":"chat","confidence":-0.2}')["confidence"] == 0.0


# ─── route_user_prompt（mock classify_intent_llm） ─────────


@pytest.mark.asyncio
async def test_route_chip_path_skips_llm(monkeypatch):
    from app.modules.consultant import router

    async def boom(text):  # noqa: ANN001
        raise AssertionError("chip 路径不应调用 LLM")

    monkeypatch.setattr(router, "classify_intent_llm", boom)
    decision = await router.route_user_prompt(
        agent=None, prompt="/consultant-hypothesis-map 生成假设地图"
    )
    assert decision.intent_label == "hypothesis_map"
    assert decision.confidence_source == "chip"
    assert decision.route_target == "consultant-hypothesis-map"
    # chip 路径原样下发（已含 /command + hint）
    assert decision.final_prompt == "/consultant-hypothesis-map 生成假设地图"


@pytest.mark.asyncio
async def test_route_llm_confident_skill(monkeypatch):
    from app.modules.consultant import router

    async def fake(text):  # noqa: ANN001
        return {"label": "stakeholder_card", "confidence": 0.9, "reason": "r"}

    monkeypatch.setattr(router, "classify_intent_llm", fake)
    decision = await router.route_user_prompt(agent=None, prompt="帮我做一张角色卡")
    assert decision.intent_label == "stakeholder_card"
    assert decision.confidence_source == "llm"
    assert decision.llm_confidence == 0.9
    assert decision.final_prompt == "/consultant-stakeholder 帮我做一张角色卡"


@pytest.mark.asyncio
async def test_route_llm_confident_chat(monkeypatch):
    from app.modules.consultant import router

    async def fake(text):  # noqa: ANN001
        return {"label": "chat", "confidence": 0.85}

    monkeypatch.setattr(router, "classify_intent_llm", fake)
    decision = await router.route_user_prompt(agent=None, prompt="帮我润色这段话")
    assert decision.intent_label == "chat"
    assert decision.confidence_source == "llm"
    assert decision.route_target is None
    assert decision.final_prompt == "帮我润色这段话"


@pytest.mark.asyncio
async def test_route_llm_low_confidence_falls_back_to_keyword(monkeypatch):
    from app.modules.consultant import router

    async def fake(text):  # noqa: ANN001
        return {"label": "chat", "confidence": 0.4}  # 低于阈值

    monkeypatch.setattr(router, "classify_intent_llm", fake)
    decision = await router.route_user_prompt(agent=None, prompt="画一张假设地图")
    assert decision.intent_label == "hypothesis_map"
    assert decision.confidence_source == "keyword"


@pytest.mark.asyncio
async def test_route_llm_none_keyword_unique(monkeypatch):
    from app.modules.consultant import router

    async def fake(text):  # noqa: ANN001
        return None  # 无 env / 失败

    monkeypatch.setattr(router, "classify_intent_llm", fake)
    decision = await router.route_user_prompt(agent=None, prompt="准备拜访方案")
    assert decision.intent_label == "visit_plan"
    assert decision.confidence_source == "keyword"
    assert decision.final_prompt == "/consultant-visit-plan 准备拜访方案"


@pytest.mark.asyncio
async def test_route_chat_fallback_zero_keyword(monkeypatch):
    from app.modules.consultant import router

    async def fake(text):  # noqa: ANN001
        return None

    monkeypatch.setattr(router, "classify_intent_llm", fake)
    decision = await router.route_user_prompt(agent=None, prompt="你好")
    assert decision.intent_label == "chat"
    assert decision.confidence_source == "chat_fallback"
    assert decision.needs_confirmation is False


@pytest.mark.asyncio
async def test_route_chat_fallback_multi_keyword_needs_confirm(monkeypatch):
    from app.modules.consultant import router

    async def fake(text):  # noqa: ANN001
        return None

    monkeypatch.setattr(router, "classify_intent_llm", fake)
    decision = await router.route_user_prompt(
        agent=None, prompt="画假设地图并整理拜访记录"
    )
    assert decision.intent_label == "chat"
    assert decision.confidence_source == "chat_fallback"
    assert decision.needs_confirmation is True
    assert set(decision.keyword_hits) == {"hypothesis_map", "interview_summary"}


@pytest.mark.asyncio
async def test_route_unknown_slash_falls_through_to_nl(monkeypatch):
    from app.modules.consultant import router

    async def fake(text):  # noqa: ANN001
        return {"label": "chat", "confidence": 0.9}

    monkeypatch.setattr(router, "classify_intent_llm", fake)
    # 未知斜杠命令 → 当作自然语言走 LLM
    decision = await router.route_user_prompt(agent=None, prompt="/foo 做什么")
    assert decision.intent_label == "chat"
    assert decision.confidence_source == "llm"


# ─── classify_intent_llm env 处理 ─────────────────────────


@pytest.mark.asyncio
async def test_classify_intent_llm_no_api_key_returns_none(monkeypatch):
    from app.modules.consultant import router

    monkeypatch.setattr(router, "_merged_env", lambda: {})
    assert await router.classify_intent_llm("画地图") is None


@pytest.mark.asyncio
async def test_classify_intent_llm_success(monkeypatch):
    from app.modules.consultant import router

    monkeypatch.setattr(
        router, "_merged_env", lambda: {"ANTHROPIC_PROVIDER_DEEPSEEK_AUTH_TOKEN": "k"}
    )
    captured: dict = {}

    async def fake_complete(**kwargs):
        captured.update(kwargs)
        return '{"label":"chat","confidence":0.9,"reason":"ok"}'

    monkeypatch.setattr(router, "generate_chat_completion", fake_complete)
    r = await router.classify_intent_llm("解释一下")
    assert r == {"label": "chat", "confidence": 0.9, "reason": "ok"}
    assert captured["system_prompt"]  # 用了意图分类 Prompt


@pytest.mark.asyncio
async def test_classify_intent_llm_exception_returns_none(monkeypatch):
    from app.modules.consultant import router

    monkeypatch.setattr(
        router, "_merged_env", lambda: {"ANTHROPIC_PROVIDER_DEEPSEEK_AUTH_TOKEN": "k"}
    )

    async def boom(**kwargs):
        raise RuntimeError("net")

    monkeypatch.setattr(router, "generate_chat_completion", boom)
    assert await router.classify_intent_llm("解释一下") is None


# ─── log_routing 落库 ──────────────────────────────────────


@pytest.mark.asyncio
async def test_log_routing_persists(db_session, test_user):
    from app.modules.consultant.router import RoutingDecision, log_routing

    decision = RoutingDecision(
        intent_label="hypothesis_map",
        route_target="consultant-hypothesis-map",
        confidence_source="keyword",
        final_prompt="/consultant-hypothesis-map 画地图",
        keyword_hits=["hypothesis_map"],
    )
    entry = await log_routing(
        db_session,
        session_id="sess-x",
        project_id=None,
        user_id=test_user.id,
        prompt="画地图",
        decision=decision,
    )
    assert entry.id is not None
    assert entry.intent_label == "hypothesis_map"
    assert entry.confidence_source == "keyword"
    assert entry.final_prompt == "/consultant-hypothesis-map 画地图"
    assert entry.keyword_hits == ["hypothesis_map"]


# ─── router_plugin_active ─────────────────────────────────


def test_router_plugin_active():
    from app.modules.consultant.router import router_plugin_active

    class A:
        pass

    a = A()
    a.plugins = "consultant-router,consultant-search,consultant-defense"
    assert router_plugin_active(a) is True

    a2 = A()
    a2.plugins = ""
    assert router_plugin_active(a2) is False

    a3 = A()
    a3.plugins = None
    assert router_plugin_active(a3) is False


# ─── seed / scan ───────────────────────────────────────────


def test_router_plugin_manifest_present():
    assert (PLUGINS_DIR / "consultant-router" / ".claude-plugin" / "plugin.json").exists()
    assert (PLUGINS_DIR / "consultant-router" / "prompts" / "intent_classifier.md").exists()


def test_intent_classifier_prompt_loadable():
    from app.modules.consultant.router import load_intent_classifier_prompt

    prompt = load_intent_classifier_prompt()
    assert "label" in prompt and "hypothesis_map" in prompt


def test_scan_plugins_discovers_consultant_router(monkeypatch):
    from app.modules.catalog import plugins as plugins_module

    monkeypatch.setattr(plugins_module, "_plugins_dir", lambda: PLUGINS_DIR)
    names = {p["name"] for p in plugins_module.scan_plugins()}
    assert "consultant-router" in names


def test_seed_default_plugins_copies_templates(app_env):
    from app.core.config import get_settings
    from app.modules.agents.workdir import seed_default_plugins

    master = get_settings().claude_data_dir / "plugins"
    seed_default_plugins()
    assert (master / "consultant-router" / ".claude-plugin" / "plugin.json").exists()
    # 非破坏性：再次播种不覆盖用户自定义
    manifest = master / "consultant-router" / ".claude-plugin" / "plugin.json"
    manifest.write_text('{"name":"custom"}', encoding="utf-8")
    seed_default_plugins()
    assert '"custom"' in manifest.read_text(encoding="utf-8")


# ─── streaming 集成（项目会话自然语言 → 路由改写 + 落库） ───


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
async def test_stream_session_chat_routes_and_logs(logged_in_client, monkeypatch):
    from app.modules.consultant import router as consultant_router
    from app.modules.sessions import streaming

    # 建项目 + 项目会话（项目 Agent 绑定 consultant-router）
    cid = (
        await logged_in_client.post("/api/customers", json={"name": "路由测试客户"})
    ).json()["id"]
    pid = (
        await logged_in_client.post(
            "/api/projects", json={"customer_id": cid, "name": "路由测试项目"}
        )
    ).json()["id"]
    sid = (
        await logged_in_client.post("/api/sessions", json={"project_id": pid})
    ).json()["id"]
    cs = await _fetch_session(sid)
    alice = await _fetch_user("alice")

    # 真实路由会加载 cs.agent_id 对应 Agent 并传入；项目 Agent 绑定 consultant-router
    from app.db.session import async_session
    from app.models import Agent

    async with async_session() as db:
        agent = await db.get(Agent, cs.agent_id)
    assert agent is not None and "consultant-router" in (agent.plugins or "")

    # 固定 LLM 分类返回 None，确保走关键词兜底（确定性）
    async def _no_llm(text):  # noqa: ANN001
        return None

    monkeypatch.setattr(consultant_router, "classify_intent_llm", _no_llm)

    captured: dict = {}

    async def fake_stream_chat(**kwargs):
        captured.update(kwargs)
        return _fake_summary()

    monkeypatch.setattr(streaming, "stream_chat", fake_stream_chat)

    response = await streaming.stream_session_chat(cs, alice, "帮我生成假设地图", agent=agent)
    await _drain(response)

    # 提示被改写为 /consultant-hypothesis-map（关键词「假设地图」命中）
    assert captured["prompt"] == "/consultant-hypothesis-map 帮我生成假设地图"

    # IntentRoutingLog 落库
    from app.db.session import async_session
    from app.models import IntentRoutingLog
    from sqlalchemy import select

    async with async_session() as db:
        rows = (
            await db.execute(
                select(IntentRoutingLog).where(IntentRoutingLog.session_id == sid)
            )
        ).scalars().all()
    assert len(rows) == 1
    assert rows[0].intent_label == "hypothesis_map"
    assert rows[0].confidence_source == "keyword"
    assert rows[0].project_id == pid
