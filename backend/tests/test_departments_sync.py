"""部门同步逻辑测试。"""

from unittest.mock import AsyncMock, patch


async def test_sync_departments_inserts_records(client, monkeypatch, app_env):
    """sync_departments 应将企微返回的部门列表写入本地表。"""
    monkeypatch.setenv("WECHAT_WORK_CORP_ID", "test_corp")
    monkeypatch.setenv("WECHAT_WORK_SECRET", "test_secret")

    from importlib import reload
    from app.core import config as core_config
    from app.modules.auth import departments as auth_departments
    reload(core_config)
    reload(auth_departments)

    from app.modules.auth import wechat_work
    from app.db.session import async_session
    from sqlalchemy import select
    from app.models import Department

    fake_list = [
        {"id": 1, "name": "总公司", "parentid": 0, "order": 100},
        {"id": 2, "name": "研发部", "parentid": 1, "order": 200},
        {"id": 3, "name": "产品部", "parentid": 1, "order": 300},
    ]

    with patch.object(wechat_work, "get_access_token", new=AsyncMock(return_value="token")), \
         patch.object(wechat_work, "get_department_list", new=AsyncMock(return_value=fake_list)):
        async with async_session() as db:
            await auth_departments.sync_departments(db)

    async with async_session() as db:
        rows = (await db.execute(select(Department).order_by(Department.id))).scalars().all()
        assert [r.id for r in rows] == [1, 2, 3]
        assert [r.name for r in rows] == ["总公司", "研发部", "产品部"]
        assert rows[1].parent_id == 1
        assert rows[1].order == 200


async def test_sync_departments_replaces_old_data(client, monkeypatch, app_env):
    """sync_departments 应全量替换旧数据。"""
    monkeypatch.setenv("WECHAT_WORK_CORP_ID", "test_corp")
    monkeypatch.setenv("WECHAT_WORK_SECRET", "test_secret")

    from importlib import reload
    from app.core import config as core_config
    from app.modules.auth import departments as auth_departments
    reload(core_config)
    reload(auth_departments)

    from app.modules.auth import wechat_work
    from app.db.session import async_session
    from sqlalchemy import select
    from app.models import Department

    # 先插入一批旧数据
    async with async_session() as db:
        db.add(Department(id=99, name="旧部门"))
        await db.commit()

    new_list = [{"id": 1, "name": "新部门"}]

    with patch.object(wechat_work, "get_access_token", new=AsyncMock(return_value="token")), \
         patch.object(wechat_work, "get_department_list", new=AsyncMock(return_value=new_list)):
        async with async_session() as db:
            await auth_departments.sync_departments(db)

    async with async_session() as db:
        rows = (await db.execute(select(Department))).scalars().all()
        assert len(rows) == 1
        assert rows[0].id == 1
        assert rows[0].name == "新部门"


async def test_sync_departments_skips_when_corp_id_missing(client, monkeypatch, app_env):
    """缺少企微配置时应跳过同步、不抛异常。"""
    monkeypatch.setenv("WECHAT_WORK_CORP_ID", "")
    monkeypatch.setenv("WECHAT_WORK_SECRET", "")

    from importlib import reload
    from app.core import config as core_config
    from app.modules.auth import departments as auth_departments
    reload(core_config)
    reload(auth_departments)

    from app.db.session import async_session

    async with async_session() as db:
        # 不应抛异常
        await auth_departments.sync_departments(db)


async def test_get_department_names_resolves_ids(client, app_env):
    """get_department_names 应返回与 id 顺序一致的名称列表。"""
    from app.db.session import async_session
    from app.models import Department
    from app.modules.auth.departments import get_department_names

    async with async_session() as db:
        db.add_all([
            Department(id=10, name="一部"),
            Department(id=20, name="二部"),
            Department(id=30, name="三部"),
        ])
        await db.commit()

    async with async_session() as db:
        names = await get_department_names(db, [30, 10, 20])
        assert names == ["三部", "一部", "二部"]


async def test_get_department_names_uses_id_for_unknown(client, app_env):
    """未知 id 应回退为字符串形式的 id。"""
    from app.db.session import async_session
    from app.models import Department
    from app.modules.auth.departments import get_department_names

    async with async_session() as db:
        db.add(Department(id=10, name="一部"))
        await db.commit()

    async with async_session() as db:
        names = await get_department_names(db, [10, 999])
        assert names == ["一部", "999"]


async def test_get_department_names_empty_list(client, app_env):
    """空 id 列表应返回空列表。"""
    from app.db.session import async_session
    from app.modules.auth.departments import get_department_names

    async with async_session() as db:
        names = await get_department_names(db, [])
        assert names == []
