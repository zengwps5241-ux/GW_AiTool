import pytest
import pytest_asyncio
from httpx import AsyncClient, ASGITransport


@pytest.fixture(autouse=True)
def _default_database_url(monkeypatch):
    """为所有测试提供默认的数据库连接地址。"""
    monkeypatch.setenv(
        "DATABASE_URL",
        "postgresql+asyncpg://postgres:postgres@localhost:5432/gokagent_test",
    )


@pytest_asyncio.fixture
async def app_env(monkeypatch, tmp_path):
    """所有 API 测试共享的环境:临时 cwd + 必要 env。"""
    monkeypatch.setenv("APP_SECRET", "test-secret")
    monkeypatch.setenv("APP_ENV", "production")
    monkeypatch.setenv("ANTHROPIC_AUTH_TOKEN", "test-token")
    monkeypatch.setenv("ANTHROPIC_BASE_URL", "https://example.com")
    monkeypatch.setenv("DATABASE_URL", "postgresql+asyncpg://postgres:postgres@localhost:5432/gokagent_test")
    monkeypatch.chdir(tmp_path)

    from importlib import reload

    # Layer 0: core
    from app.core import config as core_config, security as core_security
    reload(core_config)
    reload(core_security)

    # Layer 1: db
    from app.db import base as db_base, session as db_session, migrations as db_migrations
    reload(db_base)
    reload(db_session)
    reload(db_migrations)

    # Layer 2: models, schemas (reload submodules so they re-import fresh Base)
    from app import models, schemas
    from app.models import agent as model_agent, category as model_category, conversion_task as model_conversion_task, department as model_department, feedback as model_feedback, login_whitelist as model_login_whitelist, session as model_session, team_space as model_team_space, upload_task as model_upload_task, usage as model_usage, user as model_user
    from app.schemas import auth as schema_auth, agents as schema_agents, categories as schema_categories, sessions as schema_sessions, team_spaces as schema_team_spaces, model_settings as schema_model_settings, login_whitelist as schema_login_whitelist, upload_tasks as schema_upload_tasks, workspace_tasks as schema_workspace_tasks
    reload(model_agent)
    reload(model_category)
    reload(model_conversion_task)
    reload(model_department)
    reload(model_feedback)
    reload(model_login_whitelist)
    reload(model_session)
    reload(model_team_space)
    reload(model_upload_task)
    reload(model_usage)
    reload(model_user)
    reload(models)
    reload(schema_auth)
    reload(schema_agents)
    reload(schema_categories)
    reload(schema_sessions)
    reload(schema_team_spaces)
    reload(schema_model_settings)
    reload(schema_login_whitelist)
    reload(schema_upload_tasks)
    reload(schema_workspace_tasks)
    reload(schemas)

    # Layer 3: integrations
    from app.integrations import mineru
    from app.integrations.claude import serializers, guard, runner
    reload(mineru)
    reload(serializers)
    reload(guard)
    reload(runner)

    # Layer 4: modules
    from app.modules.agents import workdir
    from app.modules.catalog import skills, plugins, commands
    reload(workdir)
    reload(skills)
    reload(plugins)
    reload(commands)
    from app.modules.auth import service as auth_service, departments as auth_departments, login_whitelist as auth_login_whitelist
    from app.modules.agents import service as agents_service
    from app.modules.sessions import service as sessions_service, streaming
    from app.modules.team_spaces import service as team_spaces_service
    from app.modules.workspace import (
        archive,
        markdown_index,
        office_preview,
        paths,
        preview,
        scope as workspace_scope,
        service as workspace_service,
        tasks as workspace_tasks_service,
        text_ops,
    )
    from app.modules.uploads import service as uploads_service, tasks as upload_tasks_service
    from app.modules.conversions import service as conversions_service
    from app.modules.usage import service as usage_service
    reload(auth_service)
    reload(auth_departments)
    reload(auth_login_whitelist)
    reload(agents_service)
    reload(team_spaces_service)
    reload(sessions_service)
    reload(streaming)
    reload(paths)
    reload(preview)
    reload(workspace_scope)
    reload(office_preview)
    reload(archive)
    reload(markdown_index)
    reload(workspace_service)
    reload(workspace_tasks_service)
    reload(uploads_service)
    reload(upload_tasks_service)
    reload(conversions_service)
    reload(usage_service)

    # Layer 5: api
    from app.api import deps, router
    from app.api.routes import auth as auth_routes, agents as agents_routes
    from app.api.routes import sessions as sessions_routes, team_spaces as team_spaces_routes, uploads as uploads_routes, upload_tasks as upload_tasks_routes
    from app.api.routes import model_settings as model_settings_routes
    from app.api.routes import workspace as workspace_routes
    from app.api.routes import workspace_tasks as workspace_tasks_routes
    from app.api.routes import conversion_tasks as conversion_tasks_routes
    from app.api.routes import admin_categories as admin_categories_routes
    from app.api.routes import admin_login_whitelist as admin_login_whitelist_routes
    from app.api.routes import admin_skills as admin_skills_routes
    from app.api.routes import admin_plugins as admin_plugins_routes
    from app.api.routes import admin_usage as admin_usage_routes
    reload(deps)
    reload(auth_routes)
    reload(agents_routes)
    reload(sessions_routes)
    reload(team_spaces_routes)
    reload(model_settings_routes)
    reload(uploads_routes)
    reload(upload_tasks_routes)
    reload(workspace_routes)
    reload(workspace_tasks_routes)
    reload(conversion_tasks_routes)
    reload(admin_login_whitelist_routes)
    reload(admin_skills_routes)
    reload(admin_plugins_routes)
    reload(admin_categories_routes)
    reload(admin_usage_routes)
    reload(router)

    # Layer 6: main, scripts
    from app import main
    from app.scripts import create_user
    reload(main)
    reload(create_user)

    async with db_session.engine.begin() as conn:
        from sqlalchemy import text
        await conn.execute(text("DROP SCHEMA public CASCADE"))
        await conn.execute(text("CREATE SCHEMA public"))
    await db_migrations.init_db()
    yield
    await db_session.engine.dispose()


@pytest_asyncio.fixture
async def client(app_env):
    from app.main import build_app
    app = build_app()
    async with AsyncClient(
        transport=ASGITransport(app=app), base_url="http://test"
    ) as c:
        yield c


async def _login_wechat_user(client, *, code: str, userid: str, name: str):
    """按企微二维码流程登录指定测试用户。"""
    from unittest.mock import AsyncMock, patch
    from app.modules.auth import wechat_work

    res = await client.get("/api/auth/wechat-work/qrcode-config")
    assert res.status_code == 200
    state = res.json()["state"]

    res = await client.get(
        f"/api/auth/wechat-work/callback?code={code}&state={state}",
        follow_redirects=False,
    )
    assert res.status_code == 200

    res = await client.get(f"/api/auth/wechat-work/poll-code?state={state}")
    assert res.status_code == 200
    assert res.json()["code"] == code

    with patch.object(wechat_work, "get_access_token", new=AsyncMock(return_value="token")), \
         patch.object(wechat_work, "auth_get_user_info", new=AsyncMock(return_value={
             "userid": userid,
             "user_ticket": f"ticket_{userid}",
         })), \
         patch.object(wechat_work, "auth_get_user_detail", new=AsyncMock(return_value={
             "userid": userid,
             "name": name,
             "department": [],
             "position": None,
             "mobile": None,
             "email": None,
             "avatar": None,
         })), \
         patch.object(wechat_work, "get_user_detail", new=AsyncMock(return_value={
             "userid": userid,
             "name": name,
             "department": [],
             "position": None,
             "mobile": None,
             "email": None,
             "avatar": None,
         })), \
         patch.object(wechat_work, "get_department_list", new=AsyncMock(return_value=[])):
        res = await client.post(
            "/api/auth/wechat-work/login-by-code",
            json={"code": code},
        )
        assert res.status_code == 200
        assert res.json()["success"] is True

    return client


@pytest_asyncio.fixture
async def db_session(app_env):
    """提供已初始化数据库上的直接会话，供模型级测试使用。"""
    from app.db.session import async_session

    async with async_session() as session:
        yield session


@pytest_asyncio.fixture
async def test_user(db_session):
    """模型测试用基础用户。"""
    from app.models import User

    user = User(username="model_user", password_hash="x")
    db_session.add(user)
    await db_session.commit()
    await db_session.refresh(user)
    return user


@pytest_asyncio.fixture
async def logged_in_client(client):
    """通过企微自建二维码流程创建并登录一个普通用户。"""
    return await _login_wechat_user(client, code="test_code", userid="alice", name="Alice")


@pytest_asyncio.fixture
async def other_logged_in_client(app_env):
    """创建另一个独立 cookie jar 的普通登录用户。"""
    from app.main import build_app

    app = build_app()
    async with AsyncClient(
        transport=ASGITransport(app=app), base_url="http://test"
    ) as c:
        yield await _login_wechat_user(c, code="other_code", userid="bob", name="Bob")


@pytest_asyncio.fixture
async def admin_client(client):
    """通过企微自建二维码流程创建并登录一个 admin 用户。"""
    from unittest.mock import patch, AsyncMock
    from app.modules.auth import wechat_work
    from app.db.session import async_session
    from app.models.user import User
    from sqlalchemy import select

    # 1. 获取二维码配置
    res = await client.get("/api/auth/wechat-work/qrcode-config")
    assert res.status_code == 200
    config = res.json()
    state = config["state"]

    # 2. 模拟企微回调(存 code)
    res = await client.get(
        f"/api/auth/wechat-work/callback?code=admin_code&state={state}",
        follow_redirects=False,
    )
    assert res.status_code == 200

    # 3. 轮询获取 code
    res = await client.get(f"/api/auth/wechat-work/poll-code?state={state}")
    assert res.status_code == 200
    assert res.json()["code"] == "admin_code"

    # 4. 用 code 登录
    with patch.object(wechat_work, "get_access_token", new=AsyncMock(return_value="token")), \
         patch.object(wechat_work, "auth_get_user_info", new=AsyncMock(return_value={
             "userid": "admin_user",
             "user_ticket": "ticket_admin",
         })), \
         patch.object(wechat_work, "auth_get_user_detail", new=AsyncMock(return_value={
             "userid": "admin_user",
             "name": "Admin",
             "department": [],
             "position": None,
             "mobile": None,
             "email": None,
             "avatar": None,
         })), \
         patch.object(wechat_work, "get_user_detail", new=AsyncMock(return_value={
             "userid": "admin_user",
             "name": "Admin",
             "department": [],
             "position": None,
             "mobile": None,
             "email": None,
             "avatar": None,
         })), \
         patch.object(wechat_work, "get_department_list", new=AsyncMock(return_value=[])):
        res = await client.post(
            "/api/auth/wechat-work/login-by-code",
            json={"code": "admin_code"},
        )
        assert res.status_code == 200
        assert res.json()["success"] is True

    async with async_session() as session:
        result = await session.execute(select(User).where(User.username == "admin_user"))
        user = result.scalar_one()
        user.role = "admin"
        await session.commit()

    return client


@pytest_asyncio.fixture
async def super_client(client):
    """通过企微自建二维码流程创建并登录一个 super 用户。"""
    from unittest.mock import patch, AsyncMock
    from app.modules.auth import wechat_work
    from app.db.session import async_session
    from app.models.user import User
    from sqlalchemy import select

    # 1. 获取二维码配置
    res = await client.get("/api/auth/wechat-work/qrcode-config")
    assert res.status_code == 200
    config = res.json()
    state = config["state"]

    # 2. 模拟企微回调(存 code)
    res = await client.get(
        f"/api/auth/wechat-work/callback?code=super_code&state={state}",
        follow_redirects=False,
    )
    assert res.status_code == 200

    # 3. 轮询获取 code
    res = await client.get(f"/api/auth/wechat-work/poll-code?state={state}")
    assert res.status_code == 200
    assert res.json()["code"] == "super_code"

    # 4. 用 code 登录
    with patch.object(wechat_work, "get_access_token", new=AsyncMock(return_value="token")), \
         patch.object(wechat_work, "auth_get_user_info", new=AsyncMock(return_value={
             "userid": "super_user",
             "user_ticket": "ticket_super",
         })), \
         patch.object(wechat_work, "auth_get_user_detail", new=AsyncMock(return_value={
             "userid": "super_user",
             "name": "Super",
             "department": [],
             "position": None,
             "mobile": None,
             "email": None,
             "avatar": None,
         })), \
         patch.object(wechat_work, "get_user_detail", new=AsyncMock(return_value={
             "userid": "super_user",
             "name": "Super",
             "department": [],
             "position": None,
             "mobile": None,
             "email": None,
             "avatar": None,
         })), \
         patch.object(wechat_work, "get_department_list", new=AsyncMock(return_value=[])):
        res = await client.post(
            "/api/auth/wechat-work/login-by-code",
            json={"code": "super_code"},
        )
        assert res.status_code == 200
        assert res.json()["success"] is True

    async with async_session() as session:
        result = await session.execute(select(User).where(User.username == "super_user"))
        user = result.scalar_one()
        user.role = "super"
        await session.commit()

    return client
