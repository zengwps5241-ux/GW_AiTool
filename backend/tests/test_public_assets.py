"""公开资产 / 对象公开机制 API 测试（M5.5.3，§2.6 / §5.x / §6.3）。

覆盖：
- GET /api/team-spaces/public-assets：跨项目聚合 is_public=1 的 reviewed 对象（草稿/私有排除）
- GET /api/team-spaces/shared-with-me：shared_with ∋ 当前用户 的 reviewed 对象（JSONB @>）
- GET /api/team-spaces/users/search：active 用户模糊搜索（「共享给」picker 数据源）

对象公开字段（is_public / shared_with）早已存在于 StakeholderCard / BusinessMapObject /
VisitRecord 三模型，create/update 已写入；本测试只验证「跨项目可见性聚合」新端点。

注意：app.models 必须在测试函数内晚导入（app_env reload 后），避免 collection 阶段绑定
旧 Base 导致 mapper 分裂（conftest reload 舞蹈，见 test_user fixture 同款）。
"""

from sqlalchemy import select


async def _project(client, name="公开资产测试项目"):
    """通过 API 建客户 + 项目（创建者自动成为项目成员）。"""
    cid = (await client.post("/api/customers", json={"name": "客户"})).json()["id"]
    return (await client.post("/api/projects", json={"customer_id": cid, "name": name})).json()["id"]


async def _user(db_session, username):
    from app.models import User

    return (
        await db_session.execute(select(User).where(User.username == username))
    ).scalar_one()


async def _seed_card(db_session, *, project_id, created_by, name, review_status="reviewed", is_public=False, shared_with=None):
    from app.models import StakeholderCard

    card = StakeholderCard(
        project_id=project_id,
        name=name,
        created_by=created_by,
        review_status=review_status,
        is_public=1 if is_public else 0,
        shared_with=shared_with,
    )
    db_session.add(card)
    await db_session.commit()
    await db_session.refresh(card)
    return card


# ─── 公开资产聚合 ──────────────────────────────────────────────


async def test_public_assets_lists_only_public_reviewed(logged_in_client, db_session):
    """is_public=1 且 reviewed 才进公开资产；草稿公开/私有 reviewed 不进。"""
    from app.models import BusinessMapObject, VisitRecord

    pid = await _project(logged_in_client)
    alice = await _user(db_session, "alice")

    await _seed_card(db_session, project_id=pid, created_by=alice.id, name="公开卡", is_public=True)
    await _seed_card(db_session, project_id=pid, created_by=alice.id, name="私有卡", is_public=False)
    await _seed_card(
        db_session, project_id=pid, created_by=alice.id,
        name="草稿公开卡", review_status="draft", is_public=True,
    )

    # 业务地图节点 + 拜访记录各一个公开 reviewed（验证跨类型聚合）
    db_session.add_all([
        BusinessMapObject(
            project_id=pid, level="L1", name="公开节点", map_type="hypothesis",
            created_by=alice.id, review_status="reviewed", is_public=1,
        ),
        VisitRecord(
            project_id=pid, visit_type="现场访谈", summary="公开拜访摘要",
            created_by=alice.id, review_status="reviewed", is_public=1,
        ),
    ])
    await db_session.commit()

    res = await logged_in_client.get("/api/team-spaces/public-assets")
    assert res.status_code == 200
    data = res.json()
    # 卡片：仅 1 张（公开 reviewed）；草稿公开 + 私有 reviewed 排除
    assert len(data["cards"]) == 1
    card_item = data["cards"][0]
    assert card_item["title"] == "公开卡"
    assert card_item["object_type"] == "card"
    assert card_item["project_name"] == "公开资产测试项目"
    assert card_item["created_by_name"] == "Alice"
    # 业务地图片段 + 拜访记录各 1
    assert len(data["business_objects"]) == 1
    assert data["business_objects"][0]["title"] == "公开节点"
    assert len(data["visits"]) == 1
    assert data["visits"][0]["title"] == "公开拜访摘要"


async def test_public_assets_empty_when_none_public(logged_in_client, db_session):
    """无公开对象时返回三组空数组（结构稳定，前端可安全渲染）。"""
    pid = await _project(logged_in_client)
    alice = await _user(db_session, "alice")
    await _seed_card(db_session, project_id=pid, created_by=alice.id, name="仅私有", is_public=False)

    res = await logged_in_client.get("/api/team-spaces/public-assets")
    assert res.status_code == 200
    data = res.json()
    assert data["cards"] == []
    assert data["business_objects"] == []
    assert data["visits"] == []


# ─── 共享给我（shared_with ∋ 当前用户）────────────────────────


async def test_shared_with_me_returns_only_shared(
    logged_in_client, other_logged_in_client, db_session,
):
    """shared_with ∋ bob 的 reviewed 卡才进 bob 的 shared-with-me；公开但未共享不进。"""
    pid = await _project(logged_in_client)
    alice = await _user(db_session, "alice")
    bob = await _user(db_session, "bob")

    await _seed_card(
        db_session, project_id=pid, created_by=alice.id,
        name="共享给bob", shared_with=[bob.id],
    )
    # 公开但未共享给 bob → 不在 bob 的 shared-with-me
    await _seed_card(
        db_session, project_id=pid, created_by=alice.id,
        name="公开但不给bob", is_public=True,
    )

    res = await other_logged_in_client.get("/api/team-spaces/shared-with-me")
    assert res.status_code == 200
    data = res.json()
    assert len(data["cards"]) == 1
    assert data["cards"][0]["title"] == "共享给bob"

    # alice 不在任何 shared_with 内 → 自己查 shared-with-me 为空
    res2 = await logged_in_client.get("/api/team-spaces/shared-with-me")
    assert len(res2.json()["cards"]) == 0


async def test_shared_with_me_excludes_draft(logged_in_client, other_logged_in_client, db_session):
    """草稿即便 shared_with 含我也不进（仅 reviewed 公开/共享，§7.3）。"""
    pid = await _project(logged_in_client)
    alice = await _user(db_session, "alice")
    bob = await _user(db_session, "bob")
    await _seed_card(
        db_session, project_id=pid, created_by=alice.id,
        name="草稿共享", review_status="draft", shared_with=[bob.id],
    )

    res = await other_logged_in_client.get("/api/team-spaces/shared-with-me")
    assert res.status_code == 200
    assert res.json()["cards"] == []


# ─── 用户搜索（「共享给」picker 数据源）──────────────────────


async def test_user_search_finds_active_users(logged_in_client, other_logged_in_client):
    """按姓名/用户名搜索 active 用户。"""
    # other_logged_in_client 已注册 bob（display_name=Bob）
    res = await logged_in_client.get("/api/team-spaces/users/search", params={"keyword": "Bob"})
    assert res.status_code == 200
    rows = res.json()
    assert any(r["username"] == "bob" for r in rows)
    assert any(r["display_name"] == "Bob" for r in rows)

    # 用户名子串也能命中
    res2 = await logged_in_client.get("/api/team-spaces/users/search", params={"keyword": "alic"})
    assert any(r["username"] == "alice" for r in res2.json())

    # 空关键字被拒（Query min_length=1 → 422）
    res3 = await logged_in_client.get("/api/team-spaces/users/search", params={"keyword": ""})
    assert res3.status_code == 422
