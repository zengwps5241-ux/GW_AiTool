import pytest


@pytest.mark.asyncio
async def test_team_save_requires_valid_file_lock(logged_in_client, monkeypatch):
    from fakeredis.aioredis import FakeRedis
    from app.core import redis as redis_core

    redis_client = FakeRedis(decode_responses=True)
    monkeypatch.setattr(redis_core, "get_redis_client", lambda: redis_client)

    create = await logged_in_client.post("/api/team-spaces", json={"name": "研发空间"})
    assert create.status_code == 200
    space_id = create.json()["id"]

    create_file = await logged_in_client.post(
        f"/api/team-spaces/{space_id}/workspace/file",
        json={"path": "docs/a.md", "kind": "file", "content": "old"},
    )
    assert create_file.status_code == 200

    no_lock = await logged_in_client.put(
        f"/api/team-spaces/{space_id}/workspace/content",
        json={"path": "docs/a.md", "content": "new"},
    )
    assert no_lock.status_code == 409
    assert no_lock.json()["detail"]["code"] == "FILE_LOCK_EXPIRED"

    lock = await logged_in_client.post(
        f"/api/team-spaces/{space_id}/workspace/locks",
        json={"path": "docs/a.md"},
    )
    assert lock.status_code == 200
    lock_token = lock.json()["lock_token"]

    saved = await logged_in_client.put(
        f"/api/team-spaces/{space_id}/workspace/content",
        json={"path": "docs/a.md", "content": "new", "lock_token": lock_token},
    )
    assert saved.status_code == 200
    assert saved.json()["content"] == "new"

    released = await logged_in_client.request(
        "DELETE",
        f"/api/team-spaces/{space_id}/workspace/locks",
        json={"path": "docs/a.md", "lock_token": lock_token},
    )
    assert released.status_code == 200
    assert released.json()["released"] is True

    await redis_client.aclose()
