"""角色管理 API 测试（方案 A：角色 + 菜单可见性关联）。

覆盖 M6.1 验收：
- 权限（仅 admin/super；普通用户 403）
- 内置角色种子（user/admin/super，is_system=True）
- role_menus 种子关联（super→16 / admin→15 / user→10）
- 角色 CRUD（创建/查询/更新/删除；系统角色不可删；code 唯一）
- 角色-菜单关联（GET/PUT；super 不可改；非法 menu_id 拒绝）
- 用户角色分配（更新 User.role；角色/用户不存在处理）
"""

import pytest


# ─── 辅助 ────────────────────────────────────────────────────


async def _roles_map(admin_client) -> dict[str, dict]:
    """返回 {code: role_dict}，便于按 code 取 id。"""
    res = await admin_client.get("/api/admin/roles")
    assert res.status_code == 200
    return {r["code"]: r for r in res.json()}


async def _menu_codes_to_ids(db_session) -> dict[str, int]:
    """直接查 DB 取 menu code→id（M6.1 尚无菜单列表 API）。"""
    from sqlalchemy import select

    from app.models import Menu

    result = await db_session.execute(select(Menu))
    return {m.code: m.id for m in result.scalars().all()}


async def _create_user(db_session, username: str = "target_user") -> int:
    """在 DB 直接建一个 active 用户，返回 id（供角色分配测试）。"""
    from app.models import User

    u = User(username=username, password_hash="x", status="active")
    db_session.add(u)
    await db_session.commit()
    await db_session.refresh(u)
    return u.id


# ─── 权限 ────────────────────────────────────────────────────


async def test_roles_forbidden_for_user(logged_in_client):
    """普通用户不能访问角色管理接口。"""
    res = await logged_in_client.get("/api/admin/roles")
    assert res.status_code == 403


async def test_roles_allowed_for_admin(admin_client):
    """admin 可以访问角色管理接口。"""
    res = await admin_client.get("/api/admin/roles")
    assert res.status_code == 200


async def test_roles_allowed_for_super(super_client):
    """super 可以访问角色管理接口。"""
    res = await super_client.get("/api/admin/roles")
    assert res.status_code == 200


# ─── 内置角色种子 ────────────────────────────────────────────


async def test_seed_builtin_roles(admin_client):
    """种子：3 个内置角色 user/admin/super，均 is_system=True。"""
    roles = await _roles_map(admin_client)
    assert set(roles.keys()) >= {"user", "admin", "super"}
    for code in ("user", "admin", "super"):
        assert roles[code]["is_system"] is True, f"{code} 应为系统角色"
        assert roles[code]["id"] > 0


# ─── role_menus 种子关联 ─────────────────────────────────────


async def test_seed_role_menus_super_all(admin_client):
    """super 角色关联全部菜单（16 条）。"""
    roles = await _roles_map(admin_client)
    res = await admin_client.get(f"/api/admin/roles/{roles['super']['id']}/menus")
    assert res.status_code == 200
    ids = res.json()
    # 16 = 4 分组 + 12 叶子
    assert len(ids) == 16, f"super 应关联全部 16 个菜单，实际 {len(ids)}"


async def test_seed_role_menus_admin_excludes_login_whitelist(
    admin_client, db_session
):
    """admin 关联除 loginWhitelist 外的全部菜单（15 条）。"""
    roles = await _roles_map(admin_client)
    res = await admin_client.get(f"/api/admin/roles/{roles['admin']['id']}/menus")
    assert res.status_code == 200
    admin_ids = set(res.json())
    assert len(admin_ids) == 15

    # loginWhitelist 不在 admin 关联中
    code_to_id = await _menu_codes_to_ids(db_session)
    assert code_to_id["loginWhitelist"] not in admin_ids


async def test_seed_role_menus_user_minimal(admin_client, db_session):
    """user 关联：作战台4 + 文件2 + 智能体管理 + 3 个对应分组 = 10 条。"""
    roles = await _roles_map(admin_client)
    res = await admin_client.get(f"/api/admin/roles/{roles['user']['id']}/menus")
    assert res.status_code == 200
    user_ids = set(res.json())
    assert len(user_ids) == 10, f"user 应关联 10 个菜单，实际 {len(user_ids)}"

    code_to_id = await _menu_codes_to_ids(db_session)
    # 叶子：作战台 4 + 文件 2 + 智能体管理
    expected_leaves = {
        "chat",
        "businessMap",
        "marketingMap",
        "visitRecords",
        "personalSpace",
        "teamSpaces",
        "agents",
    }
    for code in expected_leaves:
        assert code_to_id[code] in user_ids, f"user 应可见 {code}"
    # 不应可见的管理/设置叶子
    for code in ("skills", "usage", "feedback", "loginWhitelist", "systemSettings"):
        assert code_to_id[code] not in user_ids, f"user 不应可见 {code}"
    # 分组：作战台/文件/管理 可见，设置不可见
    assert code_to_id["group_zhanzuo"] in user_ids
    assert code_to_id["group_file"] in user_ids
    assert code_to_id["group_admin"] in user_ids  # 因 agents 可见
    assert code_to_id["group_setting"] not in user_ids


# ─── 角色 CRUD ───────────────────────────────────────────────


async def test_create_custom_role(admin_client):
    """创建自定义角色（is_system 恒 False）。"""
    res = await admin_client.post(
        "/api/admin/roles",
        json={"code": "consultant", "name": "顾问", "description": "自定义顾问角色"},
    )
    assert res.status_code == 201
    data = res.json()
    assert data["code"] == "consultant"
    assert data["name"] == "顾问"
    assert data["is_system"] is False
    assert data["id"] > 0


async def test_create_role_duplicate_code(admin_client):
    """code 唯一约束：重复创建 → 400。"""
    await admin_client.post(
        "/api/admin/roles", json={"code": "dup", "name": "A"}
    )
    res = await admin_client.post(
        "/api/admin/roles", json={"code": "dup", "name": "B"}
    )
    assert res.status_code == 400


async def test_get_role(admin_client):
    """获取单个角色。"""
    roles = await _roles_map(admin_client)
    rid = roles["admin"]["id"]
    res = await admin_client.get(f"/api/admin/roles/{rid}")
    assert res.status_code == 200
    assert res.json()["code"] == "admin"


async def test_get_role_not_found(admin_client):
    res = await admin_client.get("/api/admin/roles/99999")
    assert res.status_code == 404


async def test_update_role(admin_client):
    """更新角色 name/description/sort_order（code/is_system 不变）。"""
    roles = await _roles_map(admin_client)
    rid = roles["user"]["id"]
    res = await admin_client.put(
        f"/api/admin/roles/{rid}",
        json={"name": "普通用户(改名)", "description": "更新描述", "sort_order": 5},
    )
    assert res.status_code == 200
    data = res.json()
    assert data["name"] == "普通用户(改名)"
    assert data["description"] == "更新描述"
    assert data["sort_order"] == 5
    # code 与 is_system 不可改
    assert data["code"] == "user"
    assert data["is_system"] is True


async def test_update_role_not_found(admin_client):
    res = await admin_client.put(
        "/api/admin/roles/99999", json={"name": "x"}
    )
    assert res.status_code == 404


async def test_delete_custom_role(admin_client):
    """自定义角色可删除（关联 role_menus 由 CASCADE 清理）。"""
    created = await admin_client.post(
        "/api/admin/roles", json={"code": "temp", "name": "临时"}
    )
    rid = created.json()["id"]
    res = await admin_client.delete(f"/api/admin/roles/{rid}")
    assert res.status_code == 204
    # 删除后查不到
    assert (await admin_client.get(f"/api/admin/roles/{rid}")).status_code == 404


async def test_delete_system_role_forbidden(admin_client):
    """系统内置角色不可删除 → 400。"""
    roles = await _roles_map(admin_client)
    for code in ("user", "admin", "super"):
        res = await admin_client.delete(f"/api/admin/roles/{roles[code]['id']}")
        assert res.status_code == 400, f"{code} 不可删除"


# ─── 角色-菜单关联 ───────────────────────────────────────────


async def test_get_role_menus_not_found(admin_client):
    res = await admin_client.get("/api/admin/roles/99999/menus")
    assert res.status_code == 404


async def test_set_role_menus_replace(admin_client, db_session):
    """批量设置自定义角色关联菜单（全量替换）。"""
    # 建一个自定义角色
    created = await admin_client.post(
        "/api/admin/roles", json={"code": "custom_a", "name": "自定义A"}
    )
    rid = created.json()["id"]
    # 初始无关联
    assert (await admin_client.get(f"/api/admin/roles/{rid}/menus")).json() == []

    code_to_id = await _menu_codes_to_ids(db_session)
    target = [code_to_id["chat"], code_to_id["businessMap"]]

    res = await admin_client.put(f"/api/admin/roles/{rid}/menus", json={"menu_ids": target})
    assert res.status_code == 200
    assert set(res.json()) == set(target)

    # GET 验证已落库
    got = await admin_client.get(f"/api/admin/roles/{rid}/menus")
    assert set(got.json()) == set(target)

    # 再次 PUT 全量替换为另一组
    res2 = await admin_client.put(
        f"/api/admin/roles/{rid}/menus",
        json={"menu_ids": [code_to_id["agents"]]},
    )
    assert res2.status_code == 200
    assert res2.json() == [code_to_id["agents"]]


async def test_set_role_menus_invalid_id(admin_client):
    """menu_id 不存在 → 400。"""
    created = await admin_client.post(
        "/api/admin/roles", json={"code": "custom_b", "name": "自定义B"}
    )
    rid = created.json()["id"]
    res = await admin_client.put(
        f"/api/admin/roles/{rid}/menus", json={"menu_ids": [99999]}
    )
    assert res.status_code == 400


async def test_set_role_menus_super_rejected(admin_client):
    """super 角色菜单关联不可修改 → 403。"""
    roles = await _roles_map(admin_client)
    super_id = roles["super"]["id"]
    res = await admin_client.put(
        f"/api/admin/roles/{super_id}/menus", json={"menu_ids": []}
    )
    assert res.status_code == 403
    # super 仍返回全部菜单
    got = await admin_client.get(f"/api/admin/roles/{super_id}/menus")
    assert len(got.json()) == 16


# ─── 用户角色分配 ─────────────────────────────────────────────


async def test_assign_user_role(admin_client, db_session):
    """修改用户角色：User.role 更新为目标 Role.code。"""
    uid = await _create_user(db_session, username="assign_target")
    roles = await _roles_map(admin_client)

    res = await admin_client.put(
        f"/api/admin/users/{uid}/role", json={"role_code": "admin"}
    )
    assert res.status_code == 200
    assert res.json() == {"user_id": uid, "role": "admin"}

    # 直接查 DB 验证 User.role 已更新
    from sqlalchemy import select

    from app.models import User

    user = (await db_session.execute(select(User).where(User.id == uid))).scalar_one()
    assert user.role == "admin"


async def test_assign_user_role_custom_code(admin_client, db_session):
    """分配自定义角色 code：User.role 存自定义 code 字符串。"""
    uid = await _create_user(db_session, username="custom_role_user")
    await admin_client.post(
        "/api/admin/roles", json={"code": "analyst", "name": "分析师"}
    )
    res = await admin_client.put(
        f"/api/admin/users/{uid}/role", json={"role_code": "analyst"}
    )
    assert res.status_code == 200
    assert res.json()["role"] == "analyst"


async def test_assign_user_role_invalid_code(admin_client, db_session):
    """角色 code 不存在 → 400。"""
    uid = await _create_user(db_session, username="bad_role_user")
    res = await admin_client.put(
        f"/api/admin/users/{uid}/role", json={"role_code": "no_such_role"}
    )
    assert res.status_code == 400


async def test_assign_user_role_user_not_found(admin_client):
    """用户不存在 → 404。"""
    res = await admin_client.put(
        "/api/admin/users/99999/role", json={"role_code": "admin"}
    )
    assert res.status_code == 404
