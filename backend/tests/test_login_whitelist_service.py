from sqlalchemy import select


async def test_login_whitelist_tables_exist(client, app_env):
    """启动迁移后应创建登录白名单表。"""
    from app.db.session import async_session
    from app.models import LoginWhitelistDepartment, LoginWhitelistUser

    async with async_session() as db:
        user_row = LoginWhitelistUser(name="张三")
        dept_row = LoginWhitelistDepartment(department_id=100)
        db.add_all([user_row, dept_row])
        await db.commit()

    async with async_session() as db:
        users = (await db.execute(select(LoginWhitelistUser))).scalars().all()
        departments = (
            await db.execute(select(LoginWhitelistDepartment))
        ).scalars().all()
        assert [u.name for u in users] == ["张三"]
        assert [d.department_id for d in departments] == [100]


async def test_empty_whitelist_allows_login(client, app_env):
    """未配置白名单时不限制企微登录。"""
    from app.db.session import async_session
    from app.modules.auth.login_whitelist import check_wechat_login_allowed

    async with async_session() as db:
        allowed = await check_wechat_login_allowed(
            db, name="任何人", department_ids=[999]
        )

    assert allowed.allowed is True
    assert allowed.reason == "empty_whitelist"


async def test_user_name_requires_exact_match_after_trim(client, app_env):
    """姓名白名单应 trim 后完全匹配，不做包含匹配。"""
    from app.db.session import async_session
    from app.models import LoginWhitelistUser
    from app.modules.auth.login_whitelist import check_wechat_login_allowed

    async with async_session() as db:
        db.add(LoginWhitelistUser(name="张三"))
        await db.commit()

    async with async_session() as db:
        exact = await check_wechat_login_allowed(
            db, name=" 张三 ", department_ids=[]
        )
        partial = await check_wechat_login_allowed(
            db, name="张三天", department_ids=[]
        )

    assert exact.allowed is True
    assert exact.reason == "user_name"
    assert partial.allowed is False
    assert partial.reason == "not_matched"


async def test_department_whitelist_allows_descendant_departments(client, app_env):
    """部门白名单应允许本部门和所有多层后代部门。"""
    from app.db.session import async_session
    from app.models import Department, LoginWhitelistDepartment
    from app.modules.auth.login_whitelist import check_wechat_login_allowed

    async with async_session() as db:
        db.add_all([
            Department(id=1, name="集团", parent_id=0),
            Department(id=2, name="研发部", parent_id=1),
            Department(id=3, name="平台组", parent_id=2),
            Department(id=4, name="产品部", parent_id=1),
            LoginWhitelistDepartment(department_id=2),
        ])
        await db.commit()

    async with async_session() as db:
        same_department = await check_wechat_login_allowed(
            db, name="李四", department_ids=[2]
        )
        descendant = await check_wechat_login_allowed(
            db, name="王五", department_ids=[3]
        )
        sibling = await check_wechat_login_allowed(
            db, name="赵六", department_ids=[4]
        )
        parent = await check_wechat_login_allowed(
            db, name="钱七", department_ids=[1]
        )

    assert same_department.allowed is True
    assert descendant.allowed is True
    assert sibling.allowed is False
    assert parent.allowed is False


async def test_search_departments_returns_paths(client, app_env):
    """部门搜索应支持模糊匹配并返回部门路径。"""
    from app.db.session import async_session
    from app.models import Department
    from app.modules.auth.login_whitelist import search_departments

    async with async_session() as db:
        db.add_all([
            Department(id=1, name="集团", parent_id=0),
            Department(id=2, name="研发部", parent_id=1),
            Department(id=3, name="研发平台组", parent_id=2),
        ])
        await db.commit()

    async with async_session() as db:
        results = await search_departments(db, "研发")

    assert [
        (item.department_id, item.name, item.path) for item in results
    ] == [
        (2, "研发部", "集团 / 研发部"),
        (3, "研发平台组", "集团 / 研发部 / 研发平台组"),
    ]
