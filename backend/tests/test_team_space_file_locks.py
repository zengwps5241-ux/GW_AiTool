import pytest
import pytest_asyncio
from fakeredis.aioredis import FakeRedis


@pytest_asyncio.fixture
async def redis_client():
    client = FakeRedis(decode_responses=True)
    yield client
    await client.aclose()


@pytest.mark.asyncio
async def test_lock_acquire_reentrant_and_locked(redis_client):
    from app.modules.team_spaces.file_locks import FileLockService

    service = FileLockService(redis_client, ttl_seconds=30, cleanup_grace_seconds=5)

    first = await service.try_lock_file(
        space_id=1,
        path="docs/a.md",
        holder_type="agent_session",
        holder_user_id=10,
        session_id="s1",
        lock_token="agent:s1",
    )
    assert first.ok is True
    assert first.state == "ACQUIRED"

    again = await service.try_lock_file(
        space_id=1,
        path="docs/a.md",
        holder_type="agent_session",
        holder_user_id=10,
        session_id="s1",
        lock_token="agent:s1",
    )
    assert again.ok is True
    assert again.state == "REENTRANT"

    blocked = await service.try_lock_file(
        space_id=1,
        path="docs/a.md",
        holder_type="user",
        holder_user_id=11,
        session_id="ui",
        lock_token="user-token",
    )
    assert blocked.ok is False
    assert blocked.reason == "FILE_LOCKED"
    assert blocked.locked_by is not None
    assert blocked.locked_by.session_id == "s1"


@pytest.mark.asyncio
async def test_expired_lock_can_be_taken_over(redis_client):
    from app.modules.team_spaces.file_locks import FileLockService

    service = FileLockService(redis_client, ttl_seconds=30, cleanup_grace_seconds=5)
    await service.try_lock_file(
        space_id=1,
        path="docs/a.md",
        holder_type="agent_session",
        holder_user_id=10,
        session_id="s1",
        lock_token="agent:s1",
        now_ms=1_000,
    )

    taken = await service.try_lock_file(
        space_id=1,
        path="docs/a.md",
        holder_type="agent_session",
        holder_user_id=11,
        session_id="s2",
        lock_token="agent:s2",
        now_ms=40_000,
    )

    assert taken.ok is True
    assert taken.state == "TAKEN_OVER_EXPIRED"


@pytest.mark.asyncio
async def test_validate_and_release_by_lock_token(redis_client):
    from app.modules.team_spaces.file_locks import FileLockService

    service = FileLockService(redis_client, ttl_seconds=30, cleanup_grace_seconds=5)
    await service.try_lock_file(
        space_id=1,
        path="docs/a.md",
        holder_type="user",
        holder_user_id=10,
        session_id="ui",
        lock_token="token-a",
        now_ms=1_000,
    )

    assert await service.validate_file_lock(space_id=1, path="docs/a.md", lock_token="token-a", now_ms=2_000)
    assert not await service.validate_file_lock(space_id=1, path="docs/a.md", lock_token="token-b", now_ms=2_000)
    assert await service.release_file_lock(space_id=1, path="docs/a.md", lock_token="token-a") is True
    assert await service.validate_file_lock(space_id=1, path="docs/a.md", lock_token="token-a", now_ms=2_000) is False


@pytest.mark.asyncio
async def test_release_owner_locks_does_not_delete_taken_over_lock(redis_client):
    from app.modules.team_spaces.file_locks import FileLockService

    service = FileLockService(redis_client, ttl_seconds=30, cleanup_grace_seconds=5)
    await service.try_lock_file(
        space_id=1,
        path="docs/a.md",
        holder_type="agent_session",
        holder_user_id=10,
        session_id="s1",
        lock_token="agent:s1",
        now_ms=1_000,
    )
    await service.try_lock_file(
        space_id=1,
        path="docs/a.md",
        holder_type="agent_session",
        holder_user_id=11,
        session_id="s2",
        lock_token="agent:s2",
        now_ms=40_000,
    )

    released = await service.release_owner_locks("agent:s1")

    assert released == 0
    assert await service.validate_file_lock(space_id=1, path="docs/a.md", lock_token="agent:s2", now_ms=41_000)
