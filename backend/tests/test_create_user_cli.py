import pytest
import pytest_asyncio
from sqlalchemy import select


@pytest_asyncio.fixture
async def fresh_db(monkeypatch, tmp_path):
    monkeypatch.setenv("APP_SECRET", "s")
    monkeypatch.setenv("ANTHROPIC_AUTH_TOKEN", "t")
    monkeypatch.setenv("ANTHROPIC_BASE_URL", "https://example.com")
    monkeypatch.setenv("DATABASE_URL", "postgresql+asyncpg://postgres:postgres@localhost:5432/gokagent_test")
    monkeypatch.chdir(tmp_path)

    from importlib import reload
    from app.core import config as core_config
    from app.db import base as db_base, session as db_session, migrations as db_migrations
    from app.models import agent as model_agent, category as model_category, session as model_session, team_space as model_team_space, user as model_user
    reload(core_config)
    reload(db_base)
    reload(db_session)
    reload(db_migrations)
    reload(model_agent)
    reload(model_category)
    reload(model_session)
    reload(model_team_space)
    reload(model_user)
    from app.scripts import create_user
    reload(create_user)
    async with db_session.engine.begin() as conn:
        from sqlalchemy import text
        await conn.execute(text("DROP SCHEMA public CASCADE"))
        await conn.execute(text("CREATE SCHEMA public"))
    await db_migrations.init_db()
    yield db_session
    await db_session.engine.dispose()


async def test_create_user_inserts_row(fresh_db):
    db_session = fresh_db
    from app.models import User
    from app.scripts.create_user import create_user

    await create_user("alice", "hunter2")

    async with db_session.async_session() as s:
        u = (await s.execute(select(User).where(User.username == "alice"))).scalar_one()
        assert u.password_hash != "hunter2"


async def test_create_user_rejects_duplicate(fresh_db):
    from app.scripts.create_user import create_user
    await create_user("alice", "hunter2")
    with pytest.raises(SystemExit):
        await create_user("alice", "again")
