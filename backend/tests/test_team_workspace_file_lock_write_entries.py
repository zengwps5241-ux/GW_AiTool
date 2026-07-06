import pytest
import pytest_asyncio
from fakeredis.aioredis import FakeRedis


@pytest_asyncio.fixture
async def redis_client(monkeypatch):
    from app.core import redis as redis_core

    client = FakeRedis(decode_responses=True)
    monkeypatch.setattr(redis_core, "get_redis_client", lambda: client)
    yield client
    await client.aclose()


@pytest.mark.asyncio
async def test_team_file_delete_is_blocked_by_existing_lock(logged_in_client, redis_client):
    from app.modules.team_spaces.file_locks import FileLockService

    create = await logged_in_client.post("/api/team-spaces", json={"name": "研发空间"})
    assert create.status_code == 200
    space_id = create.json()["id"]
    created = await logged_in_client.post(
        f"/api/team-spaces/{space_id}/workspace/file",
        json={"path": "docs/a.md", "kind": "file", "content": "old"},
    )
    assert created.status_code == 200

    service = FileLockService(redis_client, ttl_seconds=1800, cleanup_grace_seconds=300)
    await service.try_lock_file(
        space_id=space_id,
        path="docs/a.md",
        holder_type="agent_session",
        holder_user_id=999,
        session_id="agent-session",
        lock_token="agent:agent-session",
    )

    deleted = await logged_in_client.delete(f"/api/team-spaces/{space_id}/workspace/file?path=docs%2Fa.md")

    assert deleted.status_code == 409
    assert deleted.json()["detail"]["code"] == "FILE_LOCKED"
