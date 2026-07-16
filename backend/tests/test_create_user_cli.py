import pytest
from sqlalchemy import select


async def test_create_user_inserts_row(isolated_db_module):
    db_session = isolated_db_module
    from app.models import User
    from app.scripts.create_user import create_user

    await create_user("alice", "hunter2")

    async with db_session.async_session() as s:
        u = (await s.execute(select(User).where(User.username == "alice"))).scalar_one()
        assert u.password_hash != "hunter2"


async def test_create_user_rejects_duplicate(isolated_db_module):
    from app.scripts.create_user import create_user
    await create_user("alice", "hunter2")
    with pytest.raises(SystemExit):
        await create_user("alice", "again")
