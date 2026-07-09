"""拜访记录 API 测试（M2.3）。

覆盖：
- 拜访记录 CRUD + 时间倒序 + 按类型/角色筛选
- 证据 CRUD + 多维筛选（类型/强度/角色/假设）
- 派生统计（evidenceCount / verifiedHypotheses）
- §7.5 证据验证联动：建议验证状态（按强度计数）→ 人工确认 → 更新 verificationStatus + 推翻自动入偏差池
- §7.6 态度变化自动记录：角色态度信号类证据 → 自动追加 stanceChangeLog + 联动主观层 stance
- 项目级隔离（非成员 403）
"""

import pytest


# ─── 辅助 ──────────────────────────────────────────────────────


async def _project(client, name="拜访项目"):
    cid = (await client.post("/api/customers", json={"name": "客户"})).json()["id"]
    return (await client.post("/api/projects", json={"customer_id": cid, "name": name})).json()["id"]


def _base(pid: int) -> str:
    return f"/api/projects/{pid}"


async def _visit(client, pid, **overrides):
    body = {
        "visit_date": "2026-07-05",
        "visit_type": "现场访谈",
        "summary": "首次拜访",
        "next_steps": "发送方案",
        "participants_our": ["张顾问"],
        "key_takeaways": ["客户关注成本"],
    }
    body.update(overrides)
    return (await client.post(f"{_base(pid)}/visit-records", json=body)).json()


async def _card(client, pid, name="王主任"):
    return (
        await client.post(
            f"{_base(pid)}/stakeholder-cards",
            json={
                "name": name,
                "department": "信息部",
                "role_type": "economic_decision_maker",
                "subjective_layer": {"stance": "中立", "engagement": 5, "influence": 5, "support": 5},
            },
        )
    ).json()


async def _hypothesis(client, pid, name="降本假设"):
    return (
        await client.post(
            f"{_base(pid)}/business-map/objects",
            json={"level": "L2", "name": name, "map_type": "hypothesis"},
        )
    ).json()


async def _evidence(client, pid, visit_id, **overrides):
    body = {
        "visit_record_id": visit_id,
        "evidence_type": "客户原话",
        "strength": "强",
        "content": "客户说：成本太高了",
    }
    body.update(overrides)
    return (await client.post(f"{_base(pid)}/evidence-sources", json=body)).json()


# ─── 拜访记录 CRUD + 时间倒序 + 筛选 ──────────────────────────


async def test_visit_crud_and_timeline(logged_in_client):
    pid = await _project(logged_in_client)
    base = _base(pid)

    v1 = await _visit(logged_in_client, pid, visit_date="2026-07-01")
    v2 = await _visit(logged_in_client, pid, visit_date="2026-07-10")
    # 一句话记录（无日期）应排最后
    v3 = await _visit(logged_in_client, pid, visit_type="一句话记录", visit_date=None, summary="快速记录")

    # 默认列表（reviewed）含 3 条
    visits = (await logged_in_client.get(f"{base}/visit-records")).json()
    assert len(visits) == 3
    # 时间倒序：v2(07-10) → v1(07-01) → v3(无日期)
    assert visits[0]["id"] == v2["id"]
    assert visits[1]["id"] == v1["id"]
    assert visits[2]["id"] == v3["id"]

    # 按类型筛选
    typed = (await logged_in_client.get(f"{base}/visit-records?visit_type=现场访谈")).json()
    assert {v["id"] for v in typed} == {v1["id"], v2["id"]}

    # 更新 + 删除
    res = await logged_in_client.put(f"{base}/visit-records/{v1['id']}", json={"summary": "更新摘要"})
    assert res.status_code == 200
    assert res.json()["summary"] == "更新摘要"
    assert (await logged_in_client.delete(f"{base}/visit-records/{v1['id']}")).status_code == 204
    assert len((await logged_in_client.get(f"{base}/visit-records")).json()) == 2


async def test_visit_filter_by_card(logged_in_client):
    """按参与/关联角色卡筛选拜访（JSONB @> 数组包含）。"""
    pid = await _project(logged_in_client)
    base = _base(pid)
    card = await _card(logged_in_client, pid)

    await _visit(logged_in_client, pid, participants_client=[card["id"]])
    await _visit(logged_in_client, pid, related_card_ids=[card["id"]], visit_date="2026-07-08")
    await _visit(logged_in_client, pid, visit_date="2026-07-09")  # 不含该角色卡

    hits = (await logged_in_client.get(f"{base}/visit-records?card_id={card['id']}")).json()
    assert len(hits) == 2


# ─── 证据 CRUD + 多维筛选 + 派生统计 ──────────────────────────


async def test_evidence_crud_filter_and_stats(logged_in_client):
    pid = await _project(logged_in_client)
    base = _base(pid)
    v = await _visit(logged_in_client, pid)
    card = await _card(logged_in_client, pid)
    hyp = await _hypothesis(logged_in_client, pid)

    e1 = await _evidence(
        logged_in_client, pid, v["id"], evidence_type="客户原话", strength="强",
        source_role_id=card["id"], related_hypothesis_id=hyp["id"],
    )
    await _evidence(
        logged_in_client, pid, v["id"], evidence_type="行为观察", strength="弱",
    )

    # 拜访的派生统计：2 条证据，1 个关联假设
    got = (await logged_in_client.get(f"{base}/visit-records/{v['id']}")).json()
    assert got["evidence_count"] == 2
    assert got["verified_hypotheses"] == 1

    # 多维筛选：按类型
    by_type = (await logged_in_client.get(f"{base}/evidence-sources?evidence_type=客户原话")).json()
    assert [e["id"] for e in by_type] == [e1["id"]]
    # 按强度
    assert len((await logged_in_client.get(f"{base}/evidence-sources?strength=弱")).json()) == 1
    # 按角色
    by_role = (await logged_in_client.get(f"{base}/evidence-sources?source_role_id={card['id']}")).json()
    assert [e["id"] for e in by_role] == [e1["id"]]
    # 按假设
    by_hyp = (await logged_in_client.get(f"{base}/evidence-sources?related_hypothesis_id={hyp['id']}")).json()
    assert [e["id"] for e in by_hyp] == [e1["id"]]
    # 按拜访
    by_visit = (await logged_in_client.get(f"{base}/evidence-sources?visit_id={v['id']}")).json()
    assert len(by_visit) == 2

    # 删除证据后统计归零回落
    await logged_in_client.delete(f"{base}/evidence-sources/{e1['id']}")
    got = (await logged_in_client.get(f"{base}/visit-records/{v['id']}")).json()
    assert got["evidence_count"] == 1
    assert got["verified_hypotheses"] == 0  # 剩余的弱证据未关联假设


# ─── §7.5 证据验证联动 ────────────────────────────────────────


async def test_verification_suggestion_strength_rules(logged_in_client):
    """§7.5.1：按证据强度计数给建议验证状态。"""
    pid = await _project(logged_in_client)
    base = _base(pid)
    v = await _visit(logged_in_client, pid)
    hyp = await _hypothesis(logged_in_client, pid)

    # 0 条 → 未验证
    s = (await logged_in_client.get(f"{base}/evidence-sources/hypotheses/{hyp['id']}/suggestion")).json()
    assert s["suggested_status"] == "未验证"
    assert s["total_count"] == 0

    # 1 强 → 部分成立
    await _evidence(logged_in_client, pid, v["id"], related_hypothesis_id=hyp["id"], strength="强")
    s = (await logged_in_client.get(f"{base}/evidence-sources/hypotheses/{hyp['id']}/suggestion")).json()
    assert s["suggested_status"] == "部分成立"
    assert s["strong_count"] == 1

    # 累计 3 强 → 成立
    await _evidence(logged_in_client, pid, v["id"], related_hypothesis_id=hyp["id"], strength="强", content="证据2")
    await _evidence(logged_in_client, pid, v["id"], related_hypothesis_id=hyp["id"], strength="强", content="证据3")
    s = (await logged_in_client.get(f"{base}/evidence-sources/hypotheses/{hyp['id']}/suggestion")).json()
    assert s["suggested_status"] == "成立"
    assert s["strong_count"] == 3

    # 仅弱 → 待补充（另起一个假设）
    hyp2 = await _hypothesis(logged_in_client, pid, name="弱证据假设")
    await _evidence(logged_in_client, pid, v["id"], related_hypothesis_id=hyp2["id"], strength="弱")
    s = (await logged_in_client.get(f"{base}/evidence-sources/hypotheses/{hyp2['id']}/suggestion")).json()
    assert s["suggested_status"] == "待补充"


async def test_verification_confirm_updates_status_and_deviation_pool(logged_in_client):
    """§7.5.2/§7.5.3：确认验证状态 → 更新 verificationStatus；推翻自动入偏差池。"""
    pid = await _project(logged_in_client)
    base = _base(pid)
    v = await _visit(logged_in_client, pid)
    hyp = await _hypothesis(logged_in_client, pid, name="待推翻假设")
    await _evidence(logged_in_client, pid, v["id"], related_hypothesis_id=hyp["id"], strength="强")

    # 采纳建议（部分成立）
    res = await logged_in_client.post(
        f"{base}/evidence-sources/hypotheses/{hyp['id']}/confirm", json={}
    )
    assert res.status_code == 200
    body = res.json()
    assert body["verification_status"] == "部分成立"
    assert body["deviation_created"] is False

    # 假设节点 verificationStatus 已更新
    obj = (await logged_in_client.get(f"{base}/business-map/objects/{hyp['id']}")).json()
    assert obj["verification_status"] == "部分成立"

    # 顾问判断推翻 → 自动新增偏差池条目（current 节点）
    res = await logged_in_client.post(
        f"{base}/evidence-sources/hypotheses/{hyp['id']}/confirm", json={"status": "推翻"}
    )
    body = res.json()
    assert body["verification_status"] == "推翻"
    assert body["deviation_created"] is True
    dev_id = body["deviation_object_id"]
    assert dev_id is not None

    # 偏差池：current + 推翻 + linked_hypothesis_id
    currents = (await logged_in_client.get(f"{base}/business-map/objects?map_type=current")).json()
    devs = [c for c in currents if c["verification_status"] == "推翻" and c["linked_hypothesis_id"] == hyp["id"]]
    assert len(devs) == 1
    assert devs[0]["id"] == dev_id

    # 再次推翻不重复创建
    res = await logged_in_client.post(
        f"{base}/evidence-sources/hypotheses/{hyp['id']}/confirm", json={"status": "推翻"}
    )
    assert res.json()["deviation_created"] is False
    currents = (await logged_in_client.get(f"{base}/business-map/objects?map_type=current")).json()
    assert len([c for c in currents if c["linked_hypothesis_id"] == hyp["id"]]) == 1


# ─── §7.6 态度变化自动记录 ────────────────────────────────────


async def test_evidence_auto_stance_change(logged_in_client):
    """角色态度信号类证据关联角色卡 + 携带立场 → 自动追加 stanceChangeLog + 联动 stance。"""
    pid = await _project(logged_in_client)
    base = _base(pid)
    v = await _visit(logged_in_client, pid)
    card = await _card(logged_in_client, pid)  # 主观层 stance=中立

    res = await logged_in_client.post(
        f"{base}/evidence-sources",
        json={
            "visit_record_id": v["id"],
            "evidence_type": "角色态度信号",
            "strength": "中",
            "content": "王主任主动提出帮我们推动立项",
            "source_role_id": card["id"],
            "source_role_name": card["name"],
            "implied_from_stance": "中立",
            "implied_to_stance": "支持",
        },
    )
    assert res.status_code == 201

    # 角色卡 stanceChangeLog 自动追加一条，主观层 stance 联动为「支持」
    c = (await logged_in_client.get(f"{base}/stakeholder-cards/{card['id']}")).json()
    log = c["stance_change_log"]
    assert len(log) == 1
    assert log[0]["from"] == "中立"
    assert log[0]["to"] == "支持"
    assert log[0]["reason"] == "王主任主动提出帮我们推动立项"
    assert c["subjective_layer"]["stance"] == "支持"


async def test_evidence_no_stance_change_when_not_signal(logged_in_client):
    """非角色态度信号类证据（如客户原话）即便关联角色卡也不触发态度变化。"""
    pid = await _project(logged_in_client)
    base = _base(pid)
    v = await _visit(logged_in_client, pid)
    card = await _card(logged_in_client, pid)

    await _evidence(
        logged_in_client, pid, v["id"],
        evidence_type="客户原话", strength="强",
        source_role_id=card["id"],
        implied_from_stance="中立", implied_to_stance="支持",
    )
    c = (await logged_in_client.get(f"{base}/stakeholder-cards/{card['id']}")).json()
    assert c["stance_change_log"] in (None, [])


# ─── 项目级隔离 ────────────────────────────────────────────────


async def test_visit_isolation(logged_in_client, other_logged_in_client):
    """非项目成员访问拜访记录 → 403。"""
    pid = await _project(logged_in_client)
    res = await other_logged_in_client.get(f"{_base(pid)}/visit-records")
    assert res.status_code == 403


async def test_evidence_cross_project_link_rejected(logged_in_client):
    """证据关联的拜访/角色卡/假设必须属本项目，跨项目 → 400。"""
    pid = await _project(logged_in_client)
    base = _base(pid)
    # 另一个项目的拜访
    pid2 = await _project(logged_in_client, name="另一个项目")
    v2 = await _visit(logged_in_client, pid2)

    res = await logged_in_client.post(
        f"{base}/evidence-sources",
        json={"visit_record_id": v2["id"], "evidence_type": "客户原话", "strength": "强", "content": "x"},
    )
    assert res.status_code == 400
