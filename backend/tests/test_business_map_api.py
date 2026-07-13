"""业务地图 API 测试（M2.1）。

覆盖：
- 对象 CRUD + 筛选（默认 reviewed；level/map_type；include_drafts）
- 前置分析 upsert（一个项目一份）
- 草稿 upsert + 采纳（Owner→reviewed 直接发布 + 版本快照；Deputy→pending_review）
- 版本列表 + 回滚（自动留存审计快照）
- 五维健康（节点计算 / 批量重评估 / 手动覆盖）
- 项目级隔离（非成员 403；回滚仅 Owner）
"""

import pytest


# ─── 辅助 ──────────────────────────────────────────────────────


async def _project(client, customer_name="测试客户", project_name="测试项目"):
    cid = (await client.post("/api/customers", json={"name": customer_name})).json()["id"]
    return (
        (await client.post("/api/projects", json={"customer_id": cid, "name": project_name}))
        .json()["id"]
    )


def _bm(project_id: int) -> str:
    return f"/api/projects/{project_id}/business-map"


# ─── 对象 CRUD + 筛选 ─────────────────────────────────────────


async def test_object_crud_and_default_reviewed(logged_in_client):
    """手动新增对象默认 reviewed（默认列表可见）。"""
    pid = await _project(logged_in_client)
    base = _bm(pid)

    # 创建 L1 对象
    res = await logged_in_client.post(
        f"{base}/objects",
        json={
            "level": "L1",
            "name": "勘探开发域",
            "map_type": "hypothesis",
            "payload": {"coreActivities": ["盆地评价"], "capabilityChain": "研究→勘探"},
        },
    )
    assert res.status_code == 201
    oid = res.json()["id"]
    assert res.json()["review_status"] == "reviewed"

    # 默认列表（reviewed）含该对象
    lst = (await logged_in_client.get(f"{base}/objects")).json()
    assert len(lst) == 1 and lst[0]["id"] == oid

    # 更新
    res = await logged_in_client.put(
        f"{base}/objects/{oid}", json={"name": "勘探开发域（更新）"}
    )
    assert res.status_code == 200
    assert res.json()["name"] == "勘探开发域（更新）"

    # 按层级筛选
    res = await logged_in_client.get(f"{base}/objects", params={"level": "L2"})
    assert res.json() == []

    # 删除
    res = await logged_in_client.delete(f"{base}/objects/{oid}")
    assert res.status_code == 204
    assert (await logged_in_client.get(f"{base}/objects")).json() == []


async def test_object_get_not_found(logged_in_client):
    pid = await _project(logged_in_client)
    res = await logged_in_client.get(f"{_bm(pid)}/objects/99999")
    assert res.status_code == 404


# ─── 前置分析 ──────────────────────────────────────────────────


async def test_pre_analysis_upsert(logged_in_client):
    pid = await _project(logged_in_client)
    base = _bm(pid)

    # 初始无
    assert (await logged_in_client.get(f"{base}/pre-analysis")).json() is None

    # 创建
    res = await logged_in_client.put(
        f"{base}/pre-analysis",
        json={"industry_value_chain": "上游勘探→中游炼化", "customer_position": "行业龙头"},
    )
    assert res.status_code == 200
    assert res.json()["industry_value_chain"].startswith("上游")

    # 再更新（同一份）
    res = await logged_in_client.put(
        f"{base}/pre-analysis", json={"customer_position": "市场份额第二"}
    )
    assert res.status_code == 200
    assert res.json()["customer_position"] == "市场份额第二"
    # 仍只有一份
    assert (await logged_in_client.get(f"{base}/pre-analysis")).json()["id"] == res.json()["id"]


# ─── 草稿 + 采纳 ───────────────────────────────────────────────


async def test_draft_adopt_owner_publishes_and_versions(logged_in_client):
    """Owner 采纳草稿 → 对象 reviewed 直接可见 + 生成版本快照。"""
    pid = await _project(logged_in_client)
    base = _bm(pid)

    # 创建草稿
    res = await logged_in_client.put(
        f"{base}/drafts",
        json={
            "draft_data": {
                "objects": [
                    {"level": "L1", "name": "草稿L1", "payload": {"coreActivities": ["x"]}},
                    {"level": "L2", "name": "草稿L2", "parent_id": None},
                ]
            }
        },
    )
    assert res.status_code == 200
    draft_id = res.json()["id"]
    assert res.json()["status"] == "active"

    # 采纳
    res = await logged_in_client.post(f"{base}/drafts/{draft_id}/adopt")
    assert res.status_code == 200
    result = res.json()
    assert result["success"] is True
    assert result["adopted_object_count"] == 2
    assert result["review_status"] == "reviewed"
    assert result["version_number"] == 1

    # 对象已进入正式区（默认 reviewed 列表可见）
    objs = (await logged_in_client.get(f"{base}/objects")).json()
    assert {o["name"] for o in objs} == {"草稿L1", "草稿L2"}

    # 版本 #1 已生成
    versions = (await logged_in_client.get(f"{base}/versions")).json()
    assert len(versions) == 1
    assert versions[0]["version_number"] == 1
    assert len(versions[0]["snapshot_data"]["objects"]) == 2

    # 草稿已 adopted，再次采纳应 400
    res = await logged_in_client.post(f"{base}/drafts/{draft_id}/adopt")
    assert res.status_code == 400


async def test_draft_adopt_deputy_pending_review(
    logged_in_client, other_logged_in_client
):
    """Deputy 采纳 → 对象 pending_review（默认 reviewed 列表不可见）。"""
    pid = await _project(logged_in_client)
    base = _bm(pid)
    # 邀请 bob 为 deputy
    bob_id = (await other_logged_in_client.get("/api/me")).json()["id"]
    await logged_in_client.post(
        f"/api/projects/{pid}/members", json={"user_id": bob_id}
    )

    # bob 创建草稿并采纳
    res = await other_logged_in_client.put(
        f"{base}/drafts", json={"draft_data": {"objects": [{"level": "L1", "name": "deputy产出"}]}}
    )
    draft_id = res.json()["id"]
    res = await other_logged_in_client.post(f"{base}/drafts/{draft_id}/adopt")
    assert res.status_code == 200
    assert res.json()["review_status"] == "pending_review"

    # 默认列表（reviewed）看不到
    objs = (await logged_in_client.get(f"{base}/objects")).json()
    assert objs == []
    # include_drafts 可见 pending_review
    objs = (await logged_in_client.get(f"{base}/objects", params={"include_drafts": True})).json()
    assert any(o["name"] == "deputy产出" and o["review_status"] == "pending_review" for o in objs)


# ─── 版本回滚 ──────────────────────────────────────────────────


async def test_version_rollback(logged_in_client):
    """回滚到历史版本：替换 reviewed 数据 + 留存审计快照。"""
    pid = await _project(logged_in_client)
    base = _bm(pid)

    # 第一次采纳：对象 A
    r = await logged_in_client.put(
        f"{base}/drafts",
        json={"draft_data": {"objects": [{"level": "L1", "name": "A"}]}},
    )
    await logged_in_client.post(f"{base}/drafts/{r.json()['id']}/adopt")
    v1 = (await logged_in_client.get(f"{base}/versions")).json()[0]

    # 第二次采纳：对象 B（A 仍在）
    r = await logged_in_client.put(
        f"{base}/drafts",
        json={"draft_data": {"objects": [{"level": "L1", "name": "B"}]}},
    )
    await logged_in_client.post(f"{base}/drafts/{r.json()['id']}/adopt")
    names = {o["name"] for o in (await logged_in_client.get(f"{base}/objects")).json()}
    assert names == {"A", "B"}

    # 回滚到 v1（只有 A）
    res = await logged_in_client.post(f"{base}/versions/{v1['id']}/rollback")
    assert res.status_code == 200
    names = {o["name"] for o in (await logged_in_client.get(f"{base}/objects")).json()}
    assert names == {"A"}

    # 版本数：v1 + v2 + 回滚审计快照 = 3
    versions = (await logged_in_client.get(f"{base}/versions")).json()
    assert len(versions) == 3


async def test_rollback_owner_only(logged_in_client, other_logged_in_client):
    """Deputy 不能回滚 → 403。"""
    pid = await _project(logged_in_client)
    base = _bm(pid)
    bob_id = (await other_logged_in_client.get("/api/me")).json()["id"]
    await logged_in_client.post(
        f"/api/projects/{pid}/members", json={"user_id": bob_id}
    )
    # 先产生一个版本
    r = await logged_in_client.put(
        f"{base}/drafts", json={"draft_data": {"objects": [{"level": "L1", "name": "X"}]}}
    )
    await logged_in_client.post(f"{base}/drafts/{r.json()['id']}/adopt")
    vid = (await logged_in_client.get(f"{base}/versions")).json()[0]["id"]

    res = await other_logged_in_client.post(f"{base}/versions/{vid}/rollback")
    assert res.status_code == 403


# ─── 五维健康 ──────────────────────────────────────────────────


async def test_five_dim_health_compute_and_override(logged_in_client):
    """节点健康计算（auto）→ 手动覆盖（manual）→ 批量重评估。"""
    pid = await _project(logged_in_client)
    base = _bm(pid)

    # L1 对象，payload 含部分关键字段
    res = await logged_in_client.post(
        f"{base}/objects",
        json={
            "level": "L1",
            "name": "带健康的L1",
            "payload": {
                "coreActivities": ["a"],
                "capabilityChain": "a→b",
                "itSystems": [],  # 空，不计入
                "organization": None,  # 空，不计入
            },
        },
    )
    oid = res.json()["id"]

    # 计算节点健康（auto）
    res = await logged_in_client.post(f"{base}/objects/{oid}/health")
    assert res.status_code == 200
    body = res.json()
    assert body["source"] == "auto"
    assert "L5_数字意识" in body["five_dim_health"]
    assert body["five_dim_health"]["L5_数字意识"]["score"] in (1, 2, 3, 4, 5)

    # 手动覆盖
    manual = {"L5_数字意识": {"score": 5, "desc": "手动满分"}}
    res = await logged_in_client.put(f"{base}/objects/{oid}/health", json=manual)
    assert res.status_code == 200
    assert res.json()["source"] == "manual"
    assert res.json()["five_dim_health"]["L5_数字意识"]["score"] == 5

    # 批量重评估（会重新覆盖为 auto）
    res = await logged_in_client.post(f"{base}/health/recompute")
    assert res.status_code == 200
    assert any(item["object_id"] == oid for item in res.json())


async def test_health_l4_not_supported(logged_in_client):
    """L4 节点不支持五维健康 → 400。"""
    pid = await _project(logged_in_client)
    base = _bm(pid)
    res = await logged_in_client.post(
        f"{base}/objects", json={"level": "L4", "name": "能力单元"}
    )
    oid = res.json()["id"]
    res = await logged_in_client.post(f"{base}/objects/{oid}/health")
    assert res.status_code == 400


# ─── 项目级隔离 ────────────────────────────────────────────────


async def test_business_map_isolation(logged_in_client, other_logged_in_client):
    """非项目成员不能访问业务地图 → 403。"""
    pid = await _project(logged_in_client)
    res = await other_logged_in_client.get(f"{_bm(pid)}/objects")
    assert res.status_code == 403


async def test_business_map_admin_bypass(admin_client, other_logged_in_client):
    """admin 可访问任意项目的业务地图。"""
    # bob 建项目
    cid = (await other_logged_in_client.post("/api/customers", json={"name": "c"})).json()["id"]
    pid = (
        await other_logged_in_client.post(
            "/api/projects", json={"customer_id": cid, "name": "p"}
        )
    ).json()["id"]
    res = await admin_client.get(f"{_bm(pid)}/objects")
    assert res.status_code == 200


# ─── 五维健康自动派生（M5.5.5）─────────────────────────────────
# 三条写入路径（create / adopt / update）自动派生 payload.fiveDimHealth。


def _score(obj, dim="L5_数字意识"):
    return obj["payload"]["fiveDimHealth"][dim]["score"]


async def test_create_object_auto_health(logged_in_client):
    """新建 L1 全字段 → payload.fiveDimHealth 自动派生（source=auto，4/4→5 分）。"""
    pid = await _project(logged_in_client)
    base = _bm(pid)
    res = await logged_in_client.post(
        f"{base}/objects",
        json={
            "level": "L1",
            "name": "全字段L1",
            "payload": {
                "coreActivities": ["a"],
                "capabilityChain": "a→b",
                "itSystems": "xxx",
                "organization": "yyy",
            },
        },
    )
    assert res.status_code == 201
    obj = res.json()
    assert "fiveDimHealth" in obj["payload"]
    assert obj["payload"]["_healthSource"] == "auto"
    assert _score(obj) == 5  # 4/4 关键字段完整


async def test_create_object_auto_health_partial(logged_in_client):
    """新建 L1 仅 2/4 字段 → score 3（验证按完整度映射，非恒满分）。"""
    pid = await _project(logged_in_client)
    base = _bm(pid)
    res = await logged_in_client.post(
        f"{base}/objects",
        json={
            "level": "L1",
            "name": "部分L1",
            "payload": {"coreActivities": ["a"], "capabilityChain": "a→b"},
        },
    )
    assert res.status_code == 201
    assert _score(res.json()) == 3  # 2/4 = 0.5 → 3


async def test_create_object_l4_no_auto_health(logged_in_client):
    """新建 L4 → 不派生 fiveDimHealth（L4 无健康维度）。"""
    pid = await _project(logged_in_client)
    base = _bm(pid)
    res = await logged_in_client.post(
        f"{base}/objects",
        json={"level": "L4", "name": "能力单元", "payload": {"capabilityUnitName": "x"}},
    )
    assert res.status_code == 201
    assert "fiveDimHealth" not in (res.json()["payload"] or {})


async def test_adopt_draft_auto_health(logged_in_client):
    """采纳草稿 → 产出的 L1/L2 对象自带 fiveDimHealth，且随版本快照落库。"""
    pid = await _project(logged_in_client)
    base = _bm(pid)
    res = await logged_in_client.put(
        f"{base}/drafts",
        json={
            "draft_data": {
                "objects": [
                    {
                        "level": "L1",
                        "name": "草稿L1",
                        "payload": {
                            "coreActivities": ["x"],
                            "capabilityChain": "y",
                            "itSystems": "z",
                            "organization": "w",
                        },
                    },
                    {"level": "L2", "name": "草稿L2"},
                ]
            }
        },
    )
    draft_id = res.json()["id"]
    res = await logged_in_client.post(f"{base}/drafts/{draft_id}/adopt")
    assert res.status_code == 200

    objs = {o["name"]: o for o in (await logged_in_client.get(f"{base}/objects")).json()}
    # L1 全字段 → 有自动健康 + 满分
    assert objs["草稿L1"]["payload"]["_healthSource"] == "auto"
    assert _score(objs["草稿L1"]) == 5
    # L2 无 payload → 仍派生健康（0 完整度 → 1 分）
    assert "fiveDimHealth" in objs["草稿L2"]["payload"]

    # 版本快照携带健康
    ver = (await logged_in_client.get(f"{base}/versions")).json()[0]
    l1_snap = next(s for s in ver["snapshot_data"]["objects"] if s["name"] == "草稿L1")
    assert "fiveDimHealth" in (l1_snap.get("payload") or {})


async def test_update_payload_recomputes_auto(logged_in_client):
    """payload 变更（auto 态）→ 基于新 payload 重算健康分。"""
    pid = await _project(logged_in_client)
    base = _bm(pid)
    # 初始 2/4 → score 3
    res = await logged_in_client.post(
        f"{base}/objects",
        json={
            "level": "L1",
            "name": "upd",
            "payload": {"coreActivities": ["a"], "capabilityChain": "b"},
        },
    )
    oid = res.json()["id"]
    assert _score(res.json()) == 3

    # 更新为全字段 → score 5
    res = await logged_in_client.put(
        f"{base}/objects/{oid}",
        json={
            "payload": {
                "coreActivities": ["a"],
                "capabilityChain": "b",
                "itSystems": "c",
                "organization": "d",
            }
        },
    )
    assert res.status_code == 200
    assert res.json()["payload"]["_healthSource"] == "auto"
    assert _score(res.json()) == 5


async def test_update_payload_preserves_manual_override(logged_in_client):
    """manual 覆盖后更新 payload → 保留人工评分（不重算覆盖）。"""
    pid = await _project(logged_in_client)
    base = _bm(pid)
    res = await logged_in_client.post(
        f"{base}/objects",
        json={"level": "L1", "name": "m", "payload": {"coreActivities": ["a"]}},
    )
    oid = res.json()["id"]

    # 手动覆盖为满分
    manual = {"L5_数字意识": {"score": 5, "desc": "人工"}}
    res = await logged_in_client.put(f"{base}/objects/{oid}/health", json=manual)
    assert res.json()["source"] == "manual"

    # 更新 payload（补全字段，按 auto 规则仍是 5，但应保留 manual 标记）
    res = await logged_in_client.put(
        f"{base}/objects/{oid}",
        json={
            "payload": {
                "coreActivities": ["a"],
                "capabilityChain": "b",
                "itSystems": "c",
                "organization": "d",
            }
        },
    )
    assert res.status_code == 200
    assert res.json()["payload"]["_healthSource"] == "manual"
    assert _score(res.json()) == 5


# ─── 草稿过期（M5.1.3，§7.1.6）──────────────────────────────────


async def test_adopt_rejects_expired_draft(logged_in_client, db_session):
    """超过 7 天的 active 草稿 → adopt 主动标记 expired 并拒绝（§7.1.6）。"""
    from datetime import datetime, timedelta, timezone

    from app.models import BusinessMapDraft

    pid = await _project(logged_in_client)
    base = _bm(pid)
    # 建草稿（默认 expires_at = now + 7d，未过期，status=active）
    res = await logged_in_client.put(
        f"{base}/drafts", json={"draft_data": {"objects": [{"level": "L1", "name": "X"}]}}
    )
    draft_id = res.json()["id"]
    assert res.json()["status"] == "active"

    # 模拟过期：把 expires_at 置于过去（status 仍 active，未被懒标记）
    draft = await db_session.get(BusinessMapDraft, draft_id)
    draft.expires_at = datetime.now(timezone.utc) - timedelta(days=1)
    await db_session.commit()

    # adopt 须拒绝：adopt 内 _mark_expired_drafts 标记 expired 后复验 status≠active → 400
    res = await logged_in_client.post(f"{base}/drafts/{draft_id}/adopt")
    assert res.status_code == 400

    # 该草稿已被 adopt 内部标记为 expired
    await db_session.refresh(draft)
    assert draft.status == "expired"


async def test_adopt_accepts_fresh_draft(logged_in_client):
    """新鲜草稿（expires_at 在未来）→ 正常采纳（回归保护，不被过期校验误伤）。"""
    pid = await _project(logged_in_client)
    base = _bm(pid)
    res = await logged_in_client.put(
        f"{base}/drafts", json={"draft_data": {"objects": [{"level": "L1", "name": "Y"}]}}
    )
    draft_id = res.json()["id"]
    # 默认 expires_at 约 7 天后，adopt 应成功
    assert res.json()["expires_at"] is not None
    res = await logged_in_client.post(f"{base}/drafts/{draft_id}/adopt")
    assert res.status_code == 200
    assert res.json()["success"] is True
