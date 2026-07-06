async def test_admin_login_whitelist_user_crud(super_client):
    """超级管理员可以添加、查看、删除用户姓名白名单。"""
    res = await super_client.post(
        "/api/admin/login-whitelist/users",
        json={"name": " 张三 "},
    )
    assert res.status_code == 201
    user_item = res.json()
    assert user_item["name"] == "张三"

    duplicate = await super_client.post(
        "/api/admin/login-whitelist/users",
        json={"name": "张三"},
    )
    assert duplicate.status_code == 409

    empty = await super_client.post(
        "/api/admin/login-whitelist/users",
        json={"name": "   "},
    )
    assert empty.status_code == 400

    listing = await super_client.get("/api/admin/login-whitelist")
    assert listing.status_code == 200
    assert listing.json()["users"] == [user_item]
    assert listing.json()["departments"] == []

    deleted = await super_client.delete(
        f"/api/admin/login-whitelist/users/{user_item['id']}"
    )
    assert deleted.status_code == 204

    listing = await super_client.get("/api/admin/login-whitelist")
    assert listing.json()["users"] == []


async def test_admin_login_whitelist_department_crud_and_search(super_client):
    """超级管理员可以搜索、添加、查看、删除部门白名单。"""
    from app.db.session import async_session
    from app.models import Department

    async with async_session() as db:
        db.add_all([
            Department(id=1, name="集团", parent_id=0),
            Department(id=2, name="研发部", parent_id=1),
            Department(id=3, name="研发平台组", parent_id=2),
        ])
        await db.commit()

    search = await super_client.get(
        "/api/admin/login-whitelist/departments/search?q=研发"
    )
    assert search.status_code == 200
    assert search.json() == [
        {"department_id": 2, "name": "研发部", "path": "集团 / 研发部"},
        {"department_id": 3, "name": "研发平台组", "path": "集团 / 研发部 / 研发平台组"},
    ]

    created = await super_client.post(
        "/api/admin/login-whitelist/departments",
        json={"department_id": 2},
    )
    assert created.status_code == 201
    department_item = created.json()
    assert department_item["department_id"] == 2
    assert department_item["path"] == "集团 / 研发部"

    duplicate = await super_client.post(
        "/api/admin/login-whitelist/departments",
        json={"department_id": 2},
    )
    assert duplicate.status_code == 409

    missing = await super_client.post(
        "/api/admin/login-whitelist/departments",
        json={"department_id": 999},
    )
    assert missing.status_code == 404

    listing = await super_client.get("/api/admin/login-whitelist")
    assert listing.status_code == 200
    assert listing.json()["departments"] == [department_item]

    deleted = await super_client.delete(
        f"/api/admin/login-whitelist/departments/{department_item['id']}"
    )
    assert deleted.status_code == 204


async def test_login_whitelist_forbidden_for_admin(admin_client):
    """普通管理员不能访问登录白名单管理接口。"""
    res = await admin_client.get("/api/admin/login-whitelist")
    assert res.status_code == 403

    res = await admin_client.post(
        "/api/admin/login-whitelist/users",
        json={"name": "李四"},
    )
    assert res.status_code == 403


async def test_login_whitelist_forbidden_for_user(logged_in_client):
    """普通用户不能访问登录白名单管理接口。"""
    res = await logged_in_client.get("/api/admin/login-whitelist")
    assert res.status_code == 403
