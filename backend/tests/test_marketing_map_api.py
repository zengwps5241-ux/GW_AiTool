"""营销地图 API 测试（M2.2）。

覆盖：
- 角色卡 CRUD + 综合评分/等级自动计算 + 筛选（department/role_type/stance）
- 态度变化记录（追加 stanceChangeLog + 联动主观层 stance）
- 角色关系 CRUD + 关系网络图（nodes/edges）
- 话术 CRUD + 筛选
- 知识库 CRUD + 筛选
- 项目级隔离（非成员 403）
"""

import pytest


# ─── 辅助 ──────────────────────────────────────────────────────


async def _project(client, name="营销项目"):
    cid = (await client.post("/api/customers", json={"name": "客户"})).json()["id"]
    return (await client.post("/api/projects", json={"customer_id": cid, "name": name})).json()["id"]


def _base(pid: int) -> str:
    return f"/api/projects/{pid}"


# ─── 角色卡 + 综合评分 ─────────────────────────────────────────


async def test_card_crud_and_composite_score(logged_in_client):
    """创建角色卡 → 服务端按 §5.2 计算 compositeScore 与 gradeLevel。"""
    pid = await _project(logged_in_client)
    base = _base(pid)

    res = await logged_in_client.post(
        f"{base}/stakeholder-cards",
        json={
            "name": "王主任",
            "position": "信息化部主任",
            "department": "信息部",
            "role_type": "economic_decision_maker",
            "subjective_layer": {"stance": "支持", "engagement": 5, "influence": 5, "support": 5},
        },
    )
    assert res.status_code == 201
    card = res.json()
    assert card["subjective_layer"]["compositeScore"] == 5
    assert card["subjective_layer"]["gradeLevel"] == "倾向我方"
    card_id = card["id"]

    # Champion 判定：高分
    res = await logged_in_client.post(
        f"{base}/stakeholder-cards",
        json={
            "name": "李总",
            "department": "决策层",
            "subjective_layer": {"engagement": 8, "influence": 9, "support": 8},
        },
    )
    assert res.json()["subjective_layer"]["compositeScore"] == 8
    assert res.json()["subjective_layer"]["gradeLevel"] == "Champion"

    # 默认列表（reviewed）含两张
    cards = (await logged_in_client.get(f"{base}/stakeholder-cards")).json()
    assert len(cards) == 2

    # 更新
    res = await logged_in_client.put(
        f"{base}/stakeholder-cards/{card_id}", json={"position": "主任（更新）"}
    )
    assert res.status_code == 200
    assert res.json()["position"] == "主任（更新）"

    # 删除
    assert (await logged_in_client.delete(f"{base}/stakeholder-cards/{card_id}")).status_code == 204
    assert len((await logged_in_client.get(f"{base}/stakeholder-cards")).json()) == 1


async def test_card_filter_by_department_role_stance(logged_in_client):
    pid = await _project(logged_in_client)
    base = _base(pid)

    await logged_in_client.post(
        f"{base}/stakeholder-cards",
        json={"name": "A", "department": "信息部", "role_type": "technical_evaluator",
              "subjective_layer": {"stance": "支持", "engagement": 5, "influence": 5, "support": 5}},
    )
    await logged_in_client.post(
        f"{base}/stakeholder-cards",
        json={"name": "B", "department": "业务部", "role_type": "user",
              "subjective_layer": {"stance": "反对", "engagement": 1, "influence": 1, "support": 1}},
    )

    # 按 department
    assert len((await logged_in_client.get(f"{base}/stakeholder-cards", params={"department": "信息部"})).json()) == 1
    # 按 role_type
    assert len((await logged_in_client.get(f"{base}/stakeholder-cards", params={"role_type": "user"})).json()) == 1
    # 按 stance（JSONB 内）
    stanced = (await logged_in_client.get(f"{base}/stakeholder-cards", params={"stance": "支持"})).json()
    assert len(stanced) == 1 and stanced[0]["name"] == "A"


# ─── 态度变化（§7.6） ─────────────────────────────────────────


async def test_stance_change_appends_and_updates(logged_in_client):
    pid = await _project(logged_in_client)
    base = _base(pid)
    card = (
        await logged_in_client.post(
            f"{base}/stakeholder-cards",
            json={"name": "X", "subjective_layer": {"stance": "观望"}},
        )
    ).json()
    cid = card["id"]

    res = await logged_in_client.post(
        f"{base}/stakeholder-cards/{cid}/stance-changes",
        json={"from": "观望", "to": "中立", "reason": "首次拜访后认可团队专业度"},
    )
    assert res.status_code == 201
    assert res.json()["to_stance"] == "中立"

    # 卡片 stanceChangeLog 已追加，且主观层 stance 联动更新
    card = (await logged_in_client.get(f"{base}/stakeholder-cards/{cid}")).json()
    assert len(card["stance_change_log"]) == 1
    assert card["stance_change_log"][0]["to"] == "中立"
    assert card["subjective_layer"]["stance"] == "中立"


async def test_stance_change_card_not_found(logged_in_client):
    pid = await _project(logged_in_client)
    res = await logged_in_client.post(
        f"{_base(pid)}/stakeholder-cards/99999/stance-changes",
        json={"from": "a", "to": "b", "reason": "x"},
    )
    assert res.status_code == 404


# ─── 角色关系 + 关系网络图 ────────────────────────────────────


async def test_relations_and_graph(logged_in_client):
    pid = await _project(logged_in_client)
    base = _base(pid)
    a = (await logged_in_client.post(f"{base}/stakeholder-cards", json={"name": "李工"})).json()["id"]
    b = (await logged_in_client.post(f"{base}/stakeholder-cards", json={"name": "王主任"})).json()["id"]

    # 建立汇报关系
    res = await logged_in_client.post(
        f"{base}/stakeholder-relations",
        json={"from_card_id": a, "to_card_id": b, "relation_type": "reports_to", "description": "直接汇报"},
    )
    assert res.status_code == 201
    assert res.json()["from_card_name"] == "李工"
    assert res.json()["to_card_name"] == "王主任"

    # 关系列表
    assert len((await logged_in_client.get(f"{base}/stakeholder-relations")).json()) == 1

    # 关系网络图：2 节点 + 1 边
    graph = (await logged_in_client.get(f"{base}/stakeholder-relations/graph")).json()
    assert len(graph["nodes"]) == 2
    assert len(graph["edges"]) == 1
    assert graph["edges"][0]["relation_type"] == "reports_to"


async def test_relation_self_loop_rejected(logged_in_client):
    pid = await _project(logged_in_client)
    base = _base(pid)
    a = (await logged_in_client.post(f"{base}/stakeholder-cards", json={"name": "A"})).json()["id"]
    res = await logged_in_client.post(
        f"{base}/stakeholder-relations",
        json={"from_card_id": a, "to_card_id": a, "relation_type": "collaborates"},
    )
    assert res.status_code == 400


# ─── 话术 ──────────────────────────────────────────────────────


async def test_talk_scripts_crud_and_filter(logged_in_client):
    pid = await _project(logged_in_client)
    base = _base(pid)
    card = (await logged_in_client.post(f"{base}/stakeholder-cards", json={"name": "角色"})).json()["id"]

    res = await logged_in_client.post(
        f"{base}/talk-scripts",
        json={
            "stakeholder_card_id": card,
            "role_type": "economic_decision_maker",
            "scenario": "价值呈现",
            "content": "## 价值呈现\n我们的方案能为您...",
            "source_customer_quote": "我希望看到ROI",
        },
    )
    assert res.status_code == 201
    sid = res.json()["id"]
    assert res.json()["stakeholder_card_name"] == "角色"

    # 筛选 role_type
    assert len((await logged_in_client.get(f"{base}/talk-scripts", params={"role_type": "economic_decision_maker"})).json()) == 1
    assert len((await logged_in_client.get(f"{base}/talk-scripts", params={"role_type": "user"})).json()) == 0

    # 更新 + 删除
    assert (await logged_in_client.put(f"{base}/talk-scripts/{sid}", json={"scenario": "预算讨论"})).status_code == 200
    assert (await logged_in_client.delete(f"{base}/talk-scripts/{sid}")).status_code == 204


async def test_talk_script_template(logged_in_client):
    """is_template=true 且无关联角色卡 → 跨客户通用模板。"""
    pid = await _project(logged_in_client)
    res = await logged_in_client.post(
        f"{_base(pid)}/talk-scripts",
        json={"role_type": "user", "scenario": "初次拜访", "content": "通用开场白", "is_template": True},
    )
    assert res.status_code == 201
    assert res.json()["is_template"] is True
    assert res.json()["stakeholder_card_id"] is None


# ─── 知识库 ────────────────────────────────────────────────────


async def test_knowledge_base_crud_and_filter(logged_in_client):
    pid = await _project(logged_in_client)
    base = _base(pid)

    res = await logged_in_client.post(
        f"{base}/knowledge-base",
        json={"category": "role_recognition", "title": "经济决策者识别速查", "content": "典型职位..."},
    )
    assert res.status_code == 201
    kb_id = res.json()["id"]
    await logged_in_client.post(
        f"{base}/knowledge-base",
        json={"category": "onboarding_guide", "title": "新人培养流程", "content": "理论学习→模拟..."},
    )

    # 按 category 筛选
    assert len((await logged_in_client.get(f"{base}/knowledge-base", params={"category": "role_recognition"})).json()) == 1
    assert len((await logged_in_client.get(f"{base}/knowledge-base")).json()) == 2

    # 更新 + 删除
    assert (await logged_in_client.put(f"{base}/knowledge-base/{kb_id}", json={"title": "更新标题"})).status_code == 200
    assert (await logged_in_client.delete(f"{base}/knowledge-base/{kb_id}")).status_code == 204


async def test_knowledge_base_invalid_category(logged_in_client):
    pid = await _project(logged_in_client)
    res = await logged_in_client.post(
        f"{_base(pid)}/knowledge-base",
        json={"category": "invalid_cat", "title": "x", "content": "y"},
    )
    assert res.status_code == 422


# ─── 项目级隔离 ────────────────────────────────────────────────


async def test_marketing_map_isolation(logged_in_client, other_logged_in_client):
    pid = await _project(logged_in_client)
    res = await other_logged_in_client.get(f"{_base(pid)}/stakeholder-cards")
    assert res.status_code == 403


async def test_marketing_map_admin_bypass(admin_client, other_logged_in_client):
    cid = (await other_logged_in_client.post("/api/customers", json={"name": "c"})).json()["id"]
    pid = (await other_logged_in_client.post("/api/projects", json={"customer_id": cid, "name": "p"})).json()["id"]
    res = await admin_client.get(f"{_base(pid)}/stakeholder-cards")
    assert res.status_code == 200


# ─── 角色去重候选（M5.5.1 person_disambiguation）──────────────
#
# 检测逻辑仅在 save_stakeholder_card_draft 工具（Claude SDK 进程内 MCP）触发，
# 纯代码测试无法走 SDK，故直接调 service.detect_and_create_disambiguation 模拟触发。


async def _detect(pid: int, draft_id: int) -> bool:
    """用独立 session 触发去重检测（模拟 tools.py 新建草稿后的调用）。"""
    from app.db.session import async_session
    from app.modules.marketing_map import service as mm

    async with async_session() as db:
        return await mm.detect_and_create_disambiguation(db, pid, draft_id)


async def test_disambiguation_detects_exact_name_and_resolve_new(logged_in_client):
    """完全同名 → 生成候选；resolve=new → 草稿 promote 为 reviewed。"""
    pid = await _project(logged_in_client)
    base = _base(pid)
    existing = (
        await logged_in_client.post(
            f"{base}/stakeholder-cards",
            json={"name": "王主任", "department": "信息部", "role_type": "economic_decision_maker"},
        )
    ).json()
    draft = (
        await logged_in_client.post(
            f"{base}/stakeholder-cards",
            json={"name": "王主任", "department": "信息部", "review_status": "draft"},
        )
    ).json()

    assert await _detect(pid, draft["id"]) is True

    cands = (await logged_in_client.get(f"{base}/disambiguation-candidates")).json()
    assert len(cands) == 1
    assert cands[0]["draft_card_id"] == draft["id"]
    assert cands[0]["status"] == "pending"
    assert len(cands[0]["candidates"]) == 1
    assert cands[0]["candidates"][0]["id"] == existing["id"]
    assert cands[0]["candidates"][0]["score"] == 1.0
    assert "完全同名" in cands[0]["candidates"][0]["reasons"]

    # resolve=new → 草稿 promote
    res = await logged_in_client.post(
        f"{base}/disambiguation-candidates/{cands[0]['id']}/resolve",
        json={"decision": "new"},
    )
    assert res.status_code == 200
    assert res.json()["status"] == "resolved"
    assert res.json()["decision"] == "new"

    # 草稿已 reviewed；pending 列表清空
    card = (await logged_in_client.get(f"{base}/stakeholder-cards/{draft['id']}")).json()
    assert card["review_status"] == "reviewed"
    assert len((await logged_in_client.get(f"{base}/disambiguation-candidates")).json()) == 0


async def test_disambiguation_name_containment_scores_partial(logged_in_client):
    """姓名包含关系（王志强 vs 王志强主任）→ 0.6 分候选。"""
    pid = await _project(logged_in_client)
    base = _base(pid)
    await logged_in_client.post(f"{base}/stakeholder-cards", json={"name": "王志强主任"})
    draft = (
        await logged_in_client.post(
            f"{base}/stakeholder-cards",
            json={"name": "王志强", "review_status": "draft"},
        )
    ).json()

    assert await _detect(pid, draft["id"]) is True
    cands = (await logged_in_client.get(f"{base}/disambiguation-candidates")).json()
    assert len(cands) == 1
    entry = cands[0]["candidates"][0]
    assert entry["score"] == 0.6
    assert "姓名相似" in entry["reasons"]


async def test_disambiguation_no_false_positive_on_weak_signal(logged_in_client):
    """姓名不同、仅部门+角色相同（0.4 < 阈值）→ 不生成候选。"""
    pid = await _project(logged_in_client)
    base = _base(pid)
    await logged_in_client.post(
        f"{base}/stakeholder-cards",
        json={"name": "张三", "department": "信息部", "role_type": "technical_evaluator"},
    )
    draft = (
        await logged_in_client.post(
            f"{base}/stakeholder-cards",
            json={
                "name": "李四",
                "department": "信息部",
                "role_type": "technical_evaluator",
                "review_status": "draft",
            },
        )
    ).json()

    assert await _detect(pid, draft["id"]) is False
    assert len((await logged_in_client.get(f"{base}/disambiguation-candidates")).json()) == 0


async def test_disambiguation_merge_enriches_and_deletes_draft(logged_in_client):
    """resolve=merge → 草稿字段填充目标、主观层重算、草稿删除。"""
    pid = await _project(logged_in_client)
    base = _base(pid)
    target = (
        await logged_in_client.post(
            f"{base}/stakeholder-cards",
            json={"name": "王志强", "department": "信息部"},  # 目标缺 position/主观层
        )
    ).json()
    draft = (
        await logged_in_client.post(
            f"{base}/stakeholder-cards",
            json={
                "name": "王志强",
                "department": "信息部",
                "position": "主任",
                "review_status": "draft",
                "subjective_layer": {"stance": "支持", "engagement": 5, "influence": 5, "support": 5},
            },
        )
    ).json()
    assert await _detect(pid, draft["id"]) is True

    cid = (
        await logged_in_client.get(f"{base}/disambiguation-candidates")
    ).json()[0]["id"]
    res = await logged_in_client.post(
        f"{base}/disambiguation-candidates/{cid}/resolve",
        json={"decision": "merge", "merge_into_card_id": target["id"]},
    )
    assert res.status_code == 200
    assert res.json()["decision"] == "merge"
    assert res.json()["merge_into_card_id"] == target["id"]

    # 草稿已删除（404）
    assert (
        await logged_in_client.get(f"{base}/stakeholder-cards/{draft['id']}")
    ).status_code == 404

    # 目标被填充：position + 主观层 compositeScore
    merged = (
        await logged_in_client.get(f"{base}/stakeholder-cards/{target['id']}")
    ).json()
    assert merged["position"] == "主任"
    assert merged["subjective_layer"]["compositeScore"] == 5


async def test_disambiguation_merge_rejects_target_not_in_candidates(logged_in_client):
    """merge 到不在候选列表的卡 → 400（只能合并到检测出的疑似同人卡）。"""
    pid = await _project(logged_in_client)
    base = _base(pid)
    # 既有的"王主任"会与草稿"王主任"命中候选
    await logged_in_client.post(f"{base}/stakeholder-cards", json={"name": "王主任"})
    # 另一张"赵六"不会命中（与草稿不同名）
    outsider = (
        await logged_in_client.post(f"{base}/stakeholder-cards", json={"name": "赵六"})
    ).json()
    draft = (
        await logged_in_client.post(
            f"{base}/stakeholder-cards",
            json={"name": "王主任", "review_status": "draft"},
        )
    ).json()
    assert await _detect(pid, draft["id"]) is True

    cid = (
        await logged_in_client.get(f"{base}/disambiguation-candidates")
    ).json()[0]["id"]
    res = await logged_in_client.post(
        f"{base}/disambiguation-candidates/{cid}/resolve",
        json={"decision": "merge", "merge_into_card_id": outsider["id"]},
    )
    assert res.status_code == 400


async def test_disambiguation_resolve_twice_rejected(logged_in_client):
    """重复 resolve 已处理候选 → 400。"""
    pid = await _project(logged_in_client)
    base = _base(pid)
    await logged_in_client.post(f"{base}/stakeholder-cards", json={"name": "王主任"})
    draft = (
        await logged_in_client.post(
            f"{base}/stakeholder-cards",
            json={"name": "王主任", "review_status": "draft"},
        )
    ).json()
    assert await _detect(pid, draft["id"]) is True

    cid = (
        await logged_in_client.get(f"{base}/disambiguation-candidates")
    ).json()[0]["id"]
    first = await logged_in_client.post(
        f"{base}/disambiguation-candidates/{cid}/resolve", json={"decision": "new"}
    )
    assert first.status_code == 200
    second = await logged_in_client.post(
        f"{base}/disambiguation-candidates/{cid}/resolve", json={"decision": "new"}
    )
    assert second.status_code == 400


async def test_disambiguation_not_found(logged_in_client):
    """不存在的候选 id → 404。"""
    pid = await _project(logged_in_client)
    res = await logged_in_client.post(
        f"{_base(pid)}/disambiguation-candidates/99999/resolve",
        json={"decision": "new"},
    )
    assert res.status_code == 404
