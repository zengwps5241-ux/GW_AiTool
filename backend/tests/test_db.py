from sqlalchemy import select


async def test_create_user_and_session(isolated_db_module):
    """验证 User 与 ChatSession 模型可正常写入并关联查询。"""
    db_session = isolated_db_module
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
