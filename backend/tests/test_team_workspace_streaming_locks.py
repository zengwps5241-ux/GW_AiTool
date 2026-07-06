import pytest
from fakeredis.aioredis import FakeRedis


@pytest.mark.asyncio
async def test_streaming_releases_agent_file_locks(app_env, monkeypatch):
    from app.core import redis as redis_core
    from app.db.session import async_session
    from app.integrations.claude.runner import ChatRunSummary
    from app.models import Agent, ChatSession, TeamSpace, TeamSpaceMember, User
    from app.modules.sessions import streaming
    from app.modules.team_spaces.file_locks import FileLockService, agent_lock_token

    redis_client = FakeRedis(decode_responses=True)
    monkeypatch.setattr(redis_core, "get_redis_client", lambda: redis_client)

    async with async_session() as db:
        user = User(username="alice", password_hash="x")
        db.add(user)
        await db.flush()
        space = TeamSpace(name="研发空间", owner_user_id=user.id, created_by_user_id=user.id)
        db.add(space)
        await db.flush()
        db.add(TeamSpaceMember(space_id=space.id, user_id=user.id, role="editor", added_by_user_id=user.id))
        agent = Agent(name="Writer", code="writer", system_prompt="")
        db.add(agent)
        await db.flush()
        cs = ChatSession(id="session-1", user_id=user.id, agent_id=agent.id, workspace_kind="team", team_space_id=space.id)
        db.add(cs)
        await db.commit()
        await db.refresh(cs)
        await db.refresh(agent)

    async def fake_stream_chat(**kwargs):
        context = kwargs["file_lock_context"]
        service = FileLockService(redis_client, ttl_seconds=1800, cleanup_grace_seconds=300)
        await service.try_lock_file(
            space_id=context.space_id,
            path="docs/a.md",
            holder_type="agent_session",
            holder_user_id=context.user_id,
            session_id=context.session_id,
            lock_token=agent_lock_token(context.session_id),
        )
        return ChatRunSummary(
            session_id="claude-session-1",
            is_error=False,
            stop_reason="end_turn",
            usage=None,
            model_usage=None,
            duration_ms=None,
            duration_api_ms=None,
            total_cost_usd=None,
            interrupted=False,
            error_message=None,
        )

    monkeypatch.setattr(streaming, "stream_chat", fake_stream_chat)

    response = await streaming.stream_session_chat(cs, user, "写 docs/a.md", agent=agent)
    # 消费 SSE，等待后台 runner 结束并触发 finally 释放锁。
    async for _chunk in response.body_iterator:
        pass

    service = FileLockService(redis_client, ttl_seconds=1800, cleanup_grace_seconds=300)
    assert await service.validate_file_lock(
        space_id=space.id,
        path="docs/a.md",
        lock_token=agent_lock_token("session-1"),
    ) is False
    await redis_client.aclose()
