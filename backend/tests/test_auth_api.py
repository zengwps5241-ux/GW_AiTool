"""自建认证 API 测试。

V2.2 认证重构后，企微扫码登录已注释保留，认证体系切换为
自建注册登录（手机号/用户名+密码）+ 管理员审批。

本文件覆盖：
- 注册：成功 / 用户名冲突 / 手机号冲突 / 校验失败 / 默认 pending_approval
- 登录：成功（用户名/手机号）/ 密码错误 / 待审批拒绝 / 禁用拒绝 / 不存在用户
- 登出
- /me：返回扩展字段
- 管理员审批：列表 / 通过 / 驳回 / 状态校验 / 权限
"""

import pytest


# ─── 注册 ────────────────────────────────────────────────────


async def test_register_success(client):
    """自助注册成功，默认 status=pending_approval。"""
    res = await client.post(
        "/api/auth/register",
        json={"username": "newuser", "password": "pass1234", "display_name": "新用户"},
    )
    assert res.status_code == 201
    data = res.json()
    assert data["success"] is True
    assert "user_id" in data

    # 验证状态：待审批用户不能登录
    login = await client.post(
        "/api/auth/login",
        json={"login": "newuser", "password": "pass1234"},
    )
    assert login.status_code == 403


async def test_register_with_phone(client):
    """仅手机号注册：username 自动派生。"""
    res = await client.post(
        "/api/auth/register",
        json={"phone": "13800001111", "password": "pass1234"},
    )
    assert res.status_code == 201


async def test_register_missing_username_and_phone(client):
    """用户名和手机号都未提供应 400。"""
    res = await client.post(
        "/api/auth/register",
        json={"password": "pass1234"},
    )
    assert res.status_code == 400


async def test_register_short_password(client):
    """密码过短应 422（Pydantic 校验）。"""
    res = await client.post(
        "/api/auth/register",
        json={"username": "shortpw", "password": "123"},
    )
    assert res.status_code == 422


async def test_register_duplicate_username(client):
    """用户名重复应 409。"""
    await client.post(
        "/api/auth/register",
        json={"username": "dupuser", "password": "pass1234"},
    )
    res = await client.post(
        "/api/auth/register",
        json={"username": "dupuser", "password": "pass1234"},
    )
    assert res.status_code == 409


async def test_register_duplicate_phone(client):
    """手机号重复应 409。"""
    await client.post(
        "/api/auth/register",
        json={"phone": "13800002222", "password": "pass1234"},
    )
    res = await client.post(
        "/api/auth/register",
        json={"phone": "13800002222", "password": "pass1234"},
    )
    assert res.status_code == 409


# ─── 登录 ────────────────────────────────────────────────────


async def test_login_by_username(client):
    """管理员创建的 active 用户可凭用户名登录。"""
    # 复用 admin_client fixture 的创建逻辑太重，这里直接注册后审批
    await client.post(
        "/api/auth/register",
        json={"username": "loginuser", "password": "pass1234", "phone": "13800003333"},
    )
    # 直接在库中激活
    from app.db.session import async_session
    from app.models.user import User
    from sqlalchemy import select

    async with async_session() as db:
        result = await db.execute(select(User).where(User.username == "loginuser"))
        user = result.scalar_one()
        user.status = "active"
        await db.commit()

    res = await client.post(
        "/api/auth/login",
        json={"login": "loginuser", "password": "pass1234"},
    )
    assert res.status_code == 200
    assert res.json()["success"] is True

    # 登录后可访问 /api/me
    me = await client.get("/api/me")
    assert me.status_code == 200
    assert me.json()["username"] == "loginuser"


async def test_login_by_phone(client):
    """凭手机号登录。"""
    await client.post(
        "/api/auth/register",
        json={"username": "phoneuser", "password": "pass1234", "phone": "13800004444"},
    )
    from app.db.session import async_session
    from app.models.user import User
    from sqlalchemy import select

    async with async_session() as db:
        result = await db.execute(select(User).where(User.username == "phoneuser"))
        user = result.scalar_one()
        user.status = "active"
        await db.commit()

    res = await client.post(
        "/api/auth/login",
        json={"login": "13800004444", "password": "pass1234"},
    )
    assert res.status_code == 200


async def test_login_wrong_password(client):
    """密码错误应 401。"""
    await client.post(
        "/api/auth/register",
        json={"username": "wrongpw", "password": "pass1234", "phone": "13800005555"},
    )
    from app.db.session import async_session
    from app.models.user import User
    from sqlalchemy import select

    async with async_session() as db:
        result = await db.execute(select(User).where(User.username == "wrongpw"))
        user = result.scalar_one()
        user.status = "active"
        await db.commit()

    res = await client.post(
        "/api/auth/login",
        json={"login": "wrongpw", "password": "wrongpassword"},
    )
    assert res.status_code == 401


async def test_login_pending_approval_rejected(client):
    """待审批用户登录应 403。"""
    await client.post(
        "/api/auth/register",
        json={"username": "pendinguser", "password": "pass1234", "phone": "13800006666"},
    )
    res = await client.post(
        "/api/auth/login",
        json={"login": "pendinguser", "password": "pass1234"},
    )
    assert res.status_code == 403
    assert "审批" in res.json()["detail"]


async def test_login_disabled_rejected(client):
    """禁用用户登录应 403。"""
    await client.post(
        "/api/auth/register",
        json={"username": "disableduser", "password": "pass1234", "phone": "13800007777"},
    )
    from app.db.session import async_session
    from app.models.user import User
    from sqlalchemy import select

    async with async_session() as db:
        result = await db.execute(select(User).where(User.username == "disableduser"))
        user = result.scalar_one()
        user.status = "disabled"
        await db.commit()

    res = await client.post(
        "/api/auth/login",
        json={"login": "disableduser", "password": "pass1234"},
    )
    assert res.status_code == 403


async def test_login_nonexistent_user(client):
    """不存在的用户登录应 401。"""
    res = await client.post(
        "/api/auth/login",
        json={"login": "ghost", "password": "pass1234"},
    )
    assert res.status_code == 401


# ─── 登出 ────────────────────────────────────────────────────


async def test_logout(client):
    """登出后 session 清除，再访问受保护接口应 401。"""
    await client.post(
        "/api/auth/register",
        json={"username": "logoutuser", "password": "pass1234", "phone": "13800008888"},
    )
    from app.db.session import async_session
    from app.models.user import User
    from sqlalchemy import select

    async with async_session() as db:
        result = await db.execute(select(User).where(User.username == "logoutuser"))
        user = result.scalar_one()
        user.status = "active"
        await db.commit()

    await client.post(
        "/api/auth/login",
        json={"login": "logoutuser", "password": "pass1234"},
    )
    # 登录态可访问
    assert (await client.get("/api/me")).status_code == 200

    res = await client.post("/api/auth/logout")
    assert res.status_code == 204

    # 登出后 401
    assert (await client.get("/api/me")).status_code == 401


# ─── /me ────────────────────────────────────────────────────


async def test_me_returns_extended_fields(logged_in_client):
    """/api/me 应返回扩展字段。"""
    res = await logged_in_client.get("/api/me")
    assert res.status_code == 200
    data = res.json()
    assert data["username"] == "alice"
    assert data["auth_source"] == "local"
    assert "display_name" in data
    assert "phone" in data
    assert "status" in data
    assert "registration_source" in data


async def test_me_returns_role(logged_in_client):
    """/api/me 返回 role 字段，普通用户为 user。"""
    r = await logged_in_client.get("/api/me")
    assert r.status_code == 200
    data = r.json()
    assert data["role"] == "user"


async def test_me_unauthorized(client):
    """未登录访问 /api/me 应 401。"""
    res = await client.get("/api/me")
    assert res.status_code == 401


# ─── 管理员审批 ──────────────────────────────────────────────


async def test_admin_list_pending_users_empty(admin_client):
    """无待审批用户时返回空列表。"""
    res = await admin_client.get("/api/admin/pending-users")
    assert res.status_code == 200
    assert res.json() == []


async def test_admin_list_pending_users(admin_client, client):
    """注册用户后管理员可见待审批列表。"""
    await client.post(
        "/api/auth/register",
        json={"username": "waituser", "password": "pass1234", "phone": "13800009999"},
    )
    res = await admin_client.get("/api/admin/pending-users")
    assert res.status_code == 200
    data = res.json()
    assert len(data) == 1
    assert data[0]["username"] == "waituser"
    assert data[0]["status"] == "pending_approval"


async def test_admin_approve_user(admin_client, client):
    """管理员通过审批后用户变为 active，可登录。"""
    await client.post(
        "/api/auth/register",
        json={"username": "approveuser", "password": "pass1234", "phone": "13800010000"},
    )
    # 找到 user_id
    from app.db.session import async_session
    from app.models.user import User
    from sqlalchemy import select

    async with async_session() as db:
        result = await db.execute(select(User).where(User.username == "approveuser"))
        user = result.scalar_one()
        uid = user.id

    res = await admin_client.post(
        f"/api/admin/approve-user/{uid}",
        json={"action": "approve"},
    )
    assert res.status_code == 200
    assert res.json()["status"] == "active"

    # 用户现在可登录
    login = await client.post(
        "/api/auth/login",
        json={"login": "approveuser", "password": "pass1234"},
    )
    assert login.status_code == 200


async def test_admin_reject_user(admin_client, client):
    """管理员驳回后用户变为 disabled，不能登录。"""
    await client.post(
        "/api/auth/register",
        json={"username": "rejectuser", "password": "pass1234", "phone": "13800011111"},
    )
    from app.db.session import async_session
    from app.models.user import User
    from sqlalchemy import select

    async with async_session() as db:
        result = await db.execute(select(User).where(User.username == "rejectuser"))
        user = result.scalar_one()
        uid = user.id

    res = await admin_client.post(
        f"/api/admin/approve-user/{uid}",
        json={"action": "reject", "reason": "信息不符"},
    )
    assert res.status_code == 200
    assert res.json()["status"] == "disabled"

    login = await client.post(
        "/api/auth/login",
        json={"login": "rejectuser", "password": "pass1234"},
    )
    assert login.status_code == 403


async def test_admin_approve_nonexistent_user(admin_client):
    """审批不存在的用户应 404。"""
    res = await admin_client.post(
        "/api/admin/approve-user/99999",
        json={"action": "approve"},
    )
    assert res.status_code == 404


async def test_admin_approve_already_active(admin_client, client):
    """审批已是 active 的用户应 400。"""
    await client.post(
        "/api/auth/register",
        json={"username": "activeuser2", "password": "pass1234", "phone": "13800012222"},
    )
    from app.db.session import async_session
    from app.models.user import User
    from sqlalchemy import select

    async with async_session() as db:
        result = await db.execute(select(User).where(User.username == "activeuser2"))
        user = result.scalar_one()
        user.status = "active"
        await db.commit()
        uid = user.id

    res = await admin_client.post(
        f"/api/admin/approve-user/{uid}",
        json={"action": "approve"},
    )
    assert res.status_code == 400


async def test_pending_users_forbidden_for_user(logged_in_client):
    """普通用户不能访问待审批列表。"""
    res = await logged_in_client.get("/api/admin/pending-users")
    assert res.status_code == 403


async def test_pending_users_unauthorized(client):
    """未登录不能访问待审批列表。"""
    res = await client.get("/api/admin/pending-users")
    assert res.status_code == 401
