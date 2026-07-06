from datetime import UTC, datetime, timedelta

import pytest
from sqlalchemy import update


async def test_workspace_tasks_mixes_upload_and_conversion_tasks(logged_in_client):
    from app.core.config import user_workspace

    ws = user_workspace("alice")
    (ws / "manual.pdf").write_bytes(b"%PDF")

    upload_create = await logged_in_client.post("/api/upload-tasks", json={
        "target_dir": "",
        "items": [{"filename": "a.txt", "relative_path": "a.txt", "size": 5}],
    })
    await logged_in_client.post("/api/conversion-tasks/retry", json={"source_path": "manual.pdf"})

    r = await logged_in_client.get("/api/workspace-tasks")

    assert r.status_code == 200
    data = r.json()
    assert {item["type"] for item in data} == {"upload", "conversion"}
    upload = next(item for item in data if item["type"] == "upload")
    conversion = next(item for item in data if item["type"] == "conversion")
    assert upload["id"] == upload_create.json()[0]["id"]
    assert upload["name"] == "a.txt"
    assert upload["progress"] == 0
    assert conversion["name"] == "manual.pdf"
    assert conversion["progress"] is None


async def test_workspace_tasks_paginates_after_mixed_sort(logged_in_client):
    from app.core.config import user_workspace
    from app.db.session import async_session
    from app.models import ConversionTask, UploadTask

    ws = user_workspace("alice")
    (ws / "manual.pdf").write_bytes(b"%PDF")

    upload_create = await logged_in_client.post("/api/upload-tasks", json={
        "target_dir": "",
        "items": [{"filename": "older.txt", "relative_path": "older.txt", "size": 1}],
    })
    conversion_create = await logged_in_client.post(
        "/api/conversion-tasks/retry",
        json={"source_path": "manual.pdf"},
    )

    base = datetime(2026, 1, 1, tzinfo=UTC)
    async with async_session() as session:
        # 固定 created_at，确保测试只验证通用任务接口的合并排序和分页行为。
        await session.execute(
            update(UploadTask)
            .where(UploadTask.id == upload_create.json()[0]["id"])
            .values(created_at=base)
        )
        await session.execute(
            update(ConversionTask)
            .where(ConversionTask.id == conversion_create.json()["id"])
            .values(created_at=base + timedelta(seconds=1))
        )
        await session.commit()

    r = await logged_in_client.get("/api/workspace-tasks?limit=1&offset=1")

    assert r.status_code == 200
    data = r.json()
    assert len(data) == 1
    assert data[0]["type"] == "upload"
    assert data[0]["name"] == "older.txt"


async def test_workspace_tasks_uses_stable_keys_and_tie_breaker(logged_in_client):
    from app.core.config import user_workspace
    from app.db.session import async_session
    from app.models import ConversionTask, UploadTask

    ws = user_workspace("alice")
    (ws / "same-time.pdf").write_bytes(b"%PDF")

    upload_create = await logged_in_client.post("/api/upload-tasks", json={
        "target_dir": "",
        "items": [{"filename": "same-time.txt", "relative_path": "same-time.txt", "size": 1}],
    })
    conversion_create = await logged_in_client.post(
        "/api/conversion-tasks/retry",
        json={"source_path": "same-time.pdf"},
    )
    upload_id = upload_create.json()[0]["id"]
    conversion_id = conversion_create.json()["id"]
    assert upload_id == conversion_id

    same_time = datetime(2026, 1, 1, tzinfo=UTC)
    async with async_session() as session:
        # 构造跨表同 id、同 created_at，覆盖通用任务列表的最终排序规则。
        await session.execute(
            update(UploadTask)
            .where(UploadTask.id == upload_id)
            .values(created_at=same_time)
        )
        await session.execute(
            update(ConversionTask)
            .where(ConversionTask.id == conversion_id)
            .values(created_at=same_time)
        )
        await session.commit()

    r = await logged_in_client.get("/api/workspace-tasks?limit=2")

    assert r.status_code == 200
    data = r.json()
    assert [item["type"] for item in data] == ["conversion", "upload"]
    assert [item["task_key"] for item in data] == [
        f"conversion:{conversion_id}",
        f"upload:{upload_id}",
    ]
    assert len({item["task_key"] for item in data}) == 2

    first_page = await logged_in_client.get("/api/workspace-tasks?limit=1&offset=0")
    second_page = await logged_in_client.get("/api/workspace-tasks?limit=1&offset=1")

    assert first_page.status_code == 200
    assert second_page.status_code == 200
    assert first_page.json()[0]["task_key"] == f"conversion:{conversion_id}"
    assert second_page.json()[0]["task_key"] == f"upload:{upload_id}"


@pytest.mark.asyncio
async def test_team_workspace_tasks_are_isolated(logged_in_client):
    created = await logged_in_client.post("/api/team-spaces", json={"name": "任务空间"})
    space_id = created.json()["id"]
    payload = {"target_dir": "", "items": [{"filename": "a.txt", "relative_path": "a.txt", "size": 1}]}

    personal = await logged_in_client.post("/api/upload-tasks", json=payload)
    team = await logged_in_client.post(f"/api/team-spaces/{space_id}/upload-tasks", json=payload)

    assert personal.status_code == 200
    assert team.status_code == 200
    personal_tasks = await logged_in_client.get("/api/workspace-tasks")
    team_tasks = await logged_in_client.get(f"/api/team-spaces/{space_id}/workspace-tasks")
    assert all(item["workspace_kind"] == "personal" for item in personal_tasks.json())
    assert all(item["workspace_kind"] == "team" for item in team_tasks.json())
