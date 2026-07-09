import pytest
import pytest_asyncio
from httpx import AsyncClient, ASGITransport


@pytest.fixture(autouse=True)
def _default_database_url(monkeypatch):
    """为所有测试提供默认的数据库连接地址。"""
    # 本地 PostgreSQL 口令为 dev（与 backend/.env 一致）
    monkeypatch.setenv(
        "DATABASE_URL",
        "postgresql+asyncpg://postgres:dev@localhost:5432/gokagent_test",
    )


@pytest_asyncio.fixture
async def app_env(monkeypatch, tmp_path):
    """所有 API 测试共享的环境:临时 cwd + 必要 env。"""
    monkeypatch.setenv("APP_SECRET", "test-secret")
    monkeypatch.setenv("APP_ENV", "production")
    monkeypatch.setenv("ANTHROPIC_AUTH_TOKEN", "test-token")
    monkeypatch.setenv("ANTHROPIC_BASE_URL", "https://example.com")
    monkeypatch.setenv("DATABASE_URL", "postgresql+asyncpg://postgres:dev@localhost:5432/gokagent_test")
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
    from app.models import agent as model_agent, category as model_category, conversion_task as model_conversion_task, department as model_department, feedback as model_feedback, login_whitelist as model_login_whitelist, organization as model_organization, session as model_session, team_space as model_team_space, upload_task as model_upload_task, usage as model_usage, user as model_user
    from app.schemas import auth as schema_auth, agents as schema_agents, categories as schema_categories, organizations as schema_organizations, sessions as schema_sessions, team_spaces as schema_team_spaces, model_settings as schema_model_settings, login_whitelist as schema_login_whitelist, upload_tasks as schema_upload_tasks, workspace_tasks as schema_workspace_tasks
    reload(model_agent)
    reload(model_category)
    reload(model_conversion_task)
    reload(model_department)
    reload(model_feedback)
    reload(model_login_whitelist)
    reload(model_organization)
    reload(model_session)
    reload(model_team_space)
    reload(model_upload_task)
    reload(model_usage)
    reload(model_user)
    reload(models)
    reload(schema_auth)
    reload(schema_agents)
    reload(schema_categories)
    reload(schema_organizations)
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
    from app.modules.organizations import service as organizations_service
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
    reload(organizations_service)
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
    from app.api.routes import organizations as organizations_routes
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
    reload(organizations_routes)
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


async def _register_and_login(
    client: AsyncClient,
    *,
    username: str,
    password: str = "pass1234",
    phone: str | None = None,
    display_name: str | None = None,
):
    """直接在数据库创建已激活用户，再走 /api/auth/login 登录（自建认证体系）。

    V2.2 认证重构后已弃用企微二维码流程，测试改用自建登录。
    """
    from app.db.session import async_session
    from app.models.user import User
    from app.core import security

    async with async_session() as db:
        user = User(
            username=username,
            password_hash=security.hash_password(password),
            phone=phone,
            display_name=display_name or username,
            status="active",
            registration_source="admin_create",
            auth_source="local",
        )
        db.add(user)
        await db.commit()
        await db.refresh(user)
        uid = user.id

    res = await client.post(
        "/api/auth/login",
        json={"login": phone or username, "password": password},
    )
    assert res.status_code == 200, res.text
    assert res.json()["success"] is True
    return client, uid


async def _login_wechat_user(client, *, code: str, userid: str, name: str):
    """DEPRECATED: 企微二维码登录流程，V2.2 认证重构后不再使用。

    保留以兼容尚未迁移的旧测试。新测试应使用 _register_and_login。
    """
    # V2.2: 企微路由已注释，此辅助函数不再可用。
    raise RuntimeError(
        "企微登录流程已弃用（V2.2 认证重构）。请改用 _register_and_login。"
    )


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
    """创建并登录一个普通用户（自建注册登录体系）。"""
    c, _ = await _register_and_login(
        client,
        username="alice",
        phone="13800000001",
        display_name="Alice",
    )
    return c


@pytest_asyncio.fixture
async def other_logged_in_client(app_env):
    """创建另一个独立 cookie jar 的普通登录用户。"""
    from app.main import build_app

    app = build_app()
    async with AsyncClient(
        transport=ASGITransport(app=app), base_url="http://test"
    ) as c:
        _, _ = await _register_and_login(
            c,
            username="bob",
            phone="13800000002",
            display_name="Bob",
        )
        yield c


@pytest_asyncio.fixture
async def admin_client(client):
    """创建并登录一个 admin 用户（自建注册登录体系）。"""
    c, uid = await _register_and_login(
        client,
        username="admin_user",
        phone="13800000003",
        display_name="Admin",
    )
    # 提升为 admin
    from app.db.session import async_session
    from app.models.user import User
    from sqlalchemy import select

    async with async_session() as session:
        result = await session.execute(select(User).where(User.id == uid))
        user = result.scalar_one()
        user.role = "admin"
        await session.commit()
    return c


@pytest_asyncio.fixture
async def super_client(client):
    """创建并登录一个 super 用户（自建注册登录体系）。"""
    c, uid = await _register_and_login(
        client,
        username="super_user",
        phone="13800000004",
        display_name="Super",
    )
    # 提升为 super
    from app.db.session import async_session
    from app.models.user import User
    from sqlalchemy import select

    async with async_session() as session:
        result = await session.execute(select(User).where(User.id == uid))
        user = result.scalar_one()
        user.role = "super"
        await session.commit()
    return c
