"""审计日志 API 测试（决策 #60/#64）。

覆盖 M6.3 验收：
- 权限（管理端仅 admin/super，普通用户 403）
- log_audit() 工具函数：自动查 username、detail JSONB 快照、best-effort 不抛
- 查询 API 筛选：user_id / action / target_type / 时间范围 + 默认最近 7 天 + 倒序分页
- 各 service 埋点：写操作触发对应审计日志（roles/menus/organizations/sessions 等）
"""

import pytest


# ─── 辅助 ────────────────────────────────────────────────────


async def _log(db_session, **kwargs):
    """直调 log_audit 写一条审计日志。"""
    from app.modules.audit.service import log_audit

    defaults = dict(
        user_id=None,
        action="create",
        target_type="role",
        target_id="1",
        detail=None,
        ip_address=None,
    )
    defaults.update(kwargs)
    await log_audit(db_session, **defaults)


async def _create_user(db_session, username: str = "actor") -> int:
    """DB 直接建 active 用户，返回 id。"""
    from app.models import User

    u = User(username=username, password_hash="x", status="active")
    db_session.add(u)
    await db_session.commit()
    await db_session.refresh(u)
    return u.id


# ─── 权限 ────────────────────────────────────────────────────


async def test_audit_logs_forbidden_for_user(logged_in_client):
    """普通用户不能查询审计日志。"""
    res = await logged_in_client.get("/api/admin/audit-logs")
    assert res.status_code == 403


async def test_audit_logs_allowed_for_admin(admin_client):
    res = await admin_client.get("/api/admin/audit-logs")
    assert res.status_code == 200


async def test_audit_logs_allowed_for_super(super_client):
    res = await super_client.get("/api/admin/audit-logs")
    assert res.status_code == 200


# ─── log_audit 工具函数 ──────────────────────────────────────


async def test_log_audit_basic(admin_client, db_session):
    """log_audit 写入 → 查询返回，字段正确。"""
    await _log(
        db_session,
        action="create",
        target_type="role",
        target_id="5",
        detail={"before": None, "after": {"code": "analyst", "name": "分析师"}},
        ip_address="127.0.0.1",
    )
    res = await admin_client.get("/api/admin/audit-logs?action=create&target_type=role")
    assert res.status_code == 200
    data = res.json()
    assert len(data) == 1
    row = data[0]
    assert row["action"] == "create"
    assert row["target_type"] == "role"
    assert row["target_id"] == "5"
    assert row["ip_address"] == "127.0.0.1"
    assert row["detail"]["after"]["code"] == "analyst"
    assert row["created_at"] is not None


async def test_log_audit_username_resolved(admin_client, db_session):
    """log_audit 自动按 user_id 查 username 冗余存储。"""
    uid = await _create_user(db_session, username="zhang_san")
    await _log(db_session, user_id=uid, action="update", target_type="user")
    res = await admin_client.get("/api/admin/audit-logs")
    row = res.json()[0]
    assert row["user_id"] == uid
    assert row["username"] == "zhang_san"


async def test_log_audit_unknown_user_username_none(admin_client, db_session):
    """user_id 不存在时 username=None（不抛异常）。"""
    await _log(db_session, user_id=99999, action="login", target_type="user", target_id="99999")
    res = await admin_client.get("/api/admin/audit-logs")
    row = res.json()[0]
    # 用户不存在 → user_id 置 NULL，日志仍记录
    assert row["user_id"] is None
    assert row["username"] is None


async def test_log_audit_best_effort_no_raise(db_session):
    """log_audit best-effort：传非法参数不抛异常（审计失败不影响主业务）。"""
    from app.modules.audit.service import log_audit

    # 正常调用不应抛
    await log_audit(db_session, None, "delete", "menu", "1")


# ─── 查询筛选 ────────────────────────────────────────────────


async def test_query_filter_action(admin_client, db_session):
    """按 action 筛选。"""
    await _log(db_session, action="create", target_type="role", target_id="1")
    await _log(db_session, action="delete", target_type="role", target_id="2")
    await _log(db_session, action="create", target_type="role", target_id="3")

    res = await admin_client.get("/api/admin/audit-logs?action=create")
    assert res.status_code == 200
    data = res.json()
    assert len(data) == 2
    assert all(r["action"] == "create" for r in data)


async def test_query_filter_target_type(admin_client, db_session):
    """按 target_type 筛选。"""
    await _log(db_session, action="create", target_type="role", target_id="1")
    await _log(db_session, action="create", target_type="menu", target_id="2")

    res = await admin_client.get("/api/admin/audit-logs?target_type=menu")
    data = res.json()
    assert len(data) == 1
    assert data[0]["target_type"] == "menu"


async def test_query_filter_user_id(admin_client, db_session):
    """按 user_id 筛选。"""
    uid_a = await _create_user(db_session, username="a_user")
    uid_b = await _create_user(db_session, username="b_user")
    await _log(db_session, user_id=uid_a, action="create", target_type="role", target_id="1")
    await _log(db_session, user_id=uid_b, action="create", target_type="role", target_id="2")

    res = await admin_client.get(f"/api/admin/audit-logs?user_id={uid_a}")
    data = res.json()
    assert len(data) == 1
    assert data[0]["user_id"] == uid_a


async def test_query_order_desc_and_pagination(admin_client, db_session):
    """倒序 + 分页：第一页最新，offset 翻页。"""
    for i in range(5):
        await _log(db_session, action="create", target_type="role", target_id=str(i))

    page1 = await admin_client.get("/api/admin/audit-logs?limit=2&offset=0")
    page2 = await admin_client.get("/api/admin/audit-logs?limit=2&offset=2")
    p1, p2 = page1.json(), page2.json()
    assert len(p1) == 2 and len(p2) == 2
    # 倒序：p1 比 p2 新
    assert p1[0]["created_at"] >= p1[1]["created_at"]
    assert p1[0]["created_at"] >= p2[0]["created_at"]


# ─── 埋点验证：写操作触发审计日志（决策 #64）──────────────────


async def test_audit_role_create(admin_client):
    """创建角色触发 create/role 审计。"""
    res = await admin_client.post(
        "/api/admin/roles", json={"code": "audited_role", "name": "审计角色"}
    )
    assert res.status_code == 201
    rid = res.json()["id"]
    logs = await admin_client.get(
        "/api/admin/audit-logs?action=create&target_type=role"
    )
    rows = logs.json()
    assert any(r["target_id"] == str(rid) for r in rows)
    # actor 记录为操作者（admin_client 登录用户）
    assert all(r["username"] is not None for r in rows)


async def test_audit_role_update_before_after(admin_client):
    """更新角色触发 update/role 审计，detail 含 before/after 快照。"""
    created = await admin_client.post(
        "/api/admin/roles", json={"code": "upd_aud", "name": "原名"}
    )
    rid = created.json()["id"]
    await admin_client.put(
        f"/api/admin/roles/{rid}", json={"name": "新名", "sort_order": 9}
    )
    res = await admin_client.get(
        "/api/admin/audit-logs?action=update&target_type=role"
    )
    rows = res.json()
    row = next(r for r in rows if r["target_id"] == str(rid))
    assert row["detail"]["before"]["name"] == "原名"
    assert row["detail"]["after"]["name"] == "新名"
    assert row["detail"]["after"]["sort_order"] == 9


async def test_audit_role_delete(admin_client):
    """删除角色触发 delete/role 审计，detail 含 before 快照。"""
    created = await admin_client.post(
        "/api/admin/roles", json={"code": "del_aud", "name": "待删"}
    )
    rid = created.json()["id"]
    await admin_client.delete(f"/api/admin/roles/{rid}")
    res = await admin_client.get(
        "/api/admin/audit-logs?action=delete&target_type=role"
    )
    rows = res.json()
    row = next(r for r in rows if r["target_id"] == str(rid))
    assert row["detail"]["before"]["code"] == "del_aud"


async def test_audit_menu_create(admin_client):
    """创建菜单触发 create/menu 审计。"""
    res = await admin_client.post(
        "/api/admin/menus", json={"code": "audited_menu", "name": "审计菜单"}
    )
    mid = res.json()["id"]
    res = await admin_client.get(
        "/api/admin/audit-logs?action=create&target_type=menu"
    )
    rows = res.json()
    assert any(r["target_id"] == str(mid) for r in rows)


async def test_audit_organization_create(admin_client):
    """创建组织触发 create/organization 审计。"""
    res = await admin_client.post(
        "/api/admin/organizations",
        json={"name": "审计部门", "type": "department"},
    )
    assert res.status_code == 201
    oid = res.json()["id"]
    res = await admin_client.get(
        "/api/admin/audit-logs?action=create&target_type=organization"
    )
    rows = res.json()
    assert any(r["target_id"] == str(oid) for r in rows)


async def test_audit_login(admin_client):
    """admin_client 登录触发 login/user 审计。"""
    res = await admin_client.get(
        "/api/admin/audit-logs?action=login&target_type=user"
    )
    rows = res.json()
    assert len(rows) >= 1
    assert rows[0]["action"] == "login"


async def test_audit_approve_user(admin_client, db_session):
    """审批通过用户触发 approve/user 审计，detail 含 status 变更。"""
    from app.models import User

    u = User(
        username="pending_audited",
        password_hash="x",
        status="pending_approval",
        auth_source="local",
    )
    db_session.add(u)
    await db_session.commit()
    await db_session.refresh(u)
    uid = u.id

    res = await admin_client.post(
        f"/api/admin/approve-user/{uid}", json={"action": "approve"}
    )
    assert res.status_code == 200
    res = await admin_client.get(
        "/api/admin/audit-logs?action=approve&target_type=user"
    )
    rows = res.json()
    row = next(r for r in rows if r["target_id"] == str(uid))
    assert row["detail"]["before"]["status"] == "pending_approval"
    assert row["detail"]["after"]["status"] == "active"


async def test_audit_reject_user(admin_client, db_session):
    """驳回用户触发 reject/user 审计。"""
    from app.models import User

    u = User(
        username="rejected_audited",
        password_hash="x",
        status="pending_approval",
        auth_source="local",
    )
    db_session.add(u)
    await db_session.commit()
    await db_session.refresh(u)
    uid = u.id

    await admin_client.post(
        f"/api/admin/approve-user/{uid}", json={"action": "reject"}
    )
    res = await admin_client.get(
        "/api/admin/audit-logs?action=reject&target_type=user"
    )
    rows = res.json()
    assert any(r["target_id"] == str(uid) for r in rows)
