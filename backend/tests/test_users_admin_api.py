"""用户管理（管理端）API 测试。M6.4 用户管理增强。

覆盖验收：
- 权限（仅 admin/super，普通用户 403）
- GET /api/admin/users 全量列表 + 筛选（role/status/organization_id/search）+ last_login
- PUT /api/admin/users/{id}/status 启用/禁用（不可禁自己）
- POST /api/admin/users/{id}/reset-password 重置密码（新密码可登录）
- POST /api/admin/users 管理员创建用户（跳过审批 status=active，role 校验）
"""

import pytest


# ─── 辅助 ────────────────────────────────────────────────────


async def _users_list(admin_client) -> list[dict]:
    res = await admin_client.get("/api/admin/users")
    assert res.status_code == 200, res.text
    return res.json()


async def _find_user(users: list[dict], username: str) -> dict:
    return next(u for u in users if u["username"] == username)


async def _create_org_with_member(db_session, *, org_name: str, user_id: int) -> int:
    """DB 直建组织 + 用户-组织关联，返回 org_id。"""
    from app.models import Organization, UserOrganization

    org = Organization(name=org_name, type="department")
    db_session.add(org)
    await db_session.commit()
    await db_session.refresh(org)
    db_session.add(UserOrganization(organization_id=org.id, user_id=user_id))
    await db_session.commit()
    return org.id


# ─── 权限 ────────────────────────────────────────────────────


async def test_admin_users_forbidden_for_user(logged_in_client):
    res = await logged_in_client.get("/api/admin/users")
    assert res.status_code == 403


async def test_admin_users_allowed_for_admin(admin_client):
    res = await admin_client.get("/api/admin/users")
    assert res.status_code == 200


async def test_admin_users_allowed_for_super(super_client):
    res = await super_client.get("/api/admin/users")
    assert res.status_code == 200


# ─── 列表 ────────────────────────────────────────────────────


async def test_list_users_includes_self(admin_client):
    """admin_client 自己在列表中，且 last_login 已记录（fixture 登录触发）。"""
    users = await _users_list(admin_client)
    me = await _find_user(users, "admin_user")
    assert me["role"] == "admin"
    assert me["status"] == "active"
    assert me["last_login"] is not None  # M6.4 last_login


async def test_list_users_filter_role(admin_client, db_session):
    """按 role 筛选。"""
    from app.models import User

    db_session.add(User(username="role_filter_user", password_hash="x", role="user", status="active"))
    await db_session.commit()

    res = await admin_client.get("/api/admin/users?role=user")
    rows = res.json()
    assert len(rows) >= 1
    assert all(r["role"] == "user" for r in rows)
    # admin_user（role=admin）不在
    assert all(r["username"] != "admin_user" for r in rows)


async def test_list_users_filter_status(admin_client, db_session):
    """按 status 筛选。"""
    from app.models import User

    db_session.add(User(username="disabled_one", password_hash="x", status="disabled"))
    await db_session.commit()

    res = await admin_client.get("/api/admin/users?status=disabled")
    rows = res.json()
    assert len(rows) >= 1
    assert all(r["status"] == "disabled" for r in rows)


async def test_list_users_search(admin_client, db_session):
    """按 username 模糊搜索。"""
    from app.models import User

    db_session.add(User(username="zhang_searchable", password_hash="x", status="active"))
    await db_session.commit()

    res = await admin_client.get("/api/admin/users?search=zhang_search")
    rows = res.json()
    assert len(rows) == 1
    assert rows[0]["username"] == "zhang_searchable"


async def test_list_users_filter_organization(admin_client, db_session):
    """按 organization_id 筛选（只含该组织成员）。"""
    from app.models import User

    # 建一个用户 + 组织 + 关联
    u = User(username="org_member", password_hash="x", status="active")
    db_session.add(u)
    await db_session.commit()
    await db_session.refresh(u)
    org_id = await _create_org_with_member(db_session, org_name="测试部门", user_id=u.id)

    res = await admin_client.get(f"/api/admin/users?organization_id={org_id}")
    rows = res.json()
    assert len(rows) == 1
    assert rows[0]["username"] == "org_member"
    # 该用户 organizations 含此组织
    assert any(o["id"] == org_id for o in rows[0]["organizations"])


# ─── 管理员创建用户 ───────────────────────────────────────────


async def test_create_user_success(admin_client):
    """管理员创建用户：status=active，跳过审批。"""
    res = await admin_client.post(
        "/api/admin/users",
        json={"username": "new_user", "password": "pass1234", "role": "user",
              "display_name": "新用户"},
    )
    assert res.status_code == 201, res.text
    data = res.json()
    assert data["username"] == "new_user"
    assert data["status"] == "active"
    assert data["role"] == "user"
    assert data["registration_source"] == "admin_create"


async def test_create_user_login(client, admin_client):
    """创建的用户能立即用密码登录（跳过审批）。"""
    await admin_client.post(
        "/api/admin/users",
        json={"username": "loginable", "password": "pass1234"},
    )
    res = await client.post(
        "/api/auth/login", json={"login": "loginable", "password": "pass1234"}
    )
    assert res.status_code == 200
    assert res.json()["success"] is True


async def test_create_user_duplicate_username(admin_client):
    """重复 username → 400。"""
    await admin_client.post(
        "/api/admin/users", json={"username": "dup", "password": "pass1234"}
    )
    res = await admin_client.post(
        "/api/admin/users", json={"username": "dup", "password": "pass1234"}
    )
    assert res.status_code == 400


async def test_create_user_invalid_role(admin_client):
    """role 不存在 → 400。"""
    res = await admin_client.post(
        "/api/admin/users",
        json={"username": "bad_role", "password": "pass1234", "role": "no_such_role"},
    )
    assert res.status_code == 400


# ─── 用户状态管理 ─────────────────────────────────────────────


async def test_update_status_disable_then_enable(admin_client, db_session):
    """禁用某用户 → disabled，再启用 → active。"""
    from app.models import User

    u = User(username="status_target", password_hash="x", status="active")
    db_session.add(u)
    await db_session.commit()
    await db_session.refresh(u)
    uid = u.id

    res = await admin_client.put(
        f"/api/admin/users/{uid}/status", json={"status": "disabled"}
    )
    assert res.status_code == 200
    await db_session.refresh(u)
    assert u.status == "disabled"

    res2 = await admin_client.put(
        f"/api/admin/users/{uid}/status", json={"status": "active"}
    )
    assert res2.status_code == 200
    await db_session.refresh(u)
    assert u.status == "active"


async def test_cannot_disable_self(admin_client):
    """不可禁用自己的账号 → 400。"""
    users = await _users_list(admin_client)
    me = await _find_user(users, "admin_user")
    res = await admin_client.put(
        f"/api/admin/users/{me['id']}/status", json={"status": "disabled"}
    )
    assert res.status_code == 400


async def test_update_status_user_not_found(admin_client):
    res = await admin_client.put(
        "/api/admin/users/99999/status", json={"status": "disabled"}
    )
    assert res.status_code == 404


async def test_disabled_user_cannot_login(client, admin_client, db_session):
    """被禁用的用户不能登录。"""
    await admin_client.post(
        "/api/admin/users", json={"username": "will_disable", "password": "pass1234"}
    )
    users = await _users_list(admin_client)
    uid = (await _find_user(users, "will_disable"))["id"]
    await admin_client.put(f"/api/admin/users/{uid}/status", json={"status": "disabled"})

    res = await client.post(
        "/api/auth/login", json={"login": "will_disable", "password": "pass1234"}
    )
    assert res.status_code == 403  # 账号已被禁用


# ─── 重置密码 ────────────────────────────────────────────────


async def test_reset_password(client, admin_client):
    """重置密码后，新密码可登录，旧密码失败。"""
    await admin_client.post(
        "/api/admin/users", json={"username": "pwd_target", "password": "old123456"}
    )
    users = await _users_list(admin_client)
    uid = (await _find_user(users, "pwd_target"))["id"]

    res = await admin_client.post(
        f"/api/admin/users/{uid}/reset-password", json={"new_password": "new123456"}
    )
    assert res.status_code == 200

    # 旧密码失败
    res_old = await client.post(
        "/api/auth/login", json={"login": "pwd_target", "password": "old123456"}
    )
    assert res_old.status_code == 401
    # 新密码成功
    res_new = await client.post(
        "/api/auth/login", json={"login": "pwd_target", "password": "new123456"}
    )
    assert res_new.status_code == 200


async def test_reset_password_user_not_found(admin_client):
    res = await admin_client.post(
        "/api/admin/users/99999/reset-password", json={"new_password": "new123456"}
    )
    assert res.status_code == 404
