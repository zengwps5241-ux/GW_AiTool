"""AI 结构化草稿工具框架测试（M3.1）。

覆盖：
- M3.1.2：三个草稿工具的输入 JSON Schema 定义本身合法 + 校验逻辑（合法通过 / 非法报错）
- M3.1.3：handler 校验→落库→SSE 推送「待采纳」→返回工具结果
- M3.1.1：build_draft_tool_server 用 create_sdk_mcp_server 注册三工具（配置合法 + 工具可见）
- M2.4 衔接：reviews.adopt 派发器对 stakeholder/visit 草稿的采纳分支（§3.3 自确认→reviewed）

不依赖真实 Claude 会话（与 test_claude_runner 同类环境依赖测试隔离）。
"""

import pytest


# ─── M3.1.2：JSON Schema 定义 + 校验 ────────────────────────────


def test_three_draft_schemas_are_valid_jsonschema():
    """三个工具的输入 Schema 自身是合法 JSON Schema（可构造校验器）。"""
    import jsonschema

    from app.integrations.claude.tools import (
        SAVE_BUSINESS_MAP_DRAFT_SCHEMA,
        SAVE_STAKEHOLDER_CARD_DRAFT_SCHEMA,
        SAVE_VISIT_RECORD_DRAFT_SCHEMA,
    )

    for schema in (
        SAVE_BUSINESS_MAP_DRAFT_SCHEMA,
        SAVE_STAKEHOLDER_CARD_DRAFT_SCHEMA,
        SAVE_VISIT_RECORD_DRAFT_SCHEMA,
    ):
        # 能构造校验器即说明 Schema 合法
        jsonschema.Draft7Validator.check_schema(schema)


def test_validate_accepts_valid_business_map_input():
    from app.integrations.claude.tools import (
        SAVE_BUSINESS_MAP_DRAFT_SCHEMA,
        validate_tool_input,
    )

    err = validate_tool_input(
        SAVE_BUSINESS_MAP_DRAFT_SCHEMA,
        {"objects": [{"level": "L1", "name": "公司级价值链"}]},
    )
    assert err is None  # 合法入参：无错误


def test_validate_rejects_business_map_missing_objects():
    from app.integrations.claude.tools import (
        SAVE_BUSINESS_MAP_DRAFT_SCHEMA,
        validate_tool_input,
    )

    err = validate_tool_input(SAVE_BUSINESS_MAP_DRAFT_SCHEMA, {})
    assert err is not None
    assert "objects" in err


def test_validate_rejects_bad_level_enum():
    from app.integrations.claude.tools import (
        SAVE_BUSINESS_MAP_DRAFT_SCHEMA,
        validate_tool_input,
    )

    err = validate_tool_input(
        SAVE_BUSINESS_MAP_DRAFT_SCHEMA,
        {"objects": [{"level": "L9", "name": "x"}]},  # level 非法
    )
    assert err is not None


def test_validate_rejects_non_dict_input():
    from app.integrations.claude.tools import (
        SAVE_STAKEHOLDER_CARD_DRAFT_SCHEMA,
        validate_tool_input,
    )

    err = validate_tool_input(SAVE_STAKEHOLDER_CARD_DRAFT_SCHEMA, "not a dict")
    assert err is not None


# ─── M3.1.3：handler 校验→落库→SSE 推送→返回工具结果 ──────────


async def _make_ctx(client, pid, *, publish_events):
    """构造 DraftToolContext：project/user 从已登录 client 取，publish 收集事件。"""
    from app.integrations.claude.tools import DraftToolContext

    me = (await client.get("/api/me")).json()

    async def _publish(evt):
        publish_events.append(evt)

    return DraftToolContext(
        project_id=pid,
        user_id=me["id"],
        source_session_id="sess-test-1",
        publish=_publish,
    )


async def _project(client, customer_name="测试客户", project_name="测试项目"):
    cid = (await client.post("/api/customers", json={"name": customer_name})).json()["id"]
    return (
        (await client.post("/api/projects", json={"customer_id": cid, "name": project_name}))
        .json()["id"]
    )


@pytest.mark.asyncio
async def test_handle_save_business_map_draft_stores_and_publishes(logged_in_client):
    from app.integrations.claude.tools import handle_save_business_map_draft

    pid = await _project(logged_in_client)
    events: list[dict] = []
    ctx = await _make_ctx(logged_in_client, pid, publish_events=events)

    result = await handle_save_business_map_draft(
        ctx, {"objects": [{"level": "L1", "name": "公司级价值链", "generated_by_ai": True}]}
    )

    # 返回工具结果文本（非错误）
    assert result["is_error"] is False
    assert result["content"] and result["content"][0]["type"] == "text"

    # 落库：active 草稿存在且含该对象
    draft = (
        await logged_in_client.get(f"/api/projects/{pid}/business-map/drafts")
    ).json()
    assert draft is not None
    specs = draft["draft_data"].get("objects") if isinstance(draft["draft_data"], dict) else None
    assert specs and specs[0]["name"] == "公司级价值链"
    assert draft["source_session_id"] == "sess-test-1"

    # SSE 推送「待采纳」事件
    assert events, "应推送 draft_pending 事件"
    evt = events[0]
    assert evt["type"] == "draft_pending"
    assert evt["entity_type"] == "business_map_draft"
    assert evt["draft_id"] == draft["id"]
    assert evt["project_id"] == pid


@pytest.mark.asyncio
async def test_handle_save_stakeholder_card_draft_creates_draft_card(logged_in_client):
    from app.integrations.claude.tools import handle_save_stakeholder_card_draft

    pid = await _project(logged_in_client)
    events: list[dict] = []
    ctx = await _make_ctx(logged_in_client, pid, publish_events=events)

    result = await handle_save_stakeholder_card_draft(
        ctx,
        {
            "name": "王总监",
            "position": "IT 总监",
            "department": "信息中心",
            "role_type": "technical_evaluator",
            "subjective_layer": {"stance": "倾向我方", "engagement": 7, "influence": 8, "support": 6},
        },
    )

    assert result["is_error"] is False
    assert events[0]["entity_type"] == "stakeholder_card_draft"
    card_id = events[0]["draft_id"]

    # 落库：草稿态角色卡存在（include_drafts 才可见，§7.3）
    cards = (
        await logged_in_client.get(
            f"/api/projects/{pid}/stakeholder-cards?include_drafts=1"
        )
    ).json()
    matched = [c for c in cards if c["id"] == card_id]
    assert matched and matched[0]["review_status"] == "draft"
    assert matched[0]["name"] == "王总监"
    # 主观层综合评分被自动计算（§5.2）
    assert matched[0]["subjective_layer"]["compositeScore"] is not None


@pytest.mark.asyncio
async def test_handle_save_visit_record_draft_creates_draft_visit(logged_in_client):
    from app.integrations.claude.tools import handle_save_visit_record_draft

    pid = await _project(logged_in_client)
    events: list[dict] = []
    ctx = await _make_ctx(logged_in_client, pid, publish_events=events)

    result = await handle_save_visit_record_draft(
        ctx,
        {
            "visit_type": "现场访谈",
            "visit_date": "2026-07-09",
            "summary": "客户对方案 A 表达明确支持",
            "key_takeaways": ["方案 A 优先级最高"],
        },
    )

    assert result["is_error"] is False
    assert events[0]["entity_type"] == "visit_record_draft"
    visit_id = events[0]["draft_id"]

    visits = (
        await logged_in_client.get(
            f"/api/projects/{pid}/visit-records?include_drafts=1"
        )
    ).json()
    matched = [v for v in visits if v["id"] == visit_id]
    assert matched and matched[0]["review_status"] == "draft"
    assert matched[0]["summary"] == "客户对方案 A 表达明确支持"


@pytest.mark.asyncio
async def test_handle_invalid_input_returns_error_no_side_effects(logged_in_client):
    """入参不合法：返回 is_error，不落库、不推送。"""
    from app.integrations.claude.tools import handle_save_stakeholder_card_draft

    pid = await _project(logged_in_client)
    events: list[dict] = []
    ctx = await _make_ctx(logged_in_client, pid, publish_events=events)

    result = await handle_save_stakeholder_card_draft(ctx, {})  # 缺 name

    assert result["is_error"] is True
    assert result["content"][0]["type"] == "text"
    assert events == []


# ─── M3.1.1：build_draft_tool_server 注册三工具 ────────────────


@pytest.mark.asyncio
async def test_build_draft_tool_server_registers_three_tools():
    """build_draft_tool_server 返回 SDK MCP 配置，且 list_tools 暴露三个草稿工具。"""
    from mcp.types import ListToolsRequest

    from app.integrations.claude.tools import (
        DRAFT_SERVER_NAME,
        build_draft_tool_server,
    )

    async def _noop(_evt):
        return None

    ctx = DraftToolContext_for_test(
        project_id=1, user_id=1, source_session_id="s", publish=_noop
    )
    cfg = build_draft_tool_server(ctx)

    assert cfg["type"] == "sdk"
    assert cfg["name"] == DRAFT_SERVER_NAME
    srv = cfg["instance"]

    resp = await srv.request_handlers[ListToolsRequest](
        ListToolsRequest(method="tools/list")
    )
    names = {t.name for t in resp.root.tools}
    assert names == {
        "save_business_map_draft",
        "save_stakeholder_card_draft",
        "save_visit_record_draft",
    }


def test_draft_tool_allowed_names_are_mcp_prefixed():
    from app.integrations.claude.tools import (
        DRAFT_SERVER_NAME,
        draft_tool_allowed_names,
    )

    names = draft_tool_allowed_names()
    assert len(names) == 3
    assert all(n.startswith(f"mcp__{DRAFT_SERVER_NAME}__") for n in names)
    assert "mcp__consultant_drafts__save_business_map_draft" in names


# ─── M2.4 衔接：reviews.adopt 对 stakeholder/visit 草稿的采纳分支 ─


@pytest.mark.asyncio
async def test_adopt_stakeholder_card_draft_flips_to_reviewed(logged_in_client):
    """采纳角色卡草稿（§3.3 自确认→reviewed）：draft→reviewed，正式列表可见。"""
    pid = await _project(logged_in_client)
    card_id = (
        await logged_in_client.post(
            f"/api/projects/{pid}/stakeholder-cards",
            json={"name": "草稿角色", "review_status": "draft"},
        )
    ).json()["id"]

    # 草稿态：默认列表不可见
    assert not (await logged_in_client.get(f"/api/projects/{pid}/stakeholder-cards")).json()

    res = await logged_in_client.post(
        f"/api/projects/{pid}/adopt",
        json={"entity_type": "stakeholder_card_draft", "draft_id": card_id},
    )
    assert res.status_code == 200, res.text
    body = res.json()
    assert body["success"] is True
    assert body["review_status"] == "reviewed"

    # 采纳后：正式列表（不传 include_drafts）可见
    cards = (await logged_in_client.get(f"/api/projects/{pid}/stakeholder-cards")).json()
    assert any(c["id"] == card_id and c["review_status"] == "reviewed" for c in cards)


@pytest.mark.asyncio
async def test_adopt_visit_record_draft_flips_to_reviewed(logged_in_client):
    """采纳拜访记录草稿（§3.3 自确认→reviewed）。"""
    pid = await _project(logged_in_client)
    visit_id = (
        await logged_in_client.post(
            f"/api/projects/{pid}/visit-records",
            json={"visit_type": "现场访谈", "summary": "草稿拜访", "review_status": "draft"},
        )
    ).json()["id"]

    res = await logged_in_client.post(
        f"/api/projects/{pid}/adopt",
        json={"entity_type": "visit_record_draft", "draft_id": visit_id},
    )
    assert res.status_code == 200, res.text
    assert res.json()["review_status"] == "reviewed"

    visits = (await logged_in_client.get(f"/api/projects/{pid}/visit-records")).json()
    assert any(v["id"] == visit_id and v["review_status"] == "reviewed" for v in visits)


@pytest.mark.asyncio
async def test_adopt_entity_draft_wrong_state_rejected(logged_in_client):
    """采纳非 draft 态实体：400（不能把已发布的再次「采纳」）。"""
    pid = await _project(logged_in_client)
    card_id = (
        await logged_in_client.post(
            f"/api/projects/{pid}/stakeholder-cards",
            json={"name": "已发布角色", "review_status": "reviewed"},
        )
    ).json()["id"]

    res = await logged_in_client.post(
        f"/api/projects/{pid}/adopt",
        json={"entity_type": "stakeholder_card_draft", "draft_id": card_id},
    )
    assert res.status_code == 400


# 测试辅助：避免在文件顶部 import DraftToolContext（模块尚未实现的阶段也能读测试）
def DraftToolContext_for_test(*, project_id, user_id, source_session_id, publish):
    from app.integrations.claude.tools import DraftToolContext

    return DraftToolContext(
        project_id=project_id,
        user_id=user_id,
        source_session_id=source_session_id,
        publish=publish,
    )
