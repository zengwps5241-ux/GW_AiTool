import os
import pytest
from sqlalchemy import select


@pytest.fixture
async def db_engine(monkeypatch, tmp_path):
    """提供独立的数据库引擎，使用临时目录隔离测试环境。"""
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
    async with db_session.engine.begin() as conn:
        from sqlalchemy import text
        await conn.execute(text("DROP SCHEMA public CASCADE"))
        await conn.execute(text("CREATE SCHEMA public"))
    await db_migrations.init_db()
    yield db_session
    await db_session.engine.dispose()


async def test_create_user_and_session(db_engine):
    """验证 User 与 ChatSession 模型可正常写入并关联查询。"""
    db_session = db_engine
    from app.models import User, ChatSession

    async with db_session.async_session() as s:
        u = User(username="alice", password_hash="x")
        s.add(u)
        await s.flush()
        cs = ChatSession(id="abc", user_id=u.id, title="t1")
        s.add(cs)
        await s.commit()

    async with db_session.async_session() as s:
        row = (await s.execute(select(User).where(User.username == "alice"))).scalar_one()
        assert row.username == "alice"
        cs_row = (await s.execute(select(ChatSession).where(ChatSession.id == "abc"))).scalar_one()
        assert cs_row.user_id == row.id
        assert cs_row.claude_session_id is None
