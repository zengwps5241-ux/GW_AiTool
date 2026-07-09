"""统一采纳/审批 API 测试（M2.4）。

覆盖：
- 统一采纳派发（POST /adopt）：Owner→reviewed + 版本快照；Deputy→pending_review
- 待审批聚合（GET /pending-reviews）：跨四类实体汇总 + entity_type 筛选 + 项目隔离
- approve / reject：Owner 翻状态（→reviewed 发布 / →rejected 退回），各实体类型
- 权限：approve/reject 仅 Owner（Deputy 403）；非成员 403
- 状态校验：审批不存在项 404；非 pending 项 400；不支持采纳类型 400
"""

import pytest


# ─── 辅助 ──────────────────────────────────────────────────────


async def _project(client, customer_name="测试客户", project_name="测试项目"):
    cid = (await client.post("/api/customers", json={"name": customer_name})).json()["id"]
    return (
        (await client.post("/api/projects", json={"customer_id": cid, "name": project_name}))
        .json()["id"]
    )


async def _add_deputy(owner_client, deputy_client, pid):
    """把 deputy 加为项目成员（默认 deputy 角色）。"""
    bob_id = (await deputy_client.get("/api/me")).json()["id"]
    await owner_client.post(f"/api/projects/{pid}/members", json={"user_id": bob_id})
    return bob_id


def _bm(pid: int) -> str:
    return f"/api/projects/{pid}/business-map"


def _mk(pid: int) -> str:
    return f"/api/projects/{pid}"


async def _create_pending_card(client, pid, name="待审角色卡"):
    return (
        await client.post(
            f"{_mk(pid)}/stakeholder-cards",
            json={"name": name, "review_status": "pending_review"},
        )
    ).json()["id"]


async def _create_pending_visit(client, pid, summary="待审拜访"):
    return (
        await client.post(
            f"{_mk(pid)}/visit-records",
            json={"visit_type": "现场访谈", "summary": summary, "review_status": "pending_review"},
        )
    ).json()["id"]


async def _create_pending_evidence(client, pid, visit_id, content="待审证据"):
    return (
        await client.post(
            f"{_mk(pid)}/evidence-sources",
            json={
                "visit_record_id": visit_id,
                "evidence_type": "客户原话",
                "content": content,
                "review_status": "pending_review",
            },
        )
    ).json()["id"]


# ─── 统一采纳派发 ─────────────────────────────────────────────


async def test_adopt_business_map_draft_owner(logged_in_client):
    """Owner 通过统一 /adopt 采纳业务地图草稿 → reviewed + 版本快照。"""
    pid = await _project(logged_in_client)
    base = _bm(pid)
    # 建草稿
    r = await logged_in_client.put(
        f"{base}/drafts",
        json={"draft_data": {"objects": [{"level": "L1", "name": "统一采纳L1"}]}},
    )
    draft_id = r.json()["id"]
    # 统一采纳入口（entity_type 默认 business_map_draft）
    res = await logged_in_client.post(f"{_mk(pid)}/adopt", json={"draft_id": draft_id})
    assert res.status_code == 200, res.text
    result = res.json()
    assert result["success"] is True
    assert result["review_status"] == "reviewed"
    assert result["version_number"] == 1
    # 对象进正式区
    objs = (await logged_in_client.get(f"{base}/objects")).json()
    assert any(o["name"] == "统一采纳L1" for o in objs)


async def test_adopt_business_map_draft_deputy_pending(
    logged_in_client, other_logged_in_client
):
    """Deputy 通过 /adopt 采纳 → pending_review → 进入待审批列表。"""
    pid = await _project(logged_in_client)
    await _add_deputy(logged_in_client, other_logged_in_client, pid)
    base = _bm(pid)
    # Deputy 建草稿
    r = await other_logged_in_client.put(
        f"{base}/drafts", json={"draft_data": {"objects": [{"level": "L1", "name": "deputy草稿"}]}}
    )
    draft_id = r.json()["id"]
    res = await other_logged_in_client.post(f"{_mk(pid)}/adopt", json={"draft_id": draft_id})
    assert res.status_code == 200
    assert res.json()["review_status"] == "pending_review"
    # 出现在待审批列表
    lst = (await logged_in_client.get(f"{_mk(pid)}/pending-reviews")).json()
    assert len(lst) == 1
    assert lst[0]["entity_type"] == "business_map_object"
    assert lst[0]["name"] == "deputy草稿"
    assert lst[0]["review_status"] == "pending_review"


async def test_adopt_unsupported_type(logged_in_client):
    """/adopt 不支持的类型 → 400。"""
    pid = await _project(logged_in_client)
    res = await logged_in_client.post(
        f"{_mk(pid)}/adopt", json={"entity_type": "stakeholder_card_draft", "draft_id": 1}
    )
    assert res.status_code == 400


# ─── 待审批聚合 ───────────────────────────────────────────────


async def test_pending_reviews_aggregate_cross_module(logged_in_client):
    """四类 pending_review 实体统一聚合 + entity_type 筛选。"""
    pid = await _project(logged_in_client)
    await _create_pending_card(logged_in_client, pid, name="角色卡A")
    vid = await _create_pending_visit(logged_in_client, pid, summary="拜访A")
    await _create_pending_evidence(logged_in_client, pid, vid, content="证据A")

    lst = (await logged_in_client.get(f"{_mk(pid)}/pending-reviews")).json()
    types = {it["entity_type"] for it in lst}
    assert types == {"stakeholder_card", "visit_record", "evidence_source"}
    # 中文名标签正确
    labels = {it["entity_type"]: it["entity_label"] for it in lst}
    assert labels["stakeholder_card"] == "角色卡"
    assert labels["visit_record"] == "拜访记录"
    assert labels["evidence_source"] == "证据"
    # 展示名
    names = {it["entity_type"]: it["name"] for it in lst}
    assert names["stakeholder_card"] == "角色卡A"
    assert names["visit_record"] == "拜访A"
    assert names["evidence_source"] == "证据A"

    # entity_type 筛选
    lst = (
        await logged_in_client.get(f"{_mk(pid)}/pending-reviews", params={"entity_type": "visit_record"})
    ).json()
    assert len(lst) == 1 and lst[0]["entity_type"] == "visit_record"

    # 未知 entity_type → 400
    res = await logged_in_client.get(
        f"{_mk(pid)}/pending-reviews", params={"entity_type": "no_such_type"}
    )
    assert res.status_code == 400


# ─── approve / reject ─────────────────────────────────────────


async def test_approve_business_map_object_publishes(logged_in_client, other_logged_in_client):
    """Owner 审批 business_map_object → reviewed → 页面可见 + 移出待审批列表。"""
    pid = await _project(logged_in_client)
    await _add_deputy(logged_in_client, other_logged_in_client, pid)
    base = _bm(pid)
    # Deputy 采纳产 2 个 pending 对象
    r = await other_logged_in_client.put(
        f"{base}/drafts",
        json={"draft_data": {"objects": [
            {"level": "L1", "name": "待审1"}, {"level": "L1", "name": "待审2"}
        ]}},
    )
    await other_logged_in_client.post(f"{_mk(pid)}/adopt", json={"draft_id": r.json()["id"]})

    lst = (await logged_in_client.get(f"{_mk(pid)}/pending-reviews")).json()
    assert len(lst) == 2
    target = lst[0]
    # Owner 审批其中一个
    res = await logged_in_client.post(
        f"{_mk(pid)}/reviews/{target['entity_type']}/{target['entity_id']}/approve"
    )
    assert res.status_code == 200, res.text
    out = res.json()
    assert out["review_status"] == "reviewed"
    assert out["reviewed_by"] is not None
    assert out["reviewed_at"] is not None
    # 待审批列表少一个
    lst = (await logged_in_client.get(f"{_mk(pid)}/pending-reviews")).json()
    assert len(lst) == 1
    # 该对象已进业务地图默认 reviewed 列表
    objs = (await logged_in_client.get(f"{base}/objects")).json()
    assert any(o["id"] == target["entity_id"] and o["review_status"] == "reviewed" for o in objs)


async def test_approve_each_entity_type(logged_in_client):
    """Owner 逐类审批角色卡/拜访/证据 → reviewed。"""
    pid = await _project(logged_in_client)
    card_id = await _create_pending_card(logged_in_client, pid)
    visit_id = await _create_pending_visit(logged_in_client, pid)
    evi_id = await _create_pending_evidence(logged_in_client, pid, visit_id)

    for et, eid in [
        ("stakeholder_card", card_id),
        ("visit_record", visit_id),
        ("evidence_source", evi_id),
    ]:
        res = await logged_in_client.post(f"{_mk(pid)}/reviews/{et}/{eid}/approve")
        assert res.status_code == 200, (et, res.text)
        assert res.json()["review_status"] == "reviewed"
    # 全部审完，列表空
    assert (await logged_in_client.get(f"{_mk(pid)}/pending-reviews")).json() == []


async def test_reject_flips_to_rejected(logged_in_client):
    """Owner 驳回 → rejected + 移出待审批列表（可带意见）。"""
    pid = await _project(logged_in_client)
    card_id = await _create_pending_card(logged_in_client, pid)
    res = await logged_in_client.post(
        f"{_mk(pid)}/reviews/stakeholder_card/{card_id}/reject",
        json={"comment": "信息不足，补全客观层"},
    )
    assert res.status_code == 200, res.text
    assert res.json()["review_status"] == "rejected"
    # 移出待审批列表
    lst = (await logged_in_client.get(f"{_mk(pid)}/pending-reviews")).json()
    assert all(it["entity_id"] != card_id for it in lst)
    # 无 body 也可
    card2 = await _create_pending_card(logged_in_client, pid, name="角色卡B")
    res = await logged_in_client.post(f"{_mk(pid)}/reviews/stakeholder_card/{card2}/reject")
    assert res.status_code == 200
    assert res.json()["review_status"] == "rejected"


# ─── 权限与状态校验 ───────────────────────────────────────────


async def test_approve_owner_only(logged_in_client, other_logged_in_client):
    """Deputy 不能审批 → 403。"""
    pid = await _project(logged_in_client)
    await _add_deputy(logged_in_client, other_logged_in_client, pid)
    card_id = await _create_pending_card(logged_in_client, pid)
    res = await other_logged_in_client.post(
        f"{_mk(pid)}/reviews/stakeholder_card/{card_id}/approve"
    )
    assert res.status_code == 403
    # reject 同样
    res = await other_logged_in_client.post(
        f"{_mk(pid)}/reviews/stakeholder_card/{card_id}/reject"
    )
    assert res.status_code == 403


async def test_approve_not_found_and_wrong_state(logged_in_client):
    """审批不存在项 → 404；审批非 pending 项 → 400。"""
    pid = await _project(logged_in_client)
    # 不存在
    res = await logged_in_client.post(
        f"{_mk(pid)}/reviews/stakeholder_card/99999/approve"
    )
    assert res.status_code == 404
    # 非 pending（默认 reviewed 的角色卡）
    card_id = (
        await logged_in_client.post(f"{_mk(pid)}/stakeholder-cards", json={"name": "已发布"})
    ).json()["id"]
    res = await logged_in_client.post(
        f"{_mk(pid)}/reviews/stakeholder_card/{card_id}/approve"
    )
    assert res.status_code == 400


async def test_pending_reviews_project_isolation(logged_in_client, other_logged_in_client):
    """非成员看不到项目待审批列表（403）；项目间数据隔离。"""
    pid = await _project(logged_in_client, project_name="P1")
    await _create_pending_card(logged_in_client, pid, name="P1角色卡")
    # bob 非成员 → 403
    res = await other_logged_in_client.get(f"{_mk(pid)}/pending-reviews")
    assert res.status_code == 403
    # bob 自己的项目看不到 P1 的待审批
    pid2 = await _project(other_logged_in_client, customer_name="客户2", project_name="P2")
    lst = (await other_logged_in_client.get(f"{_mk(pid2)}/pending-reviews")).json()
    assert lst == []


async def test_admin_can_approve_cross_project(admin_client, logged_in_client):
    """admin 越权：可审批任意项目的待审批项（§3.2 admin 可访问任意项目）。"""
    pid = await _project(logged_in_client, project_name="admin越权项目")
    card_id = await _create_pending_card(logged_in_client, pid, name="admin审批")
    # admin 列表可见
    lst = (await admin_client.get(f"{_mk(pid)}/pending-reviews")).json()
    assert any(it["entity_id"] == card_id for it in lst)
    # admin 审批
    res = await admin_client.post(f"{_mk(pid)}/reviews/stakeholder_card/{card_id}/approve")
    assert res.status_code == 200
    assert res.json()["review_status"] == "reviewed"
